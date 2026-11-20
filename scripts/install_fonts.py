"""Install the twelve reviewed OFL fonts from official releases (run at packaging time)."""
import concurrent.futures
import hashlib
import io
import json
import struct
import time
import urllib.request
import zipfile
from pathlib import Path
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / 'fonts'

def download(url):
    for attempt in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'StoryForge-font-installer'}),timeout=90).read()
        except OSError:
            if attempt == 2: raise
            time.sleep(1)


def _font_family(path: Path) -> str:
    data = path.read_bytes()
    num_tables = struct.unpack_from(">H", data, 4)[0]
    name_offset = None
    for index in range(num_tables):
        tag, _checksum, table_offset, _length = struct.unpack_from(">4sIII", data, 12 + index * 16)
        if tag == b"name":
            name_offset = table_offset
            break
    if name_offset is None:
        raise AssertionError(f"{path.name} 没有 name 表")
    _format, count, string_offset = struct.unpack_from(">HHH", data, name_offset)
    found: dict[tuple[int, int], str] = {}
    for index in range(count):
        platform, encoding, language, name_id, length, value_offset = struct.unpack_from(">HHHHHH", data, name_offset + 6 + index * 12)
        raw = data[name_offset + string_offset + value_offset:name_offset + string_offset + value_offset + length]
        if platform == 3 and encoding in (1, 10):
            text = raw.decode("utf-16-be", errors="ignore")
        elif platform == 1:
            text = raw.decode("latin-1", errors="ignore")
        else:
            continue
        if name_id in (1, 16) and text:
            found[(name_id, language)] = text
    for name_id in (16, 1):
        for language in (0x409, 0, 0x804):
            if (name_id, language) in found:
                return found[(name_id, language)]
    for name_id in (16, 1):
        for (found_id, _language), text in found.items():
            if found_id == name_id:
                return text
    raise AssertionError(f"{path.name} 没有字体家族名")

def main():
    manifest_path = FONTS / 'manifest.json'
    existing = json.loads(manifest_path.read_text(encoding='utf-8'))['fonts']
    commit = next((f['version'] for f in existing if f.get('source', '').startswith('https://raw.githubusercontent.com/google/fonts/') and 'version' in f), None)
    if commit is None:
        commit = json.loads(download('https://api.github.com/repos/google/fonts/commits/main'))['sha']
    specs = []
    for font_id,name,file in [('zcoolkuaile','站酷快乐体','ZCOOLKuaiLe-Regular.ttf'),('zcoolqingkehuangyou','站酷庆科黄油体','ZCOOLQingKeHuangYou-Regular.ttf'),('zcoolxiaowei','站酷小薇体','ZCOOLXiaoWei-Regular.ttf'),('mashanzheng','马善政楷书','MaShanZheng-Regular.ttf'),('liujianmaocao','刘建毛草','LiuJianMaoCao-Regular.ttf'),('zhimangxing','志莽行书','ZhiMangXing-Regular.ttf'),('longcang','龙藏体','LongCang-Regular.ttf')]:
        base=f'https://raw.githubusercontent.com/google/fonts/{commit}/ofl/{font_id}/'
        specs.append((font_id,name,base+file,base+'OFL.txt',commit,'手写' if font_id not in ('zcoolxiaowei','zcoolqingkehuangyou') else '正文'))
    for font_id,name,repo,version,file,license_file in [
        ('smiley-sans','得意黑','atelier-anchor/smiley-sans','v2.0.1','smiley-sans-v2.0.1.zip','LICENSE'),
        ('zhuque-fangsong','朱雀仿宋','TrionesType/zhuque','v0.212','ZhuqueFangsong-v0.212.zip','LICENSE.txt'),
        ('chill-round-f','寒蝉全圆体','Warren2060/ChillRound','v3.200','ChillRoundF_v3.200.zip','LICENSE'),
        ('chill-round-m','寒蝉半圆体','Warren2060/ChillRound','v1.805','ChillRoundM_v1.805.zip','LICENSE'),
        ('xiaolai','小赖简体','lxgw/kose-font','v3.126','Xiaolai-Regular.ttf','OFL.txt')]:
        specs.append((font_id,name,f'https://github.com/{repo}/releases/download/{version}/{file}',f'https://raw.githubusercontent.com/{repo}/{version}/{license_file}',version,'圆体' if 'round' in font_id else '手写' if font_id=='xiaolai' else '正文'))
    def install(spec):
        font_id,name,url,license_url,version,category=spec
        cache=ROOT/'outputs'/'font-downloads'/url.rsplit('/',1)[-1];cache.parent.mkdir(parents=True,exist_ok=True)
        raw=cache.read_bytes() if cache.exists() else download(url)
        cache.write_bytes(raw)
        if url.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                files=[n for n in archive.namelist() if n.lower().endswith(('.ttf','.otf')) and '__MACOSX' not in n]
                files.sort(key=lambda n: ('regular' not in n.lower(), not n.lower().endswith('.ttf'),len(n)))
                raw=archive.read(files[0]); extension=Path(files[0]).suffix
                print(font_id,files[0],flush=True)
        else:extension='.ttf'
        file=font_id+extension
        ImageFont.truetype(io.BytesIO(raw),32)
        license_raw=download(license_url)
        if b'SIL OPEN FONT LICENSE' not in license_raw.upper():raise ValueError('Missing OFL: '+font_id)
        (FONTS/file).write_bytes(raw)
        family=_font_family(FONTS/file)
        (FONTS/'licenses'/f'{font_id}-OFL.txt').write_bytes(license_raw)
        print('installed',font_id,family,flush=True)
        return dict(id=font_id,role=name,family=family,file=file,license='SIL Open Font License 1.1',source=url,version=version,sha256=hashlib.sha256(raw).hexdigest(),category=category,selectable=True)
    installed=list(concurrent.futures.ThreadPoolExecutor(max_workers=5).map(install,specs))
    manifest=json.loads((FONTS/'manifest.json').read_text(encoding='utf-8'))
    manifest['fonts']=[f for f in manifest['fonts'] if f['id'] not in {i['id'] for i in installed}]+installed
    (FONTS/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
