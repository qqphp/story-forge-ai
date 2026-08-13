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


if __name__ == "__main__":
    unittest.main()
