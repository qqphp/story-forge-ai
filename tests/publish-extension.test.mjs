import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const backend = readFileSync(new URL("../backend/main.py", import.meta.url), "utf8");
const manifest = JSON.parse(readFileSync(new URL("../browser-extension/manifest.json", import.meta.url), "utf8"));
const content = readFileSync(new URL("../browser-extension/content.js", import.meta.url), "utf8");

test("publishing center prepares local Douyin tasks", () => {
  assert.match(page, />发布中心<\/button>/);
  assert.match(page, /function PublishCenterPage/);
  assert.match(page, /\/api\/publish\/tasks/);
  assert.match(page, /\/api\/publish\/pairing/);
  assert.match(page, /creator\.douyin\.com\/creator-micro\/content\/upload/);
  assert.match(css, /\.publish-center/);
  assert.match(page, /作品简介/);
  assert.match(page, /workflow\.description\|\|""/);
  assert.match(page, /workflow\.topics\|\|\[\]/);
  assert.match(page, /className="publish-cover-picker"/);
  assert.match(page, /抖音默认竖封面 3:4、横封面 4:3/);
  assert.match(page, /cover_urls:coverUrls/);
  assert.match(page, /topics:topics\.split/);
});

test("extension is scoped to local StoryForge and Douyin creator", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions.sort(), ["storage", "tabs"]);
  assert.ok(!manifest.permissions.includes("cookies"));
  assert.deepEqual(manifest.content_scripts[0].matches, ["https://creator.douyin.com/*"]);
  assert.ok(manifest.host_permissions.includes("http://127.0.0.1:8000/*"));
});

test("extension uploads and fills but preserves final user confirmation", () => {
  assert.match(content, /new DataTransfer\(\)/);
  assert.match(content, /attachVideo/);
  assert.match(content, /attachCovers/);
  assert.match(content, /ratio:"4:3",slotIndex:1/);
  assert.match(content, /ratio:"3:4",slotIndex:0/);
  assert.match(content, /task\.topics\|\|\[\]/);
  assert.match(content, /\/covers\/\$\{coverIndex\}/);
  assert.match(content, /fillTopics/);
  assert.match(content, /#添加话题/);
  assert.doesNotMatch(content, /topicText=.*join\(" "\)/);
  assert.match(content, /findField\("title"\)/);
  assert.match(content, /findField\("description"\)/);
  assert.match(content, /我已手动发布/);
  assert.doesNotMatch(content, /querySelector\([^\n]*发布[^\n]*\)\.click/);
  assert.match(backend, /x_storyforge_token/);
  assert.match(backend, /secrets\.compare_digest/);
  assert.match(backend, /"标签话题生成"/);
});
