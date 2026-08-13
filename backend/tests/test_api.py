import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.main as main


class StoryForgeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(main, "DB_PATH", Path(self.temp.name) / "test.db")
        self.media_patch = patch.object(main, "MEDIA", Path(self.temp.name) / "media")
        self.db_patch.start(); self.media_patch.start()
        main.MEDIA.mkdir(exist_ok=True)
        main.init_db()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.db_patch.stop(); self.media_patch.stop(); self.temp.cleanup()

    def test_health_and_empty_workflows(self):
        self.assertTrue(self.client.get("/api/health").json()["ok"])
        self.assertEqual(self.client.get("/api/workflows").json(), [])

    def test_create_rejects_missing_title(self):
        response = self.client.post("/api/workflows", json={"book_title": ""})
        self.assertEqual(response.status_code, 422)

    def test_settings_masks_secrets(self):
        payload = {**main.DEFAULT_SETTINGS, "api_key": "secret", "azure_speech_key": "speech"}
        response = self.client.put("/api/settings", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api_key"], "••••••••")

    def test_prompt_template_crud(self):
        initial = self.client.get("/api/prompts").json()
        self.assertGreaterEqual(len(initial), 3)
        created = self.client.post("/api/prompts", json={"kind": "writing", "name": "测试模板", "text": "自然地讲述"})
        self.assertEqual(created.status_code, 201)
        prompt_id = created.json()["id"]
        updated = self.client.put(f"/api/prompts/{prompt_id}", json={"name": "已更新", "text": "避免空泛表达"})
        self.assertEqual(updated.json()["name"], "已更新")
        self.assertEqual(self.client.delete(f"/api/prompts/{prompt_id}").status_code, 204)

    def test_long_writing_and_cover_prompts_can_be_saved(self):
        long_writing = "分享稿要求：" + "自然、具体、有细节。" * 1200
        long_cover = "封面要求：" + "构图克制、色彩统一、避免文字。" * 900
        writing = self.client.post("/api/prompts", json={"kind": "writing", "name": "长分享稿提示词", "text": long_writing})
        cover = self.client.post("/api/prompts", json={"kind": "cover", "name": "长封面提示词", "text": long_cover})
        self.assertEqual(writing.status_code, 201)
        self.assertEqual(cover.status_code, 201)
        self.assertEqual(writing.json()["text"], long_writing)
        self.assertEqual(cover.json()["text"], long_cover)
        revised = long_writing + "补充修改要求。" * 500
        updated = self.client.put(f"/api/prompts/{writing.json()['id']}", json={"name": "长分享稿提示词", "text": revised})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["text"], revised)

    def test_workflow_snapshots_selected_prompts(self):
        prompts = self.client.get("/api/prompts").json()
        writing = next(p for p in prompts if p["kind"] == "writing")
        cover = next(p for p in prompts if p["kind"] == "cover")
        with patch.object(main, "process_workflow"):
            response = self.client.post("/api/workflows", json={"book_title": "测试书", "writing_prompt_ids": [writing["id"]], "cover_prompt_ids": [cover["id"]]})
        self.assertEqual(response.status_code, 202)
        workflow = self.client.get(f"/api/workflows/{response.json()['id']}").json()
        self.assertEqual(workflow["writing_prompts"][0]["id"], writing["id"])
        self.assertEqual(workflow["cover_prompts"][0]["id"], cover["id"])
        self.assertEqual(workflow["cover_prompts"][0]["name"], cover["name"])

    def test_audio_extensions_follow_microsoft_formats(self):
        self.assertEqual(main.audio_extension("audio-48khz-192kbitrate-mono-mp3"), ".mp3")
        self.assertEqual(main.audio_extension("ogg-48khz-16bit-mono-opus"), ".ogg")
        self.assertEqual(main.audio_extension("webm-24khz-16bit-mono-opus"), ".webm")
        self.assertEqual(main.audio_extension("raw-24khz-16bit-mono-pcm"), ".pcm")

    def test_delete_workflow_removes_only_its_media(self):
        prompts = self.client.get("/api/prompts").json()
        writing = next(p for p in prompts if p["kind"] == "writing")
        cover = next(p for p in prompts if p["kind"] == "cover")
        with patch.object(main, "process_workflow"):
            created = self.client.post("/api/workflows", json={"book_title": "待删除", "writing_prompt_ids": [writing["id"]], "cover_prompt_ids": [cover["id"]]})
        workflow_id = created.json()["id"]
        owned_cover = main.MEDIA / f"{workflow_id}-cover-1.png"
        owned_audio = main.MEDIA / f"{workflow_id}-d1-v1.mp3"
        unrelated = main.MEDIA / "another-workflow-cover-1.png"
        owned_cover.write_bytes(b"cover"); owned_audio.write_bytes(b"audio"); unrelated.write_bytes(b"keep")
        with main.db() as conn:
            conn.execute("UPDATE workflows SET status='completed' WHERE id=?", (workflow_id,))
        response = self.client.delete(f"/api/workflows/{workflow_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_files"], 2)
        self.assertFalse(owned_cover.exists()); self.assertFalse(owned_audio.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(self.client.get(f"/api/workflows/{workflow_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
