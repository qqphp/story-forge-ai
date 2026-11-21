"""Bounded public book research with Firecrawl Search."""

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx


SEARCH_URL = "https://api.firecrawl.dev/v2/search"
RESULT_LIMIT = 5


async def search_book(book: dict[str, str], settings: dict[str, Any], log_request: Callable[..., None],
                      client_factory: Callable[..., Any]) -> list[dict[str, str]]:
    key = settings.get("firecrawl_api_key")
    if not settings.get("firecrawl_enabled", True) or not key or not settings.get("text_api_key") or not settings.get("model"):
        return []
    title = book["book_title"].replace('"', " ").strip()
    query = " ".join(part for part in (f'"{title}"', book.get("author"), book.get("edition"), "图书 简介") if part)
    payload = {"query": query[:500], "limit": RESULT_LIMIT, "sources": [{"type": "web"}], "timeout": 20000,
               "scrapeOptions": {"formats": [{"type": "markdown"}], "onlyMainContent": True}}
    sources = []
    status = "failed"
    http_status = None
    try:
        async with client_factory(timeout=25) as client:
            response = await client.post(SEARCH_URL, headers={"Authorization": f"Bearer {key}"}, json=payload)
            http_status = response.status_code
            response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("success") is not True or not isinstance(result.get("data"), dict):
            return []
        pages = result["data"].get("web", [])
        if not isinstance(pages, list):
            return []
        seen = set()
        for page in pages[:RESULT_LIMIT]:
            if not isinstance(page, dict):
                continue
            metadata = page.get("metadata") if isinstance(page.get("metadata"), dict) else {}
            url = str(page.get("url") or metadata.get("sourceURL") or "").strip()
            try:
                parsed = urlsplit(url)
                valid_url = parsed.scheme in ("http", "https") and bool(parsed.hostname) and parsed.username is None and len(url) <= 2048
            except ValueError:
                valid_url = False
            if not valid_url or url in seen:
                continue
            snippet = str(page.get("description") or metadata.get("description") or "").strip()[:500]
            content = str(page.get("markdown") or "").strip()[:2000]
            if not snippet and not content:
                continue
            seen.add(url)
            sources.append({"id": str(len(sources) + 1), "url": url, "title": str(page.get("title") or metadata.get("title") or "")[:200],
                            "description": snippet, "excerpt": content})
        status = "ok" if sources else "empty"
        return sources
    except httpx.TimeoutException:
        status = "timeout"
        return []
    except (httpx.HTTPError, ValueError):
        return []
    finally:
        log_request("图书资料搜索", SEARCH_URL, {**payload, "result_count": len(sources), "status": status, "http_status": http_status})
