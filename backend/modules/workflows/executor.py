"""Workflow execution orchestration, independent of the FastAPI entry point."""

import asyncio
import os
import subprocess
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from backend.modules.contracts import DEFAULT_IMAGE_SIZES
from backend.modules.workflows.content import demo_copy, generated_taxonomy


async def execute_workflow(
    wid: str,
    *,
    db: Callable[[], AbstractContextManager[Any]],
    workflow_row: Callable[[Any], dict[str, Any]],
    get_settings: Callable[[], dict[str, Any]],
    media_dir: Callable[[str], Path],
    save: Callable[..., None],
    is_deleting: Callable[[str], bool],
    cleanup_deleted: Callable[[str], None],
    llm: Callable[..., Any],
    speech: Callable[..., Any],
    audio_extension: Callable[[str], str],
    generate_cover: Callable[..., Any],
    video_command: Callable[..., list[str]],
) -> None:
    """Run one workflow while reporting durable progress through ``save``."""
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row:
            return
        item, settings = workflow_row(row), get_settings()
        output_dir = media_dir(item["output_dir"])
        output_dir.mkdir(parents=False, exist_ok=True)
        title, author = item["book_title"], item["author"]
        save(wid, status="running", step=1, progress=8)
        await asyncio.sleep(.4)
        description = await llm([
            {"role": "system", "content": "你是严谨的中文图书编辑。只输出100字左右的书籍简介，不虚构具体事实。"},
            {"role": "user", "content": f"书名：{title}；作者：{author or '未知'}；版本：{item['edition'] or '未指定'}"},
        ], settings)
        if is_deleting(wid): return
        description = description or f"《{title}》是一部值得慢下来阅读的作品。它从人与世界的关系出发，在细节与思考之间，带领读者重新理解选择、成长与生活的意义。"
        save(wid, step=2, progress=24, payload_update={"description": description})

        prompts = [p for p in item.get("writing_prompts", []) if p.get("enabled")] or [{"text": "适合短视频口播，真诚、有洞见", "enabled": True}]
        originals, polished = [], []
        for i, prompt in enumerate(prompts):
            if is_deleting(wid): return
            raw = await llm([
                {"role": "system", "content": "你是专业读书博主。写一篇500字以内、事实谨慎、适合口播的中文分享稿。"},
                {"role": "user", "content": f"书名：{title}\n作者：{author}\n简介：{description}\n额外要求：{prompt['text']}"},
            ], settings)
            raw = raw or demo_copy(title, author, prompt["text"], i)
            originals.append({"id": f"draft-{i+1}", "prompt": prompt["text"], "text": raw})
            improved = await llm([
                {"role": "system", "content": "按 Humanizer-zh 的目标优化中文：去除AI腔、空泛排比和过度总结，保留事实和观点，口语自然。只输出优化稿。"},
                {"role": "user", "content": raw},
            ], settings)
            if is_deleting(wid): return
            polished.append({"id": f"draft-{i+1}", "prompt": prompt["text"], "text": improved or raw.replace("真正动人的地方", "我最喜欢的是")})
        save(wid, step=3, progress=45, payload_update={"original_drafts": originals, "polished_drafts": polished})

        save(wid, step=4, progress=48)
        voices = item.get("voices") or settings.get("voices") or ["zh-CN-XiaoxiaoNeural"]
        speech_rate, background_music, audio_items = item.get("speech_rate", settings.get("speech_rate", 0)), item.get("background_music"), []
        for di, draft in enumerate(polished):
            for vi, voice in enumerate(voices):
                if is_deleting(wid): return
                base = output_dir / f"draft-{di+1}-voice-{vi+1}"
                target = base.with_suffix(audio_extension(settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")))
                used_real_speech = await speech(draft["text"], voice, speech_rate, settings, target, background_music, item.get("background_music_volume", .2), item.get("background_music_fade_in", 2), item.get("background_music_fade_out", 2))
                if is_deleting(wid): return
                actual = target if target.exists() else base.with_suffix(".wav")
                audio_items.append({"draft_id": draft["id"], "voice": voice, "speech_rate": speech_rate, "url": f"/media/{item['output_dir']}/{actual.name}", "provider": "azure" if used_real_speech else "demo"})
        save(wid, step=5, progress=64, payload_update={"audio": audio_items})

        share_text = "\n\n---\n\n".join(draft["text"] for draft in polished)
        taxonomy_raw = await llm([
            {"role": "system", "content": "你是中文内容运营编辑。根据给定书籍信息与分享稿生成内容分类。只输出严格JSON，不要Markdown：{\"tags\":[8个简短标签],\"topics\":[8个适合短视频平台的话题词]}。每项不带#，不含空格，不超过15个汉字，去重并与内容高度相关。"},
            {"role": "user", "content": f"书籍标题：{title}\n书籍简介：{description}\n分享稿：\n{share_text}"},
        ], settings, "标签话题生成")
        if is_deleting(wid): return
        tags, topics = generated_taxonomy(taxonomy_raw, title)
        save(wid, step=6, progress=74, payload_update={"tags": tags, "topics": topics})

        cover_prompts = [p for p in item.get("cover_prompts", []) if p.get("enabled")] or [{"text": "克制、文学感、适合短视频竖版", "enabled": True, "image_sizes": DEFAULT_IMAGE_SIZES}]
        covers, cover_index = [], 0
        for prompt in cover_prompts:
            for image_ratio in prompt.get("image_sizes") or DEFAULT_IMAGE_SIZES:
                if is_deleting(wid): return
                cover_index += 1
                path = output_dir / f"cover-{cover_index}.png"
                used_real_image, resolution = await generate_cover(path, title, author, description, prompt["text"], cover_index - 1, image_ratio, settings)
                if is_deleting(wid): return
                covers.append({"prompt_name": prompt.get("name", f"封面提示词 {cover_index}"), "prompt": prompt["text"], "image_ratio": image_ratio, "resolution": resolution, "url": f"/media/{item['output_dir']}/{path.name}", "provider": "teamorouter" if used_real_image else "local"})
        save(wid, step=7, progress=88, payload_update={"covers": covers})

        videos, ffmpeg = [], os.getenv("FFMPEG_PATH", "ffmpeg")
        for i, audio in enumerate(audio_items):
            if is_deleting(wid): return
            cover, narration = output_dir / Path(covers[i % len(covers)]["url"]).name, output_dir / Path(audio["url"]).name
            out = output_dir / f"video-{i+1}.mp4"
            result = await asyncio.to_thread(subprocess.run, video_command(ffmpeg, cover, narration, out), capture_output=True, timeout=180)
            if result.returncode == 0:
                videos.append({"draft_id": audio["draft_id"], "voice": audio["voice"], "url": f"/media/{item['output_dir']}/{out.name}", "background_music": background_music.get("name") if background_music else ""})
        save(wid, status="completed", step=7, progress=100, payload_update={"videos": videos})
    except Exception as exc:
        save(wid, status="failed", payload_update={"error": str(exc)[:500]})
    finally:
        if is_deleting(wid):
            cleanup_deleted(wid)
