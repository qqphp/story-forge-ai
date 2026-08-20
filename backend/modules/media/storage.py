"""Filesystem adapter for workflow-generated media."""

import json
import secrets
import shutil
import string
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any


def create_workflow_media_dir(media_root: Path) -> tuple[str, Path]:
    resolved_root = media_root.resolve()
    for _ in range(20):
        suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
        folder_name = f"{datetime.now().strftime('%Y%m%d')}{suffix}{int(time.time())}"
        target = (media_root / folder_name).resolve()
        if target.parent != resolved_root:
            raise RuntimeError("工作流产物目录越界")
        try:
            target.mkdir(parents=False, exist_ok=False)
            return folder_name, target
        except FileExistsError:
            continue
    raise RuntimeError("无法创建唯一的工作流产物目录")


def workflow_media_dir(media_root: Path, output_dir: str) -> Path:
    target = (media_root / output_dir).resolve()
    if target.parent != media_root.resolve():
        raise RuntimeError("工作流产物目录越界")
    return target


def cleanup_workflow_media(
    db: Callable[[], AbstractContextManager[Any]], media_root: Path, wid: str, output_dir: str | None = None,
) -> int:
    if not output_dir:
        with db() as conn:
            row = conn.execute("SELECT payload FROM workflows WHERE id=?", (wid,)).fetchone()
        if row:
            output_dir = json.loads(row["payload"]).get("output_dir")
    if not output_dir:
        return 0
    target = workflow_media_dir(media_root, output_dir)
    if not target.is_dir():
        return 0
    removed = sum(1 for candidate in target.rglob("*") if candidate.is_file())
    shutil.rmtree(target)
    return removed
