from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from lol_roast.lcu import (
    LCUClient,
    LCUCredentials,
    LCUError,
    discover_credentials,
    parse_lcu_event,
)


class LCUTests(unittest.TestCase):
    def test_discovers_both_command_line_styles(self) -> None:
        process = MagicMock(
            stdout=(
                '"LeagueClientUx.exe" "--remoting-auth-token=secret-token" '
                '"--app-port=54321"'
            )
        )
        with patch("lol_roast.lcu.subprocess.run", return_value=process):
            credentials = discover_credentials()
        self.assertEqual(credentials, LCUCredentials(54321, "secret-token"))

    def test_reports_permission_problem_when_process_is_visible(self) -> None:
        command_line = MagicMock(stdout="")
        process_check = MagicMock(stdout="running\n")
        with patch(
            "lol_roast.lcu.subprocess.run",
            side_effect=[command_line, process_check],
        ):
            with self.assertRaisesRegex(LCUError, "管理员身份"):
                discover_credentials()

    def test_parses_json_api_event(self) -> None:
        payload = {
            "uri": "/lol-gameflow/v1/gameflow-phase",
            "data": "ChampSelect",
        }
        event = parse_lcu_event(json.dumps([8, "OnJsonApiEvent", payload]))
        self.assertEqual(event, payload)

    def test_deduplicates_joined_members_in_order(self) -> None:
        client = LCUClient(LCUCredentials(1, "token"))
        client.conversation_messages = MagicMock(
            return_value=[
                {"type": "system", "body": "joined_room", "fromSummonerId": 2},
                {"type": "chat", "body": "hi", "fromSummonerId": 2},
                {"type": "system", "body": "joined_room", "fromSummonerId": 1},
                {"type": "system", "body": "joined_room", "fromSummonerId": 2},
            ]
        )
        self.assertEqual(client.team_summoner_ids("chat"), [2, 1])

    def test_reads_members_from_champ_select_session(self) -> None:
        client = LCUClient(LCUCredentials(1, "token"))
        client.champ_select_session = MagicMock(
            return_value={
                "myTeam": [
                    {"summonerId": 3},
                    {"summonerId": 1},
                    {"summonerId": 3},
                    {"summonerId": 0},
                ]
            }
        )
        self.assertEqual(client.champ_select_summoner_ids(), [3, 1])


if __name__ == "__main__":
    unittest.main()
