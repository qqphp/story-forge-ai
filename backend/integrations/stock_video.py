"""Search and download footage from supported royalty-free providers."""

from __future__ import annotations

import asyncio
import math
import os
import random
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from backend.integrations.video import normalize_stock_videos, probe_video_metadata


FORBIDDEN_HUMAN_TERMS = {"people", "person", "persons", "human", "humans", "man", "woman", "men", "women", "face", "portrait", "crowd", "character", "walking", "running", "reading", "sitting", "standing", "talking", "dancing"}


def natural_scenery_query(value: str) -> str:
    words = [word.strip(" ,.;:!?()[]{}\"'").lower() for word in value.split()]
    cleaned = [word for word in words if word and word not in FORBIDDEN_HUMAN_TERMS]
    return " ".join(cleaned[:7]) or "serene cinematic natural landscape"


def _pexels_items(payload: dict[str, Any], orientation: str) -> list[dict[str, Any]]:
    horizontal = orientation == "landscape"
    target_width, target_height = (1920, 1080) if horizontal else (1080, 1920)
    items: list[dict[str, Any]] = []
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
        items.append({"id": str(video.get("id", "")), "url": selected["link"], "duration": video.get("duration")})
    return items


def _pixabay_items(payload: dict[str, Any], orientation: str) -> list[dict[str, Any]]:
    horizontal = orientation == "landscape"
    items: list[dict[str, Any]] = []
    for video in payload.get("hits", []):
        source = video.get("videos", {}).get("large") or {}
        width, height = source.get("width", 0), source.get("height", 0)
        target_width, target_height = (1920, 1080) if horizontal else (1080, 1920)
        if not source.get("url") or ((width >= height) != horizontal) or width < target_width or height < target_height:
            continue
        items.append({"id": str(video.get("id", "")), "url": source["url"], "duration": video.get("duration")})
    return items


async def download_stock_videos(
    *, provider: str, api_base: str, api_key: str, query: str, orientation: str,
    output_dir: Path, target_duration: float,
    log_request: Callable[[str, str, dict[str, Any]], None],
    client_factory: Callable[..., Any] = httpx.AsyncClient,
) -> list[Path]:
    """Prepare up to ten playable clips, stopping at the narration duration."""
    if not api_key:
        raise RuntimeError(f"未配置 {provider.upper()} API 密钥")
    if not math.isfinite(target_duration) or target_duration <= 0:
        raise RuntimeError("无法读取有效配音时长")
    prefix = f"stock-{provider}-{uuid.uuid4().hex}"
    paths, created = [], []
    total, attempts, failures = 0.0, 0, 0
    seen_ids, seen_urls = set(), set()
    fallback = "serene cinematic natural landscape"
    queries = [query] + ([fallback] if query != fallback else [])
    ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
    succeeded = False
    try:
        async with client_factory(timeout=60, follow_redirects=True) as client:
            for search_query in queries:
                params = {"query" if provider == "pexels" else "q": search_query, "per_page": 40}
                headers = {}
                if provider == "pexels":
                    params.update(orientation=orientation, size="medium")
                    headers["Authorization"] = api_key
                else:
                    params.update(key=api_key, safesearch="true", video_type="all", category="nature")
                log_request("无版权视频搜索", api_base, {k: v for k, v in params.items() if k != "key"} | {"provider": provider})
                try:
                    response = await client.get(api_base, params=params, headers=headers)
                    response.raise_for_status()
                    payload = response.json()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(f"{provider} 搜索失败（HTTP {exc.response.status_code}）") from None
                except (httpx.RequestError, ValueError):
                    raise RuntimeError(f"{provider} 搜索失败，请检查接口或网络") from None
                items = _pexels_items(payload, orientation) if provider == "pexels" else _pixabay_items(payload, orientation)
                random.SystemRandom().shuffle(items)
                def duration(item):
                    value = item.get("duration")
                    return value if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else 0
                items.sort(key=duration, reverse=True)
                for item in items:
                    if attempts >= 20 or len(paths) >= 10 or total >= target_duration:
                        break
                    if item["url"] in seen_urls or (item["id"] and item["id"] in seen_ids):
                        continue
                    seen_urls.add(item["url"])
                    if item["id"]:
                        seen_ids.add(item["id"])
                    attempts += 1
                    raw = output_dir / f"{prefix}-{attempts}.mp4"
                    normalized = output_dir / f"{raw.stem}-normalized.mp4"
                    created.extend((raw, normalized))
                    try:
                        async with asyncio.timeout(60):
                            async with client.stream("GET", item["url"]) as download:
                                download.raise_for_status()
                                with raw.open("wb") as output:
                                    async for chunk in download.aiter_bytes():
                                        output.write(chunk)
                        if not raw.stat().st_size:
                            raise ValueError("empty video")
                        resolution, seconds = await asyncio.to_thread(probe_video_metadata, raw)
                        if not resolution or seconds is None or not math.isfinite(seconds) or seconds <= 0:
                            raise ValueError("invalid video")
                        await asyncio.to_thread(normalize_stock_videos, ffmpeg, [raw], output_dir, orientation, target_duration - total)
                        resolution, seconds = await asyncio.to_thread(probe_video_metadata, normalized)
                        if not resolution or seconds is None or not math.isfinite(seconds) or seconds <= 0:
                            raise ValueError("invalid normalized video")
                        paths.append(normalized)
                        total += seconds
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code in (401, 403):
                            raise RuntimeError(f"{provider} 视频下载鉴权失败（HTTP {exc.response.status_code}）") from None
                        failures += 1
                    except (httpx.RequestError, TimeoutError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
                        failures += 1
                    finally:
                        raw.unlink(missing_ok=True)
                        if normalized not in paths:
                            normalized.unlink(missing_ok=True)
                if paths or attempts >= 20:
                    break
        log_request("无版权视频准备", api_base, {
            "provider": provider, "target_duration": target_duration,
            "clip_count": len(paths), "usable_duration": round(total, 3),
            "failed_count": failures, "download_attempts": attempts,
            "loop_required": bool(paths) and total < target_duration,
        })
        if not paths:
            raise RuntimeError(f"{provider} 没有可用背景视频（已尝试 {attempts} 个素材，失败 {failures} 个）")
        succeeded = True
        return paths
    finally:
        if not succeeded:
            for path in created:
                path.unlink(missing_ok=True)
