"""Health, request-log, and model-settings routes."""

from collections.abc import Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from backend.modules.contracts import ModelListRequest, SettingsPayload


async def fetch_models(api_base: str, api_key: str) -> dict[str, Any]:
    if not api_key:
        raise HTTPException(400, "请先填写 API 密钥")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            base = api_base.rstrip("/").removesuffix("/images/generations")
            response = await client.get(base + "/models", headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        message = "鉴权失败，请检查 API 密钥" if status in (401, 403) else f"服务返回 HTTP {status}，请检查 API 地址与服务状态"
        raise HTTPException(502, message) from None
    except httpx.RequestError:
        raise HTTPException(502, "无法连接模型服务，请检查 API 地址与网络后重试") from None
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(502, "服务未返回有效的模型列表，请检查 API 地址") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise HTTPException(502, "服务未返回有效的模型列表，请检查 API 地址")
    models = list(dict.fromkeys(
        item["id"] for item in payload["data"]
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip()
    ))
    return {"models": models, "demo": False}


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
    def request_logs(request_type: str = "", start_time: int | None = None, end_time: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100)):
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
        if not settings.get("text_api_key"): return {"models": [], "demo": True}
        return await fetch_models(settings["text_api_base"], settings["text_api_key"])

    @router.post("/api/models")
    async def models_fetch(value: ModelListRequest):
        api_key = value.api_key
        if api_key == "••••••••":
            api_key = get_settings().get(f"{value.provider}_api_key", "")
        return await fetch_models(value.api_base, api_key)

    return router
