"""Search and download footage from supported royalty-free providers."""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx


FORBIDDEN_HUMAN_TERMS = {"people", "person", "persons", "human", "humans", "man", "woman", "men", "women", "face", "portrait", "crowd", "character", "walking", "running", "reading", "sitting", "standing", "talking", "dancing"}


def natural_scenery_query(value: str) -> str:
    words = [word.strip(" ,.;:!?()[]{}\"'").lower() for word in value.split()]
    cleaned = [word for word in words if word and word not in FORBIDDEN_HUMAN_TERMS]
    return " ".join(cleaned[:7]) or "serene cinematic natural landscape"


def _pexels_items(payload: dict[str, Any], orientation: str) -> list[dict[str, str]]:
    horizontal = orientation == "landscape"
    target_width, target_height = (1920, 1080) if horizontal else (1080, 1920)
    items: list[dict[str, str]] = []
    for video in payload.get("videos", []):
        if (video.get("width", 0) >= video.get("height", 0)) != horizontal:
            continue
        files = [item for item in video.get("video_files", []) if item.get("link")]
        full_hd = [
            item for item in files
            if item.get("quality") == "hd"
            and (item.get("width") or 0) >= target_width
            and (item.get("height") or 0) >= target_height
        ]
        if not full_hd:
            continue
        selected = min(
            full_hd,
            key=lambda item: abs((item.get("width") or 0) - target_width) + abs((item.get("height") or 0) - target_height),
        )
        items.append({"id": str(video.get("id", "")), "url": selected["link"]})
    return items


def _pixabay_items(payload: dict[str, Any], orientation: str) -> list[dict[str, str]]:
    horizontal = orientation == "landscape"
    items: list[dict[str, str]] = []
    for video in payload.get("hits", []):
        source = video.get("videos", {}).get("large") or {}
        width, height = source.get("width", 0), source.get("height", 0)
        target_width, target_height = (1920, 1080) if horizontal else (1080, 1920)
        if not source.get("url") or ((width >= height) != horizontal) or width < target_width or height < target_height:
            continue
        items.append({"id": str(video.get("id", "")), "url": source["url"]})
    return items


async def download_stock_videos(
    *, provider: str, api_base: str, api_key: str, query: str, orientation: str,
    output_dir: Path, log_request: Callable[[str, str, dict[str, Any]], None],
    client_factory: Callable[..., Any] = httpx.AsyncClient,
) -> list[Path]:
    """Return three randomly selected clips with at least 1080p source resolution."""
    if not api_key:
        raise RuntimeError(f"未配置 {provider.upper()} API 密钥")
    params: dict[str, Any] = {"query" if provider == "pexels" else "q": query, "per_page": 40}
    headers: dict[str, str] = {}
    if provider == "pexels":
        params.update(orientation=orientation, size="medium")
        headers["Authorization"] = api_key
    else:
        params.update(key=api_key, per_page=40, safesearch="true", video_type="all", category="nature")
    log_request("无版权视频搜索", api_base, {key: value for key, value in params.items() if key != "key"} | {"provider": provider})
    async with client_factory(timeout=60, follow_redirects=True) as client:
        response = await client.get(api_base, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
        items = _pexels_items(payload, orientation) if provider == "pexels" else _pixabay_items(payload, orientation)
        if len(items) < 3:
            raise RuntimeError(f"{provider} 没有返回至少 3 条符合{orientation}方向的视频")
        selected = random.SystemRandom().sample(items, 3)
        paths: list[Path] = []
        for index, item in enumerate(selected, 1):
            target = output_dir / f"stock-{provider}-{index}.mp4"
            async with client.stream("GET", item["url"]) as download:
                download.raise_for_status()
                with target.open("wb") as output:
                    async for chunk in download.aiter_bytes():
                        output.write(chunk)
            if not target.exists() or target.stat().st_size == 0:
                raise RuntimeError(f"{provider} 视频下载失败")
            paths.append(target)
    return paths
