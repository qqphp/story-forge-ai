from __future__ import annotations

import asyncio
import base64
import io
import hashlib
import html
import json
import math
import os
import secrets
import subprocess
import time
import uuid
import wave
import zipfile
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from backend.modules.contracts import (
    BackgroundMusicCreate, BatchWorkflowCreate, BookCreate,
    PromptTemplateCreate, PromptTemplateUpdate, PublishTaskCreate,
    PublishTaskStatusUpdate, SettingsPayload, WorkflowCreate, WorkflowOptions,
)
from backend.modules.serializers import publish_task_row, workflow_row
from backend.core.database import connection, initialize_schema
from backend.modules.media.storage import (
    cleanup_workflow_media as cleanup_media_directory,
    create_workflow_media_dir as create_media_directory,
    workflow_media_dir as resolve_media_directory,
)
from backend.modules.workflows.content import demo_copy, generated_taxonomy
from backend.modules.prompts.service import create_template, delete_template, list_templates, update_template
from backend.modules.media.music import create_music, delete_music, list_music, update_music
from backend.modules.request_logs.service import clear_logs, list_logs, record_log
from backend.modules.settings.service import load_settings, save_settings, to_public
from backend.modules.publishing.service import create_task, delete_task, list_tasks
from backend.integrations.chat import complete_chat

ROOT = Path(__file__).resolve().parent.parent
PUBLISH_PLATFORMS = ("douyin", "kuaishou", "bilibili", "xiaohongshu", "baijiahao")
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
    with connection(DB_PATH) as conn:
        yield conn


def init_db() -> None:
    initialize_schema(db)


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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "https://creator.douyin.com", "https://cp.kuaishou.com", "https://member.bilibili.com", "https://creator.xiaohongshu.com", "https://baijiahao.baidu.com"],
    allow_origin_regex=r"chrome-extension://[a-p]{32}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_local_extension_private_network(request, call_next):
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


app.mount("/media", StaticFiles(directory=MEDIA), name="media")
app.mount("/voice-samples", StaticFiles(directory=VOICE_SAMPLES), name="voice-samples")
DELETING_WORKFLOWS: set[str] = set()
DELETING_WORKFLOW_DIRS: dict[str, str] = {}
VOICE_DOWNLOAD_STATUS: dict[str, Any] = {"status": "idle", "total": 0, "completed": 0, "failed": 0}
VOICE_TRANSLATION_LOCK = asyncio.Lock()
VOICE_SAMPLE_TEXT = "你好，欢迎收听这款流畅自然的AI配音。"


def get_settings() -> dict[str, Any]:
    return load_settings(db, DEFAULT_SETTINGS)


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return to_public(settings)


def extension_pairing_token() -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM application_meta WHERE key='extension_pairing_token'").fetchone()
    if not row:
        raise RuntimeError("浏览器扩展配对码尚未初始化")
    return row["value"]


def require_extension_token(value: str | None) -> None:
    if not value or not secrets.compare_digest(value, extension_pairing_token()):
        raise HTTPException(401, "浏览器扩展配对码无效")


def log_request(request_type: str, request_url: str, request_params: dict[str, Any]) -> None:
    record_log(db, request_type, request_url, request_params)


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
    return create_media_directory(MEDIA)


def workflow_media_dir(output_dir: str) -> Path:
    return resolve_media_directory(MEDIA, output_dir)


def cleanup_workflow_media(wid: str, output_dir: str | None = None) -> int:
    return cleanup_media_directory(db, MEDIA, wid, output_dir)


async def llm(messages: list[dict[str, str]], settings: dict[str, Any], request_type: str = "文稿生成") -> str | None:
    return await complete_chat(messages, settings, request_type, log_request, httpx.AsyncClient)


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

        save_workflow(wid, step=4, progress=48)
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
        save_workflow(wid, step=5, progress=64, payload_update={"audio": audio_items})

        share_text = "\n\n---\n\n".join(draft["text"] for draft in polished)
        taxonomy_raw = await llm([
            {"role": "system", "content": "你是中文内容运营编辑。根据给定书籍信息与分享稿生成内容分类。只输出严格JSON，不要Markdown：{\"tags\":[8个简短标签],\"topics\":[8个适合短视频平台的话题词]}。每项不带#，不含空格，不超过15个汉字，去重并与内容高度相关。"},
            {"role": "user", "content": f"书籍标题：{title}\n书籍简介：{description}\n分享稿：\n{share_text}"},
        ], settings, "标签话题生成")
        if wid in DELETING_WORKFLOWS: return
        tags, topics = generated_taxonomy(taxonomy_raw, title)
        save_workflow(wid, step=6, progress=74, payload_update={"tags": tags, "topics": topics})

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
        save_workflow(wid, step=7, progress=88, payload_update={"covers": covers})

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
        save_workflow(wid, status="completed", step=7, progress=100, payload_update={"videos": videos})
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
    return list_logs(db, request_type, start_time, end_time, page, page_size)


@app.delete("/api/request-logs")
def request_logs_clear():
    return {"deleted": clear_logs(db)}


@app.get("/api/settings")
def settings_get():
    return public_settings(get_settings())


@app.put("/api/settings")
def settings_put(value: SettingsPayload):
    return public_settings(save_settings(db, get_settings(), value))


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
    return list_music(db, q, page, page_size)


@app.post("/api/background-music", status_code=201)
def background_music_create(value: BackgroundMusicCreate):
    return create_music(db, value)


@app.put("/api/background-music/{music_id}")
def background_music_update(music_id: str, value: BackgroundMusicCreate):
    return update_music(db, music_id, value)


@app.delete("/api/background-music/{music_id}", status_code=204)
def background_music_delete(music_id: str):
    delete_music(db, music_id)


@app.get("/api/prompts")
def prompts_list(kind: str | None = None):
    return list_templates(db, kind)


@app.post("/api/prompts", status_code=201)
def prompt_create(value: PromptTemplateCreate):
    return create_template(db, value)


@app.put("/api/prompts/{prompt_id}")
def prompt_update(prompt_id: str, value: PromptTemplateUpdate):
    return update_template(db, prompt_id, value)


@app.delete("/api/prompts/{prompt_id}", status_code=204)
def prompt_delete(prompt_id: str):
    delete_template(db, prompt_id)


@app.get("/api/publish/pairing")
def publish_pairing():
    return {"token": extension_pairing_token(), "api_base": "http://127.0.0.1:8000"}


@app.post("/api/publish/pairing/rotate")
def publish_pairing_rotate():
    token = secrets.token_hex(16)
    with db() as conn:
        conn.execute("UPDATE application_meta SET value=? WHERE key='extension_pairing_token'", (token,))
    return {"token": token, "api_base": "http://127.0.0.1:8000"}


@app.get("/api/publish/extension/download")
def publish_extension_download():
    extension_root = ROOT / "browser-extension"
    if not extension_root.is_dir():
        raise HTTPException(404, "浏览器扩展目录不存在")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for source in extension_root.rglob("*"):
            if source.is_file() and "__pycache__" not in source.parts:
                bundle.write(source, source.relative_to(ROOT))
    archive.seek(0)
    return StreamingResponse(archive, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="storyforge-publish-assistant.zip"'})


@app.get("/api/publish/tasks")
def publish_tasks_list(platform: str = ""):
    return list_tasks(db, platform, PUBLISH_PLATFORMS)


@app.post("/api/publish/tasks", status_code=201)
def publish_task_create(value: PublishTaskCreate):
    return create_task(db, value)


@app.delete("/api/publish/tasks/{task_id}", status_code=204)
def publish_task_delete(task_id: str):
    delete_task(db, task_id)


@app.get("/api/publish/extension/tasks/next")
def publish_extension_next(platform: str = "douyin", task_id: str = "",
                           x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    if platform not in PUBLISH_PLATFORMS:
        raise HTTPException(400, "不支持该发布平台")
    with db() as conn:
        statuses = "('prepared','filling','failed','ready')" if task_id else "('prepared','filling','ready')"
        query = ("SELECT publish_tasks.*,workflows.book_title FROM publish_tasks "
                 "JOIN workflows ON workflows.id=publish_tasks.workflow_id "
                 f"WHERE platform=? AND publish_tasks.status IN {statuses}")
        params: list[Any] = [platform]
        if task_id:
            query += " AND publish_tasks.id=?"; params.append(task_id)
        query += " ORDER BY CASE WHEN publish_tasks.status='ready' THEN 1 ELSE 0 END,publish_tasks.created_at LIMIT 1"
        row = conn.execute(query, params).fetchone()
    return {"task": publish_task_row(row) if row else None}


@app.get("/api/publish/extension/tasks/{task_id}/video")
def publish_extension_video(task_id: str, x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    with db() as conn:
        row = conn.execute("SELECT video_url FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "发布任务不存在")
    prefix = "/media/"
    if not row["video_url"].startswith(prefix):
        raise HTTPException(422, "发布视频地址无效")
    target = (MEDIA / row["video_url"][len(prefix):]).resolve()
    media_root = MEDIA.resolve()
    if media_root not in target.parents or not target.is_file():
        raise HTTPException(404, "发布视频文件不存在")
    return FileResponse(target, media_type="video/mp4", filename=target.name)


@app.get("/api/publish/extension/tasks/{task_id}/cover")
def publish_extension_cover(task_id: str, x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    with db() as conn:
        row = conn.execute("SELECT cover_url FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "发布任务不存在")
    prefix = "/media/"
    if not row["cover_url"].startswith(prefix):
        raise HTTPException(422, "发布封面地址无效")
    target = (MEDIA / row["cover_url"][len(prefix):]).resolve()
    media_root = MEDIA.resolve()
    if media_root not in target.parents or not target.is_file():
        raise HTTPException(404, "发布封面文件不存在")
    return FileResponse(target, filename=target.name)


@app.get("/api/publish/extension/tasks/{task_id}/covers/{cover_index}")
def publish_extension_cover_by_index(task_id: str, cover_index: int,
                                     x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    with db() as conn:
        row = conn.execute("SELECT covers FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "发布任务不存在")
    covers = json.loads(row["covers"] or "[]")
    if cover_index < 0 or cover_index >= len(covers):
        raise HTTPException(404, "发布封面不存在")
    cover_url = covers[cover_index].get("url", "")
    prefix = "/media/"
    if not cover_url.startswith(prefix):
        raise HTTPException(422, "发布封面地址无效")
    target = (MEDIA / cover_url[len(prefix):]).resolve()
    if MEDIA.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "发布封面文件不存在")
    return FileResponse(target, filename=target.name)


@app.put("/api/publish/extension/tasks/{task_id}")
def publish_extension_update(task_id: str, value: PublishTaskStatusUpdate,
                             x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    allowed_transitions = {
        "prepared": {"filling", "failed"},
        "filling": {"ready", "failed"},
        "ready": {"completed", "failed"},
        "failed": {"filling"},
        "completed": set(),
        "cancelled": set(),
    }
    with db() as conn:
        current = conn.execute("SELECT status FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
        if not current:
            raise HTTPException(404, "发布任务不存在")
        if value.status not in allowed_transitions[current["status"]]:
            raise HTTPException(409, f"不能从 {current['status']} 切换到 {value.status}")
        conn.execute("UPDATE publish_tasks SET status=?,error=?,updated_at=? WHERE id=?",
                     (value.status, value.error.strip(), int(time.time()), task_id))
        row = conn.execute("SELECT * FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
    return publish_task_row(row)


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
               "description": "", "tags": [], "topics": [], "original_drafts": [], "polished_drafts": [], "covers": [], "audio": [], "videos": []}
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
