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
) -> list[str]:
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
    command += ["-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p", "-shortest", "-vf", "scale=720:1280,format=yuv420p", str(output)]
    return command
