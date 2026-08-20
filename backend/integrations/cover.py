"""Cover-image providers and deterministic local fallback."""

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def make_local_cover(path: Path, title: str, author: str, index: int) -> None:
    palettes = [(22, 38, 53), (72, 52, 45), (31, 57, 47)]
    bg = palettes[index % len(palettes)]
    image = Image.new("RGB", (1080, 1440), bg)
    draw = ImageDraw.Draw(image)
    for y in range(1440):
        f = y / 1440
        color = tuple(int(c + (235 - c) * f * .22) for c in bg)
        draw.line((0, y, 1080, y), fill=color)
    draw.ellipse((660, 80, 1110, 530), fill=(227, 177, 94))
    draw.rectangle((86, 95, 100, 1330), fill=(227, 177, 94))
    try:
        font_big = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 92)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 34)
    except OSError:
        font_big = font_small = ImageFont.load_default()
    lines, line = [], ""
    for char in title:
        if len(line) >= 8:
            lines.append(line)
            line = ""
        line += char
    if line:
        lines.append(line)
    draw.multiline_text((130, 520), "\n".join(lines), font=font_big, fill=(248, 244, 233), spacing=28)
    draw.text((135, 1210), author or "STORYFORGE EDITION", font=font_small, fill=(240, 211, 158))
    image.save(path, "PNG")


async def generate_cover(
    path: Path,
    title: str,
    author: str,
    description: str,
    prompt: str,
    index: int,
    image_ratio: str,
    settings: dict[str, Any],
    log_request: Callable[[str, str, dict[str, Any]], None],
    client_factory: Callable[..., Any],
    fallback: Callable[[Path, str, str, int], None] = make_local_cover,
) -> tuple[bool, str]:
    """Use an OpenAI-compatible endpoint, falling back to a local cover."""
    if settings.get("api_key"):
        try:
            url = settings["api_base"].rstrip("/") + "/images/generations"
            ratio_prompt = f"{prompt}\n\n图片比例：{image_ratio}"
            payload = {
                "model": settings.get("image_model", "gpt-image-2"),
                "n": 1,
                "prompt": f"为《{title}》创作无文字的书籍分享封面。作者：{author}。简介：{description}。视觉要求：{ratio_prompt}",
            }
            log_request("封面生成", url, payload)
            async with client_factory(timeout=300, follow_redirects=True) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()["data"][0]
                raw = base64.b64decode(data["b64_json"]) if data.get("b64_json") else (await client.get(data["url"])).content
                path.write_bytes(raw)
                with Image.open(path) as generated:
                    return True, f"{generated.width}×{generated.height}"
        except Exception:
            pass
    fallback(path, title, author, index)
    with Image.open(path) as generated:
        return False, f"{generated.width}×{generated.height}"
