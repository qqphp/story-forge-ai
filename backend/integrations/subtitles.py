"""Subtitle files aligned to narration audio with stable-ts."""

import json
import os
import threading
from pathlib import Path
from typing import Any

_MODEL: Any = None
_MODEL_NAME: str | None = None
_MODEL_LOCK = threading.RLock()


def subtitle_language(voice: str) -> str:
    """Map a Microsoft voice name to a Whisper language code."""
    prefix = voice.split("-", 1)[0].lower()
    return prefix or "zh"


def _timestamp(seconds: float) -> str:
    millis = max(0, int(round(float(seconds) * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def normalize_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for cue in cues:
        text = str(cue.get("text", "")).strip()
        if not text:
            continue
        start = max(0.0, float(cue.get("start", 0)))
        end = max(start, float(cue.get("end", start)))
        item: dict[str, Any] = {"start": round(start, 3), "end": round(end, 3), "text": text}
        words = []
        for word in cue.get("words") or []:
            token = str(word.get("word", "")).strip()
            if not token:
                continue
            word_start = max(0.0, float(word.get("start", start)))
            word_end = max(word_start, float(word.get("end", end)))
            words.append({"word": token, "start": round(word_start, 3), "end": round(word_end, 3)})
        if words:
            item["words"] = words
        normalized.append(item)
    if not normalized:
        raise RuntimeError("没有从音频中对齐出字幕")
    return normalized


def render_srt(cues: list[dict[str, Any]]) -> str:
    blocks = []
    for index, cue in enumerate(normalize_cues(cues), 1):
        blocks.append(f"{index}\n{_timestamp(cue['start'])} --> {_timestamp(cue['end'])}\n{cue['text']}\n")
    return "\n".join(blocks)


def render_txt(cues: list[dict[str, Any]]) -> str:
    return "".join(f"{cue['text']}\n" for cue in normalize_cues(cues))


def render_json(cues: list[dict[str, Any]]) -> str:
    segments = []
    for index, cue in enumerate(normalize_cues(cues), 1):
        segment = {"id": index, "start": cue["start"], "end": cue["end"], "text": cue["text"]}
        if "words" in cue:
            segment["words"] = cue["words"]
        segments.append(segment)
    payload = {"text": "".join(segment["text"] for segment in segments), "segments": segments}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_subtitle_files(audio_path: Path, cues: list[dict[str, Any]]) -> dict[str, Path]:
    """Write srt, txt and json next to the narration file."""
    targets = {
        "srt": audio_path.with_suffix(".srt"),
        "txt": audio_path.with_suffix(".txt"),
        "json": audio_path.with_suffix(".json"),
    }
    targets["srt"].write_text(render_srt(cues), encoding="utf-8")
    targets["txt"].write_text(render_txt(cues), encoding="utf-8")
    targets["json"].write_text(render_json(cues), encoding="utf-8")
    return targets


def _load_model() -> Any:
    global _MODEL, _MODEL_NAME
    name = os.getenv("STORYFORGE_WHISPER_MODEL", "small")
    with _MODEL_LOCK:
        if _MODEL is None or _MODEL_NAME != name:
            try:
                import stable_whisper
            except ImportError as exc:
                raise RuntimeError("生成字幕需要安装 stable-ts") from exc
            _MODEL = stable_whisper.load_model(name)
            _MODEL_NAME = name
        return _MODEL


def _cues_from_result(result: Any) -> list[dict[str, Any]]:
    cues = []
    for segment in result.segments:
        cue: dict[str, Any] = {"start": segment.start, "end": segment.end, "text": segment.text}
        if getattr(segment, "words", None):
            cue["words"] = [
                {"word": word.word, "start": word.start, "end": word.end}
                for word in segment.words
            ]
        cues.append(cue)
    return cues


def generate_subtitles(audio_path: Path, text: str, language: str) -> dict[str, Path]:
    """Align the spoken script to the audio and write the three subtitle files."""
    with _MODEL_LOCK:
        model = _load_model()
        if text.strip():
            result = model.align(str(audio_path), text, language=language)
        else:
            result = model.transcribe(str(audio_path), language=language)
    return write_subtitle_files(audio_path, _cues_from_result(result))
