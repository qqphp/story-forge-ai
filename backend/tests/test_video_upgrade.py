import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from PIL import Image
from backend.integrations import record_labels
from backend.integrations.local_covers import generate_local_covers
from backend.modules.workflows.executor import compose_videos


class VideoUpgradeTests(unittest.TestCase):
    def test_labels_validate_images_preserve_alpha_and_fall_back(self):
        raw=io.BytesIO(); Image.new('RGBA',(100,80),(1,2,3,120)).save(raw,'PNG')
        with tempfile.TemporaryDirectory() as directory, patch.object(record_labels,'UPLOADS',Path(directory)):
            key=record_labels.store_label(raw.getvalue())
            with Image.open(record_labels.label_path(key)) as image:
                self.assertEqual(image.mode,'RGBA');self.assertEqual(image.getpixel((0,0))[3],120)
            self.assertEqual(record_labels.store_label(raw.getvalue()),key)
            self.assertEqual(record_labels.label_path('0'*32).name,'record-label-default.png')
            with self.assertRaises(ValueError):record_labels.store_label(b'not an image')
            with self.assertRaises(ValueError):record_labels.store_label(b'x'*(10*1024*1024+1))

    def test_local_cover_set_has_three_consistent_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);covers=generate_local_covers(root,'测试书名','')
            self.assertEqual([c['image_ratio'] for c in covers],['1:1','16:9','9:16'])
            self.assertEqual(len({c['template_id'].split('-')[0] for c in covers}),1)
            for cover,expected in zip(covers,[(1080,1080),(1920,1080),(1080,1920)]):
                with Image.open(root/Path(cover['url']).name) as image:self.assertEqual(image.size,expected)

    def test_each_draft_uses_its_square_and_directional_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);covers=[];calls=[]
            for group in ('a','b'):
                for ratio in ('1:1','16:9','9:16'):
                    name=f'{group}-{ratio.replace(":","-")}.png'
                    covers.append(dict(prompt_id=group,image_ratio=ratio,url='/media/x/'+name))
            def command(ffmpeg,cover,audio,out,**kwargs):
                self.assertTrue(kwargs['background_blur_enabled'])
                self.assertEqual(kwargs['background_blur_strength'],73)
                calls.append((cover.name,kwargs['orientation'],kwargs['background_cover'].name));return [ffmpeg,str(out)]
            def run(command,**kwargs):
                Path(command[-1]).write_bytes(b'video');return type('Result',(),dict(returncode=0,stderr=b''))()
            with patch('backend.integrations.player.player_command',side_effect=command),patch('backend.modules.workflows.executor.subprocess.run',side_effect=run),patch('backend.modules.workflows.executor.probe_audio_duration',return_value=1),patch('backend.modules.workflows.executor.probe_video_metadata',return_value=(None,1)):
                videos=asyncio.run(compose_videos('x',dict(book_title='测试',output_dir='x'),dict(burn_subtitles=False,background_blur_enabled=True,background_blur_strength=73),root,covers,[dict(draft_id=g,voice='voice',url=f'/media/x/{g}.mp3') for g in ('a','b')],description='',is_deleting=lambda _:False,llm=AsyncMock(),video_command=command,download_stock_videos=AsyncMock(),log_request=lambda *a:None))
            self.assertEqual(calls,[('a-1-1.png','landscape','a-16-9.png'),('a-1-1.png','portrait','a-9-16.png'),('b-1-1.png','landscape','b-16-9.png'),('b-1-1.png','portrait','b-9-16.png')])
            self.assertEqual(len({v['url'] for v in videos}),4)

    def test_stock_uses_longest_narration_and_reuses_each_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            covers = [dict(image_ratio=ratio, url='/media/x/cover.png') for ratio in ('1:1','16:9','9:16')]
            clips = [root / 'prepared.mp4']
            clips[0].write_bytes(b'prepared')
            calls = []
            def command(ffmpeg, cover, audio, out, **kwargs):
                calls.append((kwargs['orientation'], kwargs['duration'], kwargs['stock_manifest']))
                return [ffmpeg, str(out)]
            def run(command, **kwargs):
                Path(command[-1]).write_bytes(b'video')
                return type('Result', (), dict(returncode=0, stderr=b''))()
            download = AsyncMock(return_value=clips)
            with patch('backend.integrations.player.player_command',side_effect=command), patch('backend.modules.workflows.executor.subprocess.run',side_effect=run), patch('backend.modules.workflows.executor.probe_audio_duration',side_effect=[120,480]) as probe, patch('backend.modules.workflows.executor.probe_video_metadata',return_value=(None,1)):
                videos=asyncio.run(compose_videos('x',dict(book_title='测试',output_dir='x'),dict(video_generation_method='stock',stock_video_provider='pexels',pexels_api_base='https://api.example',pexels_api_key='secret',burn_subtitles=False),root,covers,[dict(draft_id=g,voice='voice',url=f'/media/x/{g}.mp3') for g in ('a','b')],description='',is_deleting=lambda _:False,llm=AsyncMock(return_value='mountain lake'),video_command=command,download_stock_videos=download,log_request=lambda *a:None))
            self.assertEqual(probe.call_count,2)
            self.assertEqual(download.call_args.kwargs['target_duration'],480)
            self.assertEqual([(o,d) for o,d,_ in calls],[('landscape',120),('portrait',120),('landscape',480),('portrait',480)])
            self.assertEqual(len({p for _,_,p in calls}),1)
            self.assertEqual(len(videos),4)

    def test_invalid_narration_fails_before_search(self):
        for seconds in (None,0,-1,float('nan'),float('inf')):
            with tempfile.TemporaryDirectory() as directory, patch('backend.modules.workflows.executor.probe_audio_duration',return_value=seconds):
                llm, download = AsyncMock(), AsyncMock()
                with self.assertRaisesRegex(RuntimeError,'有效配音时长'):
                    asyncio.run(compose_videos('x',{},dict(video_generation_method='stock'),Path(directory),[{}],[dict(url='/media/x/audio.wav')],description='',is_deleting=lambda _:False,llm=llm,video_command=lambda *a:[],download_stock_videos=download,log_request=lambda *a:None))
                llm.assert_not_called()
                download.assert_not_called()
