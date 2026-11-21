"""Shared record-player artwork and FFmpeg composition."""
from pathlib import Path
import math
import os
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from backend.integrations.fonts import FONTS_DIR


def layout(width, height):
    if width > height:
        return dict(cover=(120, 280, 400), disc=(350, 280, 400), caption=(850, 360, 1000, 300), wave=(960, 740, 780, 80), footer=950)
    return dict(cover=(180, 470, 470), disc=(430, 470, 470), caption=(80, 1140, 920, 320), wave=(180, 1510, 720, 100), footer=1750)


def artwork(cover: Path, output: Path, width: int, height: int, background_cover: Path | None = None, record_label_image_id: str | None = None):
    box = layout(width, height)
    with Image.open(cover) as source:
        source = source.convert('RGB')
        with Image.open(background_cover or cover) as bg_source:
            background = ImageOps.fit(bg_source.convert('RGB'), (width, height))
        layer = Image.new('RGBA', (width, height))
        draw = ImageDraw.Draw(layer)
        x, y, size = box['cover']
        panel = Image.new('RGB', (size, size), '#254658')
        fitted = ImageOps.contain(source, (size, size))
        panel.paste(fitted, ((size-fitted.width)//2, (size-fitted.height)//2))
        mask = Image.new('L', (size,size)); ImageDraw.Draw(mask).rounded_rectangle((0,0,size-1,size-1),radius=40,fill=255)
        disc_size = box['disc'][2]
        disc = Image.new('RGBA', (disc_size, disc_size))
        light = Image.new('RGBA', (disc_size, disc_size))
        dp, lp = disc.load(), light.load()
        center = disc_size / 2
        for py in range(disc_size):
            for px in range(disc_size):
                rx, ry = px-center, py-center
                radius = math.hypot(rx, ry) / center
                if radius >= 1:
                    continue
                theta = math.atan2(ry, rx)
                groove = 5 * math.sin(radius * disc_size * 2.8)
                shade = int(15 + 14 * (1-radius) + groove)
                dp[px, py] = (shade, shade+1, shade+4, min(255, int((1-radius)*center*255)))
                reflection = max(0, math.cos(theta + .65)) ** 18 + .4 * max(0, math.cos(theta - 2.2)) ** 32
                lp[px, py] = (175, 191, 210, int(reflection * 65 * radius))
        disc = Image.alpha_composite(disc, light)
        texture = ImageDraw.Draw(disc)
        for inset, start, end in ((12, 18, 76), (21, 24, 65), (34, 155, 197), (42, 161, 188), (58, 280, 307)):
            texture.arc((inset, inset, disc_size-inset-1, disc_size-inset-1), start, end, fill=(66, 72, 82, 255), width=2)
        dx, dy, _ = box['disc']
        shadow = Image.new('RGBA', layer.size)
        ImageDraw.Draw(shadow).ellipse((dx+4,dy+12,dx+disc_size+4,dy+disc_size+12),fill=(0,0,0,100))
        # Keep the shadow behind the rotating disc.
        background = Image.alpha_composite(background.convert('RGBA'), shadow.filter(ImageFilter.GaussianBlur(12))).convert('RGB')
        layer.paste(panel,(x,y),mask)
        from backend.integrations.record_labels import label_path
        label_size = round(disc_size * .46)
        with Image.open(label_path(record_label_image_id)) as original:
            label = ImageOps.fit(original.convert('RGBA'), (label_size,label_size))
        from PIL import ImageChops
        circle=Image.new('L',label.size)
        ImageDraw.Draw(circle).ellipse((0,0,label_size-1,label_size-1),fill=255)
        label.putalpha(ImageChops.multiply(label.getchannel('A'),circle))
        layer.alpha_composite(label,(dx+(disc_size-label_size)//2,dy+(disc_size-label_size)//2))
    fy=box['footer']
    cy=fy+72
    cx=width//2
    draw.rectangle((cx-13,cy-18,cx-4,cy+18),fill='white');draw.rectangle((cx+4,cy-18,cx+13,cy+18),fill='white')
    for sign in (-1,1):
        a=cx+sign*95
        draw.polygon([(a-sign*14,cy-16),(a-sign*14,cy+16),(a+sign*14,cy)],fill='white')
    background.save(output.with_suffix('.background.png'))
    layer.save(output.with_suffix('.layer.png'));disc.save(output.with_suffix('.disc.png'))
    return box


def player_command(ffmpeg, cover, narration, output, *, orientation='portrait', stock_manifest=None, subtitles=None, subtitle_style=None, background_overlay_enabled=True, background_overlay_opacity=.25, background_blur_enabled=False, background_blur_strength=20, duration=None, background_cover=None, record_label_image_id=None, **kwargs):
    from backend.integrations.video import probe_audio_duration
    from backend.integrations.subtitle_burn import burn_subtitle_filter
    duration=duration or probe_audio_duration(narration)
    if not duration or duration<=0:raise RuntimeError('无法读取配音时长')
    w,h=(1920,1080) if orientation=='landscape' else (1080,1920)
    b=artwork(cover,output,w,h,background_cover,record_label_image_id)
    command=[ffmpeg,'-y','-filter_complex_threads',str(min(8, os.cpu_count() or 1))]
    if stock_manifest:command+=['-stream_loop','-1','-f','concat','-safe','0','-i',str(stock_manifest)]
    else:command+=['-loop','1','-framerate','30','-i',str(output.with_suffix('.background.png'))]
    command+=['-i',str(narration),'-loop','1','-framerate','30','-i',str(output.with_suffix('.disc.png')),'-loop','1','-framerate','30','-i',str(output.with_suffix('.layer.png'))]
    filters=[]
    base=f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1'
    if stock_manifest:base+=',eq=saturation=0.5,colorbalance=bs=0.15'
    if not stock_manifest and background_blur_enabled and background_blur_strength > 0:
        base += f',gblur=sigma={background_blur_strength * .3:g}'
    if not stock_manifest and background_overlay_enabled:
        brightness = 1 - background_overlay_opacity
        base += f',lutrgb=r=val*{brightness}:g=val*{brightness}:b=val*{brightness}'
    filters.append(base+'[bg]')
    dx,dy,ds=b['disc'];wx,wy,ww,wh=b['wave']
    filters+=['[2:v]format=rgba,rotate=2*PI*t/12:c=none[disc]',f'[bg][disc]overlay={dx}:{dy}:shortest=1[record]','[record][3:v]overlay=0:0:shortest=1[art]',f'[1:a]asplit=2[aout][spectrum]',f'[spectrum]showfreqs=s={ww}x{wh}:r=30:mode=bar:ascale=sqrt:fscale=log:colors=white,format=rgba,colorkey=black:0.04:0.1[wave]',f'[art][wave]overlay={wx}:{wy}:shortest=1[visual]']
    fy=b['footer'];left=155;right=w-155;bar=fy+18
    # Overlay a moving dot; drawbox itself does not evaluate time per frame.
    filters += [f'[visual]drawbox=x={left}:y={bar}:w={right-left}:h=3:color=white@0.5:t=fill[track]', "color=c=0x52c9bc:s=12x12:r=30,format=rgba,geq=r=82:g=201:b=188:a=\'if(lte(hypot(X-5.5,Y-5.5),5.5),255,0)\'[dot]", f"[track][dot]overlay=x='{left}+(min(t/{duration},1))*{right-left}-6':y={bar-5}:shortest=1[timed]"]
    from backend.integrations.subtitle_burn import escape_ffmpeg_filter_path
    font=escape_ffmpeg_filter_path(FONTS_DIR/'Inter-Regular.otf')
    total=f'{int(duration)//60:02d}\\:{int(duration)%60:02d}'
    filters.append(f"[timed]drawtext=fontfile={font}:text='%{{pts\\:gmtime\\:0\\:%M\\\\\\:%S}}':x=45:y={bar-18}:fontsize=24:fontcolor=white,drawtext=fontfile={font}:text='{total}':x=w-tw-45:y={bar-18}:fontsize=24:fontcolor=white[clock]")
    tail='[clock]'
    if subtitles:
        filters.append(tail+burn_subtitle_filter(subtitles,output,w,h,style=subtitle_style)+'[captioned]');tail='[captioned]'
    filters.append(tail+'format=yuv420p[vout]')
    return command+['-filter_complex',';'.join(filters),'-map','[vout]','-map','[aout]','-t',str(duration),'-r','30','-c:v','libx264','-threads:v',str(min(4, os.cpu_count() or 1)),'-preset','veryfast','-crf','23','-c:a','aac','-b:a','128k','-movflags','+faststart',str(output)]
