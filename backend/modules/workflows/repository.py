"""Workflow persistence adapter and creation snapshot logic."""

from collections.abc import Callable
from contextlib import AbstractContextManager
import json
import time
from typing import Any

from fastapi import HTTPException

from backend.modules.serializers import workflow_row


def list_workflows(db: Callable[[], AbstractContextManager[Any]]) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
    return [workflow_row(row) for row in rows]


def get_workflow(db: Callable[[], AbstractContextManager[Any]], wid: str) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
    if not row:
        raise HTTPException(404, "工作流不存在")
    return workflow_row(row)


def save_workflow(
    db: Callable[[], AbstractContextManager[Any]],
    wid: str,
    *,
    status: str | None = None,
    step: int | None = None,
    progress: int | None = None,
    payload_update: dict[str, Any] | None = None,
) -> None:
    """Persist one workflow state transition while retaining its input snapshot."""
    with db() as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            return
        payload = json.loads(row["payload"])
        payload.update(payload_update or {})
        conn.execute(
            "UPDATE workflows SET status=?,step=?,progress=?,updated_at=?,payload=? WHERE id=?",
            (status or row["status"], step if step is not None else row["step"],
             progress if progress is not None else row["progress"], int(time.time()),
             json.dumps(payload, ensure_ascii=False), wid),
        )
