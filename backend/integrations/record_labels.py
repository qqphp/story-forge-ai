"""Application-managed circular record labels."""
import io
import hashlib
import re
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

ASSETS = Path(__file__).resolve().parents[2] / 'assets' / 'video'
UPLOADS = Path(__file__).resolve().parents[2] / 'data' / 'video_assets'


def label_path(image_id: str | None) -> Path:
    if image_id == 'initial':
        candidate = ASSETS / 'record-label-initial.png'
    elif image_id and re.fullmatch(r'[a-f0-9]{32}', image_id):
        candidate = UPLOADS / f'{image_id}.png'
    else:
        candidate = ASSETS / 'record-label-default.png'
    return candidate if candidate.is_file() else ASSETS / 'record-label-default.png'


def store_label(raw: bytes) -> str:
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('图片不能超过 10MB')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > 25_000_000:
                raise ValueError('仅支持不超过 2500 万像素的 PNG、JPEG、WebP 图片')
            image = ImageOps.exif_transpose(source).convert('RGBA')
            image.thumbnail((1600, 1600))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('图片文件无效') from exc
    output = io.BytesIO(); image.save(output, 'PNG')
    image_id = hashlib.sha256(output.getvalue()).hexdigest()[:32]
    UPLOADS.mkdir(parents=True, exist_ok=True)
    (UPLOADS / f'{image_id}.png').write_bytes(output.getvalue())
    return image_id
