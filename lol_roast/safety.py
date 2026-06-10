from __future__ import annotations

import re


class UnsafeComment(ValueError):
    pass


def validate_comment(comment: object, forbidden_terms: list[str], max_chars: int) -> str:
    if not isinstance(comment, str):
        raise UnsafeComment("锐评不是字符串")
    value = re.sub(r"\s+", " ", comment).strip()
    if not value:
        raise UnsafeComment("锐评为空")
    if len(value) > max_chars:
        raise UnsafeComment(f"锐评超过 {max_chars} 字")
    lowered = value.casefold()
    for term in forbidden_terms:
        if term.casefold() in lowered:
            raise UnsafeComment(f"锐评包含禁用词: {term}")
    if re.search(r"(加好友|微信|QQ|群号|网址|http|www\.)", value, re.IGNORECASE):
        raise UnsafeComment("锐评包含引流信息")
    return value

