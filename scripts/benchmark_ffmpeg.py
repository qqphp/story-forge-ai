"""Repeatable full-player benchmark using the completed Ming workflow; outputs only to outputs/."""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.integrations.player import player_command
from backend.integrations.video import probe_audio_duration, probe_video_metadata

parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('player','normalize'),default='player');parser.add_argument('--seconds',type=float,default=8);parser.add_argument('--orientation',choices=('portrait','landscape'),default='portrait');parser.add_argument('--stock',action='store_true');parser.add_argument('--variants',help='Comma-separated player variants, or x264 presets for normalize');args=parser.parse_args();args.variants=args.variants or ('medium,veryfast' if args.stage=='normalize' else 'baseline,t8e4')
root=Path(__file__).resolve().parents[1]
with sqlite3.connect(root/'data/storyforge.db') as conn:
    workflow=json.loads(conn.execute("SELECT payload FROM workflows WHERE book_title=? AND status='completed' ORDER BY created_at DESC LIMIT 1",('明朝那些事儿',)).fetchone()[0])
    settings=json.loads(conn.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])
media=root/'data/media'/workflow['output_dir'];audio=media/Path(workflow['audio'][0]['url']).name
covers={c['image_ratio']:media/Path(c['url']).name for c in workflow['covers']}
subtitle=media/Path(workflow['subtitles'][0]['srt_url']).name
folder=root/'outputs'/f'ffmpeg-benchmark-{time.time_ns()}';folder.mkdir()
if args.stage=='normalize':
    source=next(media.glob('stock-pixabay-*.mp4'))
    results=[]
    for preset in args.variants.split(','):
        out=folder/f'{preset}.mp4'
        command=['ffmpeg','-y','-xerror','-i',str(source),'-map','0:v:0','-an','-t',str(args.seconds),'-vf','scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30','-c:v','libx264','-preset',preset,'-pix_fmt','yuv420p',str(out)]
        start=time.perf_counter();result=subprocess.run(command,capture_output=True,timeout=180)
        record=dict(stage='normalize',preset=preset,encode_seconds=round(time.perf_counter()-start,3),success=result.returncode==0,bytes=out.stat().st_size if out.exists() else 0,metadata=probe_video_metadata(out) if result.returncode==0 else None)
        (folder/f'{preset}.log').write_bytes(result.stderr)
        results.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
        (folder/'results.json').write_text(json.dumps(dict(source=str(source),source_metadata=probe_video_metadata(source),results=results),ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESULTS',str(folder/'results.json'),flush=True)
    sys.exit(0)
variants={'baseline':(1,'libx264'),'t4':(4,'libx264'),'t8':(8,'libx264'),'qsv1':(1,'h264_qsv'),'qsv4':(4,'h264_qsv'),'t4e4':(4,'libx264'),'t8e4':(8,'libx264')}
results=[]
for name in args.variants.split(','):
    threads,encoder=variants[name];out=folder/f'{name}.mp4'
    start=time.perf_counter()
    command=player_command('ffmpeg',covers['1:1'],audio,out,orientation=args.orientation,background_cover=covers['16:9' if args.orientation=='landscape' else '9:16'],subtitles=subtitle,subtitle_style=settings.get('subtitle_style'),record_label_image_id=settings.get('record_label_image_id'),background_overlay_enabled=settings.get('background_overlay_enabled',True),background_overlay_opacity=settings.get('background_overlay_opacity',.25),background_blur_enabled=settings.get('background_blur_enabled',False),background_blur_strength=settings.get('background_blur_strength',20),duration=args.seconds,stock_manifest=(media/'stock-videos.ffconcat') if args.stock else None)
    artwork_seconds=time.perf_counter()-start
    command[command.index('-filter_complex_threads')+1]=str(threads)
    command[-1:-1]=['-threads:v','4' if name.endswith('e4') else '0']
    if encoder=='h264_qsv':
        i=command.index('-c:v');command[i+1]=encoder
        i=command.index('-crf');command[i:i+2]=['-global_quality','23']
        i=command.index('-filter_complex');command[i+1]=command[i+1].replace('format=yuv420p[vout]','format=nv12[vout]')
    start=time.perf_counter()
    try:
        result=subprocess.run(command,capture_output=True,timeout=300)
        elapsed=time.perf_counter()-start
        (folder/f'{name}.log').write_bytes(result.stderr)
        record=dict(variant=name,encoder=encoder,threads=threads,render_seconds=args.seconds,orientation=args.orientation,stock=args.stock,artwork_seconds=round(artwork_seconds,3),encode_seconds=round(elapsed,3),success=result.returncode==0,bytes=out.stat().st_size if out.exists() else 0)
        if result.returncode==0: record['metadata']=probe_video_metadata(out)
        else: record['error']=result.stderr.decode('utf-8',errors='replace')[-1500:]
    except subprocess.TimeoutExpired:
        record=dict(variant=name,success=False,error='timeout')
    results.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
    (folder/'results.json').write_text(json.dumps(dict(audio=str(audio),audio_seconds=probe_audio_duration(audio),results=results),ensure_ascii=False,indent=2),encoding='utf-8')
print('RESULTS',str(folder/'results.json'),flush=True)
