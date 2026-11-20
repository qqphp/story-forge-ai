"""Video settings compatibility and real FFmpeg composition checks."""
import io
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat
from pydantic import ValidationError
from backend.core.database import connection, initialize_schema
from backend.modules.contracts import SettingsPayload, SubtitlePreview
from backend.modules.settings.service import load_settings, save_settings
from backend.integrations.player import player_command, layout


class OverlaySettingsTests(unittest.TestCase):
    def test_blur_defaults_and_validation(self):
        for model in (SettingsPayload, SubtitlePreview):
            self.assertFalse(model().background_blur_enabled)
            self.assertEqual(model().background_blur_strength, 20)
            for strength in (0, 20, 100):
                self.assertEqual(model(background_blur_strength=strength).background_blur_strength, strength)
            for strength in (-1, 101, float('nan'), float('inf')):
                with self.assertRaises(ValidationError):
                    model(background_blur_strength=strength)

    def test_defaults_and_validation(self):
        for model in (SettingsPayload, SubtitlePreview):
            self.assertTrue(model().background_overlay_enabled)
            self.assertEqual(model().background_overlay_opacity, .25)
            for opacity in (0, .25, 1):
                self.assertEqual(model(background_overlay_opacity=opacity).background_overlay_opacity, opacity)
            for opacity in (-.01, 1.01, float('nan')):
                with self.assertRaises(ValidationError):
                    model(background_overlay_opacity=opacity)

    def test_legacy_and_omitted_fields_preserve_saved_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            db = lambda: connection(Path(directory) / 'test.db')
            initialize_schema(db)
            settings = load_settings(db, SettingsPayload().model_dump())
            self.assertEqual(settings['background_overlay_opacity'], .25)
            self.assertFalse(settings['background_blur_enabled'])
            self.assertEqual(settings['background_blur_strength'], 20)
            saved = save_settings(db, settings, SettingsPayload(background_overlay_enabled=False, background_overlay_opacity=.63, background_blur_enabled=True, background_blur_strength=73))
            saved = save_settings(db, saved, SettingsPayload())
            loaded = load_settings(db, SettingsPayload().model_dump())
            self.assertFalse(loaded['background_overlay_enabled'])
            self.assertEqual(loaded['background_overlay_opacity'], .63)
            self.assertTrue(loaded['background_blur_enabled'])
            self.assertEqual(loaded['background_blur_strength'], 73)


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class PlayerRenderTests(unittest.TestCase):
    def test_blur_strength_affects_only_image_and_video_backgrounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = root / 'cover.png'
            Image.new('RGB', (1080, 1080), (220, 180, 140)).save(cover)
            background = root / 'background.png'
            image = Image.new('RGB', (1920, 1920), 'white')
            draw = ImageDraw.Draw(image)
            for x in range(0, 1920, 32):
                draw.rectangle((x, 0, x + 15, 1919), fill='black')
            image.save(background)
            audio = root / 'audio.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(bytes(24000 * 2))
            stock = root / 'stock.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', str(background), '-t', '1', '-c:v', 'ffv1', str(stock)], check=True, capture_output=True)
            manifest = root / 'stock.ffconcat'
            manifest.write_text("file '" + stock.as_posix() + "'\n", encoding='utf-8')
            for orientation in ('portrait', 'landscape'):
                for source in (None, manifest):
                    with self.subTest(orientation=orientation, stock=bool(source)):
                        frames = []
                        for enabled, strength in ((False, 100), (True, 0), (True, 20), (True, 100)):
                            output = root / 'render.mp4'
                            command = player_command('ffmpeg', cover, audio, output, orientation=orientation, stock_manifest=source, background_cover=background, duration=1, background_overlay_enabled=False, background_blur_enabled=enabled, background_blur_strength=strength)
                            png = root / 'frame.png'
                            subprocess.run(command[:-1] + ['-frames:v', '1', '-an', '-c:v', 'png', '-f', 'image2', str(png)], check=True, capture_output=True, timeout=30)
                            with Image.open(png) as frame:
                                frames.append(frame.convert('RGB'))
                        self.assertIsNone(ImageChops.difference(frames[0], frames[1]).getbbox())
                        contrasts = [sum(ImageStat.Stat(frame.crop((32, 32, 256, 256))).stddev) for frame in frames]
                        self.assertGreater(contrasts[0], contrasts[2] + 10)
                        self.assertGreater(contrasts[2], contrasts[3] + 10)
                        x, y, _ = layout(*frames[0].size)['cover']
                        foreground = (x + 50, y + 50, x + 100, y + 100)
                        self.assertIsNone(ImageChops.difference(frames[0].crop(foreground), frames[3].crop(foreground)).getbbox())

    def test_real_background_mask_rotation_and_fixed_foreground(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cover = root / 'cover.png'
            Image.new('RGB', (1080,1080), (220,180,140)).save(cover)
            audio = root / 'audio.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(bytes(24000 * 2 * 2))
            stock = root / 'stock.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=white:s=1920x1080:r=30','-t','2','-c:v','libx264','-pix_fmt','yuv420p',str(stock)], check=True, capture_output=True)
            manifest = root / 'stock.ffconcat'
            manifest.write_text("file '" + stock.as_posix() + "'\n", encoding='utf-8')
            for orientation in ('portrait', 'landscape'):
                for source in (None, manifest):
                    frames = []
                    for enabled, opacity in ((False,.63),(True,0),(True,.25),(True,1)):
                        output = root / 'render.mp4'
                        command = player_command('ffmpeg',cover,audio,output,orientation=orientation,stock_manifest=source,duration=2,background_overlay_enabled=enabled,background_overlay_opacity=opacity)
                        png = root / 'frame.png'
                        subprocess.run(command[:-1]+['-frames:v','1','-an','-c:v','png','-f','image2',str(png)], check=True, capture_output=True, timeout=30)
                        frames.append(Image.open(png).convert('RGB'))
                    self.assertEqual(frames[0].getpixel((30,30)),frames[1].getpixel((30,30)))
                    bright = frames[1].getpixel((30,30))[0]
                    self.assertAlmostEqual(frames[2].getpixel((30,30))[0], bright*.75, delta=4)
                    self.assertLess(frames[3].getpixel((30,30))[0],4)
                    w,h=frames[0].size
                    x,y,size=layout(w,h)['cover']
                    self.assertEqual(frames[0].getpixel((x+50,y+50)),frames[3].getpixel((x+50,y+50)))
                command = player_command('ffmpeg',cover,audio,root/'motion.mp4',orientation=orientation,duration=2)
                subprocess.run(command,check=True,capture_output=True,timeout=45)
                images=[]
                for time in ('0','1'):
                    result=subprocess.run(['ffmpeg','-v','error','-ss',time,'-i',str(root/'motion.mp4'),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'],check=True,capture_output=True)
                    images.append(Image.open(io.BytesIO(result.stdout)).convert('RGB'))
                dx,dy,ds=layout(*images[0].size)['disc']
                region=(dx+int(ds*.78),dy+int(ds*.30),dx+int(ds*.92),dy+int(ds*.60))
                self.assertGreater(sum(ImageStat.Stat(ImageChops.difference(images[0].crop(region),images[1].crop(region))).mean),5)
                center=(dx+ds//2,dy+ds//2)
                self.assertLess(sum(abs(a-b) for a,b in zip(images[0].getpixel(center),images[1].getpixel(center))),12)
                with Image.open((root/'motion.mp4').with_suffix('.layer.png')) as layer:
                    self.assertIsNone(layer.crop((850,50,1850,260) if orientation=='landscape' else (80,100,1000,350)).getbbox())
