"""Workflow application services.

The API layer supplies infrastructure callbacks so this module owns workflow
state transitions without importing the FastAPI application or its globals.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
import json
import time
import uuid
from typing import Any

from fastapi import HTTPException

from backend.modules.contracts import BookCreate, WorkflowOptions
from backend.modules.workflows.broadcast import DEFAULT_WRITING_ID


def create_workflow(
    db: Callable[[], AbstractContextManager[Any]],
    create_media_dir: Callable[[], tuple[str, Any]],
    book: BookCreate,
    options: WorkflowOptions,
) -> str:
    """Persist an immutable workflow-input snapshot and reserve its media folder."""
    wid, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        writing_ids = options.writing_prompt_ids
        cover_ids = options.cover_prompt_ids
        writing_rows = conn.execute(
            f"SELECT id,name,text,duration_minutes FROM prompt_templates WHERE kind='writing' AND id IN ({','.join('?' for _ in writing_ids)})" if writing_ids else
            "SELECT id,name,text,duration_minutes FROM prompt_templates WHERE kind='writing' ORDER BY id<>?, created_at, name LIMIT 1",
            writing_ids or [DEFAULT_WRITING_ID],
        ).fetchall()
        cover_rows = conn.execute(
            f"SELECT id,name,text,image_sizes FROM prompt_templates WHERE kind='cover' AND id IN ({','.join('?' for _ in cover_ids)})" if cover_ids else
            "SELECT id,name,text,image_sizes FROM prompt_templates WHERE kind='cover' ORDER BY created_at LIMIT 1", cover_ids
        ).fetchall()
        music_row = conn.execute("SELECT id,name,url,category FROM background_music WHERE id=?", (options.background_music_id,)).fetchone() if options.background_music_id else None
        if "background_music_id" not in options.model_fields_set:
            music_row = conn.execute("SELECT id,name,url,category FROM background_music WHERE is_default=1").fetchone()
        if options.background_music_id and not music_row:
            raise HTTPException(422, "选择的背景音乐不存在")
    output_dir, _ = create_media_dir()
    payload = {"output_dir": output_dir, "local_cover": options.local_cover,
               "writing_prompts": [{**dict(row), "enabled": True} for row in writing_rows],
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


def delete_workflow(
    db: Callable[[], AbstractContextManager[Any]],
    cleanup_media: Callable[[str, str | None], int],
    deleting_workflows: set[str],
    deleting_workflow_dirs: dict[str, str],
    wid: str,
) -> dict[str, Any]:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status,payload FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            raise HTTPException(404, "工作流不存在")
        output_dir = json.loads(row["payload"]).get("output_dir")
        if row["status"] in ("queued", "running"):
            deleting_workflows.add(wid)
            if output_dir:
                deleting_workflow_dirs[wid] = output_dir
        removed_files = cleanup_media(wid, output_dir)
        conn.execute("DELETE FROM workflows WHERE id=?", (wid,))
    return {"deleted": True, "removed_files": removed_files}


def queue_retry(
    db: Callable[[], AbstractContextManager[Any]],
    wid: str,
) -> None:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT payload FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            raise HTTPException(404, "工作流不存在")
        payload = json.loads(row["payload"])
        _require_no_regeneration(payload)
        payload.update(error="", video_regenerating=False, video_error="", audio_regenerating=False, audio_error="",
                       cover_regenerating=None, cover_error=None)
        conn.execute("UPDATE workflows SET status='queued',step=0,progress=0,updated_at=?,payload=? WHERE id=?",
                     (int(time.time()), json.dumps(payload, ensure_ascii=False), wid))


def _require_no_regeneration(payload: dict[str, Any]) -> None:
    for field, label in (("cover_regenerating", "封面"), ("video_regenerating", "视频"), ("audio_regenerating", "配音")):
        if payload.get(field):
            raise HTTPException(409, f"{label}正在重新生成，请等待当前任务完成")


@contextmanager
def _queue_regeneration(db: Callable[[], AbstractContextManager[Any]], wid: str, label: str):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status,payload FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            raise HTTPException(404, "工作流不存在")
        if row["status"] != "completed":
            raise HTTPException(409, f"只有已完成的作品可以重新生成{label}")
        payload = json.loads(row["payload"])
        _require_no_regeneration(payload)
        yield payload
        conn.execute("UPDATE workflows SET payload=?,updated_at=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), int(time.time()), wid))


def queue_video_regeneration(
    db: Callable[[], AbstractContextManager[Any]],
    regenerating: set[str],
    wid: str,
) -> None:
    """Mark a completed workflow so only its video can be composed again."""
    with _queue_regeneration(db, wid, "视频") as payload:
        if not payload.get("audio"):
            raise HTTPException(409, "缺少配音，无法重新生成视频")
        if not payload.get("covers"):
            raise HTTPException(409, "缺少封面，无法重新生成视频")
        payload.update(video_regenerating=True, video_error="")
    regenerating.add(wid)


def queue_audio_regeneration(
    db: Callable[[], AbstractContextManager[Any]],
    regenerating: set[str],
    wid: str,
    voice: str,
) -> None:
    """Mark a completed workflow so its narration and subtitles can be replaced."""
    voice = voice.strip()
    if not voice:
        raise HTTPException(422, "请选择音色")
    with _queue_regeneration(db, wid, "配音") as payload:
        if not payload.get("polished_drafts"):
            raise HTTPException(409, "缺少分享稿，无法重新生成配音")
        payload.update(audio_regenerating=True, audio_error="", audio_regenerate_voice=voice)
    regenerating.add(wid)


def queue_cover_regeneration(db: Callable[[], AbstractContextManager[Any]], wid: str, cover_url: str) -> dict[str, str]:
    job = {"cover_url": cover_url, "id": uuid.uuid4().hex}
    with _queue_regeneration(db, wid, "封面") as payload:
        if not any(cover.get("url") == cover_url for cover in payload.get("covers", [])):
            raise HTTPException(404, "这张封面不存在或已被替换，请刷新后重试")
        payload.update(cover_regenerating=job, cover_error=None)
    return job


def release_interrupted_video_regenerations(db: Callable[[], AbstractContextManager[Any]]) -> None:
    """Release interrupted work without discarding already generated assets."""
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT id, status, payload FROM workflows").fetchall()
        now = int(time.time())
        for row in rows:
            payload = json.loads(row["payload"])
            changed = False
            status = row["status"]
            if status in ("running", "queued"):
                status = "failed"
                payload["error"] = "制作因服务重启而中断，请重试；已生成的产物已保留"
                changed = True
            if payload.get("video_regenerating"):
                payload["video_regenerating"] = False
                payload["video_error"] = "重新生成已中断，请再试一次"
                changed = True
            if payload.get("audio_regenerating"):
                payload["audio_regenerating"] = False
                payload["audio_error"] = "重新生成已中断，请再试一次"
                changed = True
            if job := payload.get("cover_regenerating"):
                payload["cover_regenerating"] = None
                payload["cover_error"] = {"cover_url": job["cover_url"], "message": "封面重新生成因服务重启而中断，请再试一次"}
                changed = True
            if not changed:
                continue
            conn.execute(
                "UPDATE workflows SET status=?, payload=?, updated_at=? WHERE id=?",
                (status, json.dumps(payload, ensure_ascii=False), now, row["id"]),
            )
