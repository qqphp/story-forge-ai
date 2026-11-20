"""Local provider-setting use cases and their public representation."""

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from backend.modules.contracts import SettingsPayload, SubtitleStyle


def _speech_base_from_region(region: str, default: str) -> str:
    value = region.strip()
    if not value:
        return default
    if value.startswith(("http://", "https://")):
        return value.rstrip("/")
    return f"https://{value}.tts.speech.microsoft.com"


def load_settings(db: Callable[[], AbstractContextManager[Any]], defaults: dict[str, Any]) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()
    stored = json.loads(row["payload"]) if row else {}
    if not stored.get("_player_template_version"):
        stored.update(subtitle_style=SubtitleStyle().model_dump(), burn_subtitles=True, _player_template_version=1)
        with db() as conn:
            conn.execute("INSERT INTO settings(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (json.dumps(stored, ensure_ascii=False),))
    stored.setdefault("background_overlay_enabled", True)
    stored.setdefault("background_overlay_opacity", 0.25)
    stored.setdefault("background_blur_enabled", False)
    stored.setdefault("background_blur_strength", 20)
    stored.setdefault("record_label_image_id", "initial")
    legacy_speech_region = stored.pop("azure_speech_region", None)
    for provider in ("text", "image"):
        for legacy_field in ("api_base", "api_key"):
            field = f"{provider}_{legacy_field}"
            if field not in stored and legacy_field in stored:
                stored[field] = stored[legacy_field]
    stored.pop("api_base", None)
    stored.pop("api_key", None)
    result = defaults | stored
    result["subtitle_style"] = SubtitleStyle.model_validate(result.get("subtitle_style") or {}).model_dump()
    if "azure_speech_base" not in stored:
        if legacy_speech_region:
            result["azure_speech_base"] = _speech_base_from_region(legacy_speech_region, defaults["azure_speech_base"])
        elif os.getenv("AZURE_SPEECH_BASE"):
            result["azure_speech_base"] = os.environ["AZURE_SPEECH_BASE"]
        elif os.getenv("AZURE_SPEECH_REGION"):
            result["azure_speech_base"] = _speech_base_from_region(os.environ["AZURE_SPEECH_REGION"], defaults["azure_speech_base"])
    for field in ("text_api_base", "text_api_key", "image_api_base", "image_api_key"):
        if field not in stored:
            result[field] = os.getenv(field.upper(), defaults[field])
    result["model"] = stored.get("model", os.getenv("MODEL_NAME", defaults["model"]))
    result["image_model"] = stored.get("image_model", os.getenv("IMAGE_MODEL_NAME", defaults["image_model"]))
    result["azure_speech_key"] = result.get("azure_speech_key") or os.getenv("AZURE_SPEECH_KEY", "")
    result["pexels_api_key"] = result.get("pexels_api_key") or os.getenv("PEXELS_KEY", "")
    result["pixabay_api_key"] = result.get("pixabay_api_key") or os.getenv("PIXABAY_KEY", "")
    return result


def to_public(settings: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in settings.items() if not key.startswith("_")}
    result["text_api_key"] = "••••••••" if result.get("text_api_key") else ""
    result["image_api_key"] = "••••••••" if result.get("image_api_key") else ""
    result["azure_speech_key"] = "••••••••" if result.get("azure_speech_key") else ""
    result["pexels_api_key"] = "••••••••" if result.get("pexels_api_key") else ""
    result["pixabay_api_key"] = "••••••••" if result.get("pixabay_api_key") else ""
    return result


def save_settings(db: Callable[[], AbstractContextManager[Any]], current: dict[str, Any], value: SettingsPayload) -> dict[str, Any]:
    incoming = value.model_dump()
    incoming["_player_template_version"] = 1
    for key, default in (("background_overlay_enabled", True), ("background_overlay_opacity", 0.25), ("background_blur_enabled", False), ("background_blur_strength", 20)):
        if key not in value.model_fields_set:
            incoming[key] = current.get(key, default)
    if "record_label_image_id" not in value.model_fields_set:
        incoming["record_label_image_id"] = current.get("record_label_image_id", "initial")
    if "subtitle_style" not in value.model_fields_set:
        incoming["subtitle_style"] = current.get("subtitle_style", SubtitleStyle().model_dump())
    for key in ("text_api_key", "image_api_key", "azure_speech_key", "pexels_api_key", "pixabay_api_key"):
        if incoming[key] == "••••••••":
            incoming[key] = current.get(key, "")
    with db() as conn:
        conn.execute("INSERT INTO settings(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (json.dumps(incoming, ensure_ascii=False),))
    return incoming
