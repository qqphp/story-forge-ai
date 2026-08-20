"""Publishing task creation and platform-specific validation."""

import json
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.modules.contracts import PublishTaskCreate, PublishTaskStatusUpdate
from backend.modules.serializers import publish_task_row, workflow_row


def create_task(db: Callable[[], AbstractContextManager[Any]], value: PublishTaskCreate) -> dict[str, Any]:
    if value.platform != "kuaishou" and not value.title.strip():
        raise HTTPException(422, "该平台需要作品标题")
    with db() as conn:
        workflow_record = conn.execute("SELECT * FROM workflows WHERE id=?", (value.workflow_id,)).fetchone()
        if not workflow_record:
            raise HTTPException(404, "作品不存在")
        workflow = workflow_row(workflow_record)
        videos = {asset.get("url") for asset in workflow.get("videos", []) if asset.get("url")}
        cover_assets = {asset.get("url"): asset for asset in workflow.get("covers", []) if asset.get("url")}
        video_url = value.video_url or next(iter(videos), "")
        if not video_url:
            raise HTTPException(422, "该作品还没有可发布的视频")
        if video_url not in videos:
            raise HTTPException(422, "视频不属于当前作品")
        if any(cover_url not in cover_assets for cover_url in value.cover_urls):
            raise HTTPException(422, "封面不属于当前作品")
        covers = [{key: cover_assets[url].get(key, "") for key in ("url", "image_ratio", "resolution", "prompt_name")} for url in value.cover_urls]
        unsupported = [cover["image_ratio"] or "未记录" for cover in covers if cover["image_ratio"] not in {"3:4", "4:3"}]
        if value.platform in {"douyin", "kuaishou"} and unsupported:
            label = {"douyin": "抖音", "kuaishou": "快手"}[value.platform]
            raise HTTPException(422, f"{label}封面只支持原图直传3:4或4:3，不能使用：{', '.join(unsupported)}")
        topics = value.topics or workflow.get("topics", [])
        topic_limit = {"kuaishou": 4, "douyin": 5}.get(value.platform)
        if topic_limit is not None:
            topics = topics[:topic_limit]
        tags = value.tags or workflow.get("tags", [])
        if value.platform == "bilibili":
            tags = tags[:10]
        task_id, now = uuid.uuid4().hex[:16], int(time.time())
        conn.execute("INSERT INTO publish_tasks(id,workflow_id,platform,status,title,description,tags,topics,video_url,cover_url,covers,created_at,updated_at,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (task_id, value.workflow_id, value.platform, "prepared", value.title.strip(), value.description.strip(), json.dumps(tags, ensure_ascii=False), json.dumps(topics, ensure_ascii=False), video_url, covers[0]["url"] if covers else "", json.dumps(covers, ensure_ascii=False), now, now, ""))
        row = conn.execute("SELECT publish_tasks.*,workflows.book_title FROM publish_tasks JOIN workflows ON workflows.id=publish_tasks.workflow_id WHERE publish_tasks.id=?", (task_id,)).fetchone()
    return publish_task_row(row)


def list_tasks(db: Callable[[], AbstractContextManager[Any]], platform: str, platforms: tuple[str, ...]) -> list[dict[str, Any]]:
    if platform and platform not in platforms:
        raise HTTPException(400, "不支持该发布平台")
    with db() as conn:
        query = "SELECT publish_tasks.*,workflows.book_title FROM publish_tasks JOIN workflows ON workflows.id=publish_tasks.workflow_id "
        params: tuple[str, ...] = ()
        if platform:
            query += "WHERE platform=? "
            params = (platform,)
        rows = conn.execute(query + "ORDER BY created_at DESC", params).fetchall()
    return [publish_task_row(row) for row in rows]


def delete_task(db: Callable[[], AbstractContextManager[Any]], task_id: str) -> None:
    with db() as conn:
        if conn.execute("DELETE FROM publish_tasks WHERE id=?", (task_id,)).rowcount == 0:
            raise HTTPException(404, "发布任务不存在")


def resolve_task_media(
    db: Callable[[], AbstractContextManager[Any]],
    media_root: Path,
    task_id: str,
    kind: str,
    cover_index: int | None = None,
) -> Path:
    """Resolve a task asset while enforcing the media-root boundary."""
    field = "video_url" if kind == "video" else "cover_url"
    with db() as conn:
        row = conn.execute(f"SELECT {field},covers FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "发布任务不存在")
    if cover_index is not None:
        covers = json.loads(row["covers"] or "[]")
        if cover_index < 0 or cover_index >= len(covers):
            raise HTTPException(404, "发布封面不存在")
        url = covers[cover_index].get("url", "")
    else:
        url = row[field]
    prefix = "/media/"
    label = "视频" if kind == "video" else "封面"
    if not url.startswith(prefix):
        raise HTTPException(422, f"发布{label}地址无效")
    target = (media_root / url[len(prefix):]).resolve()
    if media_root.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, f"发布{label}文件不存在")
    return target


def update_task_status(
    db: Callable[[], AbstractContextManager[Any]], task_id: str, value: PublishTaskStatusUpdate
) -> dict[str, Any]:
    allowed_transitions = {
        "prepared": {"filling", "failed"},
        "filling": {"ready", "failed"},
        "ready": {"completed", "failed"},
        "failed": {"filling"},
        "completed": set(),
        "cancelled": set(),
    }
    with db() as conn:
        current = conn.execute("SELECT status FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
        if not current:
            raise HTTPException(404, "发布任务不存在")
        if value.status not in allowed_transitions[current["status"]]:
            raise HTTPException(409, f"不能从 {current['status']} 切换到 {value.status}")
        conn.execute("UPDATE publish_tasks SET status=?,error=?,updated_at=? WHERE id=?",
                     (value.status, value.error.strip(), int(time.time()), task_id))
        row = conn.execute("SELECT * FROM publish_tasks WHERE id=?", (task_id,)).fetchone()
    return publish_task_row(row)
