import unittest

from backend.integrations.speech import speech_api_url


class SpeechApiAddressTests(unittest.TestCase):
    def test_synthesis_and_voice_list_append_paths_to_configured_base(self):
        base = "https://speech.example/custom/"
        self.assertEqual(speech_api_url(base, "/cognitiveservices/v1"), "https://speech.example/custom/cognitiveservices/v1")
        self.assertEqual(speech_api_url(base, "/cognitiveservices/voices/list"), "https://speech.example/custom/cognitiveservices/voices/list")
