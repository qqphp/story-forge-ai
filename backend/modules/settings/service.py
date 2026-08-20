"""Local provider-setting use cases and their public representation."""

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from backend.modules.contracts import SettingsPayload


def load_settings(db: Callable[[], AbstractContextManager[Any]], defaults: dict[str, Any]) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()
    result = defaults | (json.loads(row["payload"]) if row else {})
    result["api_base"] = os.getenv("MODEL_API_BASE", result["api_base"])
    result["model"] = os.getenv("MODEL_NAME", result["model"])
    result["image_model"] = os.getenv("IMAGE_MODEL_NAME", result["image_model"])
    result["api_key"] = result.get("api_key") or os.getenv("MODEL_API_KEY", "")
    result["azure_speech_key"] = result.get("azure_speech_key") or os.getenv("AZURE_SPEECH_KEY", "")
    return result


def to_public(settings: dict[str, Any]) -> dict[str, Any]:
    result = dict(settings)
    result["api_key"] = "••••••••" if result.get("api_key") else ""
    result["azure_speech_key"] = "••••••••" if result.get("azure_speech_key") else ""
    return result


def save_settings(db: Callable[[], AbstractContextManager[Any]], current: dict[str, Any], value: SettingsPayload) -> dict[str, Any]:
    incoming = value.model_dump()
    for key in ("api_key", "azure_speech_key"):
        if incoming[key] == "••••••••":
            incoming[key] = current.get(key, "")
    with db() as conn:
        conn.execute("INSERT INTO settings(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (json.dumps(incoming, ensure_ascii=False),))
    return incoming
