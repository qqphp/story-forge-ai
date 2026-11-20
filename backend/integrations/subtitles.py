"""Subtitle files aligned to narration audio with stable-ts."""

import json
import re
import unicodedata
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_MODEL: Any = None
_MODEL_NAME: str | None = None
_MODEL_LOCK = threading.RLock()
_PROCESS_LOCK = threading.Lock()
SUBTITLE_TIMEOUT = 900


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


def clean_caption(text: str, prefix: str = "", suffix: str = "") -> str:
    chars = []
    for i, char in enumerate(text):
        previous = text[i - 1] if i else prefix[-1:]
        following = text[i + 1] if i + 1 < len(text) else suffix[:1]
        protected = (char in ".,:/-" and previous.isdigit() and following.isdigit()) or (char in "'’‐-" and previous.isascii() and previous.isalpha() and following.isascii() and following.isalpha())
        if unicodedata.category(char).startswith("P") and not protected:
            if previous.isascii() and previous.isalnum() and following.isascii() and following.isalnum():
                chars.append(" ")
        else:
            chars.append(char)
    return re.sub(r"[ \t]+", " ", "".join(chars)).strip()


def normalize_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for cue in cues:
        text = clean_caption(str(cue.get("text", "")))
        if not text:
            continue
        start = max(0.0, float(cue.get("start", 0)))
        end = max(start, float(cue.get("end", start)))
        item: dict[str, Any] = {"start": round(start, 3), "end": round(end, 3), "text": text}
        words = []
        raw_words = cue.get("words") or []
        for index, word in enumerate(raw_words):
            prefix = str(raw_words[index-1].get("word", "")) if index else ""
            suffix = str(raw_words[index+1].get("word", "")) if index+1 < len(raw_words) else ""
            token = clean_caption(str(word.get("word", "")), prefix, suffix)
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
    joined = ""
    for segment in segments:
        text = segment["text"]
        if joined and text and joined[-1].isascii() and joined[-1].isalnum() and text[0].isascii() and text[0].isalnum():
            joined += " "
        joined += text
    payload = {"text": joined, "segments": segments}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def prepare_cues(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use alignment words for short phrases; legacy SRT stays within its cue span."""
    result = []
    for cue in cues:
        words = cue.get("words") or []
        if words:
            group = []
            for word in words:
                token = str(word.get("word", ""))
                if group and len(clean_caption("".join(str(w["word"]) for w in group) + token)) > 16:
                    result.append({"start": group[0]["start"], "end": group[-1]["end"], "text": "".join(str(w["word"]) for w in group), "words": group})
                    group = []
                group.append(word)
                if token.rstrip().endswith(tuple("，。！？；,!?;")):
                    result.append({"start": group[0]["start"], "end": group[-1]["end"], "text": "".join(str(w["word"]) for w in group), "words": group})
                    group = []
            if group:
                result.append({"start": group[0]["start"], "end": group[-1]["end"], "text": "".join(str(w["word"]) for w in group), "words": group})
        else:
            text = clean_caption(str(cue.get("text", "")))
            tokens = re.findall(r"[A-Za-z0-9]+(?:[.'’,:/‐-][A-Za-z0-9]+)*|\s+|.", text)
            pieces = []
            piece = ""
            for token in tokens:
                if piece and len(piece + token) > 16:
                    pieces.append(piece)
                    piece = ""
                piece += token
            if piece:
                pieces.append(piece)
            cursor = float(cue.get("start", 0)); end = float(cue.get("end", cursor))
            for piece in pieces:
                stop = min(end, cursor + (end-float(cue.get("start", 0))) * len(piece) / len(text))
                result.append({"start": cursor, "end": stop, "text": piece}); cursor=stop
    return normalize_cues(result)


def write_subtitle_files(audio_path: Path, cues: list[dict[str, Any]]) -> dict[str, Path]:
    """Write srt, txt and json next to the narration file."""
    cues = prepare_cues(cues)
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


def _align_subtitles(audio_path: Path, text: str, language: str) -> dict[str, Path]:
    """Align the spoken script to the audio and write the three subtitle files."""
    with _MODEL_LOCK:
        model = _load_model()
        if text.strip():
            result = model.align(str(audio_path), text, language=language, verbose=False)
        else:
            result = model.transcribe(str(audio_path), language=language, verbose=False)
    return write_subtitle_files(audio_path, _cues_from_result(result))


def generate_subtitles(audio_path: Path, text: str, language: str) -> dict[str, Path]:
    """Bound model work to one killable process, isolated from the API runtime."""
    if not _PROCESS_LOCK.acquire(timeout=SUBTITLE_TIMEOUT):
        raise RuntimeError("字幕任务排队超时，请稍后重试")
    try:
        env = {**os.environ, "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "PYTHONIOENCODING": "utf-8"}
        try:
            result = subprocess.run(
                [sys.executable, "-m", "backend.integrations.subtitle_worker"],
                input=json.dumps({"audio_path": str(audio_path.resolve()), "text": text, "language": language}).encode("utf-8"),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                cwd=Path(__file__).resolve().parents[2], env=env, timeout=SUBTITLE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"字幕生成超时（超过 {SUBTITLE_TIMEOUT} 秒），已终止字幕进程，请重试") from exc
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[-1000:]
            raise RuntimeError(f"字幕生成失败：{detail or '字幕进程异常退出'}")
        paths = {suffix: audio_path.with_suffix('.' + suffix) for suffix in ("srt", "txt", "json")}
        if any(not path.is_file() or not path.stat().st_size for path in paths.values()):
            raise RuntimeError("字幕生成失败：字幕文件不完整")
        return paths
    finally:
        _PROCESS_LOCK.release()
