import asyncio
import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from PIL import Image

from backend.integrations.cover import generate_cover


class CoverPromptTests(unittest.TestCase):
    def prompt_for(self, ratio, author="钱钟书"):
        raw = io.BytesIO()
        Image.new("RGB", (8, 8)).save(raw, "PNG")
        response = Mock()
        response.json.return_value = {"data": [{"b64_json": base64.b64encode(raw.getvalue()).decode()}]}
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        log = Mock()
        with tempfile.TemporaryDirectory() as directory:
            asyncio.run(generate_cover(
                Path(directory) / "cover.png", "围城", author, "知识分子的婚恋与职业困境",
                "按比例设计，非方形无文字", 0, ratio,
                {"image_api_base": "https://example.test/v1", "image_api_key": "test", "image_model": "test"},
                log, Mock(return_value=client),
            ))
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(log.call_args.args[2], payload)
        self.assertIn("知识分子的婚恋与职业困境", payload["prompt"])
        self.assertIn("不要把简介排印在画面上", payload["prompt"])
        self.assertTrue(payload["prompt"].endswith(f"图片比例：{ratio}"))
        self.assertNotIn("size", payload)
        return payload["prompt"].split("【本张图片的最终要求", 1)[1]

    def test_square_explicitly_requires_exact_title_and_author(self):
        prompt = self.prompt_for("1:1")
        self.assertIn("必须清晰排印书名：围城", prompt)
        self.assertIn("必须清晰排印作者：钱钟书", prompt)
        self.assertNotIn("禁止出现任何文字", prompt)

    def test_square_without_author_only_requires_title(self):
        prompt = self.prompt_for("1:1", "")
        self.assertIn("必须清晰排印书名：围城", prompt)
        self.assertIn("未提供作者，只排印书名", prompt)
        self.assertNotIn("必须清晰排印作者", prompt)

    def test_non_square_backgrounds_do_not_require_title(self):
        for ratio in ("16:9", "9:16", "4:5"):
            with self.subTest(ratio=ratio):
                prompt = self.prompt_for(ratio)
                self.assertIn("禁止出现任何文字", prompt)
                self.assertNotIn("必须清晰排印书名", prompt)
