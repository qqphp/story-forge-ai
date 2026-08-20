"""OpenAI-compatible chat-completions adapter."""

from collections.abc import Callable
from typing import Any


async def complete_chat(
    messages: list[dict[str, str]], settings: dict[str, Any], request_type: str,
    log_request: Callable[[str, str, dict[str, Any]], None], client_factory: Callable[..., Any],
) -> str | None:
    if not settings.get("api_key"):
        return None
    url = settings["api_base"].rstrip("/") + "/chat/completions"
    payload = {"model": settings["model"], "messages": messages, "temperature": 0.75}
    log_request(request_type, url, payload)
    async with client_factory(timeout=90) as client:
        response = await client.post(url, headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
