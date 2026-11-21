import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock
import wave
import xml.etree.ElementTree as ET

import httpx

from backend.integrations.speech import build_ssml, speech_api_url, split_narration, synthesize
from backend.integrations.video import probe_audio_duration


SSML = "{http://www.w3.org/2001/10/synthesis}"


def chinese_ssml(text, voice, rate, *music):
    return build_ssml(text, voice, rate, lambda _: "zh-CN", *music)


def pcm(seconds):
    data = io.BytesIO()
    with wave.open(data, "wb") as track:
        track.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        track.writeframes(b"\x00\x00" * round(seconds * 24000))
    return data.getvalue()


class SpeechApiAddressTests(unittest.TestCase):
    def test_synthesis_and_voice_list_append_paths_to_configured_base(self):
        base = "https://speech.example/custom/"
        self.assertEqual(speech_api_url(base, "/cognitiveservices/v1"), "https://speech.example/custom/cognitiveservices/v1")
        self.assertEqual(speech_api_url(base, "/cognitiveservices/voices/list"), "https://speech.example/custom/cognitiveservices/voices/list")

    def test_preserves_paragraphs_and_punctuation_in_ssml(self):
        root = ET.fromstring(chinese_ssml("慢一点，好吗？\n\n甲 < 乙 & 丙。", "zh-CN-XiaoxiaoNeural", -5))
        prosody = root.find(f".//{SSML}prosody")
        self.assertEqual(prosody.attrib["rate"], "-5%")
        self.assertEqual([p.text for p in prosody], ["慢一点，好吗？", "甲 < 乙 & 丙。"])

    def test_splits_at_paragraph_and_sentence_boundaries_without_losing_text(self):
        text = "读" * 899 + "。\r\n\r\n" + "想" * 799 + "？”再想一想。" + "看" * 500
        chunks = split_narration(text, 1200)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(chunks[0].endswith("\r\n\r\n"))
        self.assertTrue(chunks[1].endswith("。"))
        self.assertTrue(all(len(chunk) <= 1200 for chunk in chunks))


class LongNarrationTests(unittest.IsolatedAsyncioTestCase):
    async def run_speech(self, text, output, on_request, fmt, music=None, rate=-5):
        return await synthesize(text, "zh-CN-XiaoxiaoNeural", rate, {"azure_speech_key": "test", "voice_format": fmt},
                                output, chinese_ssml, Mock(), Mock(),
                                lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(on_request), **kwargs),
                                music, .1, .1, .1)

    async def test_near_limit_segment_is_split_and_full_twelve_minutes_are_delivered(self):
        paragraph = "读" * 900 + "。"
        text = paragraph + "\n\n" + paragraph.replace("读", "想")
        truncated, usable = pcm(600), pcm(240)
        calls = []

        def respond(request):
            self.assertEqual(request.headers["X-Microsoft-OutputFormat"], "riff-24khz-16bit-mono-pcm")
            paragraphs = ET.fromstring(request.content).iter(f"{SSML}p")
            calls.append("".join(p.text for p in paragraphs))
            return httpx.Response(200, content=truncated if len(calls) == 1 else usable)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "episode.wav"
            self.assertEqual(await self.run_speech(text, output, respond, "riff-24khz-16bit-mono-pcm"), output)
            self.assertEqual(calls[0], paragraph)
            self.assertEqual("".join(calls[1:]), text.replace("\n", ""))
            with wave.open(str(output), "rb") as track:
                self.assertEqual(track.getnframes() / track.getframerate(), 720)
            self.assertEqual(list(output.parent.iterdir()), [output])

    async def test_failed_segment_keeps_previous_audio_and_removes_staging_files(self):
        calls = []

        def respond(request):
            calls.append(request)
            return httpx.Response(200, content=pcm(1)) if len(calls) == 1 else httpx.Response(503)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "episode.wav"
            output.write_bytes(b"previous")
            with self.assertRaises(httpx.HTTPStatusError):
                await self.run_speech("读" * 1500, output, respond, "riff-24khz-16bit-mono-pcm")
            self.assertEqual(output.read_bytes(), b"previous")
            self.assertEqual(list(output.parent.iterdir()), [output])

    @unittest.skipUnless(shutil.which(os.getenv("FFMPEG_PATH", "ffmpeg")) and shutil.which(os.getenv("FFPROBE_PATH", "ffprobe")), "FFmpeg and ffprobe are required")
    async def test_segmented_audio_uses_one_continuous_music_mix(self):
        requests = []

        def respond(request):
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, content=pcm(.2))
            self.assertNotIn(b"backgroundaudio", request.content)
            return httpx.Response(200, content=pcm(2))

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "episode.mp3"
            result = await self.run_speech("读" * 1500, output, respond, "audio-24khz-48kbitrate-mono-mp3",
                                           {"url": "https://music.example/demo.wav"})
            self.assertEqual(result, output)
            self.assertEqual([request.method for request in requests], ["POST", "POST", "GET"])
            self.assertAlmostEqual(probe_audio_duration(result), 4, delta=.1)
