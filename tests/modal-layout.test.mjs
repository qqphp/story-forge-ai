import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

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
  assert.match(page, /<h2>模型配置<\/h2>/);
  assert.match(page, /<b>配置说明<\/b>/);
  assert.match(page, /<h2>语音设置<\/h2>/);
  assert.match(page, /<b>微软语音服务<\/b>/);
  assert.match(page, /<b>音色中心<\/b>/);
  assert.match(page, /<b>背景音乐<\/b>/);
});

test("voice center provides global search preview pagination and offline download", () => {
  assert.match(page, /api\/voices\/\$\{encodeURIComponent\(voice\)\}\/preview/);
  assert.match(page, /api\/voices\/download-all/);
  assert.match(page, /搜索音色、语言、地区或性别/);
  assert.match(page, /试听文案：你好，欢迎收听这款流畅自然的AI配音。/);
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
});

test("voice preview uses the fluent natural sample copy", () => {
  assert.match(page, /你好，欢迎收听这款流畅自然的AI配音。/);
  assert.doesNotMatch(page, /流程、自然的AI配音/);
});
