"""Eighteen code-drawn cover layouts, using only bundled fonts and Pillow."""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.integrations.fonts import FONTS_DIR


STYLES = (
    ("literary", "文学留白", "#F2EFE7", "#263E39", "#B99262"),
    ("paper", "复古纸张", "#E4D5B5", "#49362B", "#A0523E"),
    ("geometry", "几何拼色", "#DCE8E6", "#193F49", "#E58D63"),
    ("gold", "暗色金线", "#17262F", "#F5EBD6", "#CAA66A"),
    ("landscape", "山水剪影", "#DCE3DA", "#263F3A", "#76958A"),
    ("editorial", "现代书刊", "#F5F0E8", "#222F43", "#B9503E"),
)
SIZES = {"1:1": (1080, 1080), "16:9": (1920, 1080), "9:16": (1080, 1920)}


def _fit(draw: ImageDraw.ImageDraw, text: str, font_file: Path, width: int, height: int, initial: int):
    text = " ".join(text.split())
    for size in range(initial, 15, -2):
        font = ImageFont.truetype(str(font_file), size)
        lines, line = [], ""
        for char in text:
            if line and draw.textlength(line + char, font=font) > width:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
        value = "\n".join(lines)
        box = draw.multiline_textbbox((0, 0), value, font=font, spacing=size // 4)
        if box[2] - box[0] <= width and box[3] - box[1] <= height:
            return value, font, box
    raise RuntimeError("封面文字过长，无法排入模板")


def render_local_cover(path: Path, title: str, author: str, ratio: str, style_index: int) -> dict[str, str]:
    width, height = SIZES[ratio]
    key, name, background, ink, accent = STYLES[style_index]
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    portrait = height > width
    unit = min(width, height)
    margin = int(unit * .10)

    if key == "literary":
        draw.line((margin, height * .17, width - margin, height * .17), fill=accent, width=3)
        draw.ellipse((width * .73, height * .08, width * .73 + unit * .14, height * .08 + unit * .14), fill=accent)
        draw.line((margin, height * .22, margin, height * .71), fill=ink, width=6)
    elif key == "paper":
        for y in range(0, height, 7):
            shade = 196 + (y * 17 % 25)
            draw.line((0, y, width, y), fill=(min(255, shade + 20), shade, max(0, shade - 30)))
        draw.rectangle((margin * .6, margin * .6, width - margin * .6, height * .79), outline=ink, width=3)
        draw.rectangle((width - margin * 2, height * .1, width - margin, height * .16), fill=accent)
    elif key == "geometry":
        draw.polygon([(width * .65, 0), (width, 0), (width, height * .7)], fill=accent)
        draw.ellipse((-unit * .22, height * .59, unit * .43, height * .59 + unit * .65), fill="#8CAFAA")
        draw.rectangle((margin, height * .15, margin + unit * .16, height * .17), fill=ink)
    elif key == "gold":
        draw.rectangle((margin * .6, margin * .6, width - margin * .6, height * .78), outline=accent, width=3)
        draw.arc((width - unit * .65, -unit * .25, width + unit * .35, unit * .75), 0, 360, fill=accent, width=3)
        draw.line((margin, height * .22, margin + unit * .3, height * .22), fill=accent, width=4)
    elif key == "landscape":
        draw.ellipse((width * .76, height * .1, width * .76 + unit * .12, height * .1 + unit * .12), fill="#C6A478")
        for level, color in ((.66, "#A6B9AF"), (.72, "#78958A"), (.79, "#506F65")):
            draw.polygon([(0, height), (0, height * level), (width * .22, height * (level - .08)), (width * .49, height * (level + .03)), (width * .77, height * (level - .11)), (width, height * level), (width, height)], fill=color)
    else:
        draw.rectangle((0, 0, width * .035, height), fill=accent)
        draw.rectangle((margin, height * .1, width - margin, height * .17), fill=ink)
        draw.text((margin + 18, height * .108), "THE READING ROOM", font=ImageFont.truetype(str(FONTS_DIR / "Inter-Regular.otf"), 36), fill=background)
        draw.line((margin, height * .7, width - margin, height * .7), fill=accent, width=8)

    font_file = FONTS_DIR / ("SourceHanSerifSC-Regular.otf" if key in ("literary", "paper", "gold") else "NotoSansCJKsc-Regular.otf")
    x, y = margin + (20 if key == "literary" else 0), int(height * (.29 if portrait else .28))
    text, font, box = _fit(draw, title, font_file, width - x - margin, int(height * .29), 104 if portrait else 112)
    draw.multiline_text((x - box[0], y - box[1]), text, font=font, fill=ink, spacing=font.size // 4)
    if author.strip():
        text, font, box = _fit(draw, author, FONTS_DIR / "NotoSansCJKsc-Regular.otf", width - x - margin, int(height * .10), 36)
        draw.multiline_text((x - box[0], height * .61 - box[1]), text, font=font, fill=ink, spacing=font.size // 4)
    draw.text((margin, height * .755), "STORYFORGE  /  BOOK NOTES", font=ImageFont.truetype(str(FONTS_DIR / "Inter-Regular.otf"), 22), fill=accent)
    image.save(path, "PNG")
    return {"template_id": f"{key}-{'square' if width == height else 'portrait' if portrait else 'landscape'}", "prompt_name": name, "image_ratio": ratio, "resolution": f"{width}×{height}", "provider": "local_template"}


def generate_local_covers(output_dir: Path, title: str, author: str) -> list[dict[str, str]]:
    covers = []
    style_index = random.randrange(len(STYLES))
    for index, ratio in enumerate(SIZES, 1):
        path = output_dir / f"cover-{index}.png"
        metadata = render_local_cover(path, title, author, ratio, style_index)
        covers.append({**metadata, "url": f"/media/{output_dir.name}/{path.name}"})
    return covers
