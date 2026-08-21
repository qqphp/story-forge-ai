import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appRoot = fileURLToPath(new URL("../app/", import.meta.url));
const backendRoot = fileURLToPath(new URL("../backend/", import.meta.url));
const sourceTree = (root, suffixes) => readdirSync(root, { recursive: true })
  .filter(file => (Array.isArray(suffixes) ? suffixes : [suffixes]).some(suffix => file.endsWith(suffix)))
  .map(file => readFileSync(join(root, file), "utf8"))
  .join("\n");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const page = sourceTree(appRoot, [".ts", ".tsx"]);
const backend = sourceTree(backendRoot, ".py");

test("configuration dialogs remain scrollable at high display scaling", () => {
  assert.match(css, /\.config-modal\{[^}]*overflow-y:auto/);
  assert.match(css, /\.settings-modal\{[^}]*min-height:0/);
  assert.match(css, /\.settings-modal \.modal-actions\{[^}]*position:sticky/);
});

test("workflow voice and speech rate use matching control cards", () => {
  assert.match(page, /<VoiceControl[^>]*label="配音音色"/);
  assert.match(css, /\.workflow-speech-grid>\*\{[^}]*min-height:/);
});

test("long model lists stay inside the settings dialog", () => {
  assert.doesNotMatch(page, /models\.length\?<select/);
  assert.match(page, /<ModelSelect/);
  assert.match(css, /\.model-options\{[^}]*max-height:/);
  assert.match(css, /\.model-options\{[^}]*overflow:auto/);
  assert.match(css, /\.model-select\{[^}]*position:relative/);
  assert.match(css, /\.model-dropdown\{[^}]*position:absolute/);
});

test("audio format uses the same contained floating picker", () => {
  assert.doesNotMatch(page, /音频格式<select/);
  assert.match(page, /<FormatSelect/);
  assert.match(css, /\.format-control\{[^}]*margin-top:/);
  assert.match(css, /\.settings-pane \.settings-block>label\+\.form-grid\{[^}]*margin-top:/);
});

test("model and voice configuration are separated", () => {
  assert.match(page, />模型配置<\/button>/);
  assert.match(page, />语音设置<\/button>/);
  assert.match(page, />视频设置<\/button>/);
  assert.match(page, /<h2>模型配置<\/h2>/);
  assert.match(page, /<b>配置说明<\/b>/);
  assert.match(page, /<h2>语音设置<\/h2>/);
  assert.match(page, /<b>微软语音服务<\/b>/);
  assert.match(page, /<b>音色中心<\/b>/);
  assert.match(page, /<b>背景音乐<\/b>/);
});

test("voice center provides global search preview pagination and offline download", () => {
  assert.match(page, /api\/voices\/\$\{encodeURIComponent\(item\.short_name\)\}\/preview\?locale=/);
  assert.match(page, /api\/voices\/download-all/);
  assert.match(page, /搜索音色、语言、地区或性别/);
  assert.match(page, /试听会根据音色所属国家或地区，自动翻译并生成对应语言/);
  assert.match(page, /<Pagination page=\{voicePage\}/);
});

test("background music supports HTTPS entry search and pagination", () => {
  assert.match(page, /api\/background-music/);
  assert.match(page, /HTTPS 音频地址/);
  assert.match(page, /搜索名称或分类/);
  assert.match(page, /<Pagination page=\{musicPage\}/);
  assert.match(page, /method:editingMusicId\?"PUT":"POST"/);
  assert.match(page, /<button onClick=\{\(\)=>setPlayingMusic\(item\)\}>试听<\/button>/);
  assert.match(page, /<button onClick=\{\(\)=>editMusic\(item\)\}>编辑<\/button>/);
  assert.match(page, /className="music-player"/);
  assert.match(page, /<audio key=\{playingMusic\?\.id/);
  assert.match(css, /\.music-list\{min-height:0\}/);
  assert.match(page, /const voicePageSize=8; const musicPageSize=6;/);
});

test("workflow creation supports background music mixing controls", () => {
  assert.match(page, /function MusicMixControl/);
  assert.match(page, /background_music_id:musicId\|\|null/);
  assert.match(page, /background_music_volume:musicVolume/);
  assert.match(page, /const \[musicVolume,setMusicVolume\]=useState\(0\.2\)/);
  assert.equal((page.match(/\[musicVolume,setMusicVolume\]=useState\(0\.2\)/g) || []).length, 2);
  assert.match(page, /音量 <b>\{volume\.toFixed\(2\)\}<\/b>[\s\S]*?type="range" min="0" max="1" step="0\.05"/);
  assert.match(page, /淡入时间/);
  assert.match(page, /淡出时间/);
  assert.match(css, /\.music-mix-grid/);
});

test("cover ratios are selected as prompts and generated images expose their metadata", () => {
  assert.doesNotMatch(backend, /gpt-image-2-codex/);
  assert.match(backend, /settings\.get\("image_model", "gpt-image-2"\)/);
  assert.match(backend, /图片比例：\{image_ratio\}/);
  assert.match(page, /1\.91:1/);
  assert.match(page, /2\.35:1/);
  assert.match(page, /图片比例/);
  assert.match(page, /CoverGallery/);
  assert.match(page, /共生成 <b>\{covers\.length\}<\/b> 张图片/);
  assert.match(css, /\.cover-gallery/);
});

test("workflow details expose generated tags and topics as a seven-step pipeline", () => {
  assert.match(page, /"生成标签和话题"/);
  assert.match(page, /task\.tags\?\.length/);
  assert.match(page, /task\.topics\?\.length/);
  assert.match(page, /<h3>标签和话题<\/h3>/);
  assert.match(page, /标签话题生成/);
  assert.match(css, /grid-template-columns:repeat\(7,1fr\)/);
  assert.match(css, /\.taxonomy-panel/);
});

test("configuration and request logs use standalone sidebar pages", () => {
  assert.match(page, /className="side-nav"/);
  assert.match(page, />提示词库<\/button>/);
  assert.match(page, />模型配置<\/button>/);
  assert.match(page, />语音设置<\/button>/);
  assert.match(page, />请求日志<\/button>/);
  assert.match(page, /<RequestLogsPage/);
  assert.match(page, /type="datetime-local"/);
  assert.match(page, /method:"DELETE"/);
  assert.match(page, /<option value="视频搜索词生成">视频搜索词生成<\/option>/);
  assert.match(page, /<option value="无版权视频搜索">无版权视频搜索<\/option>/);
  assert.match(css, /\.config-page \.modal-backdrop\{position:static/);
  assert.match(css, /\.config-page \.modal\{[^}]*border:0;[^}]*background:transparent;[^}]*box-shadow:none/);
  assert.match(css, /\.config-page \.modal-head\{display:none\}/);
});

test("prompt library tabs have icons subtitles and a single-column mobile editor", () => {
  assert.match(page, /className="settings-tabs prompt-tabs"/);
  assert.match(page, /<span aria-hidden="true">文<\/span>/);
  assert.match(page, /<small>定义分享稿结构、语气与长度<\/small>/);
  assert.match(page, /<span aria-hidden="true">画<\/span>/);
  assert.match(page, /<small>定义封面风格、构图与色彩<\/small>/);
  assert.match(css, /\.config-page \.library-layout\{grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css, /\.config-page \.template-composer\{position:static;top:auto\}/);
  assert.match(css, /\.config-page \.prompt-tabs\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});

test("workspace supports compact mobile navigation and bulk list deletion", () => {
  assert.match(page, /setWorkView\("list"\)/);
  assert.match(page, /function TaskList/);
  assert.match(page, /全选当前结果/);
  assert.match(page, /删除所选/);
  assert.match(page, /Promise\.all\(ids\.map\(id=>fetch/);
  assert.match(css, /\.app-shell\{grid-template-columns:196px/);
  assert.match(css, /\.side-nav\{position:fixed;inset:auto 0(?: 0 0)?/);
  assert.match(css, /grid-template-columns:repeat\(7,minmax\(0,1fr\)\)/);
});

test("video settings configure orientation and royalty-free providers", () => {
  assert.match(page, /function VideoSettingsPage/);
  assert.match(page, /横版 16:9/);
  assert.match(page, /竖版 9:16/);
  assert.match(page, /引用无版权视频/);
  assert.match(page, /PEXELS_KEY/);
  assert.match(page, /PIXABAY_KEY/);
});

test("cover prompt requires both video cover ratios", () => {
  assert.match(page, /imageSizes\.includes\("16:9"\)&&imageSizes\.includes\("9:16"\)/);
  assert.match(page, /<ImageSizePicker value=\{imageSizes\} onChange=\{setImageSizes\}\/>/);
  assert.match(page, /disabled=\{!connected\|\|!name\.trim\(\)\|\|!text\.trim\(\)\|\|\(kind==="cover"&&!hasRequiredCoverSizes\)\|\|saving\}/);
});

test("batch creation starts with six rows and shares generation settings", () => {
  assert.match(page, /Array\.from\(\{length:6\}/);
  assert.match(page, /className="primary batch-launch"/);
  assert.match(page, /<span aria-hidden="true">▦<\/span>\s*批量制作/);
  assert.match(css, /\.batch-launch\{background:#[0-9a-f]+;color:#fff\}/i);
  assert.match(page, /api\/workflows\/batch/);
  assert.match(page, /第 \{step\} 步 \/ 2/);
  assert.match(page, /共用配音设置/);
  assert.match(page, /共用分享稿提示词/);
  assert.match(page, /共用封面提示词/);
});
