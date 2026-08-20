"""SQLite connection and schema evolution for StoryForge local state."""

import json
import secrets
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
            CREATE TABLE IF NOT EXISTS application_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS publish_tasks (
              id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
              platform TEXT NOT NULL CHECK(platform IN ('douyin','kuaishou','bilibili','xiaohongshu','baijiahao')),
              status TEXT NOT NULL CHECK(status IN ('prepared','filling','ready','completed','failed','cancelled')),
              title TEXT NOT NULL, description TEXT NOT NULL, tags TEXT NOT NULL,
              topics TEXT NOT NULL DEFAULT '[]', video_url TEXT NOT NULL,
              cover_url TEXT NOT NULL DEFAULT '', covers TEXT NOT NULL DEFAULT '[]',
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_publish_tasks_platform_status_created
              ON publish_tasks(platform, status, created_at);
            """
        )
        if not conn.execute("SELECT 1 FROM application_meta WHERE key='extension_pairing_token'").fetchone():
            conn.execute("INSERT INTO application_meta(key,value) VALUES('extension_pairing_token',?)", (secrets.token_hex(16),))
        columns = {column["name"] for column in conn.execute("PRAGMA table_info(prompt_templates)")}
        if "image_sizes" not in columns:
            conn.execute("ALTER TABLE prompt_templates ADD COLUMN image_sizes TEXT NOT NULL DEFAULT '[\"2:3\"]'")
        publish_columns = {column["name"] for column in conn.execute("PRAGMA table_info(publish_tasks)")}
        if "topics" not in publish_columns:
            conn.execute("ALTER TABLE publish_tasks ADD COLUMN topics TEXT NOT NULL DEFAULT '[]'")
        if "covers" not in publish_columns:
            conn.execute("ALTER TABLE publish_tasks ADD COLUMN covers TEXT NOT NULL DEFAULT '[]'")
        publish_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='publish_tasks'").fetchone()["sql"]
        if "kuaishou" not in publish_schema:
            conn.execute("DROP INDEX IF EXISTS idx_publish_tasks_platform_status_created")
            conn.execute("ALTER TABLE publish_tasks RENAME TO publish_tasks_legacy")
            conn.execute("""CREATE TABLE publish_tasks (
              id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
              platform TEXT NOT NULL CHECK(platform IN ('douyin','kuaishou','bilibili','xiaohongshu','baijiahao')),
              status TEXT NOT NULL CHECK(status IN ('prepared','filling','ready','completed','failed','cancelled')),
              title TEXT NOT NULL, description TEXT NOT NULL, tags TEXT NOT NULL, topics TEXT NOT NULL DEFAULT '[]',
              video_url TEXT NOT NULL, cover_url TEXT NOT NULL DEFAULT '', covers TEXT NOT NULL DEFAULT '[]',
              created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, error TEXT NOT NULL DEFAULT ''
            )""")
            conn.execute("INSERT INTO publish_tasks SELECT * FROM publish_tasks_legacy")
            conn.execute("DROP TABLE publish_tasks_legacy")
            conn.execute("CREATE INDEX idx_publish_tasks_platform_status_created ON publish_tasks(platform, status, created_at)")
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
        conn.execute("PRAGMA optimize")
