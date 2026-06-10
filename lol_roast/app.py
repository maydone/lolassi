from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import websocket

from .analysis import analyze_player
from .config import AppConfig
from .lcu import LCUClient, LCUCredentials, LCUError, discover_credentials, parse_lcu_event
from .llm import LLMError, generate_comments
from .models import Player, PlayerAnalysis

LOG = logging.getLogger(__name__)


class RoastAssistant:
    def __init__(
        self,
        config: AppConfig,
        *,
        dry_run: bool = False,
        once: bool = False,
    ):
        self.config = config
        self.dry_run = dry_run
        self.once = once
        self.processed_sessions: set[str] = set()
        self.processing_sessions: set[str] = set()
        self.stop_event = threading.Event()
        self.completed_once = threading.Event()
        self._session_lock = threading.Lock()

    def run(self) -> int:
        LOG.info("LOL 队友锐评助手启动%s", "（dry-run）" if self.dry_run else "")
        while not self.stop_event.is_set():
            try:
                credentials = discover_credentials()
                self._monitor(credentials)
            except LCUError as exc:
                LOG.warning("%s；5 秒后重试", exc)
            except KeyboardInterrupt:
                self.stop_event.set()
            except Exception:
                LOG.exception("监听异常；5 秒后重连")
            if self.once and self.completed_once.is_set():
                return 0
            self.stop_event.wait(5)
        return 0

    def _monitor(self, credentials: LCUCredentials) -> None:
        client = LCUClient(credentials)
        summoner = client.current_summoner()
        LOG.info(
            "已连接客户端：%s",
            summoner.get("gameName") or summoner.get("displayName") or "未知召唤师",
        )
        ws = client.event_socket()
        try:
            try:
                phase = client.request("GET", "/lol-gameflow/v1/gameflow-phase")
                if phase == "ChampSelect":
                    self._schedule_session(client)
            except LCUError:
                LOG.debug("启动时未处于选人阶段")
            while not self.stop_event.is_set():
                if self.once and self.completed_once.is_set():
                    return
                try:
                    raw_event = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                event = parse_lcu_event(raw_event)
                if not event:
                    continue
                if (
                    event.get("uri") == "/lol-gameflow/v1/gameflow-phase"
                    and event.get("data") == "ChampSelect"
                ):
                    self._schedule_session(client)
        finally:
            ws.close()

    def _schedule_session(self, client: LCUClient) -> None:
        thread = threading.Thread(
            target=self._process_current_session,
            args=(client,),
            name="champ-select-analysis",
            daemon=True,
        )
        thread.start()

    def _wait_for_team(self, client: LCUClient) -> tuple[str, list[int]]:
        last_error: Exception | None = None
        best: tuple[str, list[int]] | None = None
        poll_interval = 0.5
        attempts = max(1, int(self.config.team_wait_seconds / poll_interval))
        for attempt in range(attempts):
            try:
                conversation_id = client.current_champ_select_conversation()
                ids = client.champ_select_summoner_ids()
                for summoner_id in client.team_summoner_ids(conversation_id):
                    if summoner_id not in ids:
                        ids.append(summoner_id)
                if best is None or len(ids) > len(best[1]):
                    best = (conversation_id, ids)
                if len(ids) >= 5:
                    return conversation_id, ids[:5]
            except LCUError as exc:
                last_error = exc
            if attempt < attempts - 1:
                time.sleep(poll_interval)
        if best and best[1]:
            LOG.warning("只识别到 %d/5 名玩家，将继续分析已识别成员", len(best[1]))
            return best
        raise LCUError(f"无法读取选人队伍: {last_error or '没有成员数据'}")

    def _process_current_session(self, client: LCUClient) -> None:
        conversation_id = ""
        try:
            conversation_id, summoner_ids = self._wait_for_team(client)
            with self._session_lock:
                if (
                    conversation_id in self.processed_sessions
                    or conversation_id in self.processing_sessions
                ):
                    return
                self.processing_sessions.add(conversation_id)

            LOG.info(
                "发现选人会话 %s，开始分析 %d 名玩家",
                conversation_id,
                len(summoner_ids),
            )
            players = client.list_summoners(summoner_ids)
            player_by_id = {player.summoner_id: player for player in players}
            ordered_players = [player_by_id[sid] for sid in summoner_ids if sid in player_by_id]
            if not ordered_players:
                raise LCUError("召唤师资料未返回任何已识别玩家")
            if len(ordered_players) != len(summoner_ids):
                LOG.warning(
                    "召唤师资料返回 %d/%d 名，将继续分析",
                    len(ordered_players),
                    len(summoner_ids),
                )
            analyses = self._analyze_team(client, ordered_players)
            for analysis in analyses:
                LOG.info(
                    "%s | %s | %s",
                    analysis.player.display_name,
                    analysis.data_summary(),
                    "、".join(analysis.tags),
                )
            try:
                comments = generate_comments(analyses, self.config)
                LOG.info("模型锐评生成完成（%s）", self.config.model)
            except LLMError as exc:
                LOG.warning("模型锐评不可用，本局不发送：%s", exc)
                self.completed_once.set()
                return
            with self._session_lock:
                self.processed_sessions.add(conversation_id)
            self._deliver(client, conversation_id, analyses, comments)
            self.completed_once.set()
        except LCUError as exc:
            LOG.warning("本局分析取消：%s", exc)
        except Exception:
            LOG.exception("本局分析失败")
        finally:
            if conversation_id:
                with self._session_lock:
                    self.processing_sessions.discard(conversation_id)

    def _analyze_team(
        self, client: LCUClient, players: list[Player]
    ) -> list[PlayerAnalysis]:
        results: dict[int, PlayerAnalysis] = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(self._analyze_one, client, player): player
                for player in players
            }
            for future in as_completed(futures):
                player = futures[future]
                try:
                    results[player.summoner_id] = future.result()
                except Exception as exc:
                    LOG.warning("%s 战绩查询失败：%s", player.display_name, exc)
                    results[player.summoner_id] = analyze_player(player, [], self.config)
        return [results[player.summoner_id] for player in players]

    def _analyze_one(
        self,
        client: LCUClient,
        player: Player,
    ) -> PlayerAnalysis:
        worker_client = LCUClient(client.credentials, timeout=min(client.timeout, 8))
        history = worker_client.match_history(player.puuid, self.config.history_games)
        filtered = self._select_history(history)[: self.config.analysis_games]
        LOG.debug(
            "%s 历史列表 %d 局，筛选后 %d 局；队列=%s",
            player.display_name,
            len(history),
            len(filtered),
            [item.get("queueId") for item in history[:10]],
        )
        summaries_by_id: dict[int, dict[str, Any]] = {}
        game_ids = [int(item.get("gameId") or 0) for item in filtered]
        game_ids = [game_id for game_id in game_ids if game_id]
        with ThreadPoolExecutor(max_workers=min(5, len(game_ids) or 1)) as pool:
            futures = {
                pool.submit(
                    LCUClient(
                        client.credentials,
                        timeout=min(client.timeout, 8),
                    ).game_summary,
                    game_id,
                ): game_id
                for game_id in game_ids
            }
            for future in as_completed(futures):
                game_id = futures[future]
                try:
                    summaries_by_id[game_id] = future.result()
                except LCUError as exc:
                    LOG.debug("跳过对局 %s：%s", game_id, exc)
        summaries = [
            summaries_by_id[game_id]
            for game_id in game_ids
            if game_id in summaries_by_id
        ]
        return analyze_player(player, summaries, self.config)

    def _select_history(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def duration_seconds(item: dict[str, Any]) -> float:
            raw = float(
                item.get("gameDuration")
                or item.get("gameDurationSeconds")
                or item.get("duration")
                or 0
            )
            # Some Tencent client builds expose duration in milliseconds.
            return raw / 1000 if raw > 100_000 else raw

        standard = [
            item
            for item in history
            if int(item.get("queueId") or item.get("queueID") or 0)
            in self.config.allowed_queue_ids
            and duration_seconds(item) >= self.config.minimum_game_seconds
        ]
        if standard:
            return standard[: self.config.analysis_games]

        # Tencent/WeGame occasionally reports queueId=0 or a regional queue id.
        # Fall back only when the configured filter rejected the entire page.
        fallback: list[dict[str, Any]] = []
        for item in history:
            mode = str(item.get("gameMode") or "").upper()
            game_type = str(item.get("gameType") or "").upper()
            if mode in {"TFT", "PRACTICETOOL"} or game_type == "CUSTOM_GAME":
                continue
            if duration_seconds(item) < self.config.minimum_game_seconds:
                continue
            if not item.get("gameId"):
                continue
            fallback.append(item)
        return fallback[: self.config.analysis_games]

    def _deliver(
        self,
        client: LCUClient,
        conversation_id: str,
        analyses: list[PlayerAnalysis],
        comments: dict[str, str],
    ) -> None:
        messages: list[tuple[PlayerAnalysis, str]] = []
        for index, analysis in enumerate(analyses, start=1):
            player_id = f"P{index}"
            comment = comments.get(player_id)
            if not comment:
                LOG.warning("缺少 %s 的模型点评，本局不发送", analysis.player.game_name)
                return
            tier = analysis.tier(self.config.score_thresholds)
            message = (
                f"{analysis.player.game_name}【{tier}】"
                f"胜率：{analysis.win_rate:.0%} "
                f"评分：{analysis.score:.0f} "
                f"{comment}"
            )
            if len(message) > 180:
                message = message[:179] + "…"
            messages.append((analysis, message))
            LOG.info("预览 %d/%d：%s", index, len(analyses), message)

        if self.dry_run or not self.config.auto_send:
            LOG.info("预览模式：未发送任何消息")
            return

        try:
            if client.gameflow_phase() != "ChampSelect":
                LOG.warning("选人阶段已结束，取消发送")
                return
            active_conversation_id = client.current_champ_select_conversation()
            if active_conversation_id != conversation_id:
                LOG.info("选人聊天会话已更新，改用当前会话发送")
        except LCUError as exc:
            LOG.warning("发送前无法确认选人会话，取消发送：%s", exc)
            return

        for index, (analysis, message) in enumerate(messages, start=1):
            try:
                client.send_message(active_conversation_id, message)
                LOG.info("已发送 %d/%d：%s", index, len(messages), message)
            except LCUError as exc:
                if exc.status_code == 404:
                    try:
                        if client.gameflow_phase() != "ChampSelect":
                            LOG.warning("选人阶段已结束，停止发送剩余点评")
                            return
                        refreshed_id = client.current_champ_select_conversation()
                        client.send_message(refreshed_id, message)
                        active_conversation_id = refreshed_id
                        LOG.info(
                            "刷新会话后已发送 %d/%d：%s",
                            index,
                            len(messages),
                            message,
                        )
                    except LCUError as retry_exc:
                        LOG.error(
                            "刷新会话后仍发送失败（%s）：%s",
                            analysis.player.display_name,
                            retry_exc,
                        )
                else:
                    LOG.error("发送失败（%s）：%s", analysis.player.display_name, exc)
            if index < len(messages):
                time.sleep(max(2.2, self.config.message_interval_seconds))
