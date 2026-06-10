from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.deepseek.com"


@dataclass(slots=True)
class AppConfig:
    model: str = "deepseek-v4-flash"
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: int = 12
    history_games: int = 20
    analysis_games: int = 15
    team_wait_seconds: float = 4
    allowed_queue_ids: list[int] = field(default_factory=lambda: [420, 430, 440, 450])
    minimum_game_seconds: int = 900
    message_interval_seconds: float = 2.2
    auto_send: bool = True
    max_comment_chars: int = 48
    score_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "carry": 125,
            "strong": 110,
            "steady": 95,
            "risky": 80,
        }
    )
    forbidden_terms: list[str] = field(
        default_factory=lambda: [
            "举报",
            "去死",
            "废物",
            "垃圾",
            "畜生",
            "残疾",
            "脑残",
            "弱智",
            "孤儿",
            "妈",
            "爹",
            "全家",
            "滚",
            "操",
            "草泥马",
            "傻逼",
            "sb",
            "nmsl",
        ]
    )

    def __post_init__(self) -> None:
        if self.history_games < 1 or self.history_games > 50:
            raise ValueError("history_games 必须在 1 到 50 之间")
        if self.analysis_games < 1 or self.analysis_games > self.history_games:
            raise ValueError("analysis_games 必须在 1 到 history_games 之间")
        if self.team_wait_seconds < 0.5 or self.team_wait_seconds > 15:
            raise ValueError("team_wait_seconds 必须在 0.5 到 15 秒之间")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds 必须大于 0")
        if self.message_interval_seconds < 2.2:
            raise ValueError("message_interval_seconds 不能低于 2.2 秒")
        if self.max_comment_chars < 8 or self.max_comment_chars > 80:
            raise ValueError("max_comment_chars 必须在 8 到 80 之间")
        required = {"carry", "strong", "steady", "risky"}
        if set(self.score_thresholds) != required:
            raise ValueError("score_thresholds 必须包含 carry/strong/steady/risky")
        values = [
            self.score_thresholds[name]
            for name in ("carry", "strong", "steady", "risky")
        ]
        if values != sorted(values, reverse=True):
            raise ValueError("评分阈值必须满足 carry >= strong >= steady >= risky")

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("配置文件根节点必须是 JSON 对象")
        allowed = {item.name for item in cls.__dataclass_fields__.values()}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"未知配置项: {', '.join(unknown)}")
        return cls(**raw)

    def as_dict(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }
