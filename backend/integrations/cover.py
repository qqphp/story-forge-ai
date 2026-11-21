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
    if settings.get("image_api_key") and settings.get("image_model"):
        try:
            url = settings["image_api_base"].rstrip("/").removesuffix("/images/generations") + "/images/generations"
            if image_ratio == "1:1":
                text_requirement = (
                    f"生成正方形书籍封面，必须清晰排印书名：{title}\n"
                    + (f"必须清晰排印作者：{author}\n" if author.strip() else "未提供作者，只排印书名，不编造姓名或占位文字。\n")
                    + "书名为主标题，作者为次要文字，完整、准确、易读，与画面协调。"
                    "不得遗漏上述文字，不添加书名号、副标题、推荐语、出版社或水印。"
                )
            else:
                text_requirement = (
                    "生成适合视频背景的纯视觉画面，禁止出现任何文字，包括书名、作者、字母、数字、标志和水印。"
                    "按当前比例独立构图，不裁切方形封面，不预留文字框。"
                )
            ratio_prompt = (
                f"{prompt}\n\n【本张图片的最终要求；与模板冲突时以本段为准】\n"
                f"{text_requirement}\n图片比例：{image_ratio}"
            )
            payload = {
                "model": settings["image_model"],
                "n": 1,
                "prompt": (
                    f"书名：{title}\n作者：{author or '未提供'}\n"
                    f"书籍简介（仅用于理解主题、情绪和视觉意象，不要把简介排印在画面上）：\n{description}\n\n"
                    f"视觉要求：\n{ratio_prompt}"
                ),
            }
            log_request("封面生成", url, payload)
            async with client_factory(timeout=300, follow_redirects=True) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {settings['image_api_key']}", "Content-Type": "application/json"},
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
    from backend.integrations.local_covers import render_local_cover
    render_local_cover(path, title, author, image_ratio if image_ratio in ("1:1", "16:9", "9:16") else "9:16", index % 6)
    with Image.open(path) as generated:
        return False, f"{generated.width}×{generated.height}"
