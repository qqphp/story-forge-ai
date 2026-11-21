"""Prompt-template application use cases."""

import json
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from fastapi import HTTPException

from backend.modules.contracts import PromptTemplateCreate, PromptTemplateUpdate
from backend.modules.serializers import prompt_template_row


def _require_video_cover_sizes(kind: str, image_sizes: list[str]) -> None:
    if kind == "cover" and not {"1:1", "16:9", "9:16"}.issubset(image_sizes):
        raise HTTPException(400, "封面提示词必须同时选择 1:1、16:9 和 9:16 图片尺寸")


def list_templates(db: Callable[[], AbstractContextManager[Any]], kind: str | None = None) -> list[dict[str, Any]]:
    if kind and kind not in ("writing", "cover"):
        raise HTTPException(400, "提示词类型无效")
    query, params = "SELECT * FROM prompt_templates", ()
    if kind:
        query += " WHERE kind=?"
        params = (kind,)
    query += " ORDER BY created_at, name"
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [prompt_template_row(row) for row in rows]


def create_template(db: Callable[[], AbstractContextManager[Any]], value: PromptTemplateCreate) -> dict[str, Any]:
    _require_video_cover_sizes(value.kind, value.image_sizes)
    prompt_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO prompt_templates(id,kind,name,text,created_at,updated_at,image_sizes,duration_minutes) VALUES(?,?,?,?,?,?,?,?)",
                     (prompt_id, value.kind, value.name.strip(), value.text.strip(), now, now, json.dumps(value.image_sizes),
                      value.duration_minutes if value.kind == "writing" else None))
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return prompt_template_row(row)


def update_template(db: Callable[[], AbstractContextManager[Any]], prompt_id: str, value: PromptTemplateUpdate) -> dict[str, Any]:
    with db() as conn:
        existing = conn.execute("SELECT kind,duration_minutes FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "提示词不存在")
        _require_video_cover_sizes(existing["kind"], value.image_sizes)
        duration = value.duration_minutes if "duration_minutes" in value.model_fields_set else existing["duration_minutes"]
        conn.execute("UPDATE prompt_templates SET name=?,text=?,image_sizes=?,updated_at=?,duration_minutes=? WHERE id=?",
                     (value.name.strip(), value.text.strip(), json.dumps(value.image_sizes), int(time.time()),
                      duration if existing["kind"] == "writing" else None, prompt_id))
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return prompt_template_row(row)


def delete_template(db: Callable[[], AbstractContextManager[Any]], prompt_id: str) -> None:
    with db() as conn:
        result = conn.execute("DELETE FROM prompt_templates WHERE id=?", (prompt_id,))
        if result.rowcount == 0:
            raise HTTPException(404, "提示词不存在")
