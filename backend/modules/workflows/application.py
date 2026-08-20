"""Workflow application services.

The API layer supplies infrastructure callbacks so this module owns workflow
state transitions without importing the FastAPI application or its globals.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
import json
import time
import uuid
from typing import Any

from fastapi import HTTPException

from backend.modules.contracts import BookCreate, WorkflowOptions


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
    output_dir, _ = create_media_dir()
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


def delete_workflow(
    db: Callable[[], AbstractContextManager[Any]],
    cleanup_media: Callable[[str, str | None], int],
    deleting_workflows: set[str],
    deleting_workflow_dirs: dict[str, str],
    wid: str,
) -> dict[str, Any]:
    with db() as conn:
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
    save_workflow: Callable[..., None],
    wid: str,
) -> None:
    with db() as conn:
        row = conn.execute("SELECT id FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row:
        raise HTTPException(404, "工作流不存在")
    save_workflow(wid, status="queued", step=0, progress=0, payload_update={"error": ""})
