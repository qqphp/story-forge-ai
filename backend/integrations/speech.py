"""Azure Speech synthesis and its local/offline fallbacks."""

import html
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import wave


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
    safe_rate = max(-50, min(100, int(rate)))
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
    return (f'<speak version="1.0"{namespace} xml:lang="{html.escape(voice_locale(voice), quote=True)}">{background}'
            f'<voice name="{html.escape(voice, quote=True)}">'
            f'<prosody rate="{safe_rate:+d}%">{html.escape(text)}</prosody></voice></speak>')


def audio_extension(output_format: str) -> str:
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
) -> bool:
    key = settings.get("azure_speech_key")
    if not key:
        make_fallback(output.with_suffix(".wav"))
        return False
    region = settings.get("azure_speech_region", "eastus")
    fmt = settings.get("voice_format", "audio-24khz-48kbitrate-mono-mp3")
    ssml = build_ssml(text, voice, rate, background_music, background_volume, background_fade_in, background_fade_out)
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    log_request("配音生成", url, {"voice": voice, "rate": rate, "format": fmt, "text": text,
                                  "background_music": background_music, "background_volume": background_volume,
                                  "background_fade_in": background_fade_in, "background_fade_out": background_fade_out})
    async with client_factory(timeout=120) as client:
        response = await client.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": fmt, "User-Agent": "StoryForge"},
            content=ssml.encode("utf-8"),
        )
        response.raise_for_status()
        output.write_bytes(response.content)
    return True


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
