"""Turn an SRT cue file into an ASS track with a translucent dark box."""

import re
from pathlib import Path

from backend.integrations.fonts import bundled_fonts_dir, subtitle_font_family


# ASS stores alpha inverted: 00 is opaque and FF is fully transparent.
WHITE = "&H00FFFFFF"
TRANSLUCENT_DARK = "&H80000000"
MAX_SUBTITLE_LINES = 2
_SIDE_MARGIN = 48
_SRT_CLOCK = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
_BREAK_AFTER = frozenset("，。！？；、：,.!?;: ")
_KEEP_WITH_PREVIOUS = frozenset("，。！？；、：,.!?;:》）」』】〉》\"'）")


def _clock_seconds(match: re.Match[str]) -> float:
    hours, minutes, seconds, fraction = (int(part) for part in match.groups())
    millis = int(f"{fraction:<03}"[:3])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_srt(text: str) -> list[dict[str, float | str]]:
    cues: list[dict[str, float | str]] = []
    for block in re.split(r"\r?\n[ \t]*\r?\n", text.strip().lstrip("\ufeff")):
        lines = block.splitlines()
        arrow = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if arrow is None:
            continue
        start_text, end_text = (part.strip() for part in lines[arrow].split("-->", 1))
        start_match, end_match = _SRT_CLOCK.search(start_text), _SRT_CLOCK.search(end_text)
        if not start_match or not end_match:
            continue
        caption = "\n".join(line.strip() for line in lines[arrow + 1:]).strip()
        if not caption:
            continue
        start = _clock_seconds(start_match)
        cues.append({"start": start, "end": max(start, _clock_seconds(end_match)), "text": caption})
    return cues


def ass_time(seconds: float) -> str:
    total = max(0, int(round(float(seconds) * 100)))
    hours, total = divmod(total, 360_000)
    minutes, total = divmod(total, 6_000)
    secs, centis = divmod(total, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\r\n", "\n").replace("\n", r"\N")


def subtitle_layout(width: int, height: int) -> tuple[int, int, int]:
    short_side = min(width, height)
    font_size = max(42, round(short_side * 0.048))
    margin_v = max(48, round(height * (0.08 if height > width else 0.06)))
    padding = max(8, round(font_size * 0.22))
    return font_size, margin_v, padding


def glyph_units(char: str) -> float:
    """Estimate how much of an em a glyph occupies. Han glyphs are a full em."""
    if char.isspace():
        return 0.33
    code = ord(char)
    if (
        0x2E80 <= code <= 0x9FFF
        or 0xAC00 <= code <= 0xD7AF
        or 0xF900 <= code <= 0xFAFF
        or 0xFE30 <= code <= 0xFE4F
        or 0xFF01 <= code <= 0xFF60
        or 0xFFE0 <= code <= 0xFFE6
        or 0x20000 <= code <= 0x3FFFD
    ):
        return 1.0
    return 0.55


def text_units(text: str) -> float:
    return sum(glyph_units(char) for char in text)


def subtitle_line_capacity(width: int, height: int) -> float:
    """How many ems fit on one caption line inside the side margins and box padding."""
    font_size, _margin_v, padding = subtitle_layout(width, height)
    usable = width - _SIDE_MARGIN * 2 - padding * 2
    return max(6.0, usable / font_size * 0.92)


def _break_index(text: str, max_units: float) -> int:
    used = 0.0
    limit = 1
    for index, char in enumerate(text):
        used += glyph_units(char)
        if used > max_units and index > 0:
            break
        limit = index + 1
    window = text[:limit]
    used = 0.0
    best = 0
    for index, char in enumerate(window):
        used += glyph_units(char)
        if char in _BREAK_AFTER and used >= max_units * 0.45:
            best = index + 1
    cut = best or limit
    while cut < len(text) and text[cut] in _KEEP_WITH_PREVIOUS and text_units(text[:cut + 1]) <= max_units * 1.08:
        cut += 1
    return max(1, min(cut, len(text)))


def wrap_subtitle_text(text: str, max_units: float) -> list[str]:
    """Break one cue into lines that stay inside the frame. Existing line breaks are kept."""
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").split("\n"):
        rest = paragraph.strip()
        if not rest:
            continue
        while rest:
            if text_units(rest) <= max_units:
                lines.append(rest)
                break
            cut = _break_index(rest, max_units)
            lines.append(rest[:cut].strip())
            rest = rest[cut:].strip()
    return lines or [text.strip()]


def layout_subtitle_cues(cues: list[dict[str, float | str]], max_units: float, max_lines: int = MAX_SUBTITLE_LINES) -> list[dict[str, float | str]]:
    """Wrap each cue, and give any further lines their own time slice instead of a tall block."""
    laid: list[dict[str, float | str]] = []
    for cue in cues:
        lines = wrap_subtitle_text(str(cue["text"]), max_units)
        groups = [lines[index:index + max_lines] for index in range(0, len(lines), max_lines)]
        while len(groups) >= 2 and len(groups[-1]) == 1 and len(groups[-2]) > 1:
            groups[-1].insert(0, groups[-2].pop())
        start, end = float(cue["start"]), float(cue["end"])
        weights = [max(text_units("".join(group)), 1.0) for group in groups]
        total = sum(weights)
        span = max(0.0, end - start)
        cursor = start
        for index, group in enumerate(groups):
            if index == len(groups) - 1:
                piece_end = end
            else:
                piece_end = min(end, cursor + span * weights[index] / total)
            laid.append({"start": cursor, "end": max(cursor, piece_end), "text": "\n".join(group)})
            cursor = piece_end
    return laid


def render_burn_ass(srt_text: str, width: int, height: int, font_name: str) -> str:
    cues = parse_srt(srt_text)
    if not cues:
        raise RuntimeError("字幕文件没有可烧录的内容")
    font_size, margin_v, padding = subtitle_layout(width, height)
    # libass wraps on spaces. A Chinese cue has none, so it stays one line and runs past the frame.
    fitted = layout_subtitle_cues(cues, subtitle_line_capacity(width, height))
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},{WHITE},&H000000FF,&H00000000,{TRANSLUCENT_DARK},0,0,0,0,100,100,0,0,4,{padding},0,2,{_SIDE_MARGIN},{_SIDE_MARGIN},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cue in fitted:
        lines.append(f"Dialogue: 0,{ass_time(float(cue['start']))},{ass_time(float(cue['end']))},Default,,0,0,0,,{escape_ass(str(cue['text']))}")
    return "\n".join(lines) + "\n"


def escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape a path for an FFmpeg filter value inside a filtergraph."""
    text = path.resolve().as_posix()
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace(";", r"\;")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def burn_subtitle_filter(
    srt_path: Path,
    output: Path,
    width: int,
    height: int,
    fonts_dir: Path | None = None,
    font_name: str | None = None,
) -> str:
    """Write a styled ASS sidecar and return the FFmpeg ``ass`` filter."""
    if not srt_path.is_file():
        raise RuntimeError("找不到与配音对应的 SRT 字幕，无法烧录")
    fonts = fonts_dir or bundled_fonts_dir()
    family = font_name or subtitle_font_family()
    ass_path = output.with_suffix(".ass")
    ass_path.write_text(render_burn_ass(srt_path.read_text(encoding="utf-8-sig"), width, height, family), encoding="utf-8")
    return f"ass={escape_ffmpeg_filter_path(ass_path)}:fontsdir={escape_ffmpeg_filter_path(fonts)}"
