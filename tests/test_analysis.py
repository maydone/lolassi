from __future__ import annotations

import unittest

from lol_roast.analysis import analyze_player, metrics_from_summary
from lol_roast.config import AppConfig
from lol_roast.models import Player


def summary(
    *,
    player_win: bool = True,
    kills: int = 10,
    deaths: int = 2,
    assists: int = 8,
) -> dict:
    participants = []
    identities = []
    for index in range(1, 11):
        team_id = 100 if index <= 5 else 200
        stats = {
            "win": player_win if index == 1 else team_id == 100,
            "kills": kills if index == 1 else 5,
            "deaths": deaths if index == 1 else 5,
            "assists": assists if index == 1 else 6,
            "totalDamageDealtToChampions": 30000 if index == 1 else 15000,
            "goldEarned": 15000 if index == 1 else 11000,
            "visionScore": 25 if index == 1 else 15,
            "totalMinionsKilled": 200 if index == 1 else 130,
            "neutralMinionsKilled": 0,
        }
        participants.append(
            {
                "participantId": index,
                "teamId": team_id,
                "stats": stats,
            }
        )
        identities.append(
            {
                "participantId": index,
                "player": {
                    "summonerId": index,
                    "puuid": f"puuid-{index}",
                },
            }
        )
    return {
        "gameDuration": 1800,
        "gameCreation": 1,
        "participants": participants,
        "participantIdentities": identities,
    }


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = Player(1, "puuid-1", "测试玩家", "CN1")
        self.config = AppConfig()

    def test_extracts_team_relative_metrics(self) -> None:
        metrics = metrics_from_summary(summary(), self.player)
        self.assertIsNotNone(metrics)
        assert metrics is not None
        self.assertAlmostEqual(metrics.kda, 9.0)
        self.assertGreater(metrics.damage_share, 0.3)
        self.assertGreater(metrics.performance_score, 120)

    def test_analysis_handles_no_games(self) -> None:
        result = analyze_player(self.player, [], self.config)
        self.assertEqual(result.games, 0)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.tags, ["数据不足"])
        self.assertEqual(result.tier(self.config.score_thresholds), "NPC（数据不足）")

    def test_analysis_builds_explainable_tags(self) -> None:
        result = analyze_player(
            self.player,
            [summary(), summary(player_win=False), summary()],
            self.config,
        )
        self.assertEqual(result.games, 3)
        self.assertIn("近期大腿", result.tags)
        self.assertTrue({"参团积极", "输出核心"} & set(result.tags))
        self.assertEqual(result.tier(self.config.score_thresholds), "夯")
        self.assertEqual(result.recent_results[0], "胜 10/2/8")
        self.assertEqual(result.recent_results[1], "负 10/2/8")


if __name__ == "__main__":
    unittest.main()
