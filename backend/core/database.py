"""SQLite connection and schema evolution for StoryForge local state."""

import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialize_schema(db: Callable[[], ContextManager[sqlite3.Connection]]) -> None:
    """Create and migrate the on-disk schema without changing persisted data."""
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workflows (
              id TEXT PRIMARY KEY, book_title TEXT NOT NULL, author TEXT, edition TEXT,
              status TEXT NOT NULL, step INTEGER NOT NULL, progress INTEGER NOT NULL,
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prompt_templates (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('writing','cover')),
              name TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL, image_sizes TEXT NOT NULL DEFAULT '["16:9", "9:16"]'
            );
            CREATE INDEX IF NOT EXISTS idx_prompt_templates_kind ON prompt_templates(kind);
            CREATE TABLE IF NOT EXISTS background_music (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
              category TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_background_music_created_at ON background_music(created_at DESC);
            CREATE TABLE IF NOT EXISTS request_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT, request_type TEXT NOT NULL,
              request_url TEXT NOT NULL, request_params TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_request_logs_type_created_at ON request_logs(request_type, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at DESC);
            """
        )
        music_columns = {column["name"] for column in conn.execute("PRAGMA table_info(background_music)")}
        if "is_default" not in music_columns:
            conn.execute("ALTER TABLE background_music ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1))")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_music_single_default ON background_music(is_default) WHERE is_default=1")
        columns = {column["name"] for column in conn.execute("PRAGMA table_info(prompt_templates)")}
        if "image_sizes" not in columns:
            conn.execute("ALTER TABLE prompt_templates ADD COLUMN image_sizes TEXT NOT NULL DEFAULT '[\"2:3\"]'")
        if conn.execute("SELECT COUNT(*) AS count FROM prompt_templates").fetchone()["count"] == 0:
            now = int(time.time())
            conn.executemany("INSERT INTO prompt_templates VALUES(?,?,?,?,?,?,?)", [
                ("writing-short-video", "writing", "短视频口播", "适合 2 分钟短视频口播，有真实阅读感受", now, now, '["2:3"]'),
                ("writing-insight", "writing", "反常识洞见", "从一个反常识观点切入，避免剧透，结尾给出阅读建议", now, now, '["2:3"]'),
                ("cover-literary", "cover", "文学质感", "克制的文学感，竖版构图，无文字，为标题留出空间", now, now, '["16:9", "9:16"]'),
            ])
        legacy_size_ratios = {"1024x1024": "1:1", "2048x2048": "1:1", "1600x1200": "4:3", "1536x1024": "3:2", "2048x1152": "16:9", "3840x2160": "16:9", "2538x1080": "2.35:1", "1200x1600": "3:4", "1024x1536": "2:3", "2160x3840": "9:16"}
        for row in conn.execute("SELECT id,image_sizes FROM prompt_templates").fetchall():
            sizes = json.loads(row["image_sizes"])
            if any("x" in size for size in sizes):
                ratios = list(dict.fromkeys(legacy_size_ratios.get(size, "2:3") for size in sizes))
                conn.execute("UPDATE prompt_templates SET image_sizes=? WHERE id=?", (json.dumps(ratios), row["id"]))
        for row in conn.execute("SELECT id,image_sizes FROM prompt_templates WHERE kind='cover'").fetchall():
            sizes = list(dict.fromkeys(json.loads(row["image_sizes"]) + ["1:1", "16:9", "9:16"]))
            conn.execute("UPDATE prompt_templates SET image_sizes=? WHERE id=?", (json.dumps(sizes), row["id"]))
        conn.execute("PRAGMA optimize")
