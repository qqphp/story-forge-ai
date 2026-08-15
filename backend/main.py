from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import math
import os
import secrets
import shutil
import sqlite3
import string
import subprocess
import time
import uuid
import wave
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
DATA = ROOT / "data"
MEDIA = DATA / "media"
VOICE_SAMPLES = DATA / "voice_samples"
VOICE_TRANSLATIONS_PATH = DATA / "voice_sample_translations.json"
DB_PATH = DATA / "storyforge.db"
DATA.mkdir(exist_ok=True)
MEDIA.mkdir(exist_ok=True)
VOICE_SAMPLES.mkdir(exist_ok=True)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workflows (
              id TEXT PRIMARY KEY, book_title TEXT NOT NULL, author TEXT,
              edition TEXT, status TEXT NOT NULL, step INTEGER NOT NULL,
              progress INTEGER NOT NULL, created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prompt_templates (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('writing','cover')),
              name TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL, image_sizes TEXT NOT NULL DEFAULT '["2:3"]'
            );
            CREATE INDEX IF NOT EXISTS idx_prompt_templates_kind ON prompt_templates(kind);
            CREATE TABLE IF NOT EXISTS background_music (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_background_music_created_at ON background_music(created_at DESC);
            CREATE TABLE IF NOT EXISTS request_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT, request_type TEXT NOT NULL,
              request_url TEXT NOT NULL, request_params TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_request_logs_type_created_at ON request_logs(request_type, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at DESC);
            """
        )
        columns = {column["name"] for column in conn.execute("PRAGMA table_info(prompt_templates)")}
        if "image_sizes" not in columns:
            conn.execute("ALTER TABLE prompt_templates ADD COLUMN image_sizes TEXT NOT NULL DEFAULT '[\"2:3\"]'")
        count = conn.execute("SELECT COUNT(*) AS count FROM prompt_templates").fetchone()["count"]
        if count == 0:
            now = int(time.time())
            defaults = [
                ("writing-short-video", "writing", "短视频口播", "适合 2 分钟短视频口播，有真实阅读感受", now, now, '["2:3"]'),
                ("writing-insight", "writing", "反常识洞见", "从一个反常识观点切入，避免剧透，结尾给出阅读建议", now, now, '["2:3"]'),
                ("cover-literary", "cover", "文学质感", "克制的文学感，竖版构图，无文字，为标题留出空间", now, now, '["2:3"]'),
            ]
            conn.executemany("INSERT INTO prompt_templates VALUES(?,?,?,?,?,?,?)", defaults)
        legacy_size_ratios = {"1024x1024": "1:1", "2048x2048": "1:1", "1600x1200": "4:3", "1536x1024": "3:2", "2048x1152": "16:9", "3840x2160": "16:9", "2538x1080": "2.35:1", "1200x1600": "3:4", "1024x1536": "2:3", "2160x3840": "9:16"}
        for row in conn.execute("SELECT id,image_sizes FROM prompt_templates").fetchall():
            sizes = json.loads(row["image_sizes"])
            if any("x" in size for size in sizes):
                conn.execute("UPDATE prompt_templates SET image_sizes=? WHERE id=?", (json.dumps(list(dict.fromkeys(legacy_size_ratios.get(size, "2:3") for size in sizes))), row["id"]))
        conn.execute("PRAGMA optimize")


DEFAULT_SETTINGS = {
    "api_base": "https://api.teamorouter.com/v1",
    "model": "gpt-5.4-mini",
    "image_model": "gpt-image-2",
    "api_key": "",
    "azure_speech_key": "",
    "azure_speech_region": os.getenv("AZURE_SPEECH_REGION", "eastus"),
    "voice_format": "audio-24khz-48kbitrate-mono-mp3",
    "voices": ["zh-CN-XiaoxiaoNeural"],
    "speech_rate": 0,
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="StoryForge AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=MEDIA), name="media")
app.mount("/voice-samples", StaticFiles(directory=VOICE_SAMPLES), name="voice-samples")
DELETING_WORKFLOWS: set[str] = set()
DELETING_WORKFLOW_DIRS: dict[str, str] = {}
VOICE_DOWNLOAD_STATUS: dict[str, Any] = {"status": "idle", "total": 0, "completed": 0, "failed": 0}
VOICE_TRANSLATION_LOCK = asyncio.Lock()
VOICE_SAMPLE_TEXT = "你好，欢迎收听这款流畅自然的AI配音。"


class PromptItem(BaseModel):
    text: str
    enabled: bool = True


class WorkflowOptions(BaseModel):
    writing_prompt_ids: list[str] = Field(default_factory=list)
    cover_prompt_ids: list[str] = Field(default_factory=list)
    voice: str = Field(default="zh-CN-XiaoxiaoNeural", min_length=1, max_length=120)
    speech_rate: int = Field(default=0, ge=-50, le=100)
    background_music_id: str | None = Field(default=None, max_length=40)
    background_music_volume: float = Field(default=.2, ge=0, le=1)
    background_music_fade_in: float = Field(default=2, ge=0, le=10)
    background_music_fade_out: float = Field(default=2, ge=0, le=10)


class BookCreate(BaseModel):
    book_title: str = Field(min_length=1, max_length=160)
    author: str = Field(default="", max_length=120)
    edition: str = Field(default="", max_length=120)


class WorkflowCreate(WorkflowOptions, BookCreate):
    pass


class BatchWorkflowCreate(WorkflowOptions):
    books: list[BookCreate] = Field(min_length=1, max_length=50)


MAX_PROMPT_LENGTH = 100_000
DEFAULT_IMAGE_SIZES = ["2:3"]
IMAGE_SIZES = {"1:1", "4:5", "2:3", "3:4", "9:16", "6:7", "1.91:1", "2.35:1", "3:2", "4:3", "16:9"}


class PromptTemplateCreate(BaseModel):
    kind: str = Field(pattern="^(writing|cover)$")
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    image_sizes: list[str] = Field(default_factory=lambda: list(DEFAULT_IMAGE_SIZES), max_length=len(IMAGE_SIZES))

    @field_validator("image_sizes")
    @classmethod
    def validate_image_sizes(cls, values: list[str]) -> list[str]:
        values = list(dict.fromkeys(values))
        if not values or any(value not in IMAGE_SIZES for value in values):
            raise ValueError("图片尺寸无效")
        return values


class PromptTemplateUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    image_sizes: list[str] = Field(default_factory=lambda: list(DEFAULT_IMAGE_SIZES), max_length=len(IMAGE_SIZES))

    @field_validator("image_sizes")
    @classmethod
    def validate_image_sizes(cls, values: list[str]) -> list[str]:
        return PromptTemplateCreate.validate_image_sizes(values)


class SettingsPayload(BaseModel):
    api_base: str = "https://api.teamorouter.com/v1"
    model: str = "gpt-5.4-mini"
    image_model: str = "gpt-image-2"
    api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"
    voice_format: str = "audio-24khz-48kbitrate-mono-mp3"
    voices: list[str] = ["zh-CN-XiaoxiaoNeural"]
    speech_rate: int = Field(default=0, ge=-50, le=100)


class BackgroundMusicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="", max_length=80)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("背景音乐链接必须使用 https")
        return value


def get_settings() -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()
    result = DEFAULT_SETTINGS | (json.loads(row["payload"]) if row else {})
    result["api_base"] = os.getenv("MODEL_API_BASE", result["api_base"])
    result["model"] = os.getenv("MODEL_NAME", result["model"])
    result["image_model"] = os.getenv("IMAGE_MODEL_NAME", result["image_model"])
    result["api_key"] = result.get("api_key") or os.getenv("MODEL_API_KEY", "")
    result["azure_speech_key"] = result.get("azure_speech_key") or os.getenv("AZURE_SPEECH_KEY", "")
    return result


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    result = dict(settings)
    result["api_key"] = "••••••••" if result.get("api_key") else ""
    result["azure_speech_key"] = "••••••••" if result.get("azure_speech_key") else ""
    return result


def prompt_template_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["image_sizes"] = json.loads(result["image_sizes"])
    return result


def workflow_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload"])
    return {
        "id": row["id"], "book_title": row["book_title"], "author": row["author"],
        "edition": row["edition"], "status": row["status"], "step": row["step"],
        "progress": row["progress"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], **payload,
    }


def log_request(request_type: str, request_url: str, request_params: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO request_logs(request_type,request_url,request_params,created_at) VALUES(?,?,?,?)",
            (request_type, request_url, json.dumps(request_params, ensure_ascii=False), int(time.time())),
        )


def save_workflow(wid: str, *, status: str | None = None, step: int | None = None,
                  progress: int | None = None, payload_update: dict[str, Any] | None = None) -> None:
    with db() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            return
        payload = json.loads(row["payload"])
        payload.update(payload_update or {})
        conn.execute(
            "UPDATE workflows SET status=?,step=?,progress=?,updated_at=?,payload=? WHERE id=?",
            (status or row["status"], step if step is not None else row["step"],
             progress if progress is not None else row["progress"], int(time.time()),
             json.dumps(payload, ensure_ascii=False), wid),
        )


def create_workflow_media_dir() -> tuple[str, Path]:
    media_root = MEDIA.resolve()
    for _ in range(20):
        random_letters = "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
        folder_name = f"{datetime.now().strftime('%Y%m%d')}{random_letters}{int(time.time())}"
        target = (MEDIA / folder_name).resolve()
        if target.parent != media_root:
            raise RuntimeError("工作流产物目录越界")
        try:
            target.mkdir(parents=False, exist_ok=False)
            return folder_name, target
        except FileExistsError:
            continue
    raise RuntimeError("无法创建唯一的工作流产物目录")


def workflow_media_dir(output_dir: str) -> Path:
    target = (MEDIA / output_dir).resolve()
    if target.parent != MEDIA.resolve():
        raise RuntimeError("工作流产物目录越界")
    return target


def cleanup_workflow_media(wid: str, output_dir: str | None = None) -> int:
    if not output_dir:
        with db() as conn:
            row = conn.execute("SELECT payload FROM workflows WHERE id=?", (wid,)).fetchone()
        if row:
            output_dir = json.loads(row["payload"]).get("output_dir")
    if not output_dir:
        return 0
    target = workflow_media_dir(output_dir)
    if not target.is_dir():
        return 0
    removed = sum(1 for candidate in target.rglob("*") if candidate.is_file())
    shutil.rmtree(target)
    return removed


async def llm(messages: list[dict[str, str]], settings: dict[str, Any]) -> str | None:
    if not settings.get("api_key"):
        return None
    url = settings["api_base"].rstrip("/") + "/chat/completions"
    payload = {"model": settings["model"], "messages": messages, "temperature": 0.75}
    log_request("文稿生成", url, payload)
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def demo_copy(title: str, author: str, prompt: str, index: int) -> str:
    angle = prompt or ["把复杂世界重新看清", "一次真诚而克制的阅读分享", "从书页走回自己的生活"][index % 3]
    byline = f"，{author}写下的" if author else "，这本"
    return (
        f"如果一本书能让你在合上它之后，重新看待自己的生活，《{title}》或许就是这样一本书。"
        f"{byline}作品没有急着给出标准答案，而是沿着“{angle}”这条线索，把那些被我们忽略的细节慢慢照亮。\n\n"
        "它真正动人的地方，不是观点有多响亮，而是读到某一页时，你忽然发现作者写的也是自己。"
        "那些犹豫、选择和未说出口的话，都在故事里获得了新的解释。\n\n"
        f"推荐你读《{title}》。不必赶进度，给它一个安静的晚上，也给自己一次重新整理内心的机会。"
    )


def make_cover(path: Path, title: str, author: str, index: int) -> None:
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
            lines.append(line); line = ""
        line += char
    if line: lines.append(line)
    draw.multiline_text((130, 520), "\n".join(lines), font=font_big, fill=(248, 244, 233), spacing=28)
    draw.text((135, 1210), author or "STORYFORGE EDITION", font=font_small, fill=(240, 211, 158))
    image.save(path, "PNG")


async def generate_cover(path: Path, title: str, author: str, description: str,
                         prompt: str, index: int, image_ratio: str, settings: dict[str, Any]) -> tuple[bool, str]:
    """Use an OpenAI-compatible image endpoint when available, with a local fallback."""
    if settings.get("api_key"):
        try:
            url = settings["api_base"].rstrip("/") + "/images/generations"
            ratio_prompt = f"{prompt}\n\n图片比例：{image_ratio}"
            payload = {"model": settings.get("image_model", "gpt-image-2"), "n": 1,
                       "prompt": f"为《{title}》创作无文字的书籍分享封面。作者：{author}。简介：{description}。视觉要求：{ratio_prompt}"}
            log_request("封面生成", url, payload)
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
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
    make_cover(path, title, author, index)
    with Image.open(path) as generated:
        return False, f"{generated.width}×{generated.height}"


def make_demo_wav(path: Path, seconds: float = 3.0) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            envelope = min(1, i / 1000, (rate * seconds - i) / 1000)
            sample = int(2600 * envelope * math.sin(2 * math.pi * (190 + 40 * math.sin(i / rate)) * i / rate))
            frames += sample.to_bytes(2, "little", signed=True)
        out.writeframes(frames)


def speech_ssml(text: str, voice: str, rate: int,
                background_music: dict[str, Any] | None = None,
                background_volume: float = .2,
                background_fade_in: float = 2,
                background_fade_out: float = 2) -> str:
    safe_rate = max(-50, min(100, int(rate)))
    namespace = ' xmlns="http://www.w3.org/2001/10/synthesis"'
    if background_music:
        namespace += ' xmlns:mstts="https://www.w3.org/2001/mstts"'
    background = ""
    if background_music:
        volume = max(0, min(1, float(background_volume)))
        volume_text = f"{volume:.2f}".rstrip("0").rstrip(".")
        fade_in = max(0, min(10000, round(float(background_fade_in) * 1000)))
        fade_out = max(0, min(10000, round(float(background_fade_out) * 1000)))
        source = html.escape(str(background_music["url"]), quote=True)
        background = (f'<mstts:backgroundaudio src="{source}" volume="{volume_text}" '
                      f'fadein="{fade_in}" fadeout="{fade_out}"/>')
    return (f'<speak version="1.0"{namespace} xml:lang="{html.escape(voice_locale(voice), quote=True)}">{background}'
            f'<voice name="{html.escape(voice, quote=True)}">'
            f'<prosody rate="{safe_rate:+d}%">{html.escape(text)}</prosody></voice></speak>')


async def speech(text: str, voice: str, rate: int, settings: dict[str, Any], output: Path,
                 background_music: dict[str, Any] | None = None,
                 background_volume: float = .2,
                 background_fade_in: float = 2,
                 background_fade_out: float = 2) -> bool:
    key = settings.get("azure_speech_key")
    if not key:
        make_demo_wav(output.with_suffix(".wav"))
        return False
    region = settings.get("azure_speech_region", "eastus")
    fmt = settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")
    ssml = speech_ssml(text, voice, rate, background_music, background_volume,
                       background_fade_in, background_fade_out)
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    log_request("配音生成", url, {"voice": voice, "rate": rate, "format": fmt, "text": text,
                                  "background_music": background_music, "background_volume": background_volume,
                                  "background_fade_in": background_fade_in, "background_fade_out": background_fade_out})
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": fmt, "User-Agent": "StoryForge"},
            content=ssml.encode("utf-8"),
        )
        response.raise_for_status()
        output.write_bytes(response.content)
    return True


def audio_extension(output_format: str) -> str:
    if output_format.startswith("amr-"): return ".amr"
    if output_format.startswith("ogg-"): return ".ogg"
    if output_format.startswith("webm-"): return ".webm"
    if "mp3" in output_format: return ".mp3"
    if "opus" in output_format: return ".opus"
    if output_format.startswith("raw-"): return ".pcm"
    if output_format.startswith("g722-"): return ".g722"
    return ".audio"


async def download_background_music(music: dict[str, Any], output_dir: Path) -> Path:
    suffix = Path(urlparse(music["url"]).path).suffix.lower()
    if suffix not in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm"):
        suffix = ".audio"
    target = output_dir / f"background{suffix}"
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(music["url"])
        response.raise_for_status()
    target.write_bytes(response.content)
    return target


def probe_audio_duration(path: Path) -> float | None:
    ffprobe = os.getenv("FFPROBE_PATH", "ffprobe")
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                                capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def video_command(ffmpeg: str, cover: Path, narration: Path, output: Path,
                  music: Path | None = None, volume: float = .2,
                  fade_in: float = 2, fade_out: float = 2,
                  duration: float | None = None) -> list[str]:
    command = [ffmpeg, "-y", "-loop", "1", "-i", str(cover), "-i", str(narration)]
    if music:
        command += ["-stream_loop", "-1", "-i", str(music)]
        music_filters = [f"volume={max(0, min(1, volume)):.2f}"]
        if fade_in > 0:
            music_filters.append(f"afade=t=in:st=0:d={fade_in:g}")
        if fade_out > 0 and duration:
            music_filters.append(f"afade=t=out:st={max(0, duration - fade_out):g}:d={min(fade_out, duration):g}")
        command += ["-filter_complex", f"[2:a]{','.join(music_filters)}[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v", "-map", "[aout]"]
    command += ["-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p", "-shortest", "-vf", "scale=720:1280,format=yuv420p", str(output)]
    return command


async def process_workflow(wid: str) -> None:
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row: return
        item = workflow_row(row); settings = get_settings()
        output_dir = workflow_media_dir(item["output_dir"])
        output_dir.mkdir(parents=False, exist_ok=True)
        title, author = item["book_title"], item["author"]
        save_workflow(wid, status="running", step=1, progress=8)
        await asyncio.sleep(.4)
        description = await llm([
            {"role": "system", "content": "你是严谨的中文图书编辑。只输出100字左右的书籍简介，不虚构具体事实。"},
            {"role": "user", "content": f"书名：{title}；作者：{author or '未知'}；版本：{item['edition'] or '未指定'}"},
        ], settings)
        if wid in DELETING_WORKFLOWS: return
        description = description or f"《{title}》是一部值得慢下来阅读的作品。它从人与世界的关系出发，在细节与思考之间，带领读者重新理解选择、成长与生活的意义。"
        save_workflow(wid, step=2, progress=24, payload_update={"description": description})

        prompts = [p for p in item.get("writing_prompts", []) if p.get("enabled")]
        if not prompts: prompts = [{"text": "适合短视频口播，真诚、有洞见", "enabled": True}]
        originals, polished = [], []
        for i, prompt in enumerate(prompts):
            if wid in DELETING_WORKFLOWS: return
            raw = await llm([
                {"role": "system", "content": "你是专业读书博主。写一篇500字以内、事实谨慎、适合口播的中文分享稿。"},
                {"role": "user", "content": f"书名：{title}\n作者：{author}\n简介：{description}\n额外要求：{prompt['text']}"},
            ], settings)
            raw = raw or demo_copy(title, author, prompt["text"], i)
            originals.append({"id": f"draft-{i+1}", "prompt": prompt["text"], "text": raw})
            improved = await llm([
                {"role": "system", "content": "按 Humanizer-zh 的目标优化中文：去除AI腔、空泛排比和过度总结，保留事实和观点，口语自然。只输出优化稿。"},
                {"role": "user", "content": raw},
            ], settings)
            if wid in DELETING_WORKFLOWS: return
            polished.append({"id": f"draft-{i+1}", "prompt": prompt["text"], "text": improved or raw.replace("真正动人的地方", "我最喜欢的是")})
        save_workflow(wid, step=3, progress=45, payload_update={"original_drafts": originals, "polished_drafts": polished})

        voices = item.get("voices") or settings.get("voices") or ["zh-CN-XiaoxiaoNeural"]
        speech_rate = item.get("speech_rate", settings.get("speech_rate", 0))
        background_music = item.get("background_music")
        audio_items = []
        for di, draft in enumerate(polished):
            for vi, voice in enumerate(voices):
                if wid in DELETING_WORKFLOWS: return
                base = output_dir / f"draft-{di+1}-voice-{vi+1}"
                target = base.with_suffix(audio_extension(settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")))
                used_real_speech = await speech(
                    draft["text"], voice, speech_rate, settings, target,
                    background_music,
                    item.get("background_music_volume", .2),
                    item.get("background_music_fade_in", 2),
                    item.get("background_music_fade_out", 2),
                )
                if wid in DELETING_WORKFLOWS: return
                actual = target if target.exists() else base.with_suffix(".wav")
                audio_items.append({"draft_id": draft["id"], "voice": voice, "speech_rate": speech_rate, "url": f"/media/{item['output_dir']}/{actual.name}", "provider": "azure" if used_real_speech else "demo"})
        save_workflow(wid, step=4, progress=65, payload_update={"audio": audio_items})

        cover_prompts = [p for p in item.get("cover_prompts", []) if p.get("enabled")]
        if not cover_prompts: cover_prompts = [{"text": "克制、文学感、适合短视频竖版", "enabled": True, "image_sizes": DEFAULT_IMAGE_SIZES}]
        covers = []
        cover_index = 0
        for prompt in cover_prompts:
            for image_ratio in prompt.get("image_sizes") or DEFAULT_IMAGE_SIZES:
                if wid in DELETING_WORKFLOWS: return
                cover_index += 1
                path = output_dir / f"cover-{cover_index}.png"
                used_real_image, resolution = await generate_cover(path, title, author, description, prompt["text"], cover_index - 1, image_ratio, settings)
                if wid in DELETING_WORKFLOWS: return
                covers.append({"prompt_name": prompt.get("name", f"封面提示词 {cover_index}"), "prompt": prompt["text"], "image_ratio": image_ratio, "resolution": resolution, "url": f"/media/{item['output_dir']}/{path.name}", "provider": "teamorouter" if used_real_image else "local"})
        save_workflow(wid, step=5, progress=82, payload_update={"covers": covers})

        videos = []
        ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
        for i, audio in enumerate(audio_items):
            if wid in DELETING_WORKFLOWS: return
            cover = output_dir / Path(covers[i % len(covers)]["url"]).name
            audio_path = output_dir / Path(audio["url"]).name
            out = output_dir / f"video-{i+1}.mp4"
            cmd = video_command(ffmpeg, cover, audio_path, out)
            result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=180)
            if result.returncode == 0:
                videos.append({"draft_id": audio["draft_id"], "voice": audio["voice"], "url": f"/media/{item['output_dir']}/{out.name}",
                               "background_music": background_music.get("name") if background_music else ""})
        save_workflow(wid, status="completed", step=6, progress=100, payload_update={"videos": videos})
    except Exception as exc:
        save_workflow(wid, status="failed", payload_update={"error": str(exc)[:500]})
    finally:
        if wid in DELETING_WORKFLOWS:
            cleanup_workflow_media(wid, DELETING_WORKFLOW_DIRS.pop(wid, None))
            DELETING_WORKFLOWS.discard(wid)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "StoryForge AI"}


@app.get("/api/request-logs")
def request_logs(request_type: str = "", start_time: int | None = None, end_time: int | None = None,
                 page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    conditions, params = [], []
    if request_type:
        conditions.append("request_type=?"); params.append(request_type)
    if start_time is not None:
        conditions.append("created_at>=?"); params.append(start_time)
    if end_time is not None:
        conditions.append("created_at<=?"); params.append(end_time)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM request_logs{where}", params).fetchone()["count"]
        rows = conn.execute(
            f"SELECT * FROM request_logs{where} ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    items = [{**dict(row), "request_params": json.loads(row["request_params"])} for row in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.delete("/api/request-logs")
def request_logs_clear():
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM request_logs").fetchone()["count"]
        conn.execute("DELETE FROM request_logs")
    return {"deleted": count}


@app.get("/api/settings")
def settings_get():
    return public_settings(get_settings())


@app.put("/api/settings")
def settings_put(value: SettingsPayload):
    current = get_settings(); incoming = value.model_dump()
    for key in ("api_key", "azure_speech_key"):
        if incoming[key] == "••••••••": incoming[key] = current.get(key, "")
    with db() as conn:
        conn.execute("INSERT INTO settings(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                     (json.dumps(incoming, ensure_ascii=False),))
    return public_settings(incoming)


@app.get("/api/models")
async def models():
    settings = get_settings()
    if not settings.get("api_key"): return {"models": [settings["model"]], "demo": True}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(settings["api_base"].rstrip("/") + "/models",
                                    headers={"Authorization": f"Bearer {settings['api_key']}"})
        response.raise_for_status()
    return {"models": [m["id"] for m in response.json().get("data", [])], "demo": False}


async def fetch_voice_items(settings: dict[str, Any]) -> tuple[list[dict[str, str]], bool]:
    key = settings.get("azure_speech_key")
    if not key:
        names = ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-XiaoyiNeural"]
        return ([{"short_name": name, "locale": "zh-CN", "local_name": name, "display_name": name, "gender": ""} for name in names], True)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"https://{settings['azure_speech_region']}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                                    headers={"Ocp-Apim-Subscription-Key": key})
        response.raise_for_status()
    items = [{"short_name": v["ShortName"], "locale": v.get("Locale", ""), "local_name": v.get("LocalName", ""),
              "display_name": v.get("DisplayName", ""), "gender": v.get("Gender", "")} for v in response.json() if v.get("ShortName")]
    return items, False


@app.get("/api/voices")
async def voices():
    items, demo = await fetch_voice_items(get_settings())
    return {"voices": [item["short_name"] for item in items], "items": items, "demo": demo}


def voice_locale(voice: str) -> str:
    parts = voice.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else "zh-CN"


def load_voice_translations() -> dict[str, str]:
    try:
        return json.loads(VOICE_TRANSLATIONS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


async def localized_voice_sample_text(locale: str, settings: dict[str, Any]) -> str:
    locale = locale.strip() or "zh-CN"
    if locale.lower().startswith(("zh-", "yue-", "wuu-")):
        return VOICE_SAMPLE_TEXT
    cache_key = f"{locale}|{VOICE_SAMPLE_TEXT}"
    async with VOICE_TRANSLATION_LOCK:
        translations = load_voice_translations()
        if translations.get(cache_key):
            return translations[cache_key]
        translated = await llm([
            {"role": "system", "content": "你是专业本地化译者。只输出译文，不要引号、说明或额外内容。"},
            {"role": "user", "content": f"将下面试听文案翻译成 {locale} 地区自然、口语化的表达：\n{VOICE_SAMPLE_TEXT}"},
        ], settings)
        if not translated:
            return VOICE_SAMPLE_TEXT
        translated = translated.strip().strip('"“”')
        translations[cache_key] = translated
        VOICE_TRANSLATIONS_PATH.write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding="utf-8")
        return translated


def voice_sample_path(voice: str, speech_rate: int = 0, sample_text: str = VOICE_SAMPLE_TEXT) -> Path:
    cache_key = f"{voice}|{speech_rate}|{sample_text}"
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:20]
    return VOICE_SAMPLES / f"{digest}.mp3"


async def ensure_voice_sample(voice: str, settings: dict[str, Any], locale: str = "") -> Path:
    speech_rate = settings.get("speech_rate", 0)
    sample_text = await localized_voice_sample_text(locale or voice_locale(voice), settings)
    target = voice_sample_path(voice, speech_rate, sample_text)
    if target.exists() and target.stat().st_size > 0:
        return target
    preview_settings = {**settings, "voice_format": "audio-24khz-96kbitrate-mono-mp3"}
    if not await speech(sample_text, voice, speech_rate, preview_settings, target):
        raise HTTPException(503, "请先配置微软语音服务密钥")
    return target


@app.get("/api/voices/{voice}/preview")
async def voice_preview(voice: str, locale: str = ""):
    target = await ensure_voice_sample(voice, get_settings(), locale)
    return FileResponse(target, media_type="audio/mpeg")


async def download_all_voice_samples() -> None:
    settings = get_settings()
    items, _ = await fetch_voice_items(settings)
    VOICE_DOWNLOAD_STATUS.update(status="running", total=len(items), completed=0, failed=0)
    for item in items:
        try:
            await ensure_voice_sample(item["short_name"], settings, item.get("locale", ""))
            VOICE_DOWNLOAD_STATUS["completed"] += 1
        except Exception:
            VOICE_DOWNLOAD_STATUS["failed"] += 1
    VOICE_DOWNLOAD_STATUS["status"] = "completed"


@app.post("/api/voices/download-all", status_code=202)
def voices_download_all(tasks: BackgroundTasks):
    if VOICE_DOWNLOAD_STATUS["status"] in ("queued", "running"):
        return VOICE_DOWNLOAD_STATUS
    if not get_settings().get("azure_speech_key"):
        raise HTTPException(400, "请先配置微软语音服务密钥")
    VOICE_DOWNLOAD_STATUS.update(status="queued", total=0, completed=0, failed=0)
    tasks.add_task(download_all_voice_samples)
    return VOICE_DOWNLOAD_STATUS


@app.get("/api/voices/download-all/status")
def voices_download_status():
    return VOICE_DOWNLOAD_STATUS


@app.get("/api/background-music")
def background_music_list(q: str = "", page: int = Query(1, ge=1), page_size: int = Query(8, ge=1, le=50)):
    where, params = "", []
    if q.strip():
        where = " WHERE name LIKE ? OR category LIKE ?"
        needle = f"%{q.strip()}%"; params = [needle, needle]
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM background_music{where}", params).fetchone()["count"]
        rows = conn.execute(f"SELECT * FROM background_music{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                            (*params, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@app.post("/api/background-music", status_code=201)
def background_music_create(value: BackgroundMusicCreate):
    music_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO background_music(id,name,url,category,created_at) VALUES(?,?,?,?,?)",
                     (music_id, value.name.strip(), value.url, value.category.strip(), now))
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return dict(row)


@app.put("/api/background-music/{music_id}")
def background_music_update(music_id: str, value: BackgroundMusicCreate):
    with db() as conn:
        result = conn.execute("UPDATE background_music SET name=?,url=?,category=? WHERE id=?",
                              (value.name.strip(), value.url, value.category.strip(), music_id))
        if result.rowcount == 0:
            raise HTTPException(404, "背景音乐不存在")
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return dict(row)


@app.delete("/api/background-music/{music_id}", status_code=204)
def background_music_delete(music_id: str):
    with db() as conn:
        result = conn.execute("DELETE FROM background_music WHERE id=?", (music_id,))
        if result.rowcount == 0:
            raise HTTPException(404, "背景音乐不存在")


@app.get("/api/prompts")
def prompts_list(kind: str | None = None):
    if kind and kind not in ("writing", "cover"):
        raise HTTPException(400, "提示词类型无效")
    query = "SELECT * FROM prompt_templates"
    params: tuple[Any, ...] = ()
    if kind:
        query += " WHERE kind=?"; params = (kind,)
    query += " ORDER BY created_at, name"
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [prompt_template_row(row) for row in rows]


@app.post("/api/prompts", status_code=201)
def prompt_create(value: PromptTemplateCreate):
    prompt_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO prompt_templates(id,kind,name,text,created_at,updated_at,image_sizes) VALUES(?,?,?,?,?,?,?)",
                     (prompt_id, value.kind, value.name.strip(), value.text.strip(), now, now, json.dumps(value.image_sizes)))
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return prompt_template_row(row)


@app.put("/api/prompts/{prompt_id}")
def prompt_update(prompt_id: str, value: PromptTemplateUpdate):
    with db() as conn:
        result = conn.execute("UPDATE prompt_templates SET name=?,text=?,image_sizes=?,updated_at=? WHERE id=?",
                              (value.name.strip(), value.text.strip(), json.dumps(value.image_sizes), int(time.time()), prompt_id))
        if result.rowcount == 0: raise HTTPException(404, "提示词不存在")
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return prompt_template_row(row)


@app.delete("/api/prompts/{prompt_id}", status_code=204)
def prompt_delete(prompt_id: str):
    with db() as conn:
        result = conn.execute("DELETE FROM prompt_templates WHERE id=?", (prompt_id,))
        if result.rowcount == 0: raise HTTPException(404, "提示词不存在")


@app.get("/api/workflows")
def workflows_list():
    with db() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
    return [workflow_row(r) for r in rows]


@app.get("/api/workflows/{wid}")
def workflow_get(wid: str):
    with db() as conn: row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row: raise HTTPException(404, "工作流不存在")
    return workflow_row(row)


@app.delete("/api/workflows/{wid}")
def workflow_delete(wid: str):
    with db() as conn:
        row = conn.execute("SELECT status,payload FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row: raise HTTPException(404, "工作流不存在")
        output_dir = json.loads(row["payload"]).get("output_dir")
        if row["status"] in ("queued", "running"):
            DELETING_WORKFLOWS.add(wid)
            if output_dir:
                DELETING_WORKFLOW_DIRS[wid] = output_dir
        removed_files = cleanup_workflow_media(wid, output_dir)
        conn.execute("DELETE FROM workflows WHERE id=?", (wid,))
    return {"deleted": True, "removed_files": removed_files}


def create_workflow_record(book: BookCreate, options: WorkflowOptions) -> str:
    wid, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        writing_ids = options.writing_prompt_ids
        cover_ids = options.cover_prompt_ids
        writing_rows = conn.execute(
            f"SELECT id,name,text,image_sizes FROM prompt_templates WHERE kind='writing' AND id IN ({','.join('?' for _ in writing_ids)})" if writing_ids else
            "SELECT id,name,text,image_sizes FROM prompt_templates WHERE kind='writing' ORDER BY created_at LIMIT 1", writing_ids
        ).fetchall()
        cover_rows = conn.execute(
            f"SELECT id,name,text,image_sizes FROM prompt_templates WHERE kind='cover' AND id IN ({','.join('?' for _ in cover_ids)})" if cover_ids else
            "SELECT id,name,text,image_sizes FROM prompt_templates WHERE kind='cover' ORDER BY created_at LIMIT 1", cover_ids
        ).fetchall()
        music_row = conn.execute("SELECT id,name,url,category FROM background_music WHERE id=?", (options.background_music_id,)).fetchone() if options.background_music_id else None
        if options.background_music_id and not music_row:
            raise HTTPException(422, "选择的背景音乐不存在")
    output_dir, _ = create_workflow_media_dir()
    payload = {"output_dir": output_dir,
               "writing_prompts": [{"id": r["id"], "name": r["name"], "text": r["text"], "enabled": True} for r in writing_rows],
               "cover_prompts": [{"id": r["id"], "name": r["name"], "text": r["text"], "image_sizes": json.loads(r["image_sizes"]), "enabled": True} for r in cover_rows],
               "voices": [options.voice], "speech_rate": options.speech_rate,
               "background_music": dict(music_row) if music_row else None,
               "background_music_volume": options.background_music_volume,
               "background_music_fade_in": options.background_music_fade_in,
               "background_music_fade_out": options.background_music_fade_out,
               "description": "", "original_drafts": [], "polished_drafts": [], "covers": [], "audio": [], "videos": []}
    with db() as conn:
        conn.execute("INSERT INTO workflows VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (wid, book.book_title, book.author, book.edition, "queued", 0, 0, now, now, json.dumps(payload, ensure_ascii=False)))
    return wid


@app.post("/api/workflows", status_code=202)
def workflow_create(value: WorkflowCreate, tasks: BackgroundTasks):
    book = BookCreate(book_title=value.book_title, author=value.author, edition=value.edition)
    wid = create_workflow_record(book, value)
    tasks.add_task(process_workflow, wid)
    return {"id": wid, "status": "queued"}


async def process_workflows_parallel(workflow_ids: list[str]) -> None:
    await asyncio.gather(*(process_workflow(wid) for wid in workflow_ids))


@app.post("/api/workflows/batch", status_code=202)
def workflows_batch_create(value: BatchWorkflowCreate, tasks: BackgroundTasks):
    workflows = []
    for book in value.books:
        wid = create_workflow_record(book, value)
        workflows.append({"id": wid, "book_title": book.book_title, "status": "queued"})
    tasks.add_task(process_workflows_parallel, [workflow["id"] for workflow in workflows])
    return {"count": len(workflows), "workflows": workflows}


@app.post("/api/workflows/{wid}/retry", status_code=202)
def workflow_retry(wid: str, tasks: BackgroundTasks):
    with db() as conn: row = conn.execute("SELECT id FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row: raise HTTPException(404, "工作流不存在")
    save_workflow(wid, status="queued", step=0, progress=0, payload_update={"error": ""})
    tasks.add_task(process_workflow, wid)
    return {"id": wid, "status": "queued"}
