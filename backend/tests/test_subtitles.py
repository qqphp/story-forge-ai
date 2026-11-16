import json
import tempfile
import unittest
from pathlib import Path

from backend.integrations.subtitles import (
    render_json,
    render_srt,
    render_txt,
    subtitle_language,
    write_subtitle_files,
)


class SubtitleFormatTests(unittest.TestCase):
    def test_language_follows_the_voice_prefix(self):
        self.assertEqual(subtitle_language("zh-CN-XiaoxiaoNeural"), "zh")
        self.assertEqual(subtitle_language("en-US-JennyNeural"), "en")

    def test_three_formats_share_the_aligned_cues(self):
        cues = [
            {"start": 0, "end": 1.2, "text": " 你好，这是第一句。 ", "words": [{"word": "你好", "start": 0, "end": 0.4}]},
            {"start": 1.2, "end": 2.5, "text": "第二句。"},
            {"start": 2.5, "end": 3, "text": "   "},
        ]
        self.assertEqual(render_srt(cues), "1\n00:00:00,000 --> 00:00:01,200\n你好，这是第一句。\n\n2\n00:00:01,200 --> 00:00:02,500\n第二句。\n")
        self.assertEqual(render_txt(cues), "你好，这是第一句。\n第二句。\n")
        payload = json.loads(render_json(cues))
        self.assertEqual(payload["text"], "你好，这是第一句。第二句。")
        self.assertEqual(payload["segments"][0]["words"][0]["word"], "你好")
        self.assertEqual([segment["id"] for segment in payload["segments"]], [1, 2])

    def test_files_are_written_beside_the_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "draft-1-voice-1.mp3"
            audio.write_bytes(b"audio")
            written = write_subtitle_files(audio, [{"start": 0, "end": 1, "text": "配套字幕"}])
            self.assertEqual(written["srt"].read_text(encoding="utf-8").splitlines()[2], "配套字幕")
            self.assertEqual(written["txt"].read_text(encoding="utf-8"), "配套字幕\n")
            self.assertEqual(json.loads(written["json"].read_text(encoding="utf-8"))["segments"][0]["text"], "配套字幕")

    def test_blank_alignment_is_rejected(self):
        with self.assertRaises(RuntimeError):
            render_srt([{"start": 0, "end": 1, "text": "  "}])


if __name__ == "__main__":
    unittest.main()
