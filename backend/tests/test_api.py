import tempfile
import asyncio
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
        self.voice_samples_patch = patch.object(main, "VOICE_SAMPLES", Path(self.temp.name) / "voice_samples")
        self.voice_translations_patch = patch.object(main, "VOICE_TRANSLATIONS_PATH", Path(self.temp.name) / "voice_translations.json")
        self.db_patch.start(); self.media_patch.start(); self.voice_samples_patch.start(); self.voice_translations_patch.start()
        main.MEDIA.mkdir(exist_ok=True); main.VOICE_SAMPLES.mkdir(exist_ok=True)
        main.init_db()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.db_patch.stop(); self.media_patch.stop(); self.voice_samples_patch.stop(); self.voice_translations_patch.stop(); self.temp.cleanup()

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
        self.assertEqual(response.json()["speech_rate"], 0)

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
            response = self.client.post("/api/workflows", json={"book_title": "测试书", "writing_prompt_ids": [writing["id"]], "cover_prompt_ids": [cover["id"]], "voice": "zh-CN-YunxiNeural", "speech_rate": 15})
        self.assertEqual(response.status_code, 202)
        workflow = self.client.get(f"/api/workflows/{response.json()['id']}").json()
        self.assertEqual(workflow["writing_prompts"][0]["id"], writing["id"])
        self.assertEqual(workflow["cover_prompts"][0]["id"], cover["id"])
        self.assertEqual(workflow["cover_prompts"][0]["name"], cover["name"])
        self.assertEqual(workflow["voices"], ["zh-CN-YunxiNeural"])
        self.assertEqual(workflow["speech_rate"], 15)

    def test_workflow_snapshots_background_music_mix(self):
        music = self.client.post("/api/background-music", json={"name": "夜读", "url": "https://example.com/night.mp3", "category": "安静"}).json()
        with patch.object(main, "process_workflow"):
            response = self.client.post("/api/workflows", json={"book_title": "混音测试", "background_music_id": music["id"], "background_music_volume": 35, "background_music_fade_in": 1.5, "background_music_fade_out": 4})
        workflow = self.client.get(f"/api/workflows/{response.json()['id']}").json()
        self.assertEqual(workflow["background_music"]["name"], "夜读")
        self.assertEqual(workflow["background_music_volume"], 35)
        self.assertEqual(workflow["background_music_fade_in"], 1.5)
        self.assertEqual(workflow["background_music_fade_out"], 4)

    def test_batch_workflow_creation_uses_shared_configuration(self):
        prompts = self.client.get("/api/prompts").json()
        writing = next(p for p in prompts if p["kind"] == "writing")
        cover = next(p for p in prompts if p["kind"] == "cover")
        with patch.object(main, "process_workflow") as process:
            response = self.client.post("/api/workflows/batch", json={"books": [{"book_title": "第一本", "author": "作者甲"}, {"book_title": "第二本", "edition": "纪念版"}], "voice": "en-US-JennyNeural", "speech_rate": 10, "writing_prompt_ids": [writing["id"]], "cover_prompt_ids": [cover["id"]]})
        self.assertEqual(response.status_code, 202); self.assertEqual(response.json()["count"], 2)
        self.assertEqual(process.call_count, 2)
        workflows = self.client.get("/api/workflows").json()
        self.assertEqual({item["book_title"] for item in workflows}, {"第一本", "第二本"})
        self.assertTrue(all(item["voices"] == ["en-US-JennyNeural"] and item["speech_rate"] == 10 for item in workflows))
        self.assertTrue(all(item["writing_prompts"][0]["id"] == writing["id"] and item["cover_prompts"][0]["id"] == cover["id"] for item in workflows))

    def test_video_command_mixes_music_with_volume_and_fades(self):
        command = main.video_command("ffmpeg", Path("cover.png"), Path("voice.mp3"), Path("out.mp4"), Path("music.mp3"), 35, 1.5, 4, 20)
        joined = " ".join(command)
        self.assertIn("-stream_loop -1", joined); self.assertIn("volume=0.35", joined)
        self.assertIn("afade=t=in:st=0:d=1.5", joined); self.assertIn("afade=t=out:st=16:d=4", joined)
        self.assertIn("amix=inputs=2:duration=first", joined)

    def test_speech_ssml_contains_safe_rate_and_escaped_content(self):
        ssml = main.speech_ssml("读书 < 思考", 'voice"name', 120)
        self.assertIn('rate="+100%"', ssml)
        self.assertIn('name="voice&quot;name"', ssml)
        self.assertIn("读书 &lt; 思考", ssml)
        self.assertIn('xml:lang="zh-CN"', ssml)

    def test_voice_sample_is_translated_and_cached_by_locale(self):
        async def fake_llm(_messages, _settings): return "Hello, welcome to this smooth and natural AI voice."
        settings = {**main.DEFAULT_SETTINGS, "api_key": "test"}
        with patch.object(main, "llm", side_effect=fake_llm) as mocked:
            first = asyncio.run(main.localized_voice_sample_text("en-US", settings))
            second = asyncio.run(main.localized_voice_sample_text("en-US", settings))
        self.assertEqual(first, second); self.assertEqual(mocked.call_count, 1)
        self.assertTrue(main.VOICE_TRANSLATIONS_PATH.exists())

    def test_bulk_voice_download_passes_each_voice_locale(self):
        items = [{"short_name": "en-US-JennyNeural", "locale": "en-US"}, {"short_name": "ja-JP-NanamiNeural", "locale": "ja-JP"}]
        async def fake_fetch(_settings): return items, False
        async def fake_ensure(_voice, _settings, _locale): return main.VOICE_SAMPLES / "sample.mp3"
        with patch.object(main, "fetch_voice_items", side_effect=fake_fetch), patch.object(main, "ensure_voice_sample", side_effect=fake_ensure) as mocked:
            asyncio.run(main.download_all_voice_samples())
        self.assertEqual([call.args[2] for call in mocked.call_args_list], ["en-US", "ja-JP"])
        self.assertEqual(main.VOICE_DOWNLOAD_STATUS["completed"], 2)

    def test_audio_extensions_follow_microsoft_formats(self):
        self.assertEqual(main.audio_extension("audio-48khz-192kbitrate-mono-mp3"), ".mp3")
        self.assertEqual(main.audio_extension("ogg-48khz-16bit-mono-opus"), ".ogg")
        self.assertEqual(main.audio_extension("webm-24khz-16bit-mono-opus"), ".webm")
        self.assertEqual(main.audio_extension("raw-24khz-16bit-mono-pcm"), ".pcm")

    def test_voices_returns_every_available_locale(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return [{"ShortName": "zh-CN-XiaoxiaoNeural"}, {"ShortName": "en-US-JennyNeural"}, {"ShortName": "ja-JP-NanamiNeural"}]
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def get(self, *_args, **_kwargs): return Response()
        with patch.object(main, "get_settings", return_value={"azure_speech_key": "test", "azure_speech_region": "eastus"}), patch.object(main.httpx, "AsyncClient", return_value=Client()):
            result = asyncio.run(main.voices())
        self.assertEqual(result["voices"], ["zh-CN-XiaoxiaoNeural", "en-US-JennyNeural", "ja-JP-NanamiNeural"])
        self.assertEqual([item["short_name"] for item in result["items"]], result["voices"])

    def test_background_music_crud_search_and_https_validation(self):
        invalid = self.client.post("/api/background-music", json={"name": "不安全地址", "url": "http://example.com/a.mp3", "category": "测试"})
        malformed = self.client.post("/api/background-music", json={"name": "无域名", "url": "https://", "category": "测试"})
        self.assertEqual(invalid.status_code, 422); self.assertEqual(malformed.status_code, 422)
        created = self.client.post("/api/background-music", json={"name": "安静阅读", "url": "https://example.com/quiet.mp3", "category": "治愈"})
        self.assertEqual(created.status_code, 201)
        listing = self.client.get("/api/background-music", params={"q": "治愈", "page": 1, "page_size": 6}).json()
        self.assertEqual(listing["total"], 1); self.assertEqual(listing["items"][0]["name"], "安静阅读")
        updated = self.client.put(f"/api/background-music/{created.json()['id']}", json={"name": "深夜阅读", "url": "https://example.com/night.mp3", "category": "安静"})
        self.assertEqual(updated.status_code, 200); self.assertEqual(updated.json()["name"], "深夜阅读")
        self.assertEqual(self.client.delete(f"/api/background-music/{created.json()['id']}").status_code, 204)
        self.assertEqual(self.client.get("/api/background-music").json()["total"], 0)

    def test_voice_preview_uses_exact_sample_and_caches_mp3(self):
        async def fake_speech(text, voice, rate, settings, target):
            self.assertEqual(text, "你好，欢迎收听这款流畅自然的AI配音。")
            self.assertEqual(voice, "en-US-JennyNeural"); self.assertEqual(settings["voice_format"], "audio-24khz-96kbitrate-mono-mp3")
            target.write_bytes(b"ID3test"); return True
        settings = {**main.DEFAULT_SETTINGS, "azure_speech_key": "test"}
        with patch.object(main, "get_settings", return_value=settings), patch.object(main, "speech", side_effect=fake_speech):
            response = self.client.get("/api/voices/en-US-JennyNeural/preview")
        self.assertEqual(response.status_code, 200); self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertTrue(main.voice_sample_path("en-US-JennyNeural").exists())

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
