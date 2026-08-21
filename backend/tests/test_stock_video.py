import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.integrations.stock_video import _pexels_items, _pixabay_items, download_stock_videos, natural_scenery_query
from backend.integrations.video import video_command, write_concat_manifest


class StockVideoTests(unittest.TestCase):
    def test_provider_parsers_select_medium_orientation(self):
        pexels = {"videos": [{"id": 1, "width": 1920, "height": 1080, "video_files": [
            {"quality": "sd", "width": 640, "link": "small"},
            {"quality": "hd", "width": 1920, "link": "medium"},
        ]}, {"id": 2, "width": 1080, "height": 1920, "video_files": [{"quality": "hd", "width": 1080, "link": "portrait"}]}]}
        pixabay = {"hits": [{"id": 3, "videos": {"medium": {"url": "landscape", "width": 1280, "height": 720}}},
                              {"id": 4, "videos": {"medium": {"url": "portrait", "width": 720, "height": 1280}}}]}
        self.assertEqual(_pexels_items(pexels, "landscape"), [{"id": "1", "url": "medium"}])
        self.assertEqual(_pixabay_items(pixabay, "portrait"), [{"id": "4", "url": "portrait"}])

    def test_search_query_removes_human_terms(self):
        self.assertEqual(natural_scenery_query("woman walking through misty forest landscape"), "through misty forest landscape")
        self.assertEqual(natural_scenery_query("people person portrait"), "serene cinematic natural landscape")

    def test_stock_search_is_logged_without_api_key(self):
        logs = []

        class SearchResponse:
            def raise_for_status(self): pass
            def json(self):
                return {"videos": [{"id": index, "width": 1920, "height": 1080, "video_files": [{"quality": "hd", "width": 1920, "link": f"https://cdn.example/{index}.mp4"}]} for index in range(1, 5)]}

        class DownloadResponse:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def raise_for_status(self): pass
            async def aiter_bytes(self): yield b"video"

        class Client:
            def __init__(self, *args, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs): return SearchResponse()
            def stream(self, *args, **kwargs): return DownloadResponse()

        with tempfile.TemporaryDirectory() as temporary:
            paths = asyncio.run(download_stock_videos(
                provider="pexels", api_base="https://api.pexels.com/v1/videos/search",
                api_key="must-not-be-logged", query="misty mountain landscape",
                orientation="landscape", output_dir=Path(temporary),
                log_request=lambda *values: logs.append(values), client_factory=Client,
            ))
        self.assertEqual(len(paths), 3)
        self.assertEqual(logs[0][0], "无版权视频搜索")
        self.assertEqual(logs[0][1], "https://api.pexels.com/v1/videos/search")
        self.assertEqual(logs[0][2]["query"], "misty mountain landscape")
        self.assertEqual(logs[0][2]["orientation"], "landscape")
        self.assertNotIn("key", logs[0][2])
        self.assertNotIn("must-not-be-logged", str(logs[0]))

    def test_ffmpeg_commands_follow_orientation_and_loop_stock_playlist(self):
        local = video_command("ffmpeg", Path("cover.png"), Path("audio.mp3"), Path("out.mp4"), orientation="landscape")
        self.assertIn("scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,format=yuv420p", local)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clips = [root / f"clip-{index}.mp4" for index in range(3)]
            manifest = write_concat_manifest(root / "clips.ffconcat", clips)
            stock = video_command("ffmpeg", Path("cover.png"), Path("audio.mp3"), Path("out.mp4"), orientation="portrait", stock_manifest=manifest)
            self.assertIn("-stream_loop", stock)
            self.assertEqual(stock[stock.index("-map") + 1], "0:v")
            self.assertIn("scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,format=yuv420p", stock)
            self.assertEqual(len(manifest.read_text(encoding="utf-8").splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
