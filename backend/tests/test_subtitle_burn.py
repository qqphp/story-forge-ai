import re
import struct
import tempfile
import unittest
from pathlib import Path

from backend.integrations.fonts import bundled_fonts_dir, load_font_manifest, subtitle_font_family
from backend.integrations.subtitle_burn import WHITE, TRANSLUCENT_DARK, render_burn_ass, subtitle_line_capacity, text_units
from backend.integrations.video import video_command


def _font_family(path: Path) -> str:
    data = path.read_bytes()
    num_tables = struct.unpack_from(">H", data, 4)[0]
    name_offset = None
    for index in range(num_tables):
        tag, _checksum, table_offset, _length = struct.unpack_from(">4sIII", data, 12 + index * 16)
        if tag == b"name":
            name_offset = table_offset
            break
    if name_offset is None:
        raise AssertionError(f"{path.name} 没有 name 表")
    _format, count, string_offset = struct.unpack_from(">HHH", data, name_offset)
    found: dict[tuple[int, int], str] = {}
    for index in range(count):
        platform, encoding, language, name_id, length, value_offset = struct.unpack_from(">HHHHHH", data, name_offset + 6 + index * 12)
        raw = data[name_offset + string_offset + value_offset:name_offset + string_offset + value_offset + length]
        if platform == 3 and encoding in (1, 10):
            text = raw.decode("utf-16-be", errors="ignore")
        elif platform == 1:
            text = raw.decode("latin-1", errors="ignore")
        else:
            continue
        if name_id in (1, 16) and text:
            found[(name_id, language)] = text
    for name_id in (16, 1):
        for language in (0x409, 0, 0x804):
            if (name_id, language) in found:
                return found[(name_id, language)]
    for name_id in (16, 1):
        for (found_id, _language), text in found.items():
            if found_id == name_id:
                return text
    raise AssertionError(f"{path.name} 没有字体家族名")


class SubtitleBurnTests(unittest.TestCase):
    def test_ass_uses_white_text_and_translucent_dark_background(self):
        srt = "1\n00:00:00,000 --> 00:00:01,200\n你好，字幕。\n\n2\n00:00:01,200 --> 00:00:02,500\n第一行\n第二行\n"
        ass = render_burn_ass(srt, 1080, 1920, "Noto Sans CJK SC")
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn(f"Noto Sans CJK SC,52,{WHITE}", ass)
        self.assertIn(f"{TRANSLUCENT_DARK},0,0,0,0,100,100,0,0,4,", ass)
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:01.20,Default,,0,0,0,,你好，字幕。", ass)
        self.assertIn(r"第一行\N第二行", ass)

    def test_portrait_caption_wraps_inside_the_frame_and_continues_on_the_next_cue(self):
        sentence = "这是一段比较长的竖版字幕，用来说明字数很多的时候不应该只排成一行然后冲出屏幕两侧，后面这句继续把同一条字幕分成下一次出现。"
        srt = f"1\n00:00:00,000 --> 00:00:06,000\n{sentence}\n"
        ass = render_burn_ass(srt, 1080, 1920, "Noto Sans CJK SC")
        dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
        self.assertGreater(len(dialogues), 1)
        capacity = subtitle_line_capacity(1080, 1920)
        seen = ""
        previous_end = ""
        for line in dialogues:
            match = re.match(r"Dialogue: 0,([^,]+),([^,]+),Default,,0,0,0,,(.*)", line)
            self.assertIsNotNone(match)
            assert match is not None
            start_text, end_text, text = match.group(1), match.group(2), match.group(3)
            self.assertLessEqual(previous_end, start_text)
            self.assertLessEqual(start_text, end_text)
            self.assertLessEqual(end_text, "0:00:06.00")
            previous_end = end_text
            visual_lines = text.split(r"\N")
            self.assertLessEqual(len(visual_lines), 2)
            for visual in visual_lines:
                self.assertLessEqual(text_units(visual), capacity * 1.08)
                self.assertNotIn(sentence, visual)
            seen += "".join(visual_lines)
        self.assertEqual(seen, sentence)
        self.assertEqual(dialogues[0].split(",,", 1)[-1].split(r"\N")[0][-1], "，")

    def test_ffmpeg_command_burns_the_matching_srt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            srt = root / "draft.srt"
            srt.write_text("1\n00:00:01,500 --> 00:00:03,000\n{保留}\\符号\n", encoding="utf-8")
            fonts = root / "fonts"
            fonts.mkdir()
            output = root / "video-1.mp4"
            command = video_command(
                "ffmpeg", Path("cover.png"), Path("audio.mp3"), output,
                orientation="landscape", subtitles=srt, fonts_dir=fonts, subtitle_font="Noto Sans CJK SC",
            )
            video_filter = command[command.index("-vf") + 1]
            self.assertIn("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1", video_filter)
            self.assertIn("format=yuv420p", video_filter)
            self.assertIn("ass=", video_filter)
            self.assertIn("fontsdir=", video_filter)
            self.assertIn(r"\\:", video_filter)
            ass = output.with_suffix(".ass").read_text(encoding="utf-8")
            self.assertIn(r"\{保留\}\\符号", ass)
            self.assertIn(WHITE, ass)
            self.assertIn(TRANSLUCENT_DARK, ass)

    def test_command_without_subtitles_keeps_the_plain_picture_filter(self):
        command = video_command("ffmpeg", Path("cover.png"), Path("audio.mp3"), Path("out.mp4"))
        video_filter = command[command.index("-vf") + 1]
        self.assertNotIn("ass=", video_filter)
        self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p", video_filter)

    def test_missing_srt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(RuntimeError):
                video_command("ffmpeg", Path("cover.png"), Path("audio.mp3"), root / "out.mp4", subtitles=root / "missing.srt", fonts_dir=root)

    def test_bundled_font_library_contains_the_required_families(self):
        manifest = load_font_manifest()
        roles = {item["role"]: item for item in manifest["fonts"]}
        self.assertEqual(subtitle_font_family(), roles["中文主字体"]["family"])
        self.assertEqual([item["role"] for item in manifest["fonts"]], [
            "中文主字体", "中文宋体", "中文楷体", "英文主字体", "特殊符号", "彩色表情",
        ])
        fonts = bundled_fonts_dir()
        for item in roles.values():
            font_file = fonts / item["file"]
            self.assertTrue(font_file.is_file(), item["file"])
            self.assertGreater(font_file.stat().st_size, 10_000, item["file"])
            self.assertEqual(_font_family(font_file), item["family"])


if __name__ == "__main__":
    unittest.main()
