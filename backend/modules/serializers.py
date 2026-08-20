"""Stable JSON representations at the persistence seam."""

import json
import sqlite3
from typing import Any


def prompt_template_row(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["image_sizes"] = json.loads(result["image_sizes"])
    return result


def workflow_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload"])
    return {
        "id": row["id"], "book_title": row["book_title"], "author": row["author"],
        "edition": row["edition"], "status": row["status"], "step": row["step"],
        "progress": row["progress"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], **payload,
    }


def publish_task_row(row: sqlite3.Row) -> dict[str, Any]:
    def decode_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if not isinstance(value, str) or not value.strip():
            return []
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        return decoded if isinstance(decoded, list) else []

    result = dict(row)
    result["tags"] = decode_list(result.get("tags"))
    result["topics"] = decode_list(result.get("topics"))
    result["covers"] = decode_list(result.get("covers"))
    return result
