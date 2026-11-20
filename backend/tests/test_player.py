import json
import tempfile
import unittest
from pathlib import Path
from backend.integrations.subtitles import clean_caption, write_subtitle_files, prepare_cues
from backend.modules.contracts import SubtitleStyle
from backend.integrations.subtitle_burn import render_burn_ass


class PlayerSubtitleTests(unittest.TestCase):
    def test_punctuation_and_protected_tokens(self):
        self.assertEqual(clean_caption("《你好》，世界！ 3.14 don't well-known. Hello,world!"), "你好世界 3.14 don't well-known Hello world")

    def test_word_timestamps_and_all_export_formats(self):
        cues = [{"start": 1, "end": 4, "text": "你好，世界！", "words": [{"word": "你好，", "start": 1, "end": 2}, {"word": "世界！", "start": 3, "end": 4}]}]
        with tempfile.TemporaryDirectory() as directory:
            paths = write_subtitle_files(Path(directory)/'audio.wav', cues)
            payload = json.loads(paths['json'].read_text(encoding='utf-8'))
            self.assertEqual(payload['text'], '你好世界')
            self.assertEqual([(s['start'], s['end']) for s in payload['segments']], [(1, 2), (3, 4)])
            self.assertEqual(payload['segments'][0]['words'][0]['word'], '你好')
            self.assertNotIn('，', paths['srt'].read_text(encoding='utf-8'))
            self.assertEqual(paths['txt'].read_text(encoding='utf-8'), '你好\n世界\n')

    def test_blank_tokens_removed_and_legacy_span_preserved(self):
        cues = prepare_cues([{'start': 0, 'end': 1, 'text': '！？'}, {'start': 2, 'end': 10, 'text': '这是需要分成若干短句的历史字幕内容用于验证原有时间范围保持完整'}])
        self.assertEqual(cues[0]['start'], 2)
        self.assertEqual(cues[-1]['end'], 10)
        self.assertTrue(all(len(cue['text']) <= 16 for cue in cues))

    def test_caption_anchors_are_inside_separate_regions(self):
        for width, height, position in [(1920,1080,'1350,510'), (1080,1920,'540,1300')]:
            ass = render_burn_ass('1\n00:00:01,000 --> 00:00:02,000\n你好，世界！\n',width,height,'Source Han Serif SC',SubtitleStyle().model_dump())
            self.assertIn('{' + '\\pos(' + position + ')}你好世界', ass)
            self.assertNotIn('{{', ass)
