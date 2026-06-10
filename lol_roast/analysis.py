from __future__ import annotations

import time
from datetime import datetime
from statistics import fmean
from typing import Any, Iterable

from .config import AppConfig
from .models import GameMetrics, Player, PlayerAnalysis


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _participant_for_player(summary: dict[str, Any], player: Player) -> dict[str, Any] | None:
    participants = summary.get("participants") or []
    identities = summary.get("participantIdentities") or []
    participant_id = None
    for identity in identities:
        info = identity.get("player") or {}
        if int(_number(info.get("summonerId"))) == player.summoner_id or (
            player.puuid and info.get("puuid") == player.puuid
        ):
            participant_id = identity.get("participantId")
            break
    if participant_id is not None:
        return next((p for p in participants if p.get("participantId") == participant_id), None)
    return next(
        (
            p
            for p in participants
            if int(_number(p.get("summonerId"))) == player.summoner_id
            or (player.puuid and p.get("puuid") == player.puuid)
        ),
        None,
    )


def metrics_from_summary(
    summary: dict[str, Any], player: Player
) -> GameMetrics | None:
    participant = _participant_for_player(summary, player)
    if not participant:
        return None
    stats = participant.get("stats") or participant
    team_id = participant.get("teamId")
    teammates = [p for p in summary.get("participants", []) if p.get("teamId") == team_id]
    teammate_stats = [(p.get("stats") or p) for p in teammates]

    kills = int(_number(stats.get("kills")))
    deaths = int(_number(stats.get("deaths")))
    assists = int(_number(stats.get("assists")))
    damage = _number(stats.get("totalDamageDealtToChampions"))
    gold = _number(stats.get("goldEarned"))
    vision = _number(stats.get("visionScore"))
    minions = _number(stats.get("totalMinionsKilled")) + _number(stats.get("neutralMinionsKilled"))
    duration_seconds = max(
        1.0,
        _number(summary.get("gameDuration"), _number(summary.get("gameDurationSeconds"), 1)),
    )
    team_kills = sum(_number(s.get("kills")) for s in teammate_stats)
    team_damage = sum(_number(s.get("totalDamageDealtToChampions")) for s in teammate_stats)
    team_gold = sum(_number(s.get("goldEarned")) for s in teammate_stats)
    participation = (kills + assists) / team_kills if team_kills else 0.0
    damage_share = damage / team_damage if team_damage else 0.0
    gold_share = gold / team_gold if team_gold else 0.0
    kda = (kills + assists) / max(1, deaths)
    cs_per_minute = minions / (duration_seconds / 60)
    win_value = stats.get("win")
    won = win_value is True or str(win_value).casefold() in {"true", "win", "won"}
    score = 100.0
    score += 10 if won else -8
    score += max(-18, min(22, (kda - 2.5) * 6))
    score += max(-12, min(14, (participation - 0.55) * 60))
    score += max(-10, min(12, (damage_share - 0.20) * 60))
    score += max(-6, min(8, (gold_share - 0.20) * 40))
    score += max(-5, min(6, (vision - 15) / 5))
    if stats.get("firstBloodKill"):
        score += 4
    if _number(stats.get("pentaKills")):
        score += 10
    elif _number(stats.get("quadraKills")):
        score += 6
    elif _number(stats.get("tripleKills")):
        score += 3

    created = int(_number(summary.get("gameCreation")))
    if not created and isinstance(summary.get("gameCreationDate"), str):
        try:
            created = int(
                datetime.fromisoformat(
                    summary["gameCreationDate"].replace("Z", "+00:00")
                ).timestamp()
                * 1000
            )
        except ValueError:
            created = 0
    return GameMetrics(
        win=won,
        kills=kills,
        deaths=deaths,
        assists=assists,
        kda=kda,
        participation=participation,
        damage_share=damage_share,
        gold_share=gold_share,
        vision=vision,
        cs_per_minute=cs_per_minute,
        performance_score=max(40, min(180, score)),
        created_ms=created,
    )


def _weighted_score(games: list[GameMetrics]) -> float:
    if not games:
        return 100.0
    cutoff_ms = int((time.time() - 5 * 3600) * 1000)
    recent = [g.performance_score for g in games if g.created_ms and g.created_ms >= cutoff_ms]
    older = [g.performance_score for g in games if not g.created_ms or g.created_ms < cutoff_ms]
    overall = fmean(g.performance_score for g in games)
    recent_avg = fmean(recent) if recent else overall
    older_avg = fmean(older) if older else overall
    return recent_avg * 0.8 + older_avg * 0.2


def _tags(analysis: PlayerAnalysis, config: AppConfig) -> list[str]:
    tags: list[str] = []
    thresholds = config.score_thresholds
    if analysis.games == 0:
        return ["数据不足"]
    if analysis.score >= thresholds["carry"]:
        tags.append("近期大腿")
    elif analysis.score >= thresholds["strong"]:
        tags.append("状态在线")
    elif analysis.score < thresholds["risky"]:
        tags.append("高风险")
    elif analysis.score < thresholds["steady"]:
        tags.append("状态起伏")
    else:
        tags.append("表现稳定")
    if analysis.win_rate >= 0.65:
        tags.append("连胜体质")
    elif analysis.win_rate <= 0.35:
        tags.append("胜率告急")
    if analysis.avg_kda >= 4:
        tags.append("生存能力强")
    elif analysis.avg_kda < 1.8:
        tags.append("容易阵亡")
    if analysis.avg_participation >= 0.65:
        tags.append("参团积极")
    elif analysis.avg_participation < 0.42:
        tags.append("团战失联")
    if analysis.avg_damage_share >= 0.27:
        tags.append("输出核心")
    return tags[:4]


def analyze_player(
    player: Player,
    summaries: Iterable[dict[str, Any]],
    config: AppConfig,
) -> PlayerAnalysis:
    games = [
        m
        for summary in summaries
        if (m := metrics_from_summary(summary, player))
    ]
    analysis = PlayerAnalysis(
        player=player,
        games=len(games),
        score=_weighted_score(games),
        wins=sum(game.win for game in games),
        avg_kda=fmean(g.kda for g in games) if games else 0,
        avg_participation=fmean(g.participation for g in games) if games else 0,
        avg_damage_share=fmean(g.damage_share for g in games) if games else 0,
        avg_gold_share=fmean(g.gold_share for g in games) if games else 0,
        avg_vision=fmean(g.vision for g in games) if games else 0,
        avg_cs_per_minute=fmean(g.cs_per_minute for g in games) if games else 0,
        recent_kda=[f"{g.kills}/{g.deaths}/{g.assists}" for g in games[:15]],
        recent_results=[
            f"{'胜' if g.win else '负'} {g.kills}/{g.deaths}/{g.assists}"
            for g in games[:15]
        ],
    )
    analysis.tags = _tags(analysis, config)
    return analysis
