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
    prompt_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO prompt_templates(id,kind,name,text,created_at,updated_at,image_sizes) VALUES(?,?,?,?,?,?,?)", (prompt_id, value.kind, value.name.strip(), value.text.strip(), now, now, json.dumps(value.image_sizes)))
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return prompt_template_row(row)


def update_template(db: Callable[[], AbstractContextManager[Any]], prompt_id: str, value: PromptTemplateUpdate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute("UPDATE prompt_templates SET name=?,text=?,image_sizes=?,updated_at=? WHERE id=?", (value.name.strip(), value.text.strip(), json.dumps(value.image_sizes), int(time.time()), prompt_id))
        if result.rowcount == 0:
            raise HTTPException(404, "提示词不存在")
        row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (prompt_id,)).fetchone()
    return prompt_template_row(row)


def delete_template(db: Callable[[], AbstractContextManager[Any]], prompt_id: str) -> None:
    with db() as conn:
        result = conn.execute("DELETE FROM prompt_templates WHERE id=?", (prompt_id,))
        if result.rowcount == 0:
            raise HTTPException(404, "提示词不存在")
