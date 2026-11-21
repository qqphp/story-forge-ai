"""Workflow execution orchestration, independent of the FastAPI entry point."""

import asyncio
import json
import math
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from backend.modules.contracts import DEFAULT_IMAGE_SIZES
from backend.integrations.local_covers import generate_local_covers
from backend.modules.workflows.content import demo_copy, generated_taxonomy
from backend.integrations.video import probe_audio_duration, probe_video_metadata, video_encode_timeout, write_concat_manifest
from backend.integrations.stock_video import natural_scenery_query


def share_draft_user_content(title: str, author: str | None, edition: str | None) -> str:
    """User message for an original share draft: title, author, and edition only."""
    lines = [f"书名：{title.strip()}"]
    author_text = (author or "").strip()
    edition_text = (edition or "").strip()
    if author_text:
        lines.append(f"作者：{author_text}")
    if edition_text:
        lines.append(f"版本：{edition_text}")
    return "\n".join(lines)


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
    download_stock_videos: Callable[..., Any],
    log_request: Callable[[str, str, dict[str, Any]], None],
    generate_subtitles: Callable[[Path, str, str], dict[str, Path]],
    subtitle_language: Callable[[str], str],
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
            {"role": "system", "content": "你是严谨的中文图书编辑。只输出160个字以内的书籍简介，不虚构具体事实。"},
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
                {"role": "system", "content": prompt["text"]},
                {"role": "user", "content": share_draft_user_content(title, author, item.get("edition"))},
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
        save(wid, step=5, progress=58, payload_update={"audio": audio_items})

        draft_text = {draft["id"]: draft["text"] for draft in polished}
        subtitle_items = []
        for audio in audio_items:
            if is_deleting(wid): return
            narration = output_dir / Path(audio["url"]).name
            await asyncio.to_thread(generate_subtitles, narration, draft_text.get(audio["draft_id"], ""), subtitle_language(audio["voice"]))
            if is_deleting(wid): return
            subtitle_items.append({
                "draft_id": audio["draft_id"], "voice": audio["voice"],
                "srt_url": f"/media/{item['output_dir']}/{narration.with_suffix('.srt').name}",
                "txt_url": f"/media/{item['output_dir']}/{narration.with_suffix('.txt').name}",
                "json_url": f"/media/{item['output_dir']}/{narration.with_suffix('.json').name}",
            })
            save(wid, progress=58 + int(10 * len(subtitle_items) / len(audio_items)), payload_update={"subtitles": subtitle_items})
        save(wid, step=6, progress=68, payload_update={"subtitles": subtitle_items})

        share_text = "\n\n---\n\n".join(draft["text"] for draft in polished)
        taxonomy_raw = await llm([
            {"role": "system", "content": "你是中文内容运营编辑。根据给定书籍信息与分享稿生成内容分类。只输出严格JSON，不要Markdown：{\"tags\":[8个简短标签],\"topics\":[8个适合短视频平台的话题词]}。每项不带#，不含空格，不超过15个汉字，去重并与内容高度相关。"},
            {"role": "user", "content": f"书籍标题：{title}\n书籍简介：{description}\n分享稿：\n{share_text}"},
        ], settings, "标签话题生成")
        if is_deleting(wid): return
        tags, topics = generated_taxonomy(taxonomy_raw, title)
        save(wid, step=7, progress=76, payload_update={"tags": tags, "topics": topics})

        if item.get("local_cover", False):
            covers = await asyncio.to_thread(generate_local_covers, output_dir, title, author)
            if is_deleting(wid): return
        else:
            cover_prompts = [p for p in item.get("cover_prompts", []) if p.get("enabled")] or [{"text": "克制、文学感、适合短视频竖版", "enabled": True, "image_sizes": DEFAULT_IMAGE_SIZES}]
            covers, cover_index = [], 0
            for prompt in cover_prompts:
                for image_ratio in dict.fromkeys((prompt.get("image_sizes") or []) + DEFAULT_IMAGE_SIZES):
                    if is_deleting(wid): return
                    cover_index += 1
                    path = output_dir / f"cover-{cover_index}.png"
                    used_real_image, resolution = await generate_cover(path, title, author, description, prompt["text"], cover_index - 1, image_ratio, settings)
                    if is_deleting(wid): return
                    covers.append({"prompt_id": prompt.get("id"), "prompt_name": prompt.get("name", f"封面提示词 {cover_index}"), "prompt": prompt["text"], "image_ratio": image_ratio, "resolution": resolution, "url": f"/media/{item['output_dir']}/{path.name}", "provider": "openai_compatible" if used_real_image else "local"})
        save(wid, step=8, progress=88, payload_update={"covers": covers})

        videos = await compose_videos(
            wid, item, settings, output_dir, covers, audio_items, description=description,
            is_deleting=is_deleting, llm=llm, video_command=video_command,
            download_stock_videos=download_stock_videos, log_request=log_request,
            subtitle_items=subtitle_items,
        )
        if videos is None:
            return
        save(wid, status="completed", step=8, progress=100, payload_update={"videos": videos, "subtitles": subtitle_items, "covers": covers})
    except Exception as exc:
        save(wid, status="failed", payload_update={"error": workflow_failure_message(exc)})
    finally:
        if is_deleting(wid):
            cleanup_deleted(wid)


def workflow_failure_message(exc: BaseException) -> str:
    """Describe a failed workflow, including timeouts whose text is blank."""
    text = str(exc).strip()
    if "timeout" in type(exc).__name__.lower() or text.lower() == "timed out":
        return "文稿生成超时，模型在限定时间内没有返回"
    return (text or f"制作失败：{type(exc).__name__}")[:500]


def _media_name(url: str) -> str:
    return Path(str(url).split("?", 1)[0]).name


def remove_replaced_videos(output_dir: Path, previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> None:
    """Delete video files that this regeneration replaced, and leave every other asset."""
    current_names = {_media_name(str(video.get("url", ""))) for video in current}
    resolved_root = output_dir.resolve()
    for video in previous:
        name = _media_name(str(video.get("url", "")))
        if not name or name in current_names or not name.startswith("video-") or not name.endswith(".mp4"):
            continue
        path = (output_dir / name).resolve()
        if path.parent != resolved_root:
            continue
        path.unlink(missing_ok=True)
        for sidecar in path.parent.glob(path.stem + ".*"):
            sidecar.unlink(missing_ok=True)


def discard_regeneration_files(output_dir: Path, stamp: int) -> None:
    if not output_dir.is_dir():
        return
    for path in output_dir.glob(f"video-*-{stamp}*.mp4"):
        path.unlink(missing_ok=True)
        for sidecar in path.parent.glob(path.stem + ".*"):
            sidecar.unlink(missing_ok=True)


_NARRATION_SUFFIXES = {".mp3", ".wav", ".ogg", ".opus", ".webm", ".pcm"}
_SUBTITLE_SUFFIXES = {".srt", ".txt", ".json"}


def discard_audio_regeneration_files(output_dir: Path, stamp: int) -> None:
    if not output_dir.is_dir():
        return
    for path in output_dir.glob(f"draft-*-voice-1-{stamp}.*"):
        path.unlink(missing_ok=True)


def remove_replaced_narration(
    output_dir: Path,
    previous_audio: list[dict[str, Any]],
    previous_subtitles: list[dict[str, Any]],
    current_audio: list[dict[str, Any]],
    current_subtitles: list[dict[str, Any]],
) -> None:
    """Delete narration and subtitle files replaced by a successful audio regeneration."""
    keep = {_media_name(str(item.get("url", ""))) for item in current_audio}
    for item in current_subtitles:
        for key in ("srt_url", "txt_url", "json_url"):
            keep.add(_media_name(str(item.get(key, ""))))
    keep.discard("")
    urls = [str(item.get("url", "")) for item in previous_audio]
    for item in previous_subtitles:
        urls.extend(str(item.get(key, "")) for key in ("srt_url", "txt_url", "json_url"))
    resolved_root = output_dir.resolve()
    for url in urls:
        name = _media_name(url)
        if not name or name in keep or not name.startswith("draft-"):
            continue
        path = (output_dir / name).resolve()
        if path.parent != resolved_root or path.suffix.lower() not in _NARRATION_SUFFIXES | _SUBTITLE_SUFFIXES:
            continue
        path.unlink(missing_ok=True)
        if path.suffix.lower() in _NARRATION_SUFFIXES:
            for suffix in _SUBTITLE_SUFFIXES:
                sidecar = path.with_suffix(suffix)
                if sidecar.name not in keep and sidecar.resolve().parent == resolved_root:
                    sidecar.unlink(missing_ok=True)


def subtitle_file_for_audio(output_dir: Path, audio: dict[str, Any], subtitle_items: list[dict[str, Any]]) -> Path:
    """Resolve the newest subtitle file saved for this narration."""
    draft_id = audio.get("draft_id")
    voice = audio.get("voice")
    candidates = [item for item in subtitle_items if item.get("draft_id") == draft_id and item.get("srt_url")]
    exact = next((item for item in reversed(candidates) if item.get("voice") == voice), None)
    chosen = exact or (candidates[-1] if candidates else None)
    if chosen:
        return output_dir / _media_name(str(chosen["srt_url"]))
    return (output_dir / _media_name(str(audio.get("url", "")))).with_suffix(".srt")


async def compose_videos(
    wid: str,
    item: dict[str, Any],
    settings: dict[str, Any],
    output_dir: Path,
    covers: list[dict[str, Any]],
    audio_items: list[dict[str, Any]],
    *,
    description: str,
    is_deleting: Callable[[str], bool],
    llm: Callable[..., Any],
    video_command: Callable[..., list[str]],
    download_stock_videos: Callable[..., Any],
    log_request: Callable[[str, str, dict[str, Any]], None],
    output_name: Callable[[int], str] | None = None,
    subtitle_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    """Compose one video per narration from existing covers, audio, and optional subtitles."""
    if subtitle_items is None:
        subtitle_items = []
    batch = str(time.time_ns())
    videos, ffmpeg = [], os.getenv("FFMPEG_PATH", "ffmpeg")
    orientation = "landscape"
    if not covers:
        raise RuntimeError("缺少视频封面")
    background_music = item.get("background_music")
    narration_durations = []
    for audio in audio_items:
        if is_deleting(wid):
            return None
        seconds = await asyncio.to_thread(probe_audio_duration, output_dir / _media_name(audio["url"]))
        if seconds is None or not math.isfinite(seconds) or seconds <= 0:
            raise RuntimeError("无法读取有效配音时长")
        narration_durations.append(seconds)
    if not narration_durations:
        raise RuntimeError("缺少视频配音")
    created = []
    completed = False
    try:
        stock_manifest = None
        if settings.get("video_generation_method", "local") == "stock":
            provider = settings.get("stock_video_provider", "pexels")
            search_query = await llm([
                {"role": "system", "content": "Create one concise English stock-video search query (3-7 words). Use only natural scenery, landscapes, weather, plants, water, architecture, or atmospheric details. Never mention people, persons, faces, characters, crowds, portraits, or human actions. Output only the query."},
                {"role": "user", "content": f"Book title: {item['book_title']}\nBook summary: {description}"},
            ], settings, "视频搜索词生成")
            search_query = natural_scenery_query((search_query or "serene cinematic natural landscape").strip().strip('"“”'))
            clips = await download_stock_videos(
                provider=provider,
                api_base=settings[f"{provider}_api_base"],
                api_key=settings.get(f"{provider}_api_key", ""),
                query=search_query,
                orientation=orientation,
                output_dir=output_dir,
                log_request=log_request,
                target_duration=max(narration_durations),
            )
            created.extend(path.with_suffix("") for path in clips)
            manifest_path = output_dir / f"stock-videos-{batch}.ffconcat"
            created.append(manifest_path.with_suffix(""))
            stock_manifest = write_concat_manifest(manifest_path, clips)
        from backend.integrations.local_covers import render_local_cover, STYLES
        groups = {}
        for cover_item in covers:
            group_id = cover_item.get("prompt_id") or "local"
            groups.setdefault(group_id, {})[cover_item.get("image_ratio")] = cover_item
        for group_index, (group_id, group) in enumerate(groups.items()):
            template = next(iter(group.values())).get("template_id", "literary")
            style_index = next((i for i, style in enumerate(STYLES) if template.startswith(style[0])), 0)
            for ratio in DEFAULT_IMAGE_SIZES:
                if ratio not in group:
                    path = output_dir / f"cover-generated-{batch}-{group_index}-{ratio.replace(':', '-')}.png"
                    created.append(path.with_suffix(""))
                    metadata = render_local_cover(path, item["book_title"], item.get("author", ""), ratio, style_index)
                    asset = {**metadata, "prompt_id": None if group_id == "local" else group_id, "url": f"/media/{item['output_dir']}/{path.name}"}
                    group[ratio] = asset
                    covers.append(asset)
        from backend.integrations.player import player_command
        for index, audio in enumerate(audio_items):
            from backend.integrations.subtitles import write_subtitle_files
            from backend.integrations.subtitle_burn import parse_srt
            original_srt = subtitle_file_for_audio(output_dir, audio, subtitle_items)
            if original_srt.is_file():
                json_path = original_srt.with_suffix(".json")
                cues = json.loads(json_path.read_text(encoding="utf-8"))["segments"] if json_path.is_file() else parse_srt(original_srt.read_text(encoding="utf-8-sig"))
                staged = output_dir / f"draft-subtitles-{index}-{batch}.wav"
                created.append(staged.with_suffix(""))
                paths = write_subtitle_files(staged, cues)
                replacement = {"draft_id": audio["draft_id"], "voice": audio["voice"], **{f"{key}_url": f"/media/{item['output_dir']}/{path.name}" for key, path in paths.items()}}
                subtitle_items[:] = [track for track in subtitle_items if not (track.get("draft_id") == audio["draft_id"] and track.get("voice") == audio["voice"])] + [replacement]
            for orientation in ("landscape", "portrait"):
                if is_deleting(wid):
                    return None
                name = output_name(index) if output_name else f"video-{index + 1}-{batch}.mp4"
                name = name.replace(".mp4", f"-{orientation}.mp4")
                if Path(name).name != name:
                    raise RuntimeError("视频文件名无效")
                group = list(groups.values())[index % len(groups)]
                cover = output_dir / _media_name(group["1:1"]["url"])
                background_cover = output_dir / _media_name(group["16:9" if orientation == "landscape" else "9:16"]["url"])
                narration = output_dir / _media_name(str(audio["url"]))
                out = output_dir / name
                created.append(out.with_suffix(""))
                subtitles = subtitle_file_for_audio(output_dir, audio, subtitle_items) if settings.get("burn_subtitles") else None
                if subtitles is not None and not subtitles.is_file():
                    raise RuntimeError("找不到与配音对应的 SRT 字幕，无法烧录")
                narration_duration = narration_durations[index]
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        player_command(ffmpeg, cover, narration, out, background_cover=background_cover, record_label_image_id=settings.get("record_label_image_id"), duration=narration_duration, background_overlay_enabled=settings.get("background_overlay_enabled", True), background_overlay_opacity=settings.get("background_overlay_opacity", .25), background_blur_enabled=settings.get("background_blur_enabled", False), background_blur_strength=settings.get("background_blur_strength", 20), orientation=orientation, stock_manifest=stock_manifest, subtitles=subtitles, subtitle_style=settings.get("subtitle_style")),
                        capture_output=True,
                        timeout=video_encode_timeout(narration_duration),
                    )
                except subprocess.TimeoutExpired as exc:
                    waited = int(exc.timeout)
                    if narration_duration:
                        raise RuntimeError(f"视频合成超时：配音 {int(narration_duration)} 秒，编码等待超过 {waited} 秒") from exc
                    raise RuntimeError(f"视频合成超时：编码等待超过 {waited} 秒") from exc
                if result.returncode != 0:
                    detail = result.stderr.decode("utf-8", errors="replace")[-1000:]
                    raise RuntimeError(f"视频合成失败，已保留原来的视频（如有）：{detail}")
                if result.returncode == 0:
                    resolution, duration = await asyncio.to_thread(probe_video_metadata, out)
                    videos.append({
                        "draft_id": audio["draft_id"], "voice": audio["voice"],
                        "url": f"/media/{item['output_dir']}/{out.name}",
                        "background_music": background_music.get("name") if background_music else "",
                        "orientation": orientation,
                        "source": settings.get("stock_video_provider") if stock_manifest else "local",
                        "resolution": resolution or ("1920 × 1080" if orientation == "landscape" else "1080 × 1920"),
                        "duration": duration,
                    })
        completed = True
        return videos
    finally:
        for stem in created:
            for path in output_dir.glob(stem.name + ".*"):
                if not completed or path.name.endswith((".background.png", ".layer.png", ".disc.png")):
                    path.unlink(missing_ok=True)


async def regenerate_workflow_videos(
    wid: str,
    *,
    db: Callable[[], AbstractContextManager[Any]],
    workflow_row: Callable[[Any], dict[str, Any]],
    get_settings: Callable[[], dict[str, Any]],
    media_dir: Callable[[str], Path],
    save: Callable[..., None],
    is_deleting: Callable[[str], bool],
    regenerating: set[str],
    llm: Callable[..., Any],
    video_command: Callable[..., list[str]],
    download_stock_videos: Callable[..., Any],
    log_request: Callable[[str, str, dict[str, Any]], None],
) -> None:
    """Render videos again from the latest saved narration, covers, and subtitles."""
    stamp = time.time_ns()
    output_dir: Path | None = None
    succeeded = False
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row or is_deleting(wid):
            return
        item = workflow_row(row)
        if item.get("status") != "completed":
            return
        settings = get_settings()
        output_dir = media_dir(item["output_dir"])
        audio_items = item.get("audio") or []
        original_files = {p.name for p in output_dir.iterdir()}
        new_covers = [dict(cover) for cover in item.get("covers") or []]
        new_subtitles = [dict(track) for track in item.get("subtitles") or []]
        videos = await compose_videos(
            wid, item, settings, output_dir, new_covers, audio_items,
            description=item.get("description") or "",
            is_deleting=is_deleting, llm=llm, video_command=video_command,
            download_stock_videos=download_stock_videos, log_request=log_request,
            output_name=lambda index: f"video-{index + 1}-{stamp}.mp4",
            subtitle_items=new_subtitles,
        )
        if videos is None or is_deleting(wid):
            return
        if len(videos) != len(audio_items) * 2:
            raise RuntimeError("视频合成失败，已保留原来的视频")
        with db() as conn:
            current = conn.execute("SELECT status FROM workflows WHERE id=?", (wid,)).fetchone()
        if not current or current["status"] != "completed" or is_deleting(wid):
            return
        previous = item.get("videos") or []
        save(wid, payload_update={"videos": videos, "subtitles": new_subtitles, "covers": new_covers, "video_regenerating": False, "video_error": ""})
        succeeded = True
        try:
            remove_replaced_videos(output_dir, previous, videos)
            remove_replaced_narration(output_dir, [], item.get("subtitles") or [], audio_items, new_subtitles)
        except OSError:
            return
    except Exception as exc:
        if not is_deleting(wid):
            save(wid, payload_update={"video_regenerating": False, "video_error": str(exc)[:500]})
    finally:
        regenerating.discard(wid)
        if output_dir is not None and not succeeded:
            discard_regeneration_files(output_dir, stamp)
            if "original_files" in locals() and output_dir.is_dir():
                for path in output_dir.iterdir():
                    if path.name not in original_files and path.name.startswith(("cover-generated-", "draft-subtitles-", "video-")) and path.is_file():
                        path.unlink(missing_ok=True)


async def regenerate_workflow_audio(
    wid: str,
    *,
    db: Callable[[], AbstractContextManager[Any]],
    workflow_row: Callable[[Any], dict[str, Any]],
    get_settings: Callable[[], dict[str, Any]],
    media_dir: Callable[[str], Path],
    save: Callable[..., None],
    is_deleting: Callable[[str], bool],
    regenerating: set[str],
    speech: Callable[..., Any],
    audio_extension: Callable[[str], str],
    generate_subtitles: Callable[[Path, str, str], dict[str, Path]],
    subtitle_language: Callable[[str], str],
) -> None:
    """Replace narration and its subtitles with a newly selected voice."""
    stamp = time.time_ns()
    output_dir: Path | None = None
    succeeded = False
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if not row or is_deleting(wid):
            return
        item = workflow_row(row)
        if item.get("status") != "completed":
            return
        voice = str(item.get("audio_regenerate_voice") or "").strip()
        drafts = [draft for draft in item.get("polished_drafts") or [] if str(draft.get("text") or "").strip()]
        if not voice or not drafts:
            raise RuntimeError("缺少音色或分享稿，已保留原来的配音和字幕")
        settings = get_settings()
        output_dir = media_dir(item["output_dir"])
        output_dir.mkdir(parents=False, exist_ok=True)
        speech_rate = item.get("speech_rate", settings.get("speech_rate", 0))
        background_music = item.get("background_music")
        audio_items: list[dict[str, Any]] = []
        subtitle_items: list[dict[str, Any]] = []
        for index, draft in enumerate(drafts):
            if is_deleting(wid):
                return
            base = output_dir / f"draft-{index + 1}-voice-1-{stamp}"
            target = base.with_suffix(audio_extension(settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")))
            used_real_speech = await speech(
                draft["text"], voice, speech_rate, settings, target, background_music,
                item.get("background_music_volume", .2), item.get("background_music_fade_in", 2),
                item.get("background_music_fade_out", 2),
            )
            if is_deleting(wid):
                return
            actual = target if target.exists() else base.with_suffix(".wav")
            if not actual.is_file() or actual.stat().st_size <= 0:
                raise RuntimeError("配音生成失败，已保留原来的配音和字幕")
            await asyncio.to_thread(generate_subtitles, actual, draft.get("text", ""), subtitle_language(voice))
            if is_deleting(wid):
                return
            subtitle_paths = {suffix: actual.with_suffix(suffix) for suffix in _SUBTITLE_SUFFIXES}
            if any(not path.is_file() for path in subtitle_paths.values()):
                raise RuntimeError("字幕生成失败，已保留原来的配音和字幕")
            audio_items.append({
                "draft_id": draft["id"], "voice": voice, "speech_rate": speech_rate,
                "url": f"/media/{item['output_dir']}/{actual.name}",
                "provider": "azure" if used_real_speech else "demo",
            })
            subtitle_items.append({
                "draft_id": draft["id"], "voice": voice,
                "srt_url": f"/media/{item['output_dir']}/{subtitle_paths['.srt'].name}",
                "txt_url": f"/media/{item['output_dir']}/{subtitle_paths['.txt'].name}",
                "json_url": f"/media/{item['output_dir']}/{subtitle_paths['.json'].name}",
            })
        with db() as conn:
            current = conn.execute("SELECT status FROM workflows WHERE id=?", (wid,)).fetchone()
        if not current or current["status"] != "completed" or is_deleting(wid):
            return
        previous_audio = item.get("audio") or []
        previous_subtitles = item.get("subtitles") or []
        save(wid, payload_update={
            "audio": audio_items, "subtitles": subtitle_items, "voices": [voice],
            "audio_regenerating": False, "audio_error": "", "audio_regenerate_voice": "",
        })
        succeeded = True
        try:
            remove_replaced_narration(output_dir, previous_audio, previous_subtitles, audio_items, subtitle_items)
        except OSError:
            return
    except Exception as exc:
        if not is_deleting(wid):
            save(wid, payload_update={"audio_regenerating": False, "audio_error": str(exc)[:500], "audio_regenerate_voice": ""})
    finally:
        regenerating.discard(wid)
        if output_dir is not None and not succeeded:
            discard_audio_regeneration_files(output_dir, stamp)
