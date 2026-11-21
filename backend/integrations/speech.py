"""Azure Speech synthesis and its local/offline fallbacks."""

import asyncio
import html
import io
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import wave


MAX_SEGMENT_CHARS = 1200
VERIFY_DURATION_AFTER_CHARS = 350
NEAR_AZURE_LIMIT_SECONDS = 570
PARAGRAPH_END = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")
SENTENCE_END = re.compile(r"[。！？!?…]+[”’」』）)]*|\.(?=\s|$)|\n")
CLAUSE_END = re.compile(r"[，、；：,;:]|\s+")


def _safe_rate(rate: int) -> int:
    return max(-50, min(100, int(rate)))


def split_narration(text: str, limit: int) -> list[str]:
    """Choose a paragraph or sentence boundary near each limit, preserving the full script."""
    parts = []
    while len(text) > limit:
        window = text[:limit]
        cut = limit
        for boundary in (PARAGRAPH_END, SENTENCE_END, CLAUSE_END):
            end = max((match.end() for match in boundary.finditer(window)), default=0)
            if end >= limit * .6:
                cut = end
                break
        parts.append(text[:cut])
        text = text[cut:]
    if text:
        parts.append(text)
    return parts


def speech_api_url(base: str, endpoint: str) -> str:
    return f"{base.rstrip('/')}/{endpoint.lstrip('/')}"


def make_demo_wav(path: Path, seconds: float = 3.0) -> None:
    rate = 24000
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            envelope = min(1, i / 1000, (rate * seconds - i) / 1000)
            sample = int(2600 * envelope * math.sin(2 * math.pi * (190 + 40 * math.sin(i / rate)) * i / rate))
            frames += sample.to_bytes(2, "little", signed=True)
        out.writeframes(frames)


def build_ssml(
    text: str,
    voice: str,
    rate: int,
    voice_locale: Callable[[str], str],
    background_music: dict[str, Any] | None = None,
    background_volume: float = .2,
    background_fade_in: float = 2,
    background_fade_out: float = 2,
) -> str:
    safe_rate = _safe_rate(rate)
    namespace = ' xmlns="http://www.w3.org/2001/10/synthesis"'
    if background_music:
        namespace += ' xmlns:mstts="https://www.w3.org/2001/mstts"'
    background = ""
    if background_music:
        volume = max(0, min(1, float(background_volume)))
        volume_text = f"{volume:.2f}".rstrip("0").rstrip(".")
        fade_in = max(0, min(10000, round(float(background_fade_in) * 1000)))
        fade_out = max(0, min(10000, round(float(background_fade_out) * 1000)))
        source = html.escape(str(background_music["url"]), quote=True)
        background = (f'<mstts:backgroundaudio src="{source}" volume="{volume_text}" '
                      f'fadein="{fade_in}" fadeout="{fade_out}"/>')
    paragraphs = "".join(f"<p>{html.escape(line.strip())}</p>" for line in text.splitlines() if line.strip())
    return (f'<speak version="1.0"{namespace} xml:lang="{html.escape(voice_locale(voice), quote=True)}">{background}'
            f'<voice name="{html.escape(voice, quote=True)}">'
            f'<prosody rate="{safe_rate:+d}%">{paragraphs}</prosody></voice></speak>')


def audio_extension(output_format: str) -> str:
    if output_format.startswith("riff-"):
        return ".wav"
    if output_format.startswith("amr-"):
        return ".amr"
    if output_format.startswith("ogg-"):
        return ".ogg"
    if output_format.startswith("webm-"):
        return ".webm"
    if "mp3" in output_format:
        return ".mp3"
    if "opus" in output_format:
        return ".opus"
    if output_format.startswith("raw-"):
        return ".pcm"
    if output_format.startswith("g722-"):
        return ".g722"
    return ".audio"


def _finish_narration(voice_file: Path, output: Path, fmt: str, duration: float,
                      music: Path | None, volume: float, fade_in: float, fade_out: float) -> Path:
    extension = audio_extension(fmt)
    sample_rate = re.search(r"-(\d+)khz-", fmt)
    bitrate = re.search(r"-(\d+)(?:kbitrate|kbps)-", fmt)
    if extension == ".mp3":
        encoding = ["-c:a", "libmp3lame", "-f", "mp3"]
    elif extension in (".ogg", ".opus", ".webm"):
        encoding = ["-c:a", "libopus", "-f", "webm" if extension == ".webm" else "ogg"]
    else:
        extension = ".wav"
        encoding = ["-c:a", "pcm_s16le", "-f", "wav"]
    if bitrate and extension != ".wav":
        encoding += ["-b:a", f"{bitrate[1]}k"]
    if sample_rate and extension != ".wav":
        encoding += ["-ar", f"{sample_rate[1]}000"]
    target = output.with_suffix(extension)
    staged = voice_file.with_name(f"finished{extension}")
    if music is None and extension == ".wav":
        voice_file.replace(target)
        return target
    command = [os.getenv("FFMPEG_PATH", "ffmpeg"), "-v", "error", "-y", "-i", str(voice_file)]
    if music is not None:
        fade_in = min(fade_in, duration)
        fade_out = min(fade_out, duration)
        filters = f"volume={volume},atrim=duration={duration:.6f}"
        if fade_in:
            filters += f",afade=t=in:d={fade_in}"
        if fade_out:
            filters += f",afade=t=out:st={duration - fade_out:.6f}:d={fade_out}"
        command += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                    f"[1:a]aformat=channel_layouts=mono,{filters}[bed];[0:a][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.98:latency=1[mix]",
                    "-map", "[mix]"]
    result = subprocess.run([*command, "-ac", "1", *encoding, str(staged)], capture_output=True, timeout=300)
    if result.returncode or not staged.is_file() or not staged.stat().st_size:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"配音合并失败。{detail}")
    staged.replace(target)
    return target


async def synthesize(
    text: str,
    voice: str,
    rate: int,
    settings: dict[str, Any],
    output: Path,
    build_ssml: Callable[..., str],
    make_fallback: Callable[[Path], None],
    log_request: Callable[[str, str, dict[str, Any]], None],
    client_factory: Callable[..., Any],
    background_music: dict[str, Any] | None = None,
    background_volume: float = .2,
    background_fade_in: float = 2,
    background_fade_out: float = 2,
) -> Path | None:
    key = settings.get("azure_speech_key")
    if not key:
        make_fallback(output.with_suffix(".wav"))
        return None
    base = settings.get("azure_speech_base", "https://eastus.tts.speech.microsoft.com")
    fmt = settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")
    url = speech_api_url(base, "/cognitiveservices/v1")
    if not text.strip():
        raise ValueError("配音文稿为空")
    rate_factor = 1 + _safe_rate(rate) / 100
    parts = [part for part in split_narration(text, int(MAX_SEGMENT_CHARS * min(1, rate_factor))) if part.strip()]
    direct = len(text) <= VERIFY_DURATION_AFTER_CHARS * min(1, rate_factor)
    pcm_rate = 48000 if "-48khz-" in fmt else 24000
    pcm_format = f"riff-{pcm_rate // 1000}khz-16bit-mono-pcm"

    with tempfile.TemporaryDirectory(prefix="speech-", dir=output.parent) as directory:
        root = Path(directory)
        async with client_factory(timeout=120) as client:
            async def request(part: str, index: str) -> bytes:
                request_format = fmt if direct else pcm_format
                ssml = build_ssml(part, voice, rate, background_music if direct else None,
                                  background_volume, background_fade_in, background_fade_out)
                log_request("配音生成", url, {"voice": voice, "rate": rate, "format": request_format,
                                              "part": index, "parts": len(parts), "text": part, "ssml": ssml,
                                              "background_music": background_music, "background_volume": background_volume,
                                              "background_fade_in": background_fade_in, "background_fade_out": background_fade_out})
                response = await client.post(
                    url,
                    headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                             "X-Microsoft-OutputFormat": request_format, "User-Agent": "StoryForge"},
                    content=ssml.encode("utf-8"),
                )
                response.raise_for_status()
                if not response.content:
                    raise RuntimeError(f"微软语音服务未返回第 {index} 段的音频")
                return response.content

            if direct:
                staged = root / output.name
                staged.write_bytes(await request(text, "1"))
                staged.replace(output)
                return output

            voice_file = root / "narration.wav"
            with wave.open(str(voice_file), "wb") as joined:
                joined.setparams((1, 2, pcm_rate, 0, "NONE", "not compressed"))
                async def append(part: str, index: str) -> int:
                    data = await request(part, index)
                    with wave.open(io.BytesIO(data), "rb") as segment:
                        frames = segment.getnframes()
                        if (segment.getnchannels(), segment.getsampwidth(), segment.getframerate()) != (1, 2, pcm_rate) or not frames:
                            raise ValueError(f"第 {index} 段音频格式有误")
                        if frames < NEAR_AZURE_LIMIT_SECONDS * pcm_rate:
                            samples = segment.readframes(frames)
                            if len(samples) != frames * 2:
                                raise ValueError(f"第 {index} 段音频不完整")
                            joined.writeframesraw(samples)
                            return frames
                    part = part.strip()
                    subparts = [piece for piece in split_narration(part, max(1, (len(part) + 1) // 2)) if piece.strip()]
                    if len(subparts) < 2:
                        raise ValueError(f"第 {index} 段可能被微软截断，无法继续细分")
                    count = 0
                    for i, piece in enumerate(subparts, 1):
                        count += await append(piece, f"{index}.{i}")
                    return count

                frames = 0
                for i, part in enumerate(parts, 1):
                    frames += await append(part, str(i))
        music = await download_background_music(background_music, root, client_factory) if background_music else None
        return await asyncio.to_thread(_finish_narration, voice_file, output, fmt, frames / pcm_rate, music,
                                       background_volume, background_fade_in, background_fade_out)


async def download_background_music(
    music: dict[str, Any], output_dir: Path, client_factory: Callable[..., Any],
) -> Path:
    suffix = Path(urlparse(music["url"]).path).suffix.lower()
    if suffix not in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm"):
        suffix = ".audio"
    target = output_dir / f"background{suffix}"
    async with client_factory(timeout=120, follow_redirects=True) as client:
        response = await client.get(music["url"])
        response.raise_for_status()
    target.write_bytes(response.content)
    return target
