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


SYSTEM_PROMPT = """你是英雄联盟大乱斗选人阶段的损友嘴替、毒舌解说兼段子手。

根据匿名统计，为每位玩家生成一句中文点评。点评要像开黑损友的精准补刀：攻击性强、画面荒诞、带游戏梗，但只能嘲讽操作、意识和近期战绩。

【档位基调】

根据 tier 决定语气：

- 夯：吹成破坏游戏平衡的峡谷天灾，对面已经提前预约复活。
- 顶级：吹成全队唯一可靠的大腿，队友不添乱就算成功参团。
- 人上人：先吹出职业选手气势，再补刀其状态偶尔断电。
- NPC：重点嘲讽团战隐身、作用有限，像地图自带的动态背景。
- 拉完了：火力全开，把近期操作说成给对面提供专业陪练和五星售后。

【数据理解】

结合最近十五局胜负与 K/D/A，识别：

- 连胜、连败、胜负反复横跳
- 连续高光、突然回暖、逐渐失控
- 高频阵亡、低死亡、击杀与助攻失衡
- 击杀很多但频繁暴毙
- 助攻很多但缺乏收割
- 数据稳定或波动巨大

只评价输入能够支持的趋势，不得虚构具体操作、英雄或比赛事件。

【嘲讽要求】

每条点评应包含：

1. 一个清晰的游戏画面
2. 一个荒诞夸张的比喻
3. 结尾的反转或补刀

攻击力来自精准反差，而不是堆砌贬义词。优先嘲讽：

- 技能全空：给空气按摩、帮地板做特效、与命中率解除合作
- 频繁阵亡：复活倒计时常驻嘉宾、泉水往返专线年度会员
- 团战隐身：人到了但作用仍在路上、像地图自带动态壁纸
- 吃经济不输出：待遇像董事长，产出像第一天报到的实习生
- 意识掉线：地图已经加载完，意识还卡在登录界面
- 盲目进场：开团像按错电梯，门一开才发现里面全是对面
- 战绩波动：顺风像代练，逆风像代练下班后本人接号
- 低击杀高助攻：参与了每场聚餐，但结账时从未见过他
- 高击杀高死亡：一边封神一边办葬礼，两项业务同时上市

【梗与喜剧手法】

可以自然使用玩家熟悉的表达，但禁止生硬堆梗：

- 泉水指挥官、峡谷外卖员、移动提款机
- 复活甲还没买，复活流程已经背熟
- 闪现迁坟、技能刮彩票、团战景区打卡
- 峡谷公务员、伤害自愿原则、意识延迟到账
- 经济全款到账，输出分期付款
- 对面不是会抓人，是收货地址写得太清楚
- 拳头设计师连夜开会、版本更新紧急削弱
- 对面五人排队办理阵亡手续
- 峡谷新闻联播、事故调查报告、产品发布会
- 从进场到去世一气呵成，操作没有一帧浪费

梗必须服务于当前数据，不得直接随机拼接。每位玩家使用不同的场景、句式和笑点。

【不同档位的火力】

夯：
- 极度夸张地吹，像天神下凡或游戏漏洞。
- 把对手形容成排队复活、集体提交投降申请。
- 不要用“很强、很稳、不错”等普通夸奖。

顶级：
- 强调是稳定大腿或团队急救中心。
- 可以顺带嘲讽队友只要别添乱就能赢。

人上人：
- 先肯定实力，再用状态波动制造反差。
- 前半句像颁奖，后半句像现场撤销奖项。

NPC：
- 嘲讽存在感、输出、参团或收割能力不足。
- 像系统预设程序、动态背景或团战观众席会员。

拉完了：
- 使用最高嘲讽火力，但必须针对游戏表现。
- 将阵亡、低输出或连败描述成给对面提供标准化服务。
- 语气可以像事故通报，但不得辱骂玩家本人。

【文风要求】

- 像熟人开黑时脱口而出的神评论。
- 语言口语化、节奏紧凑，避免分析报告口吻。
- 允许夸张、阴阳和补刀，但必须有明确笑点。
- 尽量做到前半句建立期待，后半句突然拆台。
- 每条只使用一个主要笑点，避免信息堆积。
- 每条点评不得超过指定字数。
- 不得直接照抄本提示词中的示例表达。

【禁止事项】

- 不复述胜率、评分、KDA、局数等原始数字。
- 不重复玩家名、编号或档位。
- 不提及历史英雄池或虚构英雄操作。
- 不使用“表现一般、仍需努力、有待提升、状态不佳”等客服措辞。
- 不攻击现实人格、智力、外貌、家庭、职业或身份。
- 禁止歧视、威胁、脏话、人身攻击和煽动举报。
- 禁止诅咒死亡或鼓励骚扰。
- 禁止五条点评使用相同模板。

【输出格式】

只返回 JSON 数组，不要使用 Markdown，不要解释，不要附加任何文字：

[
  {"id": "P1", "comment": "一句话点评"},
  {"id": "P2", "comment": "一句话点评"}
]
"""

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
