from __future__ import annotations

import asyncio
import base64
import html
import io
import json
import math
import os
import sqlite3
import subprocess
import time
import uuid
import wave
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MEDIA = DATA / "media"
DB_PATH = DATA / "storyforge.db"
DATA.mkdir(exist_ok=True)
MEDIA.mkdir(exist_ok=True)


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
            """
        )


DEFAULT_SETTINGS = {
    "api_base": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "",
    "azure_speech_key": "",
    "azure_speech_region": "eastus",
    "voice_format": "audio-24khz-48kbitrate-mono-mp3",
    "voices": ["zh-CN-XiaoxiaoNeural"],
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


class PromptItem(BaseModel):
    text: str
    enabled: bool = True


class WorkflowCreate(BaseModel):
    book_title: str = Field(min_length=1, max_length=160)
    author: str = Field(default="", max_length=120)
    edition: str = Field(default="", max_length=120)
    writing_prompts: list[PromptItem] = Field(default_factory=list)
    cover_prompts: list[PromptItem] = Field(default_factory=list)


class SettingsPayload(BaseModel):
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"
    voice_format: str = "audio-24khz-48kbitrate-mono-mp3"
    voices: list[str] = ["zh-CN-XiaoxiaoNeural"]


def get_settings() -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT payload FROM settings WHERE id=1").fetchone()
    result = DEFAULT_SETTINGS | (json.loads(row["payload"]) if row else {})
    result["api_key"] = result.get("api_key") or os.getenv("MODEL_API_KEY", "")
    result["azure_speech_key"] = result.get("azure_speech_key") or os.getenv("AZURE_SPEECH_KEY", "")
    return result


def public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    result = dict(settings)
    result["api_key"] = "••••••••" if result.get("api_key") else ""
    result["azure_speech_key"] = "••••••••" if result.get("azure_speech_key") else ""
    return result


def workflow_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload"])
    return {
        "id": row["id"], "book_title": row["book_title"], "author": row["author"],
        "edition": row["edition"], "status": row["status"], "step": row["step"],
        "progress": row["progress"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], **payload,
    }


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


async def llm(messages: list[dict[str, str]], settings: dict[str, Any]) -> str | None:
    if not settings.get("api_key"):
        return None
    url = settings["api_base"].rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
            json={"model": settings["model"], "messages": messages, "temperature": 0.75},
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
                         prompt: str, index: int, settings: dict[str, Any]) -> None:
    """Use an OpenAI-compatible image endpoint when available, with a local fallback."""
    if settings.get("api_key"):
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
                response = await client.post(
                    settings["api_base"].rstrip("/") + "/images/generations",
                    headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
                    json={"model": "gpt-image-1", "size": "1024x1536", "n": 1,
                          "prompt": f"为《{title}》创作无文字的竖版书籍分享封面。作者：{author}。简介：{description}。视觉要求：{prompt}"},
                )
                response.raise_for_status()
                data = response.json()["data"][0]
                raw = base64.b64decode(data["b64_json"]) if data.get("b64_json") else (await client.get(data["url"])).content
                with Image.open(io.BytesIO(raw)) as generated:
                    generated.convert("RGB").resize((1080, 1440)).save(path, "PNG")
                return
        except Exception:
            pass
    make_cover(path, title, author, index)


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


async def speech(text: str, voice: str, settings: dict[str, Any], output: Path) -> None:
    key = settings.get("azure_speech_key")
    if not key:
        make_demo_wav(output.with_suffix(".wav"))
        return
    region = settings.get("azure_speech_region", "eastus")
    fmt = settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")
    ssml = f'<speak version="1.0" xml:lang="zh-CN"><voice name="{html.escape(voice, quote=True)}">{html.escape(text)}</voice></speak>'
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": fmt, "User-Agent": "StoryForge"},
            content=ssml.encode("utf-8"),
        )
        response.raise_for_status()
        output.write_bytes(response.content)


async def process_workflow(wid: str) -> None:
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row: return
        item = workflow_row(row); settings = get_settings()
        title, author = item["book_title"], item["author"]
        save_workflow(wid, status="running", step=1, progress=8)
        await asyncio.sleep(.4)
        description = await llm([
            {"role": "system", "content": "你是严谨的中文图书编辑。只输出100字左右的书籍简介，不虚构具体事实。"},
            {"role": "user", "content": f"书名：{title}；作者：{author or '未知'}；版本：{item['edition'] or '未指定'}"},
        ], settings)
        description = description or f"《{title}》是一部值得慢下来阅读的作品。它从人与世界的关系出发，在细节与思考之间，带领读者重新理解选择、成长与生活的意义。"
        save_workflow(wid, step=2, progress=24, payload_update={"description": description})

        prompts = [p for p in item.get("writing_prompts", []) if p.get("enabled")]
        if not prompts: prompts = [{"text": "适合短视频口播，真诚、有洞见", "enabled": True}]
        originals, polished = [], []
        for i, prompt in enumerate(prompts):
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
            polished.append({"id": f"draft-{i+1}", "prompt": prompt["text"], "text": improved or raw.replace("真正动人的地方", "我最喜欢的是")})
        save_workflow(wid, step=3, progress=45, payload_update={"original_drafts": originals, "polished_drafts": polished})

        voices = settings.get("voices") or ["zh-CN-XiaoxiaoNeural"]
        audio_items = []
        for di, draft in enumerate(polished):
            for vi, voice in enumerate(voices):
                base = MEDIA / f"{wid}-d{di+1}-v{vi+1}"
                await speech(draft["text"], voice, settings, base.with_suffix(".mp3"))
                actual = base.with_suffix(".mp3") if base.with_suffix(".mp3").exists() else base.with_suffix(".wav")
                audio_items.append({"draft_id": draft["id"], "voice": voice, "url": f"/media/{actual.name}"})
        save_workflow(wid, step=4, progress=65, payload_update={"audio": audio_items})

        cover_prompts = [p for p in item.get("cover_prompts", []) if p.get("enabled")]
        if not cover_prompts: cover_prompts = [{"text": "克制、文学感、适合短视频竖版", "enabled": True}]
        covers = []
        for i, prompt in enumerate(cover_prompts):
            path = MEDIA / f"{wid}-cover-{i+1}.png"
            await generate_cover(path, title, author, description, prompt["text"], i, settings)
            covers.append({"prompt": prompt["text"], "url": f"/media/{path.name}"})
        save_workflow(wid, step=5, progress=82, payload_update={"covers": covers})

        videos = []
        ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
        for i, audio in enumerate(audio_items):
            cover = MEDIA / Path(covers[i % len(covers)]["url"]).name
            audio_path = MEDIA / Path(audio["url"]).name
            out = MEDIA / f"{wid}-video-{i+1}.mp4"
            cmd = [ffmpeg, "-y", "-loop", "1", "-i", str(cover), "-i", str(audio_path),
                   "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k",
                   "-pix_fmt", "yuv420p", "-shortest", "-vf", "scale=720:1280,format=yuv420p", str(out)]
            result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=180)
            if result.returncode == 0:
                videos.append({"draft_id": audio["draft_id"], "voice": audio["voice"], "url": f"/media/{out.name}"})
        save_workflow(wid, status="completed", step=6, progress=100, payload_update={"videos": videos})
    except Exception as exc:
        save_workflow(wid, status="failed", payload_update={"error": str(exc)[:500]})


@app.get("/api/health")
def health():
    return {"ok": True, "service": "StoryForge AI"}


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


@app.get("/api/voices")
async def voices():
    settings = get_settings(); key = settings.get("azure_speech_key")
    if not key:
        return {"voices": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-XiaoyiNeural"], "demo": True}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"https://{settings['azure_speech_region']}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                                    headers={"Ocp-Apim-Subscription-Key": key})
        response.raise_for_status()
    return {"voices": [v["ShortName"] for v in response.json() if v.get("Locale", "").startswith("zh-")], "demo": False}


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


@app.post("/api/workflows", status_code=202)
def workflow_create(value: WorkflowCreate, tasks: BackgroundTasks):
    wid, now = uuid.uuid4().hex[:12], int(time.time())
    payload = {"writing_prompts": [p.model_dump() for p in value.writing_prompts],
               "cover_prompts": [p.model_dump() for p in value.cover_prompts],
               "description": "", "original_drafts": [], "polished_drafts": [], "covers": [], "audio": [], "videos": []}
    with db() as conn:
        conn.execute("INSERT INTO workflows VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (wid, value.book_title, value.author, value.edition, "queued", 0, 0, now, now, json.dumps(payload, ensure_ascii=False)))
    tasks.add_task(process_workflow, wid)
    return {"id": wid, "status": "queued"}


@app.post("/api/workflows/{wid}/retry", status_code=202)
def workflow_retry(wid: str, tasks: BackgroundTasks):
    with db() as conn: row = conn.execute("SELECT id FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row: raise HTTPException(404, "工作流不存在")
    save_workflow(wid, status="queued", step=0, progress=0, payload_update={"error": ""})
    tasks.add_task(process_workflow, wid)
    return {"id": wid, "status": "queued"}
