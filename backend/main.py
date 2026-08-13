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
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
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
            CREATE TABLE IF NOT EXISTS prompt_templates (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('writing','cover')),
              name TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_prompt_templates_kind ON prompt_templates(kind);
            """
        )
        count = conn.execute("SELECT COUNT(*) AS count FROM prompt_templates").fetchone()["count"]
        if count == 0:
            now = int(time.time())
            defaults = [
                ("writing-short-video", "writing", "短视频口播", "适合 2 分钟短视频口播，有真实阅读感受", now, now),
                ("writing-insight", "writing", "反常识洞见", "从一个反常识观点切入，避免剧透，结尾给出阅读建议", now, now),
                ("cover-literary", "cover", "文学质感", "克制的文学感，竖版构图，无文字，为标题留出空间", now, now),
            ]
            conn.executemany("INSERT INTO prompt_templates VALUES(?,?,?,?,?,?)", defaults)
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
DELETING_WORKFLOWS: set[str] = set()


class PromptItem(BaseModel):
    text: str
    enabled: bool = True


class WorkflowCreate(BaseModel):
    book_title: str = Field(min_length=1, max_length=160)
    author: str = Field(default="", max_length=120)
    edition: str = Field(default="", max_length=120)
    writing_prompt_ids: list[str] = Field(default_factory=list)
    cover_prompt_ids: list[str] = Field(default_factory=list)
    voice: str = Field(default="zh-CN-XiaoxiaoNeural", min_length=1, max_length=120)
    speech_rate: int = Field(default=0, ge=-50, le=100)


MAX_PROMPT_LENGTH = 100_000


class PromptTemplateCreate(BaseModel):
    kind: str = Field(pattern="^(writing|cover)$")
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)


class PromptTemplateUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)


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


def cleanup_workflow_media(wid: str) -> int:
    media_root = MEDIA.resolve()
    removed = 0
    for candidate in MEDIA.iterdir():
        resolved = candidate.resolve()
        if candidate.is_file() and resolved.parent == media_root and candidate.name.startswith(f"{wid}-"):
            candidate.unlink()
            removed += 1
    return removed


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
                         prompt: str, index: int, settings: dict[str, Any]) -> bool:
    """Use an OpenAI-compatible image endpoint when available, with a local fallback."""
    if settings.get("api_key"):
        try:
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                response = await client.post(
                    settings["api_base"].rstrip("/") + "/images/generations",
                    headers={"Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json"},
                    json={"model": settings.get("image_model", "gpt-image-2"), "size": "1024x1536", "n": 1,
                          "prompt": f"为《{title}》创作无文字的竖版书籍分享封面。作者：{author}。简介：{description}。视觉要求：{prompt}"},
                )
                response.raise_for_status()
                data = response.json()["data"][0]
                raw = base64.b64decode(data["b64_json"]) if data.get("b64_json") else (await client.get(data["url"])).content
                with Image.open(io.BytesIO(raw)) as generated:
                    generated.convert("RGB").resize((1080, 1440)).save(path, "PNG")
                return True
        except Exception:
            pass
    make_cover(path, title, author, index)
    return False


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


def speech_ssml(text: str, voice: str, rate: int) -> str:
    safe_rate = max(-50, min(100, int(rate)))
    return (f'<speak version="1.0" xml:lang="zh-CN"><voice name="{html.escape(voice, quote=True)}">'
            f'<prosody rate="{safe_rate:+d}%">{html.escape(text)}</prosody></voice></speak>')


async def speech(text: str, voice: str, rate: int, settings: dict[str, Any], output: Path) -> bool:
    key = settings.get("azure_speech_key")
    if not key:
        make_demo_wav(output.with_suffix(".wav"))
        return False
    region = settings.get("azure_speech_region", "eastus")
    fmt = settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")
    ssml = speech_ssml(text, voice, rate)
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
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
        audio_items = []
        for di, draft in enumerate(polished):
            for vi, voice in enumerate(voices):
                if wid in DELETING_WORKFLOWS: return
                base = MEDIA / f"{wid}-d{di+1}-v{vi+1}"
                target = base.with_suffix(audio_extension(settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")))
                used_real_speech = await speech(draft["text"], voice, speech_rate, settings, target)
                if wid in DELETING_WORKFLOWS: return
                actual = target if target.exists() else base.with_suffix(".wav")
                audio_items.append({"draft_id": draft["id"], "voice": voice, "speech_rate": speech_rate, "url": f"/media/{actual.name}", "provider": "azure" if used_real_speech else "demo"})
        save_workflow(wid, step=4, progress=65, payload_update={"audio": audio_items})

        cover_prompts = [p for p in item.get("cover_prompts", []) if p.get("enabled")]
        if not cover_prompts: cover_prompts = [{"text": "克制、文学感、适合短视频竖版", "enabled": True}]
        covers = []
        for i, prompt in enumerate(cover_prompts):
            if wid in DELETING_WORKFLOWS: return
            path = MEDIA / f"{wid}-cover-{i+1}.png"
            used_real_image = await generate_cover(path, title, author, description, prompt["text"], i, settings)
            if wid in DELETING_WORKFLOWS: return
            covers.append({"prompt_name": prompt.get("name", f"封面提示词 {i + 1}"), "prompt": prompt["text"], "url": f"/media/{path.name}", "provider": "teamorouter" if used_real_image else "local"})
        save_workflow(wid, step=5, progress=82, payload_update={"covers": covers})

        videos = []
        ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
        for i, audio in enumerate(audio_items):
            if wid in DELETING_WORKFLOWS: return
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
    finally:
        if wid in DELETING_WORKFLOWS:
            cleanup_workflow_media(wid)
            DELETING_WORKFLOWS.discard(wid)


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
    return [dict(row) for row in rows]


@app.post("/api/prompts", status_code=201)
def prompt_create(value: PromptTemplateCreate):
    prompt_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO prompt_templates VALUES(?,?,?,?,?,?)",
                     (prompt_id, value.kind, value.name.strip(), value.text.strip(), now, now))
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return dict(row)


@app.put("/api/prompts/{prompt_id}")
def prompt_update(prompt_id: str, value: PromptTemplateUpdate):
    with db() as conn:
        result = conn.execute("UPDATE prompt_templates SET name=?,text=?,updated_at=? WHERE id=?",
                              (value.name.strip(), value.text.strip(), int(time.time()), prompt_id))
        if result.rowcount == 0: raise HTTPException(404, "提示词不存在")
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return dict(row)


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
        row = conn.execute("SELECT status FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row: raise HTTPException(404, "工作流不存在")
        if row["status"] in ("queued", "running"):
            DELETING_WORKFLOWS.add(wid)
        removed_files = cleanup_workflow_media(wid)
        conn.execute("DELETE FROM workflows WHERE id=?", (wid,))
    return {"deleted": True, "removed_files": removed_files}


@app.post("/api/workflows", status_code=202)
def workflow_create(value: WorkflowCreate, tasks: BackgroundTasks):
    wid, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        writing_ids = value.writing_prompt_ids
        cover_ids = value.cover_prompt_ids
        writing_rows = conn.execute(
            f"SELECT id,name,text FROM prompt_templates WHERE kind='writing' AND id IN ({','.join('?' for _ in writing_ids)})" if writing_ids else
            "SELECT id,name,text FROM prompt_templates WHERE kind='writing' ORDER BY created_at LIMIT 1", writing_ids
        ).fetchall()
        cover_rows = conn.execute(
            f"SELECT id,name,text FROM prompt_templates WHERE kind='cover' AND id IN ({','.join('?' for _ in cover_ids)})" if cover_ids else
            "SELECT id,name,text FROM prompt_templates WHERE kind='cover' ORDER BY created_at LIMIT 1", cover_ids
        ).fetchall()
    payload = {"writing_prompts": [{"id": r["id"], "name": r["name"], "text": r["text"], "enabled": True} for r in writing_rows],
               "cover_prompts": [{"id": r["id"], "name": r["name"], "text": r["text"], "enabled": True} for r in cover_rows],
               "voices": [value.voice], "speech_rate": value.speech_rate,
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
