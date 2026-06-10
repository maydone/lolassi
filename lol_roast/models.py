from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Player:
    summoner_id: int
    puuid: str
    game_name: str
    tag_line: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.game_name}#{self.tag_line}" if self.tag_line else self.game_name


@dataclass(slots=True)
class GameMetrics:
    win: bool
    kills: int
    deaths: int
    assists: int
    kda: float
    participation: float
    damage_share: float
    gold_share: float
    vision: float
    cs_per_minute: float
    performance_score: float
    created_ms: int = 0


@dataclass(slots=True)
class PlayerAnalysis:
    player: Player
    games: int
    score: float
    wins: int
    avg_kda: float
    avg_participation: float
    avg_damage_share: float
    avg_gold_share: float
    avg_vision: float
    avg_cs_per_minute: float
    recent_kda: list[str] = field(default_factory=list)
    recent_results: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    def tier(self, thresholds: dict[str, float]) -> str:
        if not self.games:
            return "NPC（数据不足）"
        if self.score >= thresholds["carry"]:
            return "夯"
        if self.score >= thresholds["strong"]:
            return "顶级"
        if self.score >= thresholds["steady"]:
            return "人上人"
        if self.score >= thresholds["risky"]:
            return "NPC"
        return "拉完了"

    def anonymous_payload(
        self, anonymous_id: str, thresholds: dict[str, float]
    ) -> dict[str, object]:
        return {
            "id": anonymous_id,
            "tier": self.tier(thresholds),
            "games": self.games,
            "score": round(self.score),
            "win_rate": round(self.win_rate * 100),
            "avg_kda": round(self.avg_kda, 2),
            "participation": round(self.avg_participation * 100),
            "damage_share": round(self.avg_damage_share * 100),
            "gold_share": round(self.avg_gold_share * 100),
            "vision": round(self.avg_vision, 1),
            "cs_per_minute": round(self.avg_cs_per_minute, 1),
            "tags": self.tags,
            "recent_games": self.recent_results,
        }

    def data_summary(self) -> str:
        if not self.games:
            return "暂无可用战绩"
        return (
            f"{self.games}局 胜率{self.win_rate:.0%} "
            f"KDA {self.avg_kda:.1f} 参团{self.avg_participation:.0%} "
            f"评分{self.score:.0f}"
        )
