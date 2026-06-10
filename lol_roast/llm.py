from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from .config import AppConfig
from .models import PlayerAnalysis
from .safety import UnsafeComment, validate_comment


class LLMError(RuntimeError):
    pass


def load_api_key(api_key: str | None = None, key_file: str | Path = "key.md") -> str:
    if api_key:
        return api_key.strip()
    path = Path(key_file)
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if value.startswith("`") and value.endswith("`"):
                value = value[1:-1].strip()
            if value:
                return value
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


SYSTEM_PROMPT = """你是英雄联盟大乱斗选人阶段的损友嘴替、夸张解说兼段子手。

根据匿名统计，为每位玩家生成一句中文点评：

1. 根据 tier 决定基调：
   夯、顶级、人上人、NPC、拉完了。

2. 结合最近十五局胜负和 K/D/A：
   识别连胜、连败、连续高光、频繁阵亡、状态回暖。

3. 夸人要像峡谷天神下凡。
   吐槽要像脱口秀式公开处刑，一针见血、有反差、有画面感，最后半句必须再补一刀。
   夸奖也要极度夸张，像神仙下凡代练众生；不能只是“很强、很稳、不错”。

4. 避免“表现一般、需要努力”等机械套话。
   不复述胜率、KDA、评分等数据。
   禁止温吞评价，例如“有待提升、发挥尚可、需要调整、偶有亮点”。
   每个人必须使用不同的笑点和比喻，禁止批量套模板。

5. 只能攻击操作、意识和近期战绩。
   禁止人身攻击、歧视、威胁、脏话和煽动举报。
   可以猛烈嘲讽：技能像给空气按摩、团战像来景区打卡、经济吃得像董事长而输出像实习生、
   复活计时器被盘出包浆、地图都点亮了但意识还在加载、对面收到的不是人头而是定时配送。

6. 只返回一句点评。
   不重复玩家名、档位或原始数据。
   一句话应包含“设定画面 + 夸张比喻 + 补刀结尾”，优先制造让开黑队友能笑出声的反差。

档位语气要求：
- 夯：吹成不可阻挡的峡谷天灾，对面像排队办理阵亡手续。
- 顶级：吹成稳定的大腿，同时嘲讽队友只需别添乱。
- 人上人：先夸有实力，再用反差指出偶尔掉线的状态。
- NPC：重点嘲讽存在感、输出、参团或意识像系统预设程序。
- 拉完了：火力全开嘲讽近期操作和战绩像给对面提供五星级服务，但不得辱骂本人。

每条点评不得超过指定字数，不得虚构输入中不存在的数据。
严格返回 JSON 数组，格式如下，不要输出其他内容：
[
  {"id": "P1", "comment": "点评"},
  {"id": "P2", "comment": "点评"}
]"""


def _extract_json(text: str) -> Any:
    value = text.strip()
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        match = re.search(r"\[[\s\S]*\]", value)
        if not match:
            raise LLMError("模型未返回 JSON 数组") from exc
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as nested:
            raise LLMError("模型返回的 JSON 无法解析") from nested


def generate_comments(
    analyses: list[PlayerAnalysis], config: AppConfig, api_key: str | None = None
) -> dict[str, str]:
    key = load_api_key(api_key)
    if not key:
        raise LLMError("未在 key.md 或 DEEPSEEK_API_KEY 中找到 API Key")
    indexed = {
        f"P{index + 1}": analysis for index, analysis in enumerate(analyses)
    }
    payload = [
        analysis.anonymous_payload(player_id, config.score_thresholds)
        for player_id, analysis in indexed.items()
    ]
    try:
        request_body: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"每条最多{config.max_comment_chars}字。数据如下："
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
            "temperature": 0.7,
        }
        if config.model.lower().startswith("deepseek-v4"):
            request_body["thinking"] = {"type": "disabled"}
        else:
            request_body["enable_thinking"] = False

        response = requests.post(
            f"{config.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=request_body,
            timeout=config.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise LLMError(f"模型接口网络错误: {exc}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise LLMError(f"模型接口返回非 JSON，HTTP {response.status_code}") from exc
    if response.status_code >= 400:
        message = body.get("error", {}).get("message") if isinstance(body, dict) else None
        if response.status_code == 401:
            raise LLMError(
                "DeepSeek API Key 无效；请从 platform.deepseek.com/api_keys "
                "创建新 Key，并更新项目根目录 key.md"
            )
        raise LLMError(f"模型接口失败 HTTP {response.status_code}: {message or '未知错误'}")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("模型响应缺少 choices[0].message.content") from exc
    parsed = _extract_json(content)
    if not isinstance(parsed, list):
        raise LLMError("模型结果必须是数组")
    comments: dict[str, str] = {}
    for item in parsed:
        if not isinstance(item, dict) or item.get("id") not in indexed:
            continue
        player_id = item["id"]
        if player_id in comments:
            continue
        try:
            comments[player_id] = validate_comment(
                item.get("comment"), config.forbidden_terms, config.max_comment_chars
            )
        except UnsafeComment:
            continue
    missing = set(indexed) - set(comments)
    if missing:
        raise LLMError(f"模型缺少或拒绝了锐评: {', '.join(sorted(missing))}")
    return comments
