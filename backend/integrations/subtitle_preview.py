"""Render the same ASS track used for video burning to a temporary PNG."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from backend.integrations.subtitle_burn import burn_subtitle_filter
from backend.modules.contracts import SubtitlePreview

_PREVIEW_SLOTS = threading.BoundedSemaphore(2)


def render_preview(value: SubtitlePreview) -> bytes:
    if not _PREVIEW_SLOTS.acquire(timeout=2):
        raise RuntimeError("字幕预览繁忙，请稍后重试")
    try:
        with tempfile.TemporaryDirectory(prefix="storyforge-preview-") as directory:
            root = Path(directory)
            srt = root / "sample.srt"
            srt.write_text(f"1\n00:00:00,000 --> 00:00:03,000\n{value.text}\n", encoding="utf-8")
            width, height = (1920, 1080) if value.orientation == "landscape" else (1080, 1920)
            filters = burn_subtitle_filter(srt, root / "sample.mp4", width, height, style=value.style.model_dump())
            try:
                result = subprocess.run([
                    os.getenv("FFMPEG_PATH", "ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                    f"color=c=0x263e49:s={width}x{height}:d=1", "-vf", filters,
                    "-frames:v", "1", "-threads", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
                ], capture_output=True, timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("字幕预览超时，请重试") from exc
            if result.returncode:
                raise RuntimeError("字幕预览失败：" + result.stderr.decode("utf-8", errors="replace")[-400:])
            return result.stdout
    finally:
        _PREVIEW_SLOTS.release()
