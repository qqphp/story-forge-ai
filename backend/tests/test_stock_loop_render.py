import asyncio
import io
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

import httpx
from PIL import Image, ImageChops, ImageStat
from backend.integrations.stock_video import download_stock_videos
from backend.integrations.video import probe_video_metadata, write_concat_manifest
from backend.integrations.player import player_command, layout


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class StockLoopRenderTests(unittest.TestCase):
    def test_real_preparation_and_loop_render_in_both_orientations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payloads = {}
            for index, color in enumerate(('red','blue'),1):
                path=root/f'source-{index}.mp4'
                subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color={color}:s=1920x1080:r=30','-t','0.4','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True,timeout=30)
                payloads[index]=path.read_bytes()
            def handle(request):
                if request.url.host=='api.example':
                    return httpx.Response(200,json={'hits':[dict(id=i,duration=10-i,videos={'large':dict(url=f'https://cdn.example/{i}',width=1920,height=1080)}) for i in (1,2)]})
                return httpx.Response(200,content=payloads[int(request.url.path[1:])])
            def factory(**kwargs):
                return httpx.AsyncClient(transport=httpx.MockTransport(handle),**kwargs)
            logs=[]
            clips=asyncio.run(download_stock_videos(provider='pixabay',api_base='https://api.example/search',api_key='secret',query='mountain lake',orientation='landscape',output_dir=root,target_duration=2.4,log_request=lambda *args:logs.append(args),client_factory=factory))
            self.assertEqual(len(clips),2)
            self.assertTrue(logs[-1][2]['loop_required'])
            manifest=write_concat_manifest(root/'clips.ffconcat',clips)
            cover=root/'cover.png'; Image.new('RGB',(1080,1080),(220,180,140)).save(cover)
            audio=root/'audio.wav'
            with wave.open(str(audio),'wb') as wav:
                wav.setparams((1,2,24000,0,'NONE','not compressed'))
                wav.writeframes(bytes(int(24000*2*2.4)))
            for orientation in ('landscape','portrait'):
                with self.subTest(orientation=orientation):
                    output=root/f'{orientation}.mp4'
                    command=player_command('ffmpeg',cover,audio,output,orientation=orientation,stock_manifest=manifest,duration=2.4,background_blur_enabled=True,background_blur_strength=50,background_overlay_enabled=True,background_overlay_opacity=.25)
                    subprocess.run(command,check=True,capture_output=True,timeout=60)
                    resolution,seconds=probe_video_metadata(output)
                    self.assertEqual(resolution,'1920 × 1080' if orientation=='landscape' else '1080 × 1920')
                    self.assertAlmostEqual(seconds,2.4,delta=.1)
                    images=[]
                    for stamp in ('0.05','0.45','0.85'):
                        result=subprocess.run(['ffmpeg','-v','error','-ss',stamp,'-i',str(output),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],check=True,capture_output=True,timeout=15)
                        images.append(Image.open(io.BytesIO(result.stdout)).convert('RGB'))
                    a,b,c=[image.getpixel((30,30)) for image in images]
                    self.assertGreater(sum(abs(x-y) for x,y in zip(a,b)),50)
                    self.assertLess(sum(abs(x-y) for x,y in zip(a,c)),10)
                    x,y,_=layout(*images[0].size)['cover']
                    fg=(x+50,y+50,x+100,y+100)
                    diff=ImageChops.difference(images[0].crop(fg),images[1].crop(fg))
                    self.assertLess(sum(ImageStat.Stat(diff).mean),10)
