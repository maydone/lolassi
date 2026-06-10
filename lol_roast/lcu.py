from __future__ import annotations

import base64
import json
import logging
import re
import ssl
import subprocess
from dataclasses import dataclass
from typing import Any

import requests
import urllib3
import websocket

from .models import Player

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
LOG = logging.getLogger(__name__)


class LCUError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class LCUCredentials:
    port: int
    token: str


def discover_credentials() -> LCUCredentials:
    script = (
        "$p=Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe'\" "
        "| Select-Object -First 1 -ExpandProperty CommandLine; "
        "if($p){[Console]::OutputEncoding=[Text.Encoding]::UTF8; $p}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    command_line = result.stdout.strip()
    token_match = re.search(r"--remoting-auth-token(?:=|\s+)[\"']?([^\"'\s]+)", command_line)
    port_match = re.search(r"--app-port(?:=|\s+)[\"']?(\d+)", command_line)
    if not token_match or not port_match:
        process_check = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "if(Get-Process LeagueClientUx -ErrorAction SilentlyContinue){'running'}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if process_check.stdout.strip() == "running":
            raise LCUError(
                "LeagueClientUx.exe 已运行，但当前终端无权读取 LCU 凭据；"
                "请关闭本程序，右键以管理员身份运行 PowerShell 后重试"
            )
        raise LCUError("未发现 LeagueClientUx.exe；请先登录英雄联盟客户端")
    return LCUCredentials(port=int(port_match.group(1)), token=token_match.group(1))


class LCUClient:
    def __init__(self, credentials: LCUCredentials, timeout: float = 15):
        self.credentials = credentials
        self.base_url = f"https://127.0.0.1:{credentials.port}"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = ("riot", credentials.token)
        self.session.verify = False

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(
            method, self.base_url + path, timeout=self.timeout, **kwargs
        )
        if response.status_code >= 400:
            detail = response.text[:300]
            raise LCUError(
                f"LCU {method} {path} 返回 {response.status_code}: {detail}",
                status_code=response.status_code,
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise LCUError(f"LCU {path} 返回非 JSON 数据") from exc

    def current_summoner(self) -> dict[str, Any]:
        return self.request("GET", "/lol-summoner/v1/current-summoner")

    def gameflow_phase(self) -> str:
        return str(self.request("GET", "/lol-gameflow/v1/gameflow-phase"))

    def conversations(self) -> list[dict[str, Any]]:
        return self.request("GET", "/lol-chat/v1/conversations")

    def current_champ_select_conversation(self) -> str:
        for conversation in self.conversations():
            if conversation.get("type") == "championSelect":
                return str(conversation["id"])
        raise LCUError("当前没有选人聊天会话")

    def conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/lol-chat/v1/conversations/{conversation_id}/messages")

    def champ_select_session(self) -> dict[str, Any]:
        return self.request("GET", "/lol-champ-select/v1/session")

    def champ_select_summoner_ids(self) -> list[int]:
        session = self.champ_select_session()
        ids: list[int] = []
        for member in session.get("myTeam") or []:
            summoner_id = int(member.get("summonerId") or 0)
            if summoner_id > 0 and summoner_id not in ids:
                ids.append(summoner_id)
        return ids

    def team_summoner_ids(self, conversation_id: str) -> list[int]:
        ids: list[int] = []
        for message in self.conversation_messages(conversation_id):
            summoner_id = int(message.get("fromSummonerId") or 0)
            if (
                message.get("type") == "system"
                and message.get("body") == "joined_room"
                and summoner_id > 0
                and summoner_id not in ids
            ):
                ids.append(summoner_id)
        return ids

    def list_summoners(self, summoner_ids: list[int]) -> list[Player]:
        joined = ",".join(str(value) for value in summoner_ids)
        data = self.request("GET", f"/lol-summoner/v2/summoners?ids=[{joined}]")
        return [
            Player(
                summoner_id=int(item["summonerId"]),
                puuid=str(item.get("puuid") or ""),
                game_name=str(item.get("gameName") or item.get("displayName") or "未知玩家"),
                tag_line=str(item.get("tagLine") or ""),
            )
            for item in data
        ]

    def match_history(self, puuid: str, count: int) -> list[dict[str, Any]]:
        data = self.request(
            "GET",
            f"/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex={count}",
        )
        return ((data or {}).get("games") or {}).get("games") or []

    def game_summary(self, game_id: int) -> dict[str, Any]:
        return self.request("GET", f"/lol-match-history/v1/games/{game_id}")

    def send_message(self, conversation_id: str, message: str) -> None:
        self.request(
            "POST",
            f"/lol-chat/v1/conversations/{conversation_id}/messages",
            json={"body": message, "type": "chat"},
        )

    def event_socket(self) -> websocket.WebSocket:
        auth = base64.b64encode(f"riot:{self.credentials.token}".encode()).decode()
        ws = websocket.create_connection(
            f"wss://127.0.0.1:{self.credentials.port}/",
            header=[f"Authorization: Basic {auth}"],
            sslopt={"cert_reqs": ssl.CERT_NONE},
            timeout=30,
        )
        ws.send('[5, "OnJsonApiEvent"]')
        ws.settimeout(1)
        return ws


def parse_lcu_event(raw: str | bytes) -> dict[str, Any] | None:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, list) or len(event) < 3 or event[0] != 8:
        return None
    payload = event[2]
    return payload if isinstance(payload, dict) else None
