"""Health, request-log, and model-settings routes."""

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import APIRouter, Query

from backend.modules.contracts import SettingsPayload


def build_router(
    db: Callable[[], Any], get_settings: Callable[[], dict[str, Any]],
    public_settings: Callable[[dict[str, Any]], dict[str, Any]],
    save_settings: Callable[..., dict[str, Any]],
    list_logs: Callable[..., dict[str, Any]], clear_logs: Callable[..., int],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    def health(): return {"ok": True, "service": "StoryForge AI"}

    @router.get("/api/request-logs")
    def request_logs(request_type: str = "", start_time: int | None = None, end_time: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
        return list_logs(db, request_type, start_time, end_time, page, page_size)

    @router.delete("/api/request-logs")
    def request_logs_clear(): return {"deleted": clear_logs(db)}

    @router.get("/api/settings")
    def settings_get(): return public_settings(get_settings())

    @router.put("/api/settings")
    def settings_put(value: SettingsPayload): return public_settings(save_settings(db, get_settings(), value))

    @router.get("/api/models")
    async def models():
        settings = get_settings()
        if not settings.get("api_key"): return {"models": [settings["model"]], "demo": True}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(settings["api_base"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {settings['api_key']}"})
            response.raise_for_status()
        return {"models": [model["id"] for model in response.json().get("data", [])], "demo": False}

    return router
