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
        default = conn.execute("SELECT * FROM background_music WHERE is_default=1").fetchone()
    return {"items": [music_row(row) for row in rows], "default_item": music_row(default) if default else None, "total": total, "page": page, "page_size": page_size}


def music_row(row: Any) -> dict[str, Any]:
    return {**dict(row), "is_default": bool(row["is_default"])}


def set_default_music(db: Callable[[], AbstractContextManager[Any]], music_id: str, is_default: bool) -> dict[str, Any]:
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT id FROM background_music WHERE id=?", (music_id,)).fetchone():
            raise HTTPException(404, "背景音乐不存在")
        if is_default:
            conn.execute("UPDATE background_music SET is_default=0 WHERE is_default=1")
        conn.execute("UPDATE background_music SET is_default=? WHERE id=?", (int(is_default), music_id))
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return music_row(row)


def create_music(db: Callable[[], AbstractContextManager[Any]], value: BackgroundMusicCreate) -> dict[str, Any]:
    music_id, now = uuid.uuid4().hex[:12], int(time.time())
    with db() as conn:
        conn.execute("INSERT INTO background_music(id,name,url,category,created_at) VALUES(?,?,?,?,?)", (music_id, value.name.strip(), value.url, value.category.strip(), now))
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return music_row(row)


def update_music(db: Callable[[], AbstractContextManager[Any]], music_id: str, value: BackgroundMusicCreate) -> dict[str, Any]:
    with db() as conn:
        result = conn.execute("UPDATE background_music SET name=?,url=?,category=? WHERE id=?", (value.name.strip(), value.url, value.category.strip(), music_id))
        if result.rowcount == 0:
            raise HTTPException(404, "背景音乐不存在")
        row = conn.execute("SELECT * FROM background_music WHERE id=?", (music_id,)).fetchone()
    return music_row(row)


def delete_music(db: Callable[[], AbstractContextManager[Any]], music_id: str) -> None:
    with db() as conn:
        if conn.execute("DELETE FROM background_music WHERE id=?", (music_id,)).rowcount == 0:
            raise HTTPException(404, "背景音乐不存在")
