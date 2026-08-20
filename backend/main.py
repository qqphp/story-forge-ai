from __future__ import annotations

import asyncio
import io
import hashlib
import json
import os
import secrets
import time
import uuid
import zipfile
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
from backend.modules.prompts.service import create_template, delete_template, list_templates, update_template
from backend.modules.media.music import create_music, delete_music, list_music, update_music
from backend.modules.request_logs.service import clear_logs, list_logs, record_log
from backend.modules.settings.service import load_settings, save_settings, to_public
from backend.modules.publishing.service import create_task, delete_task, list_tasks, resolve_task_media, update_task_status
from backend.integrations.chat import complete_chat
from backend.integrations.cover import generate_cover as generate_external_cover, make_local_cover
from backend.integrations.speech import (
    audio_extension as speech_audio_extension,
    build_ssml,
    make_demo_wav as make_demo_audio,
    synthesize,
)
from backend.integrations.video import video_command as build_video_command
from backend.modules.workflows.application import create_workflow, delete_workflow, queue_retry
from backend.modules.workflows.executor import execute_workflow
from backend.modules.workflows.repository import get_workflow, list_workflows, save_workflow as persist_workflow
from backend.api.system import build_router as build_system_router

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


app.include_router(build_system_router(db, get_settings, public_settings, save_settings, list_logs, clear_logs))


def save_workflow(wid: str, **changes: Any) -> None:
    persist_workflow(db, wid, **changes)


def create_workflow_media_dir() -> tuple[str, Path]:
    return create_media_directory(MEDIA)


def workflow_media_dir(output_dir: str) -> Path:
    return resolve_media_directory(MEDIA, output_dir)


def cleanup_workflow_media(wid: str, output_dir: str | None = None) -> int:
    return cleanup_media_directory(db, MEDIA, wid, output_dir)


async def llm(messages: list[dict[str, str]], settings: dict[str, Any], request_type: str = "文稿生成") -> str | None:
    return await complete_chat(messages, settings, request_type, log_request, httpx.AsyncClient)


def make_cover(path: Path, title: str, author: str, index: int) -> None:
    make_local_cover(path, title, author, index)


async def generate_cover(path: Path, title: str, author: str, description: str,
                         prompt: str, index: int, image_ratio: str, settings: dict[str, Any]) -> tuple[bool, str]:
    return await generate_external_cover(
        path, title, author, description, prompt, index, image_ratio, settings,
        log_request, httpx.AsyncClient, make_cover,
    )


def make_demo_wav(path: Path, seconds: float = 3.0) -> None:
    make_demo_audio(path, seconds)


def speech_ssml(text: str, voice: str, rate: int,
                background_music: dict[str, Any] | None = None,
                background_volume: float = .2,
                background_fade_in: float = 2,
                background_fade_out: float = 2) -> str:
    return build_ssml(text, voice, rate, voice_locale, background_music, background_volume, background_fade_in, background_fade_out)


async def speech(text: str, voice: str, rate: int, settings: dict[str, Any], output: Path,
                 background_music: dict[str, Any] | None = None,
                 background_volume: float = .2,
                 background_fade_in: float = 2,
                 background_fade_out: float = 2) -> bool:
    return await synthesize(text, voice, rate, settings, output, speech_ssml, make_demo_wav,
                            log_request, httpx.AsyncClient, background_music, background_volume,
                            background_fade_in, background_fade_out)


def audio_extension(output_format: str) -> str:
    return speech_audio_extension(output_format)


async def process_workflow(wid: str) -> None:
    def cleanup_deleted(workflow_id: str) -> None:
        cleanup_workflow_media(workflow_id, DELETING_WORKFLOW_DIRS.pop(workflow_id, None))
        DELETING_WORKFLOWS.discard(workflow_id)

    await execute_workflow(wid, db=db, workflow_row=workflow_row, get_settings=get_settings,
                           media_dir=workflow_media_dir, save=save_workflow,
                           is_deleting=DELETING_WORKFLOWS.__contains__, cleanup_deleted=cleanup_deleted,
                           llm=llm, speech=speech, audio_extension=audio_extension,
                           generate_cover=generate_cover, video_command=build_video_command)


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
    target = resolve_task_media(db, MEDIA, task_id, "video")
    return FileResponse(target, media_type="video/mp4", filename=target.name)


@app.get("/api/publish/extension/tasks/{task_id}/cover")
def publish_extension_cover(task_id: str, x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    target = resolve_task_media(db, MEDIA, task_id, "cover")
    return FileResponse(target, filename=target.name)


@app.get("/api/publish/extension/tasks/{task_id}/covers/{cover_index}")
def publish_extension_cover_by_index(task_id: str, cover_index: int,
                                     x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    target = resolve_task_media(db, MEDIA, task_id, "cover", cover_index)
    return FileResponse(target, filename=target.name)


@app.put("/api/publish/extension/tasks/{task_id}")
def publish_extension_update(task_id: str, value: PublishTaskStatusUpdate,
                             x_storyforge_token: str | None = Header(default=None)):
    require_extension_token(x_storyforge_token)
    return update_task_status(db, task_id, value)


@app.get("/api/workflows")
def workflows_list():
    return list_workflows(db)


@app.get("/api/workflows/{wid}")
def workflow_get(wid: str):
    return get_workflow(db, wid)


@app.delete("/api/workflows/{wid}")
def workflow_delete(wid: str):
    return delete_workflow(db, cleanup_workflow_media, DELETING_WORKFLOWS, DELETING_WORKFLOW_DIRS, wid)


def create_workflow_record(book: BookCreate, options: WorkflowOptions) -> str:
    return create_workflow(db, create_workflow_media_dir, book, options)


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
    queue_retry(db, save_workflow, wid)
    tasks.add_task(process_workflow, wid)
    return {"id": wid, "status": "queued"}
