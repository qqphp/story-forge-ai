"""Bundled font files used when subtitles are burned into a video."""

import json
from pathlib import Path
from typing import Any


FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"
MANIFEST_PATH = FONTS_DIR / "manifest.json"


def load_font_manifest() -> dict[str, Any]:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("内置字体库清单不可用") from exc


def bundled_fonts_dir() -> Path:
    """Return the flat font directory FFmpeg can pass as ``fontsdir``."""
    manifest = load_font_manifest()
    missing = [item["file"] for item in manifest.get("fonts", []) if not (FONTS_DIR / item["file"]).is_file()]
    if missing:
        raise RuntimeError("内置字体库缺少文件：" + "、".join(missing))
    return FONTS_DIR


def subtitle_font_family() -> str:
    family = str(load_font_manifest().get("subtitle_family", "")).strip()
    if not family:
        raise RuntimeError("内置字体库没有字幕主字体")
    return family
