import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from backend.integrations.stock_video import download_stock_videos


def clip(provider, ident, duration=30, url=None):
    url = url or f'https://cdn.example/{ident}.mp4'
    if provider == 'pexels':
        return dict(id=ident, duration=duration, width=1920, height=1080, video_files=[dict(quality='hd', width=1920, height=1080, link=url)])
    return dict(id=ident, duration=duration, videos=dict(large=dict(width=1920, height=1080, url=url)))


class DurationStockTests(unittest.TestCase):
    def prepare(self, provider, pages, target=480, real=None, bad=(), auth=False, normalize_bad=(), empty=(), invalid=()):
        self.downloads, self.searches, self.logs, self.limits = [], [], [], []
        self.calls = 0
        durations = {}
        def handle(request):
            if request.url.host == 'api.example':
                self.searches.append(dict(request.url.params))
                if auth:
                    return httpx.Response(401)
                items = pages[min(len(self.searches)-1, len(pages)-1)]
                return httpx.Response(200, json={'videos' if provider=='pexels' else 'hits': items})
            ident = int(request.url.path.split('/')[-1].split('.')[0])
            self.downloads.append(ident)
            return httpx.Response(500 if ident in bad else 200, content=b'' if ident in empty else str(ident).encode())
        def probe(path):
            if path.stem.endswith('-normalized'):
                return ('1920 × 1080', durations[path])
            ident = int(path.read_bytes())
            return (None, None) if ident in invalid else ('1920 × 1080', real.get(ident, 30) if real else 30)
        def normalize(ffmpeg, paths, output_dir, orientation, limit):
            ident = int(paths[0].read_bytes())
            self.limits.append(limit)
            if ident in normalize_bad:
                raise RuntimeError('bad decode')
            out = output_dir / (paths[0].stem+'-normalized.mp4')
            out.write_bytes(b'normalized')
            durations[out] = min(real.get(ident,30) if real else 30, limit)
            return [out]
        def factory(**kwargs):
            return httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            self.root = Path(directory)
            with patch('backend.integrations.stock_video.probe_video_metadata', side_effect=probe), patch('backend.integrations.stock_video.normalize_stock_videos', side_effect=normalize):
                try:
                    paths = asyncio.run(download_stock_videos(provider=provider, api_base='https://api.example/search', api_key='test-secret', query='mountain lake', orientation='landscape', output_dir=self.root, target_duration=target, log_request=lambda *args: self.logs.append(args), client_factory=factory))
                    self.assertTrue(all(p.exists() for p in paths))
                    self.assertEqual(len(list(self.root.glob('*.mp4'))),len(paths))
                    return paths
                except Exception:
                    self.assertEqual(list(self.root.iterdir()), [])
                    raise

    def test_both_providers_stop_by_real_duration_and_trim_last_clip(self):
        for provider in ('pexels','pixabay'):
            with self.subTest(provider=provider):
                paths=self.prepare(provider, [[clip(provider,1,999),clip(provider,2,998),clip(provider,3,997)]], target=65, real={1:40,2:40,3:40})
                self.assertEqual(len(paths),2)
                self.assertEqual(self.downloads,[1,2])
                self.assertEqual(self.limits,[65,25])
                self.assertFalse(self.logs[-1][2]['loop_required'])
                self.assertNotIn('test-secret',str(self.logs))

    def test_one_long_clip_is_enough(self):
        for provider in ('pexels','pixabay'):
            self.assertEqual(len(self.prepare(provider,[[clip(provider,1)]], target=10)),1)

    def test_ten_clip_cap_and_shortage(self):
        for provider in ('pexels','pixabay'):
            self.assertEqual(len(self.prepare(provider,[[clip(provider,i) for i in range(15)]],target=480)),10)
            self.assertEqual(len(self.downloads),10)
            self.assertTrue(self.logs[-1][2]['loop_required'])
            self.assertEqual(len(self.searches),1)

    def test_less_than_three_is_allowed(self):
        self.assertEqual(len(self.prepare('pixabay',[[clip('pixabay',1),clip('pixabay',2)]])),2)
        self.assertEqual(len(self.searches),1)

    def test_unknown_durations_and_deduplication(self):
        items=[clip('pexels',1,None),clip('pexels',2,0),clip('pexels',3,100),clip('pexels',3,100),clip('pexels',4,99,url='https://cdn.example/3.mp4')]
        self.assertEqual(len(self.prepare('pexels',[items])),3)
        self.assertEqual(self.downloads[0],3)
        self.assertEqual(set(self.downloads),{1,2,3})

    def test_failed_empty_invalid_and_bad_decode_are_skipped(self):
        items=[clip('pixabay',i,100-i) for i in range(1,6)]
        self.assertEqual(len(self.prepare('pixabay',[items],target=20,bad=(1,),empty=(2,),invalid=(3,),normalize_bad=(4,))),1)
        self.assertEqual(self.downloads,[1,2,3,4,5])
        self.assertEqual(self.logs[-1][2]['failed_count'],4)

    def test_empty_search_falls_back_once(self):
        self.assertEqual(len(self.prepare('pexels',[[],[clip('pexels',1)]])),1)
        self.assertEqual(len(self.searches),2)
        self.assertEqual(self.searches[1]['query'],'serene cinematic natural landscape')

    def test_all_invalid_fail_and_attempt_budget_is_shared(self):
        first=[clip('pixabay',i,100-i) for i in range(15)]
        second=[clip('pixabay',i,100-i) for i in range(10,35)]
        with self.assertRaisesRegex(RuntimeError,'没有可用背景视频'):
            self.prepare('pixabay',[first,second],bad=tuple(range(35)))
        self.assertEqual(len(self.searches),2)
        self.assertEqual(len(self.downloads),20)
        self.assertEqual(len(set(self.downloads)),20)

    def test_zero_results_fail_after_one_fallback(self):
        with self.assertRaisesRegex(RuntimeError,'没有可用背景视频'):
            self.prepare('pexels',[[],[]])
        self.assertEqual(len(self.searches),2)

    def test_authentication_failure_stops_without_key_in_error(self):
        with self.assertRaisesRegex(RuntimeError,'HTTP 401') as caught:
            self.prepare('pixabay',[[]],auth=True)
        self.assertNotIn('test-secret',str(caught.exception))
        self.assertEqual(len(self.searches),1)

    def test_invalid_real_durations_are_not_counted(self):
        for seconds in (0,-1,float('nan'),float('inf')):
            with self.subTest(seconds=seconds):
                paths=self.prepare('pexels',[[clip('pexels',1,100),clip('pexels',2,90)]],target=20,real={1:seconds,2:30})
                self.assertEqual(len(paths),1)
                self.assertEqual(self.downloads,[1,2])
                self.assertEqual(self.logs[-1][2]['failed_count'],1)
