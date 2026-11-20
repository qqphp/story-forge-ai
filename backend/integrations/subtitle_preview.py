"""Render the same ASS track used for video burning to a temporary PNG."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path

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
            from backend.integrations.player import player_command
            from backend.integrations.local_covers import render_local_cover
            cover = root / "cover.png"
            background_cover = root / "background.png"
            render_local_cover(background_cover, "在阅读中遇见自己", "StoryForge", "16:9" if value.orientation == "landscape" else "9:16", 0)
            render_local_cover(cover, "在阅读中遇见自己", "StoryForge", "1:1", 0)
            audio = root / "sample.wav"
            import wave, math, struct
            with wave.open(str(audio), "wb") as sample:
                sample.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                sample.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / 24000))) for i in range(48000)))
            try:
                command = player_command(os.getenv("FFMPEG_PATH", "ffmpeg"), cover, audio, root / "sample.mp4", orientation=value.orientation, background_cover=background_cover, record_label_image_id=value.record_label_image_id, subtitles=srt, subtitle_style=value.style.model_dump(), background_overlay_enabled=value.background_overlay_enabled, background_overlay_opacity=value.background_overlay_opacity, duration=2)
                subprocess.run(command[:-1] + ["-frames:v", "1", "-an", command[-1]], capture_output=True, timeout=15, check=True)
                result = subprocess.run([os.getenv("FFMPEG_PATH", "ffmpeg"), "-v", "error", "-ss", "0", "-i", str(root / "sample.mp4"), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"], capture_output=True, timeout=5)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError("播放器预览渲染失败") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("字幕预览超时，请重试") from exc
            if result.returncode:
                raise RuntimeError("字幕预览失败：" + result.stderr.decode("utf-8", errors="replace")[-400:])
            return result.stdout
    finally:
        _PREVIEW_SLOTS.release()
