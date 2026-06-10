from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from lol_roast.app import RoastAssistant
from lol_roast.config import AppConfig
from lol_roast.lcu import LCUError
from lol_roast.models import Player, PlayerAnalysis


def result(index: int) -> PlayerAnalysis:
    return PlayerAnalysis(
        player=Player(index, f"p{index}", f"玩家{index}", "12345"),
        games=5,
        score=100,
        wins=2,
        avg_kda=2,
        avg_participation=0.5,
        avg_damage_share=0.2,
        avg_gold_share=0.2,
        avg_vision=10,
        avg_cs_per_minute=5,
    )


class DeliveryTests(unittest.TestCase):
    def test_dry_run_never_sends(self) -> None:
        client = MagicMock()
        app = RoastAssistant(AppConfig(), dry_run=True)
        app._deliver(client, "session", [result(1)], {"P1": "稳得像默认设置"})
        client.send_message.assert_not_called()

    def test_send_order_and_minimum_interval(self) -> None:
        client = MagicMock()
        app = RoastAssistant(
            AppConfig(message_interval_seconds=2.2),
            dry_run=False,
        )
        client.gameflow_phase.return_value = "ChampSelect"
        client.current_champ_select_conversation.return_value = "session"
        analyses = [result(1), result(2)]
        with patch("lol_roast.app.time.sleep") as sleep:
            app._deliver(
                client,
                "session",
                analyses,
                {"P1": "第一句攻击力拉满。", "P2": "第二句节目效果拉满。"},
            )
        self.assertEqual(client.send_message.call_count, 2)
        self.assertIn("玩家1", client.send_message.call_args_list[0].args[1])
        self.assertNotIn("#12345", client.send_message.call_args_list[0].args[1])
        self.assertNotIn("局", client.send_message.call_args_list[0].args[1])
        self.assertNotIn("KDA", client.send_message.call_args_list[0].args[1])
        self.assertEqual(
            client.send_message.call_args_list[0].args[1],
            "玩家1【人上人】胜率：40% 评分：100 第一句攻击力拉满。",
        )
        self.assertIn("玩家2", client.send_message.call_args_list[1].args[1])
        sleep.assert_called_once_with(2.2)

    def test_one_send_failure_does_not_block_remaining_players(self) -> None:
        client = MagicMock()
        client.send_message.side_effect = [LCUError("closed"), None]
        client.gameflow_phase.return_value = "ChampSelect"
        client.current_champ_select_conversation.return_value = "session"
        app = RoastAssistant(AppConfig(), dry_run=False)
        with patch("lol_roast.app.time.sleep"):
            app._deliver(
                client,
                "session",
                [result(1), result(2)],
                {"P1": "第一句。", "P2": "第二句。"},
            )
        self.assertEqual(client.send_message.call_count, 2)

    def test_missing_llm_comment_does_not_send(self) -> None:
        client = MagicMock()
        app = RoastAssistant(AppConfig(), dry_run=False)
        app._deliver(client, "session", [result(1)], {})
        client.send_message.assert_not_called()

    def test_send_refreshes_expired_conversation_after_404(self) -> None:
        client = MagicMock()
        client.gameflow_phase.return_value = "ChampSelect"
        client.current_champ_select_conversation.side_effect = [
            "old-session",
            "new-session",
        ]
        client.send_message.side_effect = [
            LCUError("expired", status_code=404),
            None,
        ]
        app = RoastAssistant(AppConfig(), dry_run=False)
        app._deliver(client, "old-session", [result(1)], {"P1": "状态不错"})
        self.assertEqual(client.send_message.call_count, 2)
        self.assertEqual(client.send_message.call_args_list[1].args[0], "new-session")

    def test_send_cancels_after_champ_select_ends(self) -> None:
        client = MagicMock()
        client.gameflow_phase.return_value = "InProgress"
        app = RoastAssistant(AppConfig(), dry_run=False)
        app._deliver(client, "session", [result(1)], {"P1": "模型点评。"})
        client.send_message.assert_not_called()

    def test_history_filter_falls_back_for_tencent_queue_ids(self) -> None:
        app = RoastAssistant(AppConfig())
        history = [
            {
                "gameId": 1,
                "queueId": 9999,
                "gameDuration": 1_800_000,
                "gameMode": "CLASSIC",
                "gameType": "MATCHED_GAME",
            },
            {
                "gameId": 2,
                "queueId": 0,
                "gameDuration": 1800,
                "gameMode": "TFT",
                "gameType": "MATCHED_GAME",
            },
        ]
        self.assertEqual([item["gameId"] for item in app._select_history(history)], [1])

    def test_history_filter_prefers_configured_queues(self) -> None:
        app = RoastAssistant(AppConfig())
        history = [
            {"gameId": 1, "queueId": 9999, "gameDuration": 1800},
            {"gameId": 2, "queueId": 420, "gameDuration": 1800},
        ]
        self.assertEqual([item["gameId"] for item in app._select_history(history)], [2])

    def test_wait_for_team_continues_with_one_detected_member(self) -> None:
        client = MagicMock()
        client.current_champ_select_conversation.return_value = "session"
        client.champ_select_summoner_ids.return_value = [7]
        client.team_summoner_ids.return_value = []
        app = RoastAssistant(AppConfig())
        with patch("lol_roast.app.time.sleep"):
            conversation_id, ids = app._wait_for_team(client)
        self.assertEqual(conversation_id, "session")
        self.assertEqual(ids, [7])


if __name__ == "__main__":
    unittest.main()
