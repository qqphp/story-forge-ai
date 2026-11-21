"""Generate and publish a replacement for one saved cover."""

import asyncio
import json
import random
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from PIL import Image

from backend.integrations.local_covers import STYLES, render_local_cover
from backend.modules.contracts import IMAGE_SIZES
from backend.modules.serializers import workflow_row


def _cover_path(output_dir: Path, url: str) -> Path | None:
    prefix = f"/media/{output_dir.name}/"
    name = url.removeprefix(prefix)
    if not url.startswith(prefix) or not name or "/" in name or "\\" in name:
        return None
    path = output_dir / name
    return path if path.resolve().parent == output_dir.resolve() else None


def _cover_ratio(cover: dict[str, Any], original: Path | None) -> str:
    if cover.get("image_ratio") in IMAGE_SIZES:
        return cover["image_ratio"]
    if not original or not original.is_file():
        raise ValueError("这张旧封面没有比例记录，也找不到原图")
    with Image.open(original) as image:
        aspect = image.width / image.height
    return min(sorted(IMAGE_SIZES), key=lambda ratio: abs(aspect - float(ratio.partition(":")[0]) / float(ratio.partition(":")[2])))


def _finish_job(db, wid: str, job: dict[str, str], staged: Path | None = None,
                replacement: dict[str, Any] | None = None, target: Path | None = None, error: str = "") -> bool:
    published = False
    try:
        with db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT payload FROM workflows WHERE id=? AND status='completed'", (wid,)).fetchone()
            if not row:
                return False
            payload = json.loads(row["payload"])
            if payload.get("cover_regenerating") != job:
                return False
            if staged is not None and target is not None:
                index = next((i for i, cover in enumerate(payload["covers"]) if cover.get("url") == job["cover_url"]), None)
                if index is None:
                    raise RuntimeError("原封面已被替换，请刷新后重试")
                staged.replace(target)
                published = True
                payload["covers"][index] = replacement
            payload["cover_regenerating"] = None
            payload["cover_error"] = {"cover_url": job["cover_url"], "message": error} if error else None
            conn.execute("UPDATE workflows SET payload=?,updated_at=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), int(time.time()), wid))
        return published
    except Exception:
        if published and target is not None:
            with suppress(OSError):
                target.unlink(missing_ok=True)
        raise


async def regenerate_workflow_cover(wid: str, job: dict[str, str], *, db, media_dir: Callable[[str], Path],
                                    get_settings: Callable[..., Any], generate_cover: Callable[..., Any]) -> None:
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            return
        item = workflow_row(row)
        if item.get("cover_regenerating") != job:
            return
        old_cover = next(cover for cover in item["covers"] if cover.get("url") == job["cover_url"])
        output_dir = media_dir(item["output_dir"])
        original = _cover_path(output_dir, job["cover_url"])
        ratio = _cover_ratio(old_cover, original)
        title, author = item["book_title"], item.get("author") or ""
        snapshot = next((prompt for prompt in item.get("cover_prompts", [])
                         if old_cover.get("prompt_id") and prompt.get("id") == old_cover["prompt_id"]), {})
        prompt = old_cover.get("prompt") or snapshot.get("text")
        target = output_dir / f"cover-regenerated-{job['id']}.png"
        with tempfile.TemporaryDirectory(prefix="cover-staging-", dir=output_dir.parent) as temporary:
            staged = Path(temporary) / "new.png"
            replacement = {**old_cover, "image_ratio": ratio, "url": f"/media/{output_dir.name}/{target.name}"}
            if old_cover.get("provider") == "openai_compatible" or (not old_cover.get("template_id") and not old_cover.get("provider") and prompt):
                if not prompt:
                    raise ValueError("这张旧封面缺少原始提示词，无法按原配置生成")
                used_model, _ = await generate_cover(staged, title, author, item.get("description") or "", prompt, 0,
                                                     ratio, get_settings(), allow_fallback=False)
                if not used_model:
                    raise RuntimeError("图片服务未生成封面，请重试")
            else:
                previous_style = str(old_cover.get("template_id") or "").rsplit("-", 1)[0]
                available_styles = [index for index, style in enumerate(STYLES) if style[0] != previous_style]
                metadata = await asyncio.to_thread(render_local_cover, staged, title, author, ratio, random.choice(available_styles))
                replacement.update(metadata)
            with Image.open(staged) as image:
                image.load()
                replacement["resolution"] = f"{image.width}×{image.height}"
                if image.format != "PNG":
                    image.save(staged, "PNG")
            if _finish_job(db, wid, job, staged, replacement, target):
                if original and sum(cover.get("url") == job["cover_url"] for cover in item["covers"]) == 1:
                    with suppress(OSError):
                        original.unlink(missing_ok=True)
    except Exception as exc:
        _finish_job(db, wid, job, error=str(exc)[:500] or "封面重新生成失败，请再试一次")
