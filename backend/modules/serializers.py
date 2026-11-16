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
