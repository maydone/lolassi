from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from lol_roast.config import AppConfig
from lol_roast.llm import LLMError, SYSTEM_PROMPT, generate_comments, load_api_key
from lol_roast.models import Player, PlayerAnalysis
from lol_roast.safety import UnsafeComment, validate_comment


def analysis(index: int) -> PlayerAnalysis:
    return PlayerAnalysis(
        player=Player(index, f"p-{index}", f"玩家{index}"),
        games=10,
        score=105,
        wins=5,
        avg_kda=3,
        avg_participation=0.6,
        avg_damage_share=0.2,
        avg_gold_share=0.2,
        avg_vision=20,
        avg_cs_per_minute=6,
        tags=["表现稳定"],
        recent_results=["胜 8/2/10", "负 2/8/3"],
    )


class LLMTests(unittest.TestCase):
    def test_loads_key_from_markdown_file(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key.md"
            path.write_text("# API Key\n\n`sk-test-key`\n", encoding="utf-8")
            self.assertEqual(load_api_key(key_file=path), "sk-test-key")

    def test_prompt_requests_exaggerated_humor_without_personal_attacks(self) -> None:
        self.assertIn("大乱斗选人阶段", SYSTEM_PROMPT)
        self.assertIn("最近十五局", SYSTEM_PROMPT)
        self.assertIn("脱口秀式公开处刑", SYSTEM_PROMPT)
        self.assertIn("最后半句必须再补一刀", SYSTEM_PROMPT)
        self.assertIn("火力全开", SYSTEM_PROMPT)
        self.assertIn("只能攻击操作、意识和近期战绩", SYSTEM_PROMPT)

    def test_accepts_complete_safe_json(self) -> None:
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '[{"id":"P1","comment":"数据不炸，主打一个稳"},'
                            '{"id":"P2","comment":"参团准时，输出随缘"}]'
                        )
                    }
                }
            ]
        }
        with patch("lol_roast.llm.requests.post", return_value=response) as post:
            comments = generate_comments([analysis(1), analysis(2)], AppConfig(), "key")
        self.assertEqual(set(comments), {"P1", "P2"})
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["model"], "deepseek-v4-flash")
        self.assertNotIn("enable_thinking", sent)
        self.assertEqual(sent["thinking"], {"type": "disabled"})
        self.assertNotIn("玩家1", str(sent))
        self.assertIn('"tier": "人上人"', sent["messages"][1]["content"])
        self.assertIn("胜 8/2/10", sent["messages"][1]["content"])

    def test_disables_thinking_for_qwen_models(self) -> None:
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '[{"id":"P1","comment":"稳得像写进版本公告"}]'}}]
        }
        config = AppConfig(model="qwen3.6-27b")
        with patch("lol_roast.llm.requests.post", return_value=response) as post:
            generate_comments([analysis(1)], config, "key")
        self.assertFalse(post.call_args.kwargs["json"]["enable_thinking"])

    def test_missing_comment_rejects_whole_generation(self) -> None:
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '[{"id":"P1","comment":"还算稳定"}]'}}]
        }
        with patch("lol_roast.llm.requests.post", return_value=response):
            with self.assertRaises(LLMError):
                generate_comments([analysis(1), analysis(2)], AppConfig(), "key")

    def test_network_error_is_wrapped_for_data_fallback(self) -> None:
        import requests

        with patch(
            "lol_roast.llm.requests.post",
            side_effect=requests.Timeout("timeout"),
        ):
            with self.assertRaisesRegex(LLMError, "网络错误"):
                generate_comments([analysis(1)], AppConfig(), "key")

    def test_invalid_key_reports_key_or_region_problem(self) -> None:
        response = MagicMock(status_code=401)
        response.json.return_value = {
            "error": {"message": "Incorrect API key provided."}
        }
        with patch("lol_roast.llm.requests.post", return_value=response):
            with self.assertRaisesRegex(LLMError, "DeepSeek API Key 无效"):
                generate_comments([analysis(1)], AppConfig(), "key")

    def test_safety_rejects_abuse(self) -> None:
        with self.assertRaises(UnsafeComment):
            validate_comment("建议大家举报这个废物", AppConfig().forbidden_terms, 48)


if __name__ == "__main__":
    unittest.main()
