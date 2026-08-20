"""Background-music catalog use cases."""

import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from fastapi import HTTPException

from backend.modules.contracts import BackgroundMusicCreate


def list_music(db: Callable[[], AbstractContextManager[Any]], query: str, page: int, page_size: int) -> dict[str, Any]:
    where, params = "", []
    if query.strip():
        where = " WHERE name LIKE ? OR category LIKE ?"
        needle = f"%{query.strip()}%"
        params = [needle, needle]
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM background_music{where}", params).fetchone()["count"]
        rows = conn.execute(f"SELECT * FROM background_music{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*params, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def create_music(db: Callable[[], AbstractContextManager[Any]], value: BackgroundMusicCreate) -> dict[str, Any]:
    music_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO background_music(id,name,url,category,created_at) VALUES(?,?,?,?,?)", (music_id, value.name.strip(), value.url, value.category.strip(), now))
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return dict(row)


def update_music(db: Callable[[], AbstractContextManager[Any]], music_id: str, value: BackgroundMusicCreate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute("UPDATE background_music SET name=?,url=?,category=? WHERE id=?", (value.name.strip(), value.url, value.category.strip(), music_id))
        if result.rowcount == 0:
            raise HTTPException(404, "背景音乐不存在")
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return dict(row)


def delete_music(db: Callable[[], AbstractContextManager[Any]], music_id: str) -> None:
    with db() as conn:
        if conn.execute("DELETE FROM background_music WHERE id=?", (music_id,)).rowcount == 0:
            raise HTTPException(404, "背景音乐不存在")
