import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

import backend.main as main
from backend.integrations.local_covers import STYLES, SIZES, render_local_cover
from backend.integrations.subtitle_burn import render_burn_ass
from backend.integrations.subtitle_preview import render_preview
from backend.integrations.subtitles import write_subtitle_files
from backend.integrations.video import video_command
from backend.modules.contracts import SubtitlePreview, SubtitleStyle
from backend.modules.media.music import set_default_music
from backend.modules.request_logs.service import clear_logs
from backend.modules.workflows import executor


class CreationOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for field, value in (("DB_PATH", root / "state.db"), ("MEDIA", root / "media")):
            changer = patch.object(main, field, value)
            changer.start(); self.addCleanup(changer.stop)
        main.MEDIA.mkdir()
        self.client = TestClient(main.app)
        main.init_db()
        self.addCleanup(self.client.close)

    def music(self, name):
        response = self.client.post("/api/background-music", json={"name": name, "url": "https://example.com/music.mp3"})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def create(self, **values):
        with patch.object(main, "process_workflow", AsyncMock()):
            response = self.client.post("/api/workflows", json={"book_title": "百年孤独", "author": "马尔克斯", **values})
        self.assertEqual(response.status_code, 202)
        return self.client.get(f"/api/workflows/{response.json()['id']}").json()

    def test_single_default_survives_filtering_and_clear_delete(self):
        a, b = self.music("A"), self.music("B")
        for item in (a, b):
            response = self.client.put(f"/api/background-music/{item['id']}/default", json={"is_default": True})
            self.assertTrue(response.json()["is_default"])
        data = self.client.get("/api/background-music", params={"q": "A", "page_size": 1}).json()
        self.assertEqual(data["default_item"]["id"], b["id"])
        self.assertFalse(data["items"][0]["is_default"])
        self.client.put(f"/api/background-music/{b['id']}/default", json={"is_default": False})
        self.assertIsNone(self.client.get("/api/background-music").json()["default_item"])
        self.client.put(f"/api/background-music/{a['id']}/default", json={"is_default": True})
        self.client.delete(f"/api/background-music/{a['id']}")
        self.assertIsNone(self.client.get("/api/background-music").json()["default_item"])

    def test_default_outside_first_page_is_returned_and_concurrent_updates_are_unique(self):
        items = [self.music(str(i)) for i in range(53)]
        with main.db() as conn:
            conn.execute("UPDATE background_music SET created_at=0 WHERE id=?", (items[0]["id"],))
        set_default_music(main.db, items[0]["id"], True)
        listing = self.client.get("/api/background-music?page_size=50").json()
        self.assertNotIn(items[0]["id"], [item["id"] for item in listing["items"]])
        self.assertEqual(listing["default_item"]["id"], items[0]["id"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda item: set_default_music(main.db, item["id"], True), items[:8]))
        with main.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM background_music WHERE is_default=1").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE background_music SET is_default=1")

    def test_default_music_omission_null_and_snapshots_for_single_and_batch(self):
        music = self.music("默认音乐")
        set_default_music(main.db, music["id"], True)
        chosen = self.create(local_cover=True)
        self.assertTrue(chosen["local_cover"])
        self.assertEqual(chosen["background_music"]["id"], music["id"])
        self.assertIsNone(self.create(background_music_id=None)["background_music"])
        with patch.object(main, "process_workflows_parallel", AsyncMock()):
            batch = self.client.post("/api/workflows/batch", json={"books": [{"book_title": "甲"}, {"book_title": "乙"}], "local_cover": True}).json()
        for task in batch["workflows"]:
            item = self.client.get(f"/api/workflows/{task['id']}").json()
            self.assertTrue(item["local_cover"])
            self.assertEqual(item["background_music"]["id"], music["id"])
        self.client.delete(f"/api/background-music/{music['id']}")
        self.assertEqual(self.client.get(f"/api/workflows/{chosen['id']}").json()["background_music"]["name"], "默认音乐")

    def test_local_workflow_never_calls_image_model_and_generates_only_two_covers(self):
        task = self.create(local_cover=True)

        async def speech(_text, _voice, _rate, _settings, path, *_args):
            path.write_bytes(b"audio")
            return True

        def subtitles(path, text, _language):
            return write_subtitle_files(path, [{"start": 0, "end": 1, "text": text}])

        with patch.object(main, "llm", AsyncMock(return_value="书籍分享稿")), \
             patch.object(main, "speech", side_effect=speech), \
             patch.object(main, "generate_subtitles", side_effect=subtitles), \
             patch.object(main, "generate_cover", AsyncMock()) as external, \
             patch.object(executor, "compose_videos", AsyncMock(return_value=[])):
            asyncio.run(main.process_workflow(task["id"]))
        external.assert_not_called()
        result = self.client.get(f"/api/workflows/{task['id']}").json()
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertEqual(len(result["covers"]), 2)
        for asset in result["covers"]:
            self.assertIn(asset["template_id"], [f"{s[0]}-{suffix}" for s in STYLES for suffix in ("portrait", "landscape")])
            with Image.open(main.MEDIA / result["output_dir"] / Path(asset["url"]).name) as image:
                self.assertEqual(image.size, SIZES[asset["image_ratio"]])
        self.assertEqual(self.client.get("/api/request-logs?request_type=封面生成").json()["total"], 0)

    def test_logs_default_to_twelve_and_delete_all_filtered_and_unfiltered_records(self):
        for i in range(29):
            main.log_request("文稿生成" if i % 2 else "封面生成", "https://example.com", {"i": i})
        pages = [self.client.get(f"/api/request-logs?page={page}").json() for page in (1, 2, 3)]
        self.assertEqual([len(page["items"]) for page in pages], [12, 12, 5])
        ids = [item["id"] for page in pages for item in page["items"]]
        self.assertEqual(len(set(ids)), 29)
        self.assertEqual(self.client.delete("/api/request-logs").json()["deleted"], 29)
        with main.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0], 0)
        main.log_request("文稿生成", "https://example.com/new", {})
        self.assertEqual(self.client.get("/api/request-logs").json()["total"], 1)

    def test_failed_log_deletion_keeps_records_and_unknown_music_keeps_default(self):
        from contextlib import contextmanager
        main.log_request("文稿生成", "https://example.com", {})

        @contextmanager
        def readonly_logs():
            with main.db() as conn:
                conn.set_authorizer(lambda action, *_args: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DELETE else sqlite3.SQLITE_OK)
                yield conn

        with self.assertRaises(sqlite3.DatabaseError):
            clear_logs(readonly_logs)
        self.assertEqual(self.client.get("/api/request-logs").json()["total"], 1)
        music = self.music("原默认")
        set_default_music(main.db, music["id"], True)
        self.assertEqual(self.client.put("/api/background-music/missing/default", json={"is_default": True}).status_code, 404)
        main.init_db()
        self.assertEqual(self.client.get("/api/background-music").json()["default_item"]["id"], music["id"])

    def test_preview_timeout_returns_error_and_other_api_remains_available(self):
        with patch("backend.integrations.subtitle_preview.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 10)):
            response = self.client.post("/api/subtitle-preview", json={})
        self.assertEqual(response.status_code, 503)
        self.assertIn("超时", response.json()["detail"])
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_styles_validate_roundtrip_and_survive_older_settings_clients(self):
        settings = self.client.get("/api/settings").json()
        style = SubtitleStyle(font_id="lxgw-wenkai", text_color="#FFEEDD", mode="outline", position="top", bold=True).model_dump()
        settings["subtitle_style"] = style
        self.assertEqual(self.client.put("/api/settings", json=settings).json()["subtitle_style"], style)
        del settings["subtitle_style"]
        self.client.put("/api/settings", json=settings)
        self.assertEqual(self.client.get("/api/settings").json()["subtitle_style"], style)
        self.assertEqual(self.client.post("/api/subtitle-preview", json={"style": {"font_id": "../../bad"}}).status_code, 422)
        self.assertEqual(self.client.post("/api/subtitle-preview", json={"text": "字" * 201}).status_code, 422)
        self.assertEqual(len(self.client.get("/api/subtitle-fonts").json()["items"]), 4)


class VisualGenerationTests(unittest.TestCase):
    def test_all_twelve_templates_with_long_text_and_empty_author(self):
        with tempfile.TemporaryDirectory() as folder:
            for ratio, size in SIZES.items():
                for index in range(6):
                    path = Path(folder) / f"{index}.png"
                    for title, author in (("百年孤独", "马尔克斯"), ("长书名" * 53, "长作者" * 40), ("空作者", "")):
                        with self.subTest(ratio=ratio, template=index, title=title[:4]):
                            render_local_cover(path, title, author, ratio, index)
                            with Image.open(path) as image:
                                self.assertEqual(image.size, size)

    def test_actual_ffmpeg_preview_and_video_share_styles_in_both_orientations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            srt = root / "sample.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n慢下来，读一本好书。\n", encoding="utf-8")
            main.make_demo_wav(root / "audio.wav", 1)
            for orientation, ratio in (("landscape", "16:9"), ("portrait", "9:16")):
                for mode in ("box", "outline"):
                    style = SubtitleStyle(mode=mode, text_color="#FFE0A0", bold=True, position="top").model_dump()
                    preview = render_preview(SubtitlePreview(orientation=orientation, style=style))
                    with Image.open(io.BytesIO(preview)) as image:
                        self.assertEqual(image.size, SIZES[ratio])
                cover = root / "cover.png"
                Image.new("RGB", SIZES[ratio], "#263e49").save(cover)
                out = root / f"{orientation}.mp4"
                command = video_command("ffmpeg", cover, root / "audio.wav", out, orientation=orientation, subtitles=srt, subtitle_style=style)
                result = subprocess.run(command, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr[-1000:])
                ass = out.with_suffix(".ass").read_text(encoding="utf-8")
                self.assertIn("&H00A0E0FF", ass)
                self.assertIn(",-1,0,0,0,100,100,0,0,1,2,0,8,", ass)
                self.assertGreater(out.stat().st_size, 1000)

    def test_default_style_preserves_legacy_ass(self):
        srt = "1\n00:00:00,000 --> 00:00:01,000\n原有字幕\n"
        for width, height in SIZES.values():
            self.assertEqual(render_burn_ass(srt, width, height, "Noto Sans CJK SC"), render_burn_ass(srt, width, height, "Noto Sans CJK SC", SubtitleStyle().model_dump()))
