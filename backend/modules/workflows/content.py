"""Pure content transformations used by the workflow application layer."""

import json
from typing import Any


def demo_copy(title: str, author: str, prompt: str, index: int) -> str:
    angle = prompt or ["把复杂世界重新看清", "一次真诚而克制的阅读分享", "从书页走回自己的生活"][index % 3]
    byline = f"，{author}写下的" if author else "，这本"
    return (
        f"如果一本书能让你在合上它之后，重新看待自己的生活，《{title}》或许就是这样一本书。"
        f"{byline}作品没有急着给出标准答案，而是沿着“{angle}”这条线索，把那些被我们忽略的细节慢慢照亮。\n\n"
        "它真正动人的地方，不是观点有多响亮，而是读到某一页时，你忽然发现作者写的也是自己。"
        "那些犹豫、选择和未说出口的话，都在故事里获得了新的解释。\n\n"
        f"推荐你读《{title}》。不必赶进度，给它一个安静的晚上，也给自己一次重新整理内心的机会。"
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
