import tempfile
import asyncio
import base64
import io
import json
import os
import unittest
import xml.etree.ElementTree as ET
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles

import backend.main as main
from backend.modules.workflows import executor
from backend.modules.workflows.broadcast import DEFAULT_WRITING_GUIDANCE, DEFAULT_WRITING_ID, PREVIOUS_WRITING_GUIDANCE, STAGES


def broadcast_reply(messages, script="简短内容", description="一部关于选择的小说。"):
    system = messages[0]["content"]
    if system.endswith(STAGES["research"][2]):
        return json.dumps({"match_status": "identified", "author": "", "description": description,
                           "evidence": [], "interpretations": [], "unknowns": []})
    if system.endswith(STAGES["plan"][2]):
        return '{"theme":"选择","sections":[]}'
    if system.endswith(STAGES["review"][2]):
        return '{"score":90,"critical_issues":[],"suggestions":[],"revision_stage":"none"}'
    return script


class StoryForgeApiTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"FIRECRAWL_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(main, "DB_PATH", Path(self.temp.name) / "test.db")
        self.media_patch = patch.object(main, "MEDIA", Path(self.temp.name) / "media")
        self.voice_samples_patch = patch.object(main, "VOICE_SAMPLES", Path(self.temp.name) / "voice_samples")
        self.voice_translations_patch = patch.object(main, "VOICE_TRANSLATIONS_PATH", Path(self.temp.name) / "voice_translations.json")
        self.db_patch.start(); self.media_patch.start(); self.voice_samples_patch.start(); self.voice_translations_patch.start()
        main.MEDIA.mkdir(exist_ok=True); main.VOICE_SAMPLES.mkdir(exist_ok=True)
        main.init_db()
        # Encoding stubs must not also intercept ffprobe and overwrite its inputs.
        for name, value in (("probe_audio_duration", 1.5), ("probe_video_metadata", (None, 1.5))):
            probe_patch = patch.object(executor, name, return_value=value)
            probe_patch.start()
            self.addCleanup(probe_patch.stop)
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.REGENERATING_VIDEOS.clear()
        self.db_patch.stop(); self.media_patch.stop(); self.voice_samples_patch.stop(); self.voice_translations_patch.stop(); self.temp.cleanup()

    def test_background_blur_settings_round_trip_and_preview_validation(self):
        settings = self.client.get("/api/settings").json()
        self.assertFalse(settings["background_blur_enabled"])
        self.assertEqual(settings["background_blur_strength"], 20)
        for enabled, strength in ((True, 73), (False, 73), (True, 0), (True, 100)):
            response = self.client.put("/api/settings", json={**settings, "background_blur_enabled": enabled, "background_blur_strength": strength})
            self.assertEqual(response.status_code, 200)
            saved = self.client.get("/api/settings").json()
            self.assertEqual(saved["background_blur_enabled"], enabled)
            self.assertEqual(saved["background_blur_strength"], strength)
        for strength in (-1, 101):
            self.assertEqual(self.client.put("/api/settings", json={**settings, "background_blur_strength": strength}).status_code, 422)
            self.assertEqual(self.client.post("/api/subtitle-preview", json={"background_blur_strength": strength}).status_code, 422)

    def test_background_overlay_settings_round_trip_and_preview_validation(self):
        settings = self.client.get("/api/settings").json()
        self.assertTrue(settings["background_overlay_enabled"])
        self.assertEqual(settings["background_overlay_opacity"], .25)
        for enabled, opacity in ((False, .63), (True, 0), (True, .25), (True, 1)):
            response = self.client.put("/api/settings", json={**settings, "background_overlay_enabled": enabled, "background_overlay_opacity": opacity})
            self.assertEqual(response.status_code, 200)
            saved = self.client.get("/api/settings").json()
            self.assertEqual(saved["background_overlay_enabled"], enabled)
            self.assertEqual(saved["background_overlay_opacity"], opacity)
        for opacity in (-.01, 1.01):
            self.assertEqual(self.client.put("/api/settings", json={**settings, "background_overlay_opacity": opacity}).status_code, 422)
            self.assertEqual(self.client.post("/api/subtitle-preview", json={"background_overlay_opacity": opacity}).status_code, 422)

    def test_record_label_upload_is_staged_until_settings_save(self):
        from backend.integrations import record_labels
        raw = io.BytesIO()
        Image.new("RGBA", (20,20), (10,20,30,120)).save(raw,"PNG")
        before = self.client.get("/api/settings").json()
        with patch.object(record_labels,"UPLOADS",Path(self.temp.name)/"labels"):
            response=self.client.post("/api/video/record-label-images",content=raw.getvalue(),headers={"Content-Type":"image/png"})
            self.assertEqual(response.status_code,201)
            image_id=response.json()["id"]
            self.assertEqual(self.client.get("/api/settings").json()["record_label_image_id"],before["record_label_image_id"])
            saved=self.client.put("/api/settings",json={**before,"record_label_image_id":image_id})
            self.assertEqual(saved.json()["record_label_image_id"],image_id)
            self.assertEqual(self.client.get(response.json()["url"]).status_code,200)
            self.assertEqual(self.client.post("/api/video/record-label-images",content=b"bad").status_code,422)
            self.assertEqual(self.client.get("/api/settings").json()["record_label_image_id"],image_id)
            self.assertEqual(self.client.get("/api/video/record-label-images/invalid").status_code,404)
            self.client.put("/api/settings",json={**before,"record_label_image_id":None})
            self.assertIsNone(self.client.get("/api/settings").json()["record_label_image_id"])

    def test_health_and_empty_workflows(self):
        self.assertTrue(self.client.get("/api/health").json()["ok"])
        self.assertEqual(self.client.get("/api/workflows").json(), [])

    def test_local_media_supports_range_requests(self):
        path = main.MEDIA / "range-test.mp4"
        path.write_bytes(b"0123456789")
        media_route = next(route for route in main.app.routes if getattr(route, "path", "") == "/media")
        with patch.object(media_route, "app", StaticFiles(directory=main.MEDIA)):
            response = self.client.get("/media/range-test.mp4", headers={"Range": "bytes=2-5"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
        self.assertEqual(response.content, b"2345")

    def test_create_rejects_missing_title(self):
        response = self.client.post("/api/workflows", json={"book_title": ""})
        self.assertEqual(response.status_code, 422)

    def test_settings_masks_secrets(self):
        payload = {**main.DEFAULT_SETTINGS, "text_api_key": "text-test-key", "image_api_key": "image-test-key", "azure_speech_key": "speech", "pexels_api_key": "pexels", "pixabay_api_key": "pixabay"}
        response = self.client.put("/api/settings", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text_api_key"], "••••••••")
        self.assertEqual(response.json()["image_api_key"], "••••••••")
        self.assertNotIn("api_key", response.json())
        self.assertNotIn("api_base", response.json())
        self.assertEqual(response.json()["pexels_api_key"], "••••••••")
        self.assertEqual(response.json()["pixabay_api_key"], "••••••••")
        self.assertEqual(response.json()["video_orientation"], "portrait")
        self.assertEqual(response.json()["burn_subtitles"], True)
        self.assertEqual(response.json()["speech_rate"], 0)
        enabled = self.client.put("/api/settings", json={**payload, "burn_subtitles": True})
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(enabled.json()["burn_subtitles"], True)

    def test_models_and_chat_use_text_address_and_key(self):
        settings = {
            **main.DEFAULT_SETTINGS,
            "text_api_base": "https://text.example/custom/v2/", "text_api_key": "text-test-key",
            "image_api_base": "https://image.example/v1", "image_api_key": "image-test-key",
            "model": "text-model",
        }
        self.client.put("/api/settings", json=settings)
        calls = []

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "text-model"}], "choices": [{"message": {"content": "generated text"}}]}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def get(self, url, **kwargs): calls.append((url, kwargs)); return Response()
            async def post(self, url, **kwargs): calls.append((url, kwargs)); return Response()

        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            response = self.client.get("/api/models")
            result = asyncio.run(main.llm([{"role": "user", "content": "test"}], settings))
        self.assertEqual(response.json(), {"models": ["text-model"], "demo": False})
        self.assertEqual(result, "generated text")
        self.assertEqual(calls[0][0], "https://text.example/custom/v2/models")
        self.assertEqual(calls[1][0], "https://text.example/custom/v2/chat/completions")
        for _, kwargs in calls:
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer text-test-key")
        self.assertEqual(calls[1][1]["json"]["model"], settings["model"])

    def test_text_requests_do_not_use_image_credentials(self):
        settings = {**main.DEFAULT_SETTINGS, "image_api_key": "image-test-key"}
        self.client.put("/api/settings", json=settings)
        with patch.object(main.httpx, "AsyncClient") as client:
            response = self.client.get("/api/models")
            result = asyncio.run(main.llm([], settings))
        self.assertTrue(response.json()["demo"])
        self.assertIsNone(result)
        client.assert_not_called()

    def test_manual_model_fetch_uses_current_input_or_matching_masked_key_without_saving(self):
        settings = {**main.DEFAULT_SETTINGS, "text_api_key": "stored-text-test-key", "image_api_key": "stored-image-test-key"}
        self.client.put("/api/settings", json=settings)
        before = self.client.get("/api/settings").json()
        calls = []

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "gpt-image-2"}, {"id": "other-model"}, {"id": "other-model"}, {"id": ""}, {}]}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def get(self, url, **kwargs): calls.append((url, kwargs)); return Response()

        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            for provider, key, expected in (("text", "new-text-test-key", "new-text-test-key"), ("text", "••••••••", "stored-text-test-key"), ("image", "••••••••", "stored-image-test-key")):
                with self.subTest(provider=provider, masked=key == "••••••••"):
                    response = self.client.post("/api/models", json={"provider": provider, "api_base": "https://unsaved.example/custom/v2/", "api_key": key})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["models"], ["gpt-image-2", "other-model"])
                    self.assertEqual(calls[-1][0], "https://unsaved.example/custom/v2/models")
                    self.assertEqual(calls[-1][1]["headers"]["Authorization"], f"Bearer {expected}")
        self.assertEqual(self.client.get("/api/settings").json(), before)

    def test_manual_model_fetch_rejects_missing_credentials_and_invalid_requests(self):
        self.client.put("/api/settings", json=main.DEFAULT_SETTINGS)
        with patch.object(main.httpx, "AsyncClient") as client:
            for key in ("", "••••••••"):
                response = self.client.post("/api/models", json={"provider": "image", "api_base": "https://example.com/v1", "api_key": key})
                self.assertEqual(response.status_code, 400)
            for value in ({"provider": "unsupported", "api_base": "https://example.com"}, {"provider": "text", "api_base": "not-a-url"}):
                self.assertEqual(self.client.post("/api/models", json=value).status_code, 422)
        client.assert_not_called()

    def test_image_root_and_generation_endpoint_resolve_models_and_generation_correctly(self):
        raw = io.BytesIO()
        Image.new("RGB", (4, 3), "navy").save(raw, "PNG")
        encoded = base64.b64encode(raw.getvalue()).decode()
        calls = []

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": "image-test-model", "b64_json": encoded}]}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def get(self, url, **_): calls.append(("GET", url)); return Response()
            async def post(self, url, **_): calls.append(("POST", url)); return Response()

        addresses = (
            ("https://proaiapi.vip/v1", "https://proaiapi.vip/v1"),
            ("https://proaiapi.vip/v1/images/generations", "https://proaiapi.vip/v1"),
            ("https://proaiapi.vip/v1/images/generations/", "https://proaiapi.vip/v1"),
            ("https://proxy.example/custom/v2/images/generations", "https://proxy.example/custom/v2"),
        )
        for address, root in addresses:
            with self.subTest(address=address), patch.object(main.httpx, "AsyncClient", return_value=Client()):
                response = self.client.post("/api/models", json={"provider": "image", "api_base": address, "api_key": "image-test-key"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["models"], ["image-test-model"])
                generated, _ = asyncio.run(main.generate_cover(main.MEDIA / "endpoint-cover.png", "测试书", "作者", "简介", "文学感", 0, "4:3", {
                    **main.DEFAULT_SETTINGS, "image_api_base": address, "image_api_key": "image-test-key", "image_model": "image-test-model",
                }))
                self.assertTrue(generated)
                self.assertEqual(calls[-2:], [("GET", root + "/models"), ("POST", root + "/images/generations")])

    def test_manual_model_fetch_reports_safe_errors_and_handles_empty_lists(self):
        request = httpx.Request("GET", "https://example.com/models")
        responses = [
            (httpx.Response(401, text="private-upstream-test-key", request=request), 502),
            (httpx.Response(500, text="private-upstream-test-key", request=request), 502),
            (httpx.Response(200, text="invalid JSON", request=request), 502),
            (httpx.Response(200, json={"unexpected": []}, request=request), 502),
            (httpx.Response(200, json={"data": []}, request=request), 200),
        ]
        for upstream, expected_status in responses:
            with self.subTest(status=upstream.status_code, expected=expected_status):
                client = AsyncMock()
                client.__aenter__.return_value = client
                client.get.return_value = upstream
                with patch.object(main.httpx, "AsyncClient", return_value=client):
                    response = self.client.post("/api/models", json={"provider": "image", "api_base": "https://example.com", "api_key": "input-test-key"})
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("input-test-key", response.text)
                self.assertNotIn("private-upstream-test-key", response.text)
                if expected_status == 200:
                    self.assertEqual(response.json()["models"], [])
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.side_effect = httpx.ConnectError("input-test-key must not be returned", request=request)
        with patch.object(main.httpx, "AsyncClient", return_value=client):
            response = self.client.post("/api/models", json={"provider": "text", "api_base": "https://example.com", "api_key": "input-test-key"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("input-test-key", response.text)

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

    def test_cover_template_image_sizes_are_saved_and_snapshotted(self):
        sizes = ["1:1", "16:9", "9:16", "2:3"]
        cover = self.client.post("/api/prompts", json={
            "kind": "cover", "name": "多尺寸封面", "text": "无文字、文学感", "image_sizes": sizes,
        })
        self.assertEqual(cover.status_code, 201)
        self.assertEqual(cover.json()["image_sizes"], sizes)
        with patch.object(main, "process_workflow"):
            response = self.client.post("/api/workflows", json={"book_title": "尺寸测试", "cover_prompt_ids": [cover.json()["id"]]})
        workflow = self.client.get(f"/api/workflows/{response.json()['id']}").json()
        self.assertEqual(workflow["cover_prompts"][0]["image_sizes"], sizes)

    def test_new_cover_templates_default_to_video_cover_ratios(self):
        cover = self.client.post("/api/prompts", json={"kind": "cover", "name": "默认比例", "text": "无文字、文学感"})
        self.assertEqual(cover.status_code, 201)
        self.assertEqual(cover.json()["image_sizes"], ["1:1", "16:9", "9:16"])

    def test_cover_template_requires_both_video_cover_ratios(self):
        created = self.client.post("/api/prompts", json={"kind": "cover", "name": "缺少竖版", "text": "无文字、文学感", "image_sizes": ["16:9"]})
        self.assertEqual(created.status_code, 400)
        self.assertIn("16:9 和 9:16", created.json()["detail"])

    def test_cover_generation_uses_ratio_prompt_without_resolution_or_local_resize(self):
        image = Image.new("RGB", (73, 41), "navy")
        raw = io.BytesIO(); image.save(raw, "PNG"); encoded = base64.b64encode(raw.getvalue()).decode()
        calls = []

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"b64_json": encoded}]}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, **kwargs): calls.append({"url": url, **kwargs}); return Response()

        target = main.MEDIA / "ratio-cover.png"
        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            generated, resolution = asyncio.run(main.generate_cover(target, "测试书", "作者", "简介", "文学感", 0, "16:9", {
                "text_api_base": "https://text.example/v1", "text_api_key": "text-test-key",
                "image_api_base": "https://image.example/custom/", "image_api_key": "image-test-key",
                "image_model": "gpt-image-2",
            }))
        self.assertTrue(generated); self.assertEqual(resolution, "73×41")
        self.assertEqual(calls[0]["url"], "https://image.example/custom/images/generations")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer image-test-key")
        self.assertEqual(calls[0]["json"]["model"], "gpt-image-2")
        self.assertNotIn("size", calls[0]["json"])
        self.assertIn("图片比例：16:9", calls[0]["json"]["prompt"])
        self.assertNotIn("创作无文字的书籍分享封面", calls[0]["json"]["prompt"])
        self.assertEqual(target.read_bytes(), raw.getvalue())

    def test_missing_image_key_uses_local_cover_even_with_text_key(self):
        target = main.MEDIA / "local-cover.png"

        def fallback(path, *_): Image.new("RGB", (73, 41), "navy").save(path, "PNG")

        with patch.object(main, "make_cover", side_effect=fallback) as local, patch.object(main.httpx, "AsyncClient") as client:
            generated, resolution = asyncio.run(main.generate_cover(target, "测试书", "作者", "简介", "文学感", 0, "16:9", {
                **main.DEFAULT_SETTINGS, "text_api_key": "text-test-key",
            }))
        self.assertFalse(generated)
        self.assertEqual(resolution, "1920×1080")
        local.assert_not_called()
        client.assert_not_called()

    def test_unselected_models_do_not_send_remote_generation_requests(self):
        target = main.MEDIA / "unselected-model-cover.png"
        settings = {**main.DEFAULT_SETTINGS, "text_api_key": "text-test-key", "image_api_key": "image-test-key"}

        def fallback(path, *_): Image.new("RGB", (73, 41), "navy").save(path, "PNG")

        with patch.object(main, "make_cover", side_effect=fallback), patch.object(main.httpx, "AsyncClient") as client:
            self.assertIsNone(asyncio.run(main.llm([], settings)))
            generated, _ = asyncio.run(main.generate_cover(target, "测试书", "作者", "简介", "文学感", 0, "16:9", settings))
        self.assertFalse(generated)
        client.assert_not_called()

    def test_request_logs_support_filters_details_and_clear(self):
        main.log_request("文稿生成", "https://example.com/chat", {"model": "test", "messages": [{"content": "文稿"}]})
        main.log_request("封面生成", "https://example.com/images", {"prompt": "图片比例：1:1"})
        listing = self.client.get("/api/request-logs", params={"request_type": "封面生成"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["items"][0]["request_params"]["prompt"], "图片比例：1:1")
        cleared = self.client.delete("/api/request-logs")
        self.assertEqual(cleared.json()["deleted"], 2)
        self.assertEqual(self.client.get("/api/request-logs").json()["total"], 0)

    def test_tag_topic_generation_is_logged_with_its_own_request_type(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": '{"tags":[],"topics":[]}'}}]}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs): return Response()

        settings = {**main.DEFAULT_SETTINGS, "text_api_key": "key", "text_api_base": "https://example.com/v1", "model": "text-model"}
        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            asyncio.run(main.llm([{"role": "user", "content": "生成话题"}], settings, "标签话题生成"))
        listing = self.client.get("/api/request-logs", params={"request_type": "标签话题生成"}).json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["request_params"]["messages"][0]["content"], "生成话题")

    def test_video_search_prompt_generation_is_logged_with_its_own_request_type(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": "misty mountain landscape"}}]}

        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs): return Response()

        settings = {**main.DEFAULT_SETTINGS, "text_api_key": "key", "text_api_base": "https://example.com/v1", "model": "text-model"}
        messages = [{"role": "user", "content": "根据《测试书》的简介生成视频搜索词"}]
        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            asyncio.run(main.llm(messages, settings, "视频搜索词生成"))
        listing = self.client.get("/api/request-logs", params={"request_type": "视频搜索词生成"}).json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["request_url"], "https://example.com/v1/chat/completions")
        self.assertEqual(listing["items"][0]["request_params"]["messages"], messages)

    def test_new_workflow_generates_eight_tags_and_topics_before_covers(self):
        with patch.object(main, "process_workflow"):
            created = self.client.post("/api/workflows", json={"book_title": "西游记"})
        workflow_id = created.json()["id"]

        async def fake_llm(messages, _settings, request_type="文稿生成"):
            if request_type == "标签话题生成":
                return '{"tags":["古典文学","神魔小说","人物成长","名著阅读","团队协作","东方想象"],"topics":["西游记","读书","好书推荐","名著解读","读书分享","经典文学"]}'
            return broadcast_reply(messages, script="这是一篇《西游记》分享稿。")

        async def fake_speech(_text, _voice, _rate, _settings, target, *_args):
            target.write_bytes(b"audio")
            return target

        def fake_subtitles(audio_path, text, _language):
            from backend.integrations.subtitles import write_subtitle_files
            return write_subtitle_files(audio_path, [{"start": 0, "end": 1.25, "text": text}])

        async def fake_cover(path, *_args):
            Image.new("RGB", (120, 160), "navy").save(path, "PNG")
            return True, "120×160"

        class FinishedVideo:
            returncode = 0

        with patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", side_effect=fake_speech), \
             patch.object(main, "generate_subtitles", side_effect=fake_subtitles), \
             patch.object(main, "generate_cover", side_effect=fake_cover), \
             patch.object(executor.subprocess, "run", return_value=FinishedVideo()):
            asyncio.run(main.process_workflow(workflow_id))
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertEqual(workflow["step"], 7)
        self.assertEqual(workflow["polished_drafts"][0]["review_score"], 90)
        self.assertEqual(workflow["status"], "completed")
        self.assertEqual(len(workflow["subtitles"]), len(workflow["audio"]))
        self.assertTrue(workflow["subtitles"][0]["srt_url"].endswith(".srt"))
        self.assertTrue(workflow["subtitles"][0]["txt_url"].endswith(".txt"))
        self.assertTrue(workflow["subtitles"][0]["json_url"].endswith(".json"))
        self.assertEqual(len(workflow["tags"]), 8)
        self.assertEqual(len(workflow["topics"]), 8)
        self.assertEqual(workflow["topics"][0], "西游记")
        self.assertTrue(workflow["covers"])

    def test_workflow_uses_default_cover_size_when_no_cover_template_is_available(self):
        with main.db() as conn:
            conn.execute("DELETE FROM prompt_templates WHERE kind='cover'")
        with patch.object(main, "process_workflow"):
            created = self.client.post("/api/workflows", json={"book_title": "无封面模板测试"})
        workflow_id = created.json()["id"]

        async def fake_llm(messages, *_args):
            return broadcast_reply(messages)

        async def fake_speech(_text, _voice, _rate, _settings, target, *_args):
            target.write_bytes(b"audio")
            return target

        def fake_subtitles(audio_path, text, _language):
            from backend.integrations.subtitles import write_subtitle_files
            return write_subtitle_files(audio_path, [{"start": 0, "end": 1, "text": text or "字幕"}])

        async def fake_cover(path, *_args):
            Image.new("RGB", (120, 160), "navy").save(path, "PNG")
            return False, "120×160"

        class FinishedVideo:
            returncode = 0

        with patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", side_effect=fake_speech), \
             patch.object(main, "generate_subtitles", side_effect=fake_subtitles), \
             patch.object(main, "generate_cover", side_effect=fake_cover), \
             patch.object(executor.subprocess, "run", return_value=FinishedVideo()):
            asyncio.run(main.process_workflow(workflow_id))
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertEqual(workflow["status"], "completed")
        self.assertEqual(workflow["covers"][0]["image_ratio"], "1:1")

    def test_workflow_burns_the_matching_srt_when_enabled(self):
        self.client.put("/api/settings", json={**main.DEFAULT_SETTINGS, "burn_subtitles": True, "video_orientation": "portrait"})
        with patch.object(main, "process_workflow"):
            created = self.client.post("/api/workflows", json={"book_title": "字幕烧录"})
        workflow_id = created.json()["id"]

        async def fake_llm(messages, *_args):
            return broadcast_reply(messages)

        async def fake_speech(_text, _voice, _rate, _settings, target, *_args):
            target.write_bytes(b"audio")
            return target

        def fake_subtitles(audio_path, text, _language):
            from backend.integrations.subtitles import write_subtitle_files
            return write_subtitle_files(audio_path, [{"start": 0, "end": 1.5, "text": text or "烧录这句"}])

        async def fake_cover(path, *_args):
            Image.new("RGB", (120, 160), "navy").save(path, "PNG")
            return False, "120×160"

        captured = []

        class FinishedVideo:
            returncode = 0
            stdout = ""
            stderr = b""

        def fake_run(command, **_kwargs):
            captured.append(command)
            return FinishedVideo()

        with patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", side_effect=fake_speech), \
             patch.object(main, "generate_subtitles", side_effect=fake_subtitles), \
             patch.object(main, "generate_cover", side_effect=fake_cover), \
             patch.object(executor.subprocess, "run", side_effect=fake_run):
            asyncio.run(main.process_workflow(workflow_id))
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertEqual(workflow["status"], "completed", workflow.get("error"))
        encodes = [command for command in captured if "-filter_complex" in command]
        self.assertEqual(len(encodes), len(workflow["videos"]))
        video_filter = encodes[0][encodes[0].index("-filter_complex") + 1]
        self.assertIn("ass=", video_filter)
        self.assertIn("fontsdir=", video_filter)
        output_dir = main.MEDIA / workflow["output_dir"]
        ass = (output_dir / Path(workflow["videos"][0]["url"]).name).with_suffix(".ass").read_text(encoding="utf-8")
        self.assertIn("简短内容", ass)
        self.assertIn("&H00FFFFFF", ass)
        self.assertIn("&HFF000000", ass)
        self.assertTrue((output_dir / "draft-1-voice-1.srt").is_file())

    def test_blank_timeout_becomes_a_visible_workflow_error(self):
        self.assertEqual(executor.workflow_failure_message(TimeoutError("")), "文稿生成超时，模型在限定时间内没有返回")
        self.assertEqual(executor.workflow_failure_message(RuntimeError("封面生成失败")), "封面生成失败")
        self.assertEqual(executor.workflow_failure_message(RuntimeError("   ")), "制作失败：RuntimeError")

    def test_broadcast_uses_fixed_stages_with_snapshotted_book_and_template(self):
        writing = self.client.post("/api/prompts", json={
            "kind": "writing", "name": "口播结构", "text": "用第一人称讲一个具体场景。", "duration_minutes": 5,
        }).json()
        calls = []
        sources = [{"id": "1", "url": "https://publisher.example/book", "excerpt": "作品简介", "title": "出版社目录"}]

        async def fake_llm(messages, _settings, request_type="文稿生成"):
            key = next(key for key, (_, _, instruction) in STAGES.items() if messages[0]["content"].endswith(instruction))
            data = json.loads(messages[1]["content"])
            self.assertIn("小琳爱读书的365天", messages[0]["content"])
            calls.append((key, data))
            if key == "research":
                reply = json.loads(broadcast_reply(messages))
                reply.update(unknowns=["没有具体版本的正文可供核对"], evidence=[{"point": "作品讨论了选择。", "source_ids": ["1"]}])
                return json.dumps(reply, ensure_ascii=False)
            if key == "review":
                self.assertTrue(data["research"]["unknowns"])
                if len([stage for stage, _ in calls if stage == key]) == 1:
                    return broadcast_reply(messages)
                self.assertEqual(data["script"], "最后交付的正文。")
            if key == "tts":
                return "最后交付的正文。" if data.get("review_feedback") else "没有具体版本的正文可供核对。待审核正文。"
            return broadcast_reply(messages)

        def run(payload):
            calls.clear()
            with patch.object(main, "process_workflow"):
                created = self.client.post("/api/workflows", json=payload)
            with patch.object(main, "search_book", AsyncMock(return_value=sources)) as search, \
                 patch.object(main, "llm", side_effect=fake_llm), patch.object(main, "speech", AsyncMock(side_effect=RuntimeError("draft captured"))) as speech:
                asyncio.run(main.process_workflow(created.json()["id"]))
            search.assert_awaited_once()
            speech.assert_awaited_once()
            self.assertEqual(speech.await_args.args[0], "最后交付的正文。")
            return self.client.get(f"/api/workflows/{created.json()['id']}").json()

        full = run({
            "book_title": "百年孤独", "author": "加西亚·马尔克斯", "edition": "精装纪念版",
            "writing_prompt_ids": [writing["id"]], "source_notes": "第一章的读书笔记",
        })
        self.assertEqual(full["step"], 3)
        self.assertNotIn("source_notes", full)
        self.assertEqual(full["writing_prompts"][0]["duration_minutes"], 5)
        self.assertEqual([key for key, _ in calls], [*STAGES, "edit", "tts", "review"])
        self.assertEqual(calls[0][1]["book"], {"book_title": "百年孤独", "author": "加西亚·马尔克斯", "edition": "精装纪念版"})
        self.assertEqual(calls[0][1]["web_sources"], sources)
        self.assertEqual(calls[2][1]["research"]["evidence"], ["作品讨论了选择。"])
        self.assertNotIn("unknowns", calls[2][1]["research"])
        self.assertEqual(calls[2][1]["template_preferences"], writing["text"])
        self.assertIn("5 分钟", calls[2][1]["length_requirement"])
        self.assertEqual(full["polished_drafts"][0]["text"], "最后交付的正文。")

        run({"book_title": "活着", "writing_prompt_ids": [writing["id"]]})
        self.assertEqual(calls[0][1]["book"], {"book_title": "活着"})

    def test_ambiguous_book_stops_before_writing_and_blank_titles_are_rejected(self):
        self.assertEqual(self.client.post("/api/workflows", json={"book_title": "  "}).status_code, 422)
        self.assertEqual(self.client.post("/api/workflows/batch", json={"books": [{"book_title": "  "}]}).status_code, 422)
        with patch.object(main, "process_workflow"):
            wid = self.client.post("/api/workflows", json={"book_title": "同名图书"}).json()["id"]
        response = {"match_status": "ambiguous", "author": "", "description": "", "evidence": [], "interpretations": [], "unknowns": []}
        with patch.object(main, "llm", AsyncMock(return_value=json.dumps(response))) as llm:
            asyncio.run(main.process_workflow(wid))
        llm.assert_awaited_once()
        workflow = self.client.get(f"/api/workflows/{wid}").json()
        self.assertEqual((workflow["status"], workflow["step"]), ("failed", 1))
        self.assertIn("同名书", workflow["error"])

    def test_firecrawl_settings_preserve_environment_and_mask_saved_key(self):
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "example-environment-key"}):
            form = self.client.get("/api/settings").json()
            self.assertTrue(form["firecrawl_enabled"])
            self.assertEqual(form["firecrawl_api_key"], "••••••••")
            self.assertEqual(self.client.put("/api/settings", json=form).json()["firecrawl_api_key"], "••••••••")
            with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "rotated-environment-key"}):
                self.assertEqual(main.get_settings()["firecrawl_api_key"], "rotated-environment-key")
            saved = self.client.put("/api/settings", json={**form, "firecrawl_enabled": False, "firecrawl_api_key": " example-page-key "}).json()
            self.assertFalse(saved["firecrawl_enabled"])
            self.assertEqual(saved["firecrawl_api_key"], "••••••••")
            self.client.put("/api/settings", json={"speech_rate": -5})
            self.assertFalse(main.get_settings()["firecrawl_enabled"])
            self.assertEqual(main.get_settings()["firecrawl_api_key"], "example-page-key")
            cleared = self.client.put("/api/settings", json={**saved, "firecrawl_api_key": ""})
            self.assertEqual(cleared.json()["firecrawl_api_key"], "")
            self.assertEqual(main.get_settings()["firecrawl_api_key"], "")

    def test_firecrawl_logs_bounded_searches_and_falls_back_after_provider_errors(self):
        book = {"book_title": "昆虫记", "author": "法布尔", "edition": "纪念版"}
        settings = {"firecrawl_enabled": True, "firecrawl_api_key": "example-firecrawl-key", "text_api_key": "test", "model": "mock"}
        calls = []

        def respond(request):
            self.assertEqual(str(request.url), "https://api.firecrawl.dev/v2/search")
            self.assertEqual(request.headers["Authorization"], "Bearer example-firecrawl-key")
            params = json.loads(request.content)
            self.assertEqual(params["query"], '"昆虫记" 法布尔 纪念版 图书 简介')
            self.assertEqual(params["limit"], 5)
            self.assertEqual(params["sources"], [{"type": "web"}])
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, json={"success": True, "data": {"web": [
                    {"title": "图书目录", "url": f"https://publisher.example/{index}", "markdown": "正文 " * 1500}
                    for index in range(8)
                ]}})
            if len(calls) == 2:
                return httpx.Response(429)
            raise httpx.ReadTimeout("example timeout")

        for attempt in range(3):
            client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            with patch.object(main.httpx, "AsyncClient", return_value=client):
                sources = asyncio.run(main.search_book(book, settings))
            if attempt == 0:
                self.assertEqual(len(sources), 5)
                self.assertTrue(all(len(page["excerpt"]) == 2000 for page in sources))
            else:
                self.assertEqual(sources, [])
        with patch.object(main.httpx, "AsyncClient") as client:
            self.assertEqual(asyncio.run(main.search_book(book, {**settings, "firecrawl_enabled": False})), [])
            client.assert_not_called()
        logs = self.client.get("/api/request-logs", params={"request_type": "图书资料搜索"}).json()
        self.assertEqual(logs["total"], 3)
        self.assertEqual({(row["request_params"]["result_count"], row["request_params"]["status"], row["request_params"]["http_status"])
                          for row in logs["items"]}, {(5, "ok", 200), (0, "failed", 429), (0, "timeout", None)})
        self.assertNotIn("example-firecrawl-key", json.dumps(logs))

    def test_migration_updates_only_the_unmodified_builtin_writing_prompt(self):
        for previous, expected in ((PREVIOUS_WRITING_GUIDANCE, DEFAULT_WRITING_GUIDANCE), ("我的自定义节目", "我的自定义节目")):
            with self.subTest(previous=previous):
                with main.db() as conn:
                    conn.execute("UPDATE prompt_templates SET text=?,duration_minutes=7 WHERE id=?", (previous, DEFAULT_WRITING_ID))
                    conn.execute("PRAGMA user_version=1")
                main.init_db()
                prompt = next(item for item in self.client.get("/api/prompts").json() if item["id"] == DEFAULT_WRITING_ID)
                self.assertEqual((prompt["text"], prompt["duration_minutes"]), (expected, 7))

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

    def test_old_workflow_steps_migrate_once_and_drafts_remain_available(self):
        with patch.object(main, "process_workflow"):
            ids = [self.client.post("/api/workflows", json={"book_title": "旧书"}).json()["id"] for _ in range(3)]
        for wid, step in zip(ids, [3, 4, 8]):
            main.save_workflow(wid, step=step, payload_update={"polished_drafts": [{"text": "旧稿"}]})
        with main.db() as conn:
            conn.execute("DELETE FROM prompt_templates WHERE id='writing-xiaolin'")
            conn.execute("ALTER TABLE prompt_templates DROP COLUMN duration_minutes")
            conn.execute("PRAGMA user_version=0")
        main.init_db()
        main.init_db()
        rows = [self.client.get(f"/api/workflows/{wid}").json() for wid in ids]
        self.assertEqual([row["step"] for row in rows], [2, 3, 7])
        self.assertTrue(all(row["polished_drafts"] == [{"text": "旧稿"}] for row in rows))
        pipeline = self.client.get("/api/prompts/writing-pipeline").json()
        self.assertEqual([stage["id"] for stage in pipeline["stages"]], list(STAGES))

    def test_twice_rejected_script_stops_at_writing_without_calling_speech(self):
        async def fake_llm(messages, *_args):
            if messages[0]["content"].endswith(STAGES["review"][2]):
                return '{"score":84,"critical_issues":["引文没有依据"],"suggestions":[],"revision_stage":"draft"}'
            return broadcast_reply(messages)

        with patch.object(main, "process_workflow"):
            wid = self.client.post("/api/workflows", json={"book_title": "审核测试"}).json()["id"]
        with patch.object(main, "llm", side_effect=fake_llm), patch.object(main, "speech", AsyncMock()) as speech:
            asyncio.run(main.process_workflow(wid))
        speech.assert_not_awaited()
        workflow = self.client.get(f"/api/workflows/{wid}").json()
        self.assertEqual((workflow["status"], workflow["step"]), ("failed", 2))
        self.assertIn("引文没有依据", workflow["error"])

    def test_workflow_snapshots_background_music_mix(self):
        music = self.client.post("/api/background-music", json={"name": "夜读", "url": "https://example.com/night.mp3", "category": "安静"}).json()
        with patch.object(main, "process_workflow"):
            response = self.client.post("/api/workflows", json={"book_title": "混音测试", "background_music_id": music["id"], "background_music_volume": .35, "background_music_fade_in": 1.5, "background_music_fade_out": 4})
        workflow = self.client.get(f"/api/workflows/{response.json()['id']}").json()
        self.assertEqual(workflow["background_music"]["name"], "夜读")
        self.assertEqual(workflow["background_music_volume"], .35)
        self.assertEqual(workflow["background_music_fade_in"], 1.5)
        self.assertEqual(workflow["background_music_fade_out"], 4)

        rejected = self.client.post("/api/workflows", json={
            "book_title": "音量超限", "background_music_id": music["id"],
            "background_music_volume": 1.01,
        })
        self.assertEqual(rejected.status_code, 422)

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
        self.assertTrue(all(item["background_music_volume"] == .2 for item in workflows))
        self.assertTrue(all(item["writing_prompts"][0]["id"] == writing["id"] and item["cover_prompts"][0]["id"] == cover["id"] for item in workflows))

    def test_speech_ssml_puts_background_audio_before_voice(self):
        ssml = main.speech_ssml(
            "带背景音乐的口播", "zh-CN-XiaoxiaoNeural", 0,
            {"url": "https://example.com/music?a=1&b=2"}, .35, 1.5, 4,
        )
        root = ET.fromstring(ssml)
        children = list(root)
        self.assertEqual(children[0].tag, "{https://www.w3.org/2001/mstts}backgroundaudio")
        self.assertTrue(children[1].tag.endswith("voice"))
        self.assertEqual(children[0].attrib, {
            "src": "https://example.com/music?a=1&b=2",
            "volume": "0.35", "fadein": "1500", "fadeout": "4000",
        })

    def test_batch_runner_processes_workflows_concurrently(self):
        active = 0
        maximum_active = 0
        all_started = asyncio.Event()

        async def fake_process(_wid):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 3:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=.2)
            active -= 1

        with patch.object(main, "process_workflow", side_effect=fake_process):
            asyncio.run(main.process_workflows_parallel(["one", "two", "three"]))
        self.assertEqual(maximum_active, 3)

    def test_speech_ssml_contains_safe_rate_and_escaped_content(self):
        ssml = main.speech_ssml("读书 < 思考", 'voice"name', 120)
        self.assertIn('rate="+100%"', ssml)
        self.assertIn('name="voice&quot;name"', ssml)
        self.assertIn("读书 &lt; 思考", ssml)
        self.assertIn('xml:lang="zh-CN"', ssml)

    def test_voice_sample_is_translated_and_cached_by_locale(self):
        async def fake_llm(_messages, _settings): return "Hello, welcome to this smooth and natural AI voice."
        settings = {**main.DEFAULT_SETTINGS, "text_api_key": "test"}
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
        calls = []
        class Response:
            def raise_for_status(self): pass
            def json(self): return [
                {
                    "ShortName": "zh-CN-XiaoxiaoNeural", "Locale": "zh-CN", "LocaleName": "Chinese (Mandarin, Simplified)",
                    "LocalName": "晓晓", "DisplayName": "Xiaoxiao", "Gender": "Female", "VoiceType": "Neural", "Status": "GA",
                    "SampleRateHertz": "48000", "StyleList": ["chat", "newscast"], "RolePlayList": ["YoungAdultFemale"],
                    "SecondaryLocaleList": ["en-US"], "VoiceTag": {"TailoredScenarios": ["Chat"], "VoicePersonalities": ["Warm"]},
                },
                {"ShortName": "en-US-JennyNeural"},
                {"ShortName": "ja-JP-NanamiNeural"},
                {"DisplayName": "missing short name"},
                "not-a-voice",
            ]
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def get(self, url, **_kwargs): calls.append(url); return Response()
        with patch.object(main, "get_settings", return_value={"azure_speech_key": "test", "azure_speech_base": "https://eastus.tts.speech.microsoft.com/"}), patch.object(main.httpx, "AsyncClient", return_value=Client()):
            result = asyncio.run(main.voices())
        self.assertEqual(calls, ["https://eastus.tts.speech.microsoft.com/cognitiveservices/voices/list"])
        self.assertEqual(result["voices"], ["zh-CN-XiaoxiaoNeural", "en-US-JennyNeural", "ja-JP-NanamiNeural"])
        self.assertEqual([item["short_name"] for item in result["items"]], result["voices"])
        xiaoxiao = result["items"][0]
        self.assertEqual(xiaoxiao["locale"], "zh-CN")
        self.assertEqual(xiaoxiao["locale_name"], "Chinese (Mandarin, Simplified)")
        self.assertEqual(xiaoxiao["local_name"], "晓晓")
        self.assertEqual(xiaoxiao["gender"], "Female")
        self.assertEqual(xiaoxiao["voice_type"], "Neural")
        self.assertEqual(xiaoxiao["status"], "GA")
        self.assertEqual(xiaoxiao["sample_rate_hertz"], "48000")
        self.assertEqual(xiaoxiao["styles"], ["chat", "newscast"])
        self.assertEqual(xiaoxiao["roles"], ["YoungAdultFemale"])
        self.assertEqual(xiaoxiao["secondary_locales"], ["en-US"])
        self.assertEqual(xiaoxiao["scenarios"], ["Chat"])
        self.assertEqual(xiaoxiao["personalities"], ["Warm"])
        jenny = result["items"][1]
        self.assertEqual(jenny["gender"], "")
        self.assertEqual(jenny["styles"], [])
        self.assertEqual(jenny["scenarios"], [])
        self.assertEqual(jenny["personalities"], [])

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
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertRegex(workflow["output_dir"], r"^\d{8}[a-z]{4}\d+$")
        output_dir = main.MEDIA / workflow["output_dir"]
        owned_cover = output_dir / "cover-1.png"
        owned_audio = output_dir / "draft-1-voice-1.mp3"
        unrelated = main.MEDIA / "another-workflow" / "cover-1.png"
        unrelated.parent.mkdir()
        owned_cover.write_bytes(b"cover"); owned_audio.write_bytes(b"audio"); unrelated.write_bytes(b"keep")
        with main.db() as conn:
            conn.execute("UPDATE workflows SET status='completed' WHERE id=?", (workflow_id,))
        response = self.client.delete(f"/api/workflows/{workflow_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed_files"], 2)
        self.assertFalse(owned_cover.exists()); self.assertFalse(owned_audio.exists())
        self.assertFalse(output_dir.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(self.client.get(f"/api/workflows/{workflow_id}").status_code, 404)

    def _completed_workflow(self, title: str) -> dict:
        with patch.object(main, "process_workflow"):
            created = self.client.post("/api/workflows", json={"book_title": title})
        workflow_id = created.json()["id"]

        async def fake_llm(messages, *_args):
            return broadcast_reply(messages)

        async def fake_speech(_text, _voice, _rate, _settings, target, *_args):
            target.write_bytes(b"audio-bytes")
            return target

        def fake_subtitles(audio_path, text, _language):
            from backend.integrations.subtitles import write_subtitle_files
            return write_subtitle_files(audio_path, [{"start": 0, "end": 1.5, "text": text or "原字幕"}])

        async def fake_cover(path, *_args):
            Image.new("RGB", (120, 160), "navy").save(path, "PNG")
            return False, "120×160"

        class FinishedVideo:
            returncode = 0
            stdout = ""
            stderr = b""

        def fake_run(command, **_kwargs):
            Path(command[-1]).write_bytes(b"original-video")
            return FinishedVideo()

        with patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", side_effect=fake_speech), \
             patch.object(main, "generate_subtitles", side_effect=fake_subtitles), \
             patch.object(main, "generate_cover", side_effect=fake_cover), \
             patch.object(executor.subprocess, "run", side_effect=fake_run):
            asyncio.run(main.process_workflow(workflow_id))
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertEqual(workflow["status"], "completed", workflow.get("error"))
        self.assertTrue(workflow["videos"])
        return workflow

    def _cover_workflow(self):
        with patch.object(main, "process_workflow"):
            wid = self.client.post("/api/workflows", json={"book_title": "旧作品", "author": "作者"}).json()["id"]
        item = self.client.get(f"/api/workflows/{wid}").json()
        output = main.MEDIA / item["output_dir"]
        covers = [{"url": f"/media/{output.name}/cover-1.png", "image_ratio": "1:1", "provider": "local_template", "template_id": "literary-square"},
                  {"url": f"/media/{output.name}/cover-2.png", "image_ratio": "16:9", "provider": "openai_compatible", "prompt": "原记录的创作提示词"}]
        for index, size in enumerate(((100, 100), (160, 90)), 1):
            Image.new("RGB", size, "navy").save(output / f"cover-{index}.png")
        assets = {"audio": [{"url": f"/media/{output.name}/track.mp3"}], "videos": [{"url": f"/media/{output.name}/video.mp4"}],
                  "subtitles": [{"srt_url": f"/media/{output.name}/track.srt"}], "polished_drafts": [{"text": "已完成的播讲稿"}]}
        main.save_workflow(wid, status="completed", step=7, progress=100, payload_update={"covers": covers, **assets})
        return wid, output, covers, assets

    def test_regenerating_one_legacy_cover_preserves_other_assets(self):
        wid, output, covers, assets = self._cover_workflow()
        with patch.object(main, "generate_cover", AsyncMock()) as ai:
            response = self.client.post(f"/api/workflows/{wid}/regenerate-cover", json={"cover_url": covers[0]["url"]})
        self.assertEqual(response.status_code, 202)
        ai.assert_not_called()
        item = self.client.get(f"/api/workflows/{wid}").json()
        self.assertIsNone(item["cover_regenerating"])
        self.assertIsNone(item["cover_error"])
        self.assertEqual(item["covers"][1], covers[1])
        first = item["covers"][0]
        self.assertNotEqual(first["template_id"], covers[0]["template_id"])
        with Image.open(output / Path(first["url"]).name) as image:
            self.assertEqual(image.size, (1080, 1080))

        async def generate(path, title, author, description, prompt, index, ratio, settings, *, allow_fallback):
            self.assertEqual((prompt, ratio, allow_fallback), (covers[1]["prompt"], "16:9", False))
            Image.new("RGB", (320, 180), "beige").save(path)
            return True, "320×180"

        with patch.object(main, "generate_cover", side_effect=generate) as ai:
            response = self.client.post(f"/api/workflows/{wid}/regenerate-cover", json={"cover_url": covers[1]["url"]})
        self.assertEqual(response.status_code, 202)
        ai.assert_awaited_once()
        item = self.client.get(f"/api/workflows/{wid}").json()
        self.assertEqual(item["covers"][0], first)
        self.assertNotEqual(item["covers"][1]["url"], covers[1]["url"])
        self.assertTrue((output / Path(item["covers"][1]["url"]).name).is_file())
        for key, expected in assets.items():
            self.assertEqual(item[key], expected)

    def test_cover_regeneration_failure_conflicts_and_restart_keep_old_images(self):
        wid, output, covers, _ = self._cover_workflow()
        endpoint = f"/api/workflows/{wid}/regenerate-cover"
        body = {"cover_url": covers[1]["url"]}
        files = {path.name: path.read_bytes() for path in output.iterdir()}
        with patch.object(main, "generate_cover", AsyncMock(side_effect=RuntimeError("图片服务失败"))):
            self.assertEqual(self.client.post(endpoint, json=body).status_code, 202)
        after = self.client.get(f"/api/workflows/{wid}").json()
        self.assertEqual(after["covers"], covers)
        self.assertEqual(after["cover_error"], {"cover_url": body["cover_url"], "message": "图片服务失败"})
        self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, files)
        self.assertEqual(self.client.post(endpoint, json={"cover_url": "/media/other/cover.png"}).status_code, 404)

        with patch.object(main, "process_cover_regeneration", AsyncMock()):
            self.assertEqual(self.client.post(endpoint, json=body).status_code, 202)
            self.assertEqual(self.client.post(endpoint, json={"cover_url": covers[0]["url"]}).status_code, 409)
            self.assertEqual(self.client.post(f"/api/workflows/{wid}/regenerate-video").status_code, 409)
            self.assertEqual(self.client.post(f"/api/workflows/{wid}/regenerate-audio", json={"voice": "zh-CN-XiaoxiaoNeural"}).status_code, 409)
            self.assertEqual(self.client.post(f"/api/workflows/{wid}/retry").status_code, 409)
        main.release_interrupted_video_regenerations(main.db)
        current = self.client.get(f"/api/workflows/{wid}").json()
        self.assertIsNone(current["cover_regenerating"])
        self.assertEqual(current["cover_error"]["cover_url"], body["cover_url"])
        self.assertIn("中断", current["cover_error"]["message"])
        self.assertEqual(current["covers"], covers)

    def test_completed_workflow_regenerates_video_from_current_settings_only(self):
        before = self._completed_workflow("按设置重合成")
        output_dir = main.MEDIA / before["output_dir"]
        preserved = {
            "audio": (output_dir / "draft-1-voice-1.mp3").read_bytes(),
            "srt": (output_dir / "draft-1-voice-1.srt").read_bytes(),
            "cover": (output_dir / "cover-1.png").read_bytes(),
        }
        self.client.put("/api/settings", json={**main.DEFAULT_SETTINGS, "video_orientation": "landscape", "burn_subtitles": True, "video_generation_method": "local"})
        captured = []

        class FinishedVideo:
            returncode = 0
            stdout = ""
            stderr = b""

        def fake_run(command, **_kwargs):
            captured.append(command)
            Path(command[-1]).write_bytes(b"regenerated-video")
            return FinishedVideo()

        llm, speech, cover, subtitles = AsyncMock(), AsyncMock(), AsyncMock(), Mock()
        with patch.object(main, "llm", llm), patch.object(main, "speech", speech), \
             patch.object(main, "generate_cover", cover), patch.object(main, "generate_subtitles", subtitles), \
             patch.object(executor.subprocess, "run", side_effect=fake_run):
            response = self.client.post(f"/api/workflows/{before['id']}/regenerate-video")
        self.assertEqual(response.status_code, 202)
        llm.assert_not_called(); speech.assert_not_called(); cover.assert_not_called(); subtitles.assert_not_called()
        after = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(after["status"], "completed", after.get("video_error"))
        self.assertFalse(after["video_regenerating"])
        self.assertEqual(after["video_error"], "")
        for key in ("description", "original_drafts", "polished_drafts", "audio", "covers", "tags", "topics"):
            self.assertEqual(after[key], before[key])
        self.assertEqual((output_dir / "draft-1-voice-1.mp3").read_bytes(), preserved["audio"])
        self.assertEqual((output_dir / "draft-1-voice-1.srt").read_bytes(), preserved["srt"])
        self.assertEqual((output_dir / "cover-1.png").read_bytes(), preserved["cover"])
        self.assertFalse((output_dir / "video-1.mp4").exists())
        command = " ".join(str(part) for part in captured[0])
        self.assertIn(".layer.png", command)
        self.assertNotIn("cover-2.png", command)
        self.assertIn("scale=1920:1080", command)
        self.assertIn(".ass", command)
        new_video = output_dir / Path(after["videos"][0]["url"]).name
        self.assertEqual(new_video.read_bytes(), b"regenerated-video")
        self.assertEqual(after["videos"][0]["orientation"], "landscape")
        self.assertEqual(after["videos"][0]["source"], "local")
        self.assertEqual(after["videos"][0]["resolution"], "1920 × 1080")
        ass = new_video.with_suffix(".ass").read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1920", ass)
        self.assertIn("PlayResY: 1080", ass)
        self.assertNotIn(before["id"], main.REGENERATING_VIDEOS)

    def test_second_orientation_failure_keeps_all_previous_assets(self):
        before = self._completed_workflow("第二版失败")
        main.save_workflow(before["id"], payload_update={"covers": [c for c in before["covers"] if c["image_ratio"] != "1:1"]})
        before = self.client.get(f"/api/workflows/{before['id']}").json()
        root = main.MEDIA / before["output_dir"]
        previous = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
        count = 0
        def encode(command, **kwargs):
            nonlocal count
            count += 1
            Path(command[-1]).write_bytes(b"partial")
            return type("Result", (), {"returncode": 1 if count == 2 else 0, "stderr": b"second encode failed"})()
        with patch.object(executor.subprocess, "run", side_effect=encode):
            self.assertEqual(self.client.post(f"/api/workflows/{before['id']}/regenerate-video").status_code, 202)
        after = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(after["videos"], before["videos"])
        self.assertEqual(after["subtitles"], before["subtitles"])
        self.assertTrue(after["video_error"])
        self.assertEqual({p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}, previous)

    def test_failed_video_regeneration_keeps_the_previous_video(self):
        before = self._completed_workflow("合成失败保留")
        output_dir = main.MEDIA / before["output_dir"]

        class FailedVideo:
            returncode = 1
            stdout = ""
            stderr = b"failed"

        def fake_run(command, **_kwargs):
            Path(command[-1]).write_bytes(b"broken")
            return FailedVideo()

        speech, cover, subtitles = AsyncMock(), AsyncMock(), Mock()
        with patch.object(main, "llm", AsyncMock()), patch.object(main, "speech", speech), \
             patch.object(main, "generate_cover", cover), patch.object(main, "generate_subtitles", subtitles), \
             patch.object(executor.subprocess, "run", side_effect=fake_run):
            response = self.client.post(f"/api/workflows/{before['id']}/regenerate-video")
        self.assertEqual(response.status_code, 202)
        speech.assert_not_called(); cover.assert_not_called(); subtitles.assert_not_called()
        after = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(after["status"], "completed")
        self.assertEqual(after["videos"], before["videos"])
        self.assertEqual(after["polished_drafts"], before["polished_drafts"])
        self.assertEqual(after["audio"], before["audio"])
        self.assertEqual(after["covers"], before["covers"])
        self.assertEqual(after["subtitles"], before["subtitles"])
        self.assertFalse(after["video_regenerating"])
        self.assertIn("保留原来的视频", after["video_error"])
        self.assertEqual((output_dir / Path(before["videos"][0]["url"]).name).read_bytes(), b"original-video")
        self.assertEqual({p.name for p in output_dir.glob("video-1-*.mp4")}, {Path(v["url"]).name for v in before["videos"]})

    def test_video_regeneration_rejects_unfinished_or_incomplete_works(self):
        with patch.object(main, "process_workflow"):
            queued = self.client.post("/api/workflows", json={"book_title": "仍在排队"})
        rejected = self.client.post(f"/api/workflows/{queued.json()['id']}/regenerate-video")
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("已完成", rejected.json()["detail"])
        self.assertEqual(self.client.post("/api/workflows/missing/regenerate-video").status_code, 404)
        workflow = self._completed_workflow("缺少配音")
        main.save_workflow(workflow["id"], payload_update={"audio": []})
        missing_audio = self.client.post(f"/api/workflows/{workflow['id']}/regenerate-video")
        self.assertEqual(missing_audio.status_code, 409)
        self.assertIn("配音", missing_audio.json()["detail"])

    def test_video_regeneration_cannot_start_twice(self):
        workflow = self._completed_workflow("重复点击")

        async def stuck(_wid):
            return

        with patch.object(main, "process_video_regeneration", side_effect=stuck):
            first = self.client.post(f"/api/workflows/{workflow['id']}/regenerate-video")
            second = self.client.post(f"/api/workflows/{workflow['id']}/regenerate-video")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        current = self.client.get(f"/api/workflows/{workflow['id']}").json()
        self.assertEqual(current["status"], "completed")
        self.assertTrue(current["video_regenerating"])
        self.assertEqual(current["videos"], workflow["videos"])

    def test_interrupted_video_regeneration_is_released_for_another_attempt(self):
        from backend.modules.workflows.application import release_interrupted_video_regenerations
        workflow = self._completed_workflow("中断恢复")
        main.save_workflow(workflow["id"], payload_update={"video_regenerating": True, "video_error": ""})
        release_interrupted_video_regenerations(main.db)
        restored = self.client.get(f"/api/workflows/{workflow['id']}").json()
        self.assertFalse(restored["video_regenerating"])
        self.assertIn("中断", restored["video_error"])
        self.assertEqual(restored["videos"], workflow["videos"])
        self.assertEqual(restored["audio"], workflow["audio"])

    def test_interrupted_creation_is_failed_and_keeps_completed_steps(self):
        from backend.modules.workflows.application import release_interrupted_video_regenerations
        workflow = self._completed_workflow("制作中断")
        main.save_workflow(workflow["id"], status="running", step=5, progress=58)
        release_interrupted_video_regenerations(main.db)
        restored = self.client.get(f"/api/workflows/{workflow['id']}").json()
        self.assertEqual(restored["status"], "failed")
        self.assertEqual(restored["step"], 5)
        self.assertIn("中断", restored["error"])
        self.assertEqual(restored["audio"], workflow["audio"])

    def test_stock_video_regeneration_downloads_footage_without_recreating_assets(self):
        before = self._completed_workflow("素材重合成")
        self.client.put("/api/settings", json={
            **main.DEFAULT_SETTINGS, "video_orientation": "landscape", "video_generation_method": "stock",
            "stock_video_provider": "pexels", "pexels_api_key": "pexels-test",
        })
        download_calls = {}

        async def fake_download(**kwargs):
            download_calls.update(kwargs)
            paths = []
            for index in range(3):
                path = kwargs["output_dir"] / f"clip-{index}.mp4"
                path.write_bytes(b"clip")
                paths.append(path)
            return paths

        llm_types = []

        async def fake_llm(_messages, _settings, request_type="文稿生成"):
            llm_types.append(request_type)
            return "misty mountain lake"

        speech, cover, subtitles = AsyncMock(), AsyncMock(), Mock()
        captured = []

        class FinishedVideo:
            returncode = 0
            stdout = ""
            stderr = b""

        def fake_run(command, **_kwargs):
            captured.append([str(part) for part in command])
            Path(command[-1]).write_bytes(b"stock-video")
            return FinishedVideo()

        with patch.object(main, "download_stock_videos", side_effect=fake_download), \
             patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", speech), patch.object(main, "generate_cover", cover), \
             patch.object(main, "generate_subtitles", subtitles), \
             patch.object(executor.subprocess, "run", side_effect=fake_run):
            response = self.client.post(f"/api/workflows/{before['id']}/regenerate-video")
        self.assertEqual(response.status_code, 202)
        after = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(after.get("video_error"), "", captured)
        self.assertEqual(after["status"], "completed")
        self.assertEqual(llm_types, ["视频搜索词生成"])
        self.assertIn("stock-videos-", " ".join(captured[0]))
        self.assertEqual(download_calls["target_duration"], 1.5)
        self.assertEqual(download_calls["provider"], "pexels")
        self.assertEqual(download_calls["orientation"], "landscape")
        self.assertEqual(download_calls["api_key"], "pexels-test")
        self.assertEqual(after["videos"][0]["source"], "pexels")
        self.assertEqual(after["videos"][0]["orientation"], "landscape")
        self.assertNotEqual(after["videos"][0]["url"], before["videos"][0]["url"])
        for key in ("description", "polished_drafts", "audio", "covers"):
            self.assertEqual(after[key], before[key])
        speech.assert_not_called(); cover.assert_not_called(); subtitles.assert_not_called()


    def test_regenerated_audio_and_subtitles_are_used_by_later_video(self):
        before = self._completed_workflow("重配后再合成")
        output_dir = main.MEDIA / before["output_dir"]
        old_audio = output_dir / "draft-1-voice-1.mp3"
        old_srt = output_dir / "draft-1-voice-1.srt"
        self.assertEqual(old_audio.read_bytes(), b"audio-bytes")
        speech_calls = []

        async def fake_speech(text, voice, rate, _settings, target, *_args):
            speech_calls.append((text, voice, rate))
            target.write_bytes(b"new-audio")
            return target

        def fake_subtitles(audio_path, _text, language):
            self.assertEqual(language, "en")
            from backend.integrations.subtitles import write_subtitle_files
            return write_subtitle_files(audio_path, [{"start": 0.2, "end": 1.8, "text": "新字幕"}])

        with patch.object(main, "speech", side_effect=fake_speech), patch.object(main, "generate_subtitles", side_effect=fake_subtitles):
            response = self.client.post(f"/api/workflows/{before['id']}/regenerate-audio", json={"voice": " en-US-JennyNeural "})
        self.assertEqual(response.status_code, 202, response.text)
        regenerated = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(regenerated["status"], "completed", regenerated.get("audio_error"))
        self.assertFalse(regenerated["audio_regenerating"])
        self.assertEqual(regenerated["audio_error"], "")
        self.assertEqual(regenerated["voices"], ["en-US-JennyNeural"])
        self.assertEqual(len(regenerated["audio"]), 1)
        self.assertEqual(regenerated["audio"][0]["voice"], "en-US-JennyNeural")
        self.assertEqual(regenerated["audio"][0]["speech_rate"], before["audio"][0]["speech_rate"])
        self.assertEqual(regenerated["subtitles"][0]["voice"], "en-US-JennyNeural")
        self.assertEqual(regenerated["covers"], before["covers"])
        self.assertEqual(regenerated["videos"], before["videos"])
        self.assertEqual(speech_calls, [("简短内容", "en-US-JennyNeural", before["audio"][0]["speech_rate"])])
        new_audio = output_dir / Path(regenerated["audio"][0]["url"]).name
        new_srt = output_dir / Path(regenerated["subtitles"][0]["srt_url"]).name
        self.assertNotEqual(new_audio.name, old_audio.name)
        self.assertEqual(new_audio.read_bytes(), b"new-audio")
        self.assertIn("新字幕", new_srt.read_text(encoding="utf-8"))
        self.assertFalse(old_audio.exists())
        self.assertFalse(old_srt.exists())

        self.client.put("/api/settings", json={**main.DEFAULT_SETTINGS, "burn_subtitles": True, "video_orientation": "portrait", "video_generation_method": "local"})
        captured = []

        class FinishedVideo:
            returncode = 0
            stdout = ""
            stderr = b""

        def fake_run(command, **_kwargs):
            captured.append([str(part) for part in command])
            Path(command[-1]).write_bytes(b"video-from-new-audio")
            return FinishedVideo()

        speech, subtitles = AsyncMock(), Mock()
        with patch.object(main, "llm", AsyncMock(return_value="quiet lake")), patch.object(main, "speech", speech), \
             patch.object(main, "generate_cover", AsyncMock()), patch.object(main, "generate_subtitles", subtitles), \
             patch.object(executor.subprocess, "run", side_effect=fake_run):
            video_response = self.client.post(f"/api/workflows/{before['id']}/regenerate-video")
        self.assertEqual(video_response.status_code, 202)
        speech.assert_not_called(); subtitles.assert_not_called()
        after = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(after.get("video_error"), "", captured)
        self.assertEqual(after["audio"], regenerated["audio"])
        self.assertEqual(after["subtitles"][0]["voice"], regenerated["subtitles"][0]["voice"])
        command = captured[0]
        narration = next(part for part in command if part.endswith(".mp3"))
        self.assertEqual(Path(narration).name, new_audio.name)
        ass = (output_dir / Path(after["videos"][0]["url"]).name).with_suffix(".ass").read_text(encoding="utf-8")
        self.assertIn("新字幕", ass)
        self.assertNotIn("简短内容", ass)

    def test_failed_audio_regeneration_keeps_previous_narration(self):
        before = self._completed_workflow("配音失败保留")
        output_dir = main.MEDIA / before["output_dir"]

        async def fake_speech(*_args, **_kwargs):
            raise RuntimeError("语音服务不可用")

        with patch.object(main, "speech", side_effect=fake_speech), patch.object(main, "generate_subtitles", Mock()):
            response = self.client.post(f"/api/workflows/{before['id']}/regenerate-audio", json={"voice": "en-US-JennyNeural"})
        self.assertEqual(response.status_code, 202)
        after = self.client.get(f"/api/workflows/{before['id']}").json()
        self.assertEqual(after["audio"], before["audio"])
        self.assertEqual(after["subtitles"], before["subtitles"])
        self.assertFalse(after["audio_regenerating"])
        self.assertIn("语音服务不可用", after["audio_error"])
        self.assertEqual((output_dir / "draft-1-voice-1.mp3").read_bytes(), b"audio-bytes")
        self.assertEqual(list(output_dir.glob("draft-1-voice-1-*")), [])

    def test_audio_regeneration_rejects_invalid_or_busy_work(self):
        with patch.object(main, "process_workflow"):
            queued = self.client.post("/api/workflows", json={"book_title": "仍在排队"})
        rejected = self.client.post(f"/api/workflows/{queued.json()['id']}/regenerate-audio", json={"voice": "en-US-JennyNeural"})
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("已完成", rejected.json()["detail"])
        self.assertEqual(self.client.post("/api/workflows/missing/regenerate-audio", json={"voice": "en-US-JennyNeural"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/workflows/{queued.json()['id']}/regenerate-audio", json={"voice": " "}).status_code, 422)
        workflow = self._completed_workflow("配音条件")
        main.save_workflow(workflow["id"], payload_update={"polished_drafts": []})
        missing_drafts = self.client.post(f"/api/workflows/{workflow['id']}/regenerate-audio", json={"voice": "en-US-JennyNeural"})
        self.assertEqual(missing_drafts.status_code, 409)
        self.assertIn("分享稿", missing_drafts.json()["detail"])
        busy = self._completed_workflow("正在合成视频")
        main.save_workflow(busy["id"], payload_update={"video_regenerating": True})
        while_video = self.client.post(f"/api/workflows/{busy['id']}/regenerate-audio", json={"voice": "en-US-JennyNeural"})
        self.assertEqual(while_video.status_code, 409)
        self.assertIn("视频", while_video.json()["detail"])
        narrating = self._completed_workflow("正在重配")
        main.save_workflow(narrating["id"], payload_update={"audio_regenerating": True})
        while_audio = self.client.post(f"/api/workflows/{narrating['id']}/regenerate-video")
        self.assertEqual(while_audio.status_code, 409)
        self.assertIn("配音", while_audio.json()["detail"])

    def test_audio_regeneration_cannot_start_twice(self):
        workflow = self._completed_workflow("重复重配")

        async def stuck(_wid):
            return

        with patch.object(main, "process_audio_regeneration", side_effect=stuck):
            first = self.client.post(f"/api/workflows/{workflow['id']}/regenerate-audio", json={"voice": "en-US-JennyNeural"})
            second = self.client.post(f"/api/workflows/{workflow['id']}/regenerate-audio", json={"voice": "en-US-JennyNeural"})
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        current = self.client.get(f"/api/workflows/{workflow['id']}").json()
        self.assertTrue(current["audio_regenerating"])
        self.assertEqual(current["audio"], workflow["audio"])
        self.assertEqual(current["subtitles"], workflow["subtitles"])
        main.REGENERATING_AUDIO.discard(workflow["id"])

    def test_interrupted_audio_regeneration_is_released_for_another_attempt(self):
        from backend.modules.workflows.application import release_interrupted_video_regenerations
        workflow = self._completed_workflow("配音中断")
        main.save_workflow(workflow["id"], payload_update={"audio_regenerating": True, "audio_error": ""})
        release_interrupted_video_regenerations(main.db)
        restored = self.client.get(f"/api/workflows/{workflow['id']}").json()
        self.assertFalse(restored["audio_regenerating"])
        self.assertIn("中断", restored["audio_error"])
        self.assertEqual(restored["audio"], workflow["audio"])
        self.assertEqual(restored["subtitles"], workflow["subtitles"])


if __name__ == "__main__":
    unittest.main()
