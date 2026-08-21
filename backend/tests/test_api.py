import tempfile
import asyncio
import base64
import io
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from fastapi.testclient import TestClient

import backend.main as main
from backend.modules.workflows import executor


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

    def test_creator_pages_private_network_preflight_is_allowed(self):
        for origin in ("https://creator.douyin.com", "https://cp.kuaishou.com", "https://member.bilibili.com", "https://creator.xiaohongshu.com", "https://baijiahao.baidu.com"):
            response = self.client.options("/api/publish/extension/tasks/next", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-StoryForge-Token",
                "Access-Control-Request-Private-Network": "true",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
            self.assertEqual(response.headers["access-control-allow-private-network"], "true")

    def test_create_rejects_missing_title(self):
        response = self.client.post("/api/workflows", json={"book_title": ""})
        self.assertEqual(response.status_code, 422)

    def test_settings_masks_secrets(self):
        payload = {**main.DEFAULT_SETTINGS, "api_key": "secret", "azure_speech_key": "speech", "pexels_api_key": "pexels", "pixabay_api_key": "pixabay"}
        response = self.client.put("/api/settings", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api_key"], "••••••••")
        self.assertEqual(response.json()["pexels_api_key"], "••••••••")
        self.assertEqual(response.json()["pixabay_api_key"], "••••••••")
        self.assertEqual(response.json()["video_orientation"], "portrait")
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
        self.assertEqual(cover.json()["image_sizes"], ["16:9", "9:16"])

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
            async def post(self, *args, **kwargs): calls.append(kwargs); return Response()

        target = main.MEDIA / "ratio-cover.png"
        with patch.object(main.httpx, "AsyncClient", return_value=Client()):
            generated, resolution = asyncio.run(main.generate_cover(target, "测试书", "作者", "简介", "文学感", 0, "16:9", {"api_base": "https://example.com/v1", "api_key": "key"}))
        self.assertTrue(generated); self.assertEqual(resolution, "73×41")
        self.assertEqual(calls[0]["json"]["model"], "gpt-image-2")
        self.assertNotIn("size", calls[0]["json"])
        self.assertIn("图片比例：16:9", calls[0]["json"]["prompt"])
        self.assertEqual(target.read_bytes(), raw.getvalue())

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

        settings = {**main.DEFAULT_SETTINGS, "api_key": "key", "api_base": "https://example.com/v1"}
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

        settings = {**main.DEFAULT_SETTINGS, "api_key": "key", "api_base": "https://example.com/v1"}
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
            if "书籍简介" in messages[0]["content"]:
                return "一部讲述取经团队历经考验、坚持理想的古典小说。"
            if "Humanizer-zh" in messages[0]["content"]:
                return "这是一篇更自然的《西游记》分享稿。"
            return "这是一篇《西游记》分享稿。"

        async def fake_speech(_text, _voice, _rate, _settings, target, *_args):
            target.write_bytes(b"audio")
            return False

        async def fake_cover(path, *_args):
            Image.new("RGB", (120, 160), "navy").save(path, "PNG")
            return True, "120×160"

        class FailedVideo:
            returncode = 1

        with patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", side_effect=fake_speech), \
             patch.object(main, "generate_cover", side_effect=fake_cover), \
             patch.object(executor.subprocess, "run", return_value=FailedVideo()):
            asyncio.run(main.process_workflow(workflow_id))
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertEqual(workflow["step"], 7)
        self.assertEqual(workflow["status"], "completed")
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

        async def fake_llm(*_args, **_kwargs):
            return "简短内容"

        async def fake_speech(_text, _voice, _rate, _settings, target, *_args):
            target.write_bytes(b"audio")
            return False

        async def fake_cover(path, *_args):
            Image.new("RGB", (120, 160), "navy").save(path, "PNG")
            return False, "120×160"

        class FailedVideo:
            returncode = 1

        with patch.object(main, "llm", side_effect=fake_llm), \
             patch.object(main, "speech", side_effect=fake_speech), \
             patch.object(main, "generate_cover", side_effect=fake_cover), \
             patch.object(executor.subprocess, "run", return_value=FailedVideo()):
            asyncio.run(main.process_workflow(workflow_id))
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        self.assertEqual(workflow["status"], "completed")
        self.assertEqual(workflow["covers"][0]["image_ratio"], "16:9")

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

    def test_douyin_publish_task_pairing_and_status_flow(self):
        with patch.object(main, "process_workflow"):
            created = self.client.post("/api/workflows", json={"book_title": "准备发布"})
        workflow_id = created.json()["id"]
        workflow = self.client.get(f"/api/workflows/{workflow_id}").json()
        video_url = f"/media/{workflow['output_dir']}/video-1.mp4"
        cover_url = f"/media/{workflow['output_dir']}/cover-1.png"
        horizontal_cover_url = f"/media/{workflow['output_dir']}/cover-2.png"
        square_cover_url = f"/media/{workflow['output_dir']}/cover-3.png"
        (main.MEDIA / workflow["output_dir"] / "video-1.mp4").write_bytes(b"test-video")
        (main.MEDIA / workflow["output_dir"] / "cover-1.png").write_bytes(b"test-cover")
        (main.MEDIA / workflow["output_dir"] / "cover-2.png").write_bytes(b"horizontal-cover")
        with main.db() as conn:
            row = conn.execute("SELECT payload FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            payload = main.json.loads(row["payload"])
            payload.update(
                videos=[{"url": video_url}], tags=["文学名著", "人物成长"],
                topics=["读书", "好书推荐"],
                covers=[{"url": cover_url, "image_ratio": "3:4"}, {"url": horizontal_cover_url, "image_ratio": "4:3"}, {"url": square_cover_url, "image_ratio": "1:1"}],
            )
            conn.execute("UPDATE workflows SET status='completed',payload=? WHERE id=?",
                         (main.json.dumps(payload, ensure_ascii=False), workflow_id))
        task_response = self.client.post("/api/publish/tasks", json={
            "workflow_id": workflow_id, "platform": "douyin", "title": "一本值得读的书",
            "description": "这是作品简介", "topics": ["读书", "好书推荐", "名著解读", "读书分享", "经典文学", "文学阅读", "#读书"],
            "video_url": video_url, "cover_urls": [cover_url, horizontal_cover_url],
        })
        self.assertEqual(task_response.status_code, 201)
        task = task_response.json()
        self.assertEqual(task["status"], "prepared")
        self.assertEqual(task["tags"], ["文学名著", "人物成长"])
        self.assertEqual(task["topics"], ["读书", "好书推荐", "名著解读", "读书分享", "经典文学"])
        self.assertEqual([cover["image_ratio"] for cover in task["covers"]], ["3:4", "4:3"])
        unsupported = self.client.post("/api/publish/tasks", json={
            "workflow_id": workflow_id, "title": "不裁剪方图", "video_url": video_url,
            "cover_urls": [square_cover_url],
        })
        self.assertEqual(unsupported.status_code, 422)
        self.assertIn("原图直传3:4或4:3", unsupported.json()["detail"])
        pairing = self.client.get("/api/publish/pairing").json()
        self.assertEqual(self.client.get("/api/publish/extension/tasks/next").status_code, 401)
        headers = {"X-StoryForge-Token": pairing["token"]}
        next_task = self.client.get("/api/publish/extension/tasks/next", headers=headers).json()["task"]
        self.assertEqual(next_task["id"], task["id"])
        video = self.client.get(f"/api/publish/extension/tasks/{task['id']}/video", headers=headers)
        self.assertEqual(video.status_code, 200)
        self.assertEqual(video.content, b"test-video")
        cover = self.client.get(f"/api/publish/extension/tasks/{task['id']}/cover", headers=headers)
        self.assertEqual(cover.status_code, 200)
        self.assertEqual(cover.content, b"test-cover")
        horizontal_cover = self.client.get(f"/api/publish/extension/tasks/{task['id']}/covers/1", headers=headers)
        self.assertEqual(horizontal_cover.status_code, 200)
        self.assertEqual(horizontal_cover.content, b"horizontal-cover")
        filling = self.client.put(f"/api/publish/extension/tasks/{task['id']}", headers=headers,
                                  json={"status": "filling"})
        self.assertEqual(filling.status_code, 200)
        ready = self.client.put(f"/api/publish/extension/tasks/{task['id']}", headers=headers,
                                json={"status": "ready"})
        self.assertEqual(ready.json()["status"], "ready")
        completed = self.client.put(f"/api/publish/extension/tasks/{task['id']}", headers=headers,
                                    json={"status": "completed"})
        self.assertEqual(completed.json()["status"], "completed")
        for platform in ("kuaishou", "bilibili", "xiaohongshu", "baijiahao"):
            created_platform_task = self.client.post("/api/publish/tasks", json={
                "workflow_id": workflow_id, "platform": platform,
                **({} if platform == "kuaishou" else {"title": "一本值得读的书"}),
                "description": "这是作品简介", "tags": [f"标签{i}" for i in range(1, 11)],
                "topics": ["读书", "好书推荐", "名著解读", "读书分享", "经典文学", "文学阅读"], "video_url": video_url,
                "cover_urls": [cover_url if platform == "kuaishou" else square_cover_url],
            })
            self.assertEqual(created_platform_task.status_code, 201)
            platform_task = created_platform_task.json()
            self.assertEqual(platform_task["platform"], platform)
            if platform == "kuaishou":
                self.assertEqual(platform_task["title"], "")
                self.assertEqual(platform_task["topics"], ["读书", "好书推荐", "名著解读", "读书分享"])
            if platform == "bilibili":
                self.assertEqual(platform_task["tags"], [f"标签{i}" for i in range(1, 11)])
            self.assertEqual(self.client.get("/api/publish/tasks", params={"platform": platform}).json()[0]["id"], platform_task["id"])
            self.assertEqual(self.client.get("/api/publish/extension/tasks/next", params={"platform": platform}, headers=headers).json()["task"]["id"], platform_task["id"])
        extension_zip = self.client.get("/api/publish/extension/download")
        self.assertEqual(extension_zip.status_code, 200)
        self.assertEqual(extension_zip.headers["content-type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(extension_zip.content)) as bundle:
            self.assertIn("browser-extension/manifest.json", bundle.namelist())
            self.assertIn("browser-extension/multi-platform.js", bundle.namelist())

    def test_publish_task_rejects_foreign_or_missing_video(self):
        with patch.object(main, "process_workflow"):
            workflow_id = self.client.post("/api/workflows", json={"book_title": "无视频"}).json()["id"]
        missing = self.client.post("/api/publish/tasks", json={"workflow_id": workflow_id, "title": "测试"})
        foreign = self.client.post("/api/publish/tasks", json={
            "workflow_id": workflow_id, "title": "测试", "video_url": "/media/other/video.mp4"
        })
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(foreign.status_code, 422)

    def test_publish_task_list_tolerates_legacy_blank_json_fields(self):
        with patch.object(main, "process_workflow"):
            workflow_id = self.client.post("/api/workflows", json={"book_title": "旧发布任务"}).json()["id"]
        now = 1_700_000_000
        with main.db() as conn:
            conn.execute(
                "INSERT INTO publish_tasks(id,workflow_id,platform,status,title,description,tags,topics,video_url,cover_url,covers,created_at,updated_at,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("legacy-task", workflow_id, "douyin", "prepared", "旧任务", "", "[]", "   ", "/media/legacy.mp4", "", "[]", now, now, ""),
            )
        response = self.client.get("/api/publish/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["topics"], [])


if __name__ == "__main__":
    unittest.main()
