import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.integrations import subtitles

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


class SubtitleProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / "中文配音.wav"
        self.audio.write_bytes(b"audio")
        # Exercise the real child-process boundary without downloading a model.
        (self.root / "stable_whisper.py").write_text('''
import os, time
from pathlib import Path
from types import SimpleNamespace
def load_model(name):
    class Model:
        def align(self, audio, text, language, **kwargs):
            print("model progress")
            Path(audio).with_suffix(".started").touch()
            time.sleep(float(os.getenv("TEST_ALIGN_DELAY", "0")))
            return SimpleNamespace(segments=[SimpleNamespace(start=0, end=1, text=text, words=[])])
    return Model()
''', encoding="utf-8")
        self.env = patch.dict(os.environ, {"PYTHONPATH": str(self.root) + os.pathsep + os.environ.get("PYTHONPATH", "")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_worker_writes_unicode_subtitles_without_using_parent_model(self):
        with patch.object(subtitles, "_load_model", side_effect=AssertionError("model loaded in API process")):
            paths = subtitles.generate_subtitles(self.audio, "你好，世界。", "zh")
        self.assertEqual(paths["txt"].read_text(encoding="utf-8"), "你好，世界。\n")

    def test_hung_alignment_is_terminated(self):
        with patch.dict(os.environ, {"TEST_ALIGN_DELAY": "20"}), patch.object(subtitles, "SUBTITLE_TIMEOUT", 0.3):
            with self.assertRaisesRegex(RuntimeError, "字幕生成超时"):
                subtitles.generate_subtitles(self.audio, "你好", "zh")
        self.assertFalse(self.audio.with_suffix(".srt").exists())

    def test_api_and_database_respond_while_subtitles_are_running(self):
        import backend.main as main
        from fastapi.testclient import TestClient

        with patch.object(main, "DB_PATH", self.root / "test.db"), \
             patch.dict(os.environ, {"TEST_ALIGN_DELAY": "2"}), \
             TestClient(main.app) as client, ThreadPoolExecutor() as pool:
            future = pool.submit(subtitles.generate_subtitles, self.audio, "并发字幕", "zh")
            deadline = time.monotonic() + 5
            while not self.audio.with_suffix(".started").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(self.audio.with_suffix(".started").exists())
            started = time.monotonic()
            for path in ("/api/health", "/api/workflows", "/api/settings", "/api/prompts"):
                self.assertEqual(client.get(path).status_code, 200)
            self.assertLess(time.monotonic() - started, 1)
            self.assertFalse(future.done())
            future.result(timeout=5)


if __name__ == "__main__":
    unittest.main()
