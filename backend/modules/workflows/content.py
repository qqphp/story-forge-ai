"""Pure content transformations used by the workflow application layer."""

import json
from typing import Any

from backend.modules.workflows.broadcast import PROGRAM_NAME


def demo_copy(title: str, author: str | None) -> str:
    byline = f"，作者是{author}" if author else ""
    return (
        f"你好，欢迎来到{PROGRAM_NAME}。今天这段配音用来试听节目的声音和节奏。"
        f"我们准备分享的书是《{title}》{byline}。\n\n"
        "有时候，读完一页，可以先把书放下来，想一想刚才哪句话让自己停住了。"
        "谢谢你今天的陪伴，我们下次再见。"
    )


def generated_taxonomy(raw: str | None, title: str) -> tuple[list[str], list[str]]:
    def cleaned(values: Any, fallbacks: list[str]) -> list[str]:
        source = values if isinstance(values, list) else []
        terms = [str(value).strip().lstrip("#").strip().replace(" ", "") for value in source]
        terms.extend(fallbacks)
        return [value for value in dict.fromkeys(terms) if value and len(value) <= 30][:8]

    parsed: dict[str, Any] = {}
    if raw:
        candidate = raw.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                parsed = value
        except json.JSONDecodeError:
            parsed = {}
    safe_title = title.strip().replace(" ", "")[:30]
    tags = cleaned(parsed.get("tags"), [safe_title, "图书", "阅读", "文学", "书籍分享", "阅读思考", "内容创作", "经典阅读"])
    topics = cleaned(parsed.get("topics"), [safe_title, "读书", "好书推荐", "读书分享", "阅读", "书单推荐", "一起读书", "每日阅读"])
    return tags, topics
