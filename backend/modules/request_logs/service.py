"""Request-log query and retention use cases."""

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any


def list_logs(db: Callable[[], AbstractContextManager[Any]], request_type: str, start_time: int | None, end_time: int | None, page: int, page_size: int) -> dict[str, Any]:
    conditions, params = [], []
    if request_type:
        conditions.append("request_type=?"); params.append(request_type)
    if start_time is not None:
        conditions.append("created_at>=?"); params.append(start_time)
    if end_time is not None:
        conditions.append("created_at<=?"); params.append(end_time)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS count FROM request_logs{where}", params).fetchone()["count"]
        rows = conn.execute(f"SELECT * FROM request_logs{where} ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (*params, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [{**dict(row), "request_params": json.loads(row["request_params"])} for row in rows], "total": total, "page": page, "page_size": page_size}


def clear_logs(db: Callable[[], AbstractContextManager[Any]]) -> int:
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM request_logs").fetchone()["count"]
        conn.execute("DELETE FROM request_logs")
    return count


def record_log(db: Callable[[], AbstractContextManager[Any]], request_type: str, request_url: str, request_params: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute("INSERT INTO request_logs(request_type,request_url,request_params,created_at) VALUES(?,?,?,?)", (request_type, request_url, json.dumps(request_params, ensure_ascii=False), int(time.time())))
