"""FFmpeg command construction and media probing."""

import os
from pathlib import Path
import subprocess


def probe_audio_duration(path: Path) -> float | None:
    ffprobe = os.getenv("FFPROBE_PATH", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def video_command(
    ffmpeg: str,
    cover: Path,
    narration: Path,
    output: Path,
    music: Path | None = None,
    volume: float = .2,
    fade_in: float = 2,
    fade_out: float = 2,
    duration: float | None = None,
    orientation: str = "portrait",
    stock_manifest: Path | None = None,
) -> list[str]:
    width, height = (1280, 720) if orientation == "landscape" else (720, 1280)
    if stock_manifest:
        command = [ffmpeg, "-y", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", str(stock_manifest), "-i", str(narration)]
    else:
        command = [ffmpeg, "-y", "-loop", "1", "-i", str(cover), "-i", str(narration)]
    if music:
        command += ["-stream_loop", "-1", "-i", str(music)]
        music_filters = [f"volume={max(0, min(1, volume)):.2f}"]
        if fade_in > 0:
            music_filters.append(f"afade=t=in:st=0:d={fade_in:g}")
        if fade_out > 0 and duration:
            music_filters.append(f"afade=t=out:st={max(0, duration - fade_out):g}:d={min(fade_out, duration):g}")
        command += ["-filter_complex", f"[2:a]{','.join(music_filters)}[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v", "-map", "[aout]"]
    elif stock_manifest:
        command += ["-map", "0:v", "-map", "1:a"]
    command += ["-c:v", "libx264"]
    if not stock_manifest:
        command += ["-tune", "stillimage"]
    command += ["-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", "-shortest",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,format=yuv420p", str(output)]
    return command


def write_concat_manifest(path: Path, videos: list[Path]) -> Path:
    """Create an FFmpeg concat playlist; ``-stream_loop -1`` repeats it to narration length."""
    def quote(value: Path) -> str:
        return value.resolve().as_posix().replace("'", "'\\''")
    path.write_text("".join(f"file '{quote(video)}'\n" for video in videos), encoding="utf-8")
    return path


def normalize_stock_videos(ffmpeg: str, videos: list[Path], output_dir: Path, orientation: str) -> list[Path]:
    """Normalize varying provider clips so FFmpeg's concat demuxer can loop them safely."""
    width, height = (1280, 720) if orientation == "landscape" else (720, 1280)
    normalized: list[Path] = []
    for index, source in enumerate(videos, 1):
        target = output_dir / f"stock-normalized-{index}.mp4"
        result = subprocess.run([
            ffmpeg, "-y", "-i", str(source), "-an", "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target),
        ], capture_output=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"第 {index} 段无版权视频标准化失败")
        normalized.append(target)
    return normalized
