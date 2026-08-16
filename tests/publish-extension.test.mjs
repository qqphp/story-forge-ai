import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const backend = readFileSync(new URL("../backend/main.py", import.meta.url), "utf8");
const manifest = JSON.parse(readFileSync(new URL("../browser-extension/manifest.json", import.meta.url), "utf8"));
const content = readFileSync(new URL("../browser-extension/content.js", import.meta.url), "utf8");
const coverUpload = readFileSync(new URL("../browser-extension/cover-upload.js", import.meta.url), "utf8");

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
  assert.match(page, /selectedWorkflowRecord\.covers\|\|\[\]/);
  assert.match(page, /抖音默认竖封面 3:4、横封面 4:3/);
  assert.match(page, /cover_urls:coverUrls/);
  assert.match(page, /topics:topics\.split/);
});

test("extension is scoped to local StoryForge and Douyin creator", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions.sort(), ["storage", "tabs"]);
  assert.ok(!manifest.permissions.includes("cookies"));
  assert.deepEqual(manifest.content_scripts[0].matches, ["https://creator.douyin.com/*"]);
  assert.deepEqual(manifest.content_scripts[0].js, ["cover-upload.js", "content.js"]);
  assert.ok(manifest.host_permissions.includes("http://127.0.0.1:8000/*"));
});

test("extension uploads and fills but preserves final user confirmation", () => {
  assert.match(content, /new DataTransfer\(\)/);
  assert.match(content, /attachVideo/);
  assert.match(content, /attachCovers/);
  assert.match(content, /ratio:"4:3"/);
  assert.match(content, /ratio:"3:4"/);
  assert.match(content, /task\.topics\|\|\[\]/);
  assert.match(content, /\/covers\/\$\{coverIndex\}/);
  assert.match(content, /assertOriginalRatio/);
  assert.match(content, /Math\.abs\(actual-expected\)>\.01/);
  assert.match(content, /new File\(\[blob\],filename/);
  assert.doesNotMatch(content, /drawImage|toBlob|OffscreenCanvas|createElement\("canvas"\)/);
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

test("extension opens the ratio cover card before the modal upload control", () => {
  assert.doesNotMatch(content, /exactTextElements\("选择封面"\)/);
  assert.match(content, /"3:4":"竖封面3:4"/);
  assert.match(content, /"4:3":"横封面4:3"/);
  assert.match(content, /function findCoverTrigger/);
  assert.match(content, /querySelectorAll\("img"\)/);
  assert.match(content, /设置\$\{orientation\}封面/);
  assert.match(content, /const uploadButton=exactTextElements\("上传封面",dialog\)\.at\(-1\)/);
  assert.match(content, /imageInputsNear\(uploadButton,dialog\)/);
  assert.match(content, /assignFile\(input,file\);await new Promise\(resolve=>setTimeout\(resolve,3000\)\)/);
});

test("each cover upload ignores file inputs left by the previous cover dialog", () => {
  const context = {};
  vm.runInNewContext(coverUpload, context);
  const staleHorizontalInput = { id: "horizontal" };
  const selected = context.StoryForgeCoverUpload.pickImageInput({
    allInputs: [staleHorizontalInput],
    triggerInputs: [],
    previousInputs: new Set([staleHorizontalInput]),
  });
  assert.equal(selected, null);

  const activeVerticalInput = { id: "vertical" };
  assert.equal(context.StoryForgeCoverUpload.pickImageInput({
    allInputs: [staleHorizontalInput, activeVerticalInput],
    triggerInputs: [activeVerticalInput],
    previousInputs: new Set([staleHorizontalInput]),
  }), activeVerticalInput);

  const portalVerticalInput = { id: "vertical-portal" };
  assert.equal(context.StoryForgeCoverUpload.pickImageInput({
    allInputs: [staleHorizontalInput, portalVerticalInput],
    triggerInputs: [],
    previousInputs: new Set([staleHorizontalInput]),
  }), portalVerticalInput);
});

test("cover files use a canonical supported image type and upload vertical before horizontal", () => {
  const context = {};
  vm.runInNewContext(coverUpload, context);
  const format = context.StoryForgeCoverUpload.imageFormatFromBytes([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]);
  assert.equal(format.mimeType, "image/png");
  assert.equal(format.extension, ".png");
  const jpegFormat = context.StoryForgeCoverUpload.imageFormatFromBytes([0xff,0xd8,0xff,0xe0]);
  assert.equal(jpegFormat.mimeType, "image/jpeg");
  assert.equal(jpegFormat.extension, ".jpg");
  assert.match(content, /\[\{ratio:"3:4"\},\{ratio:"4:3"\}\]/);
  assert.doesNotMatch(content, /setTimeout\(resolve,5000\)/);
});

test("cover upload chooses the file input associated with the upload-cover button", () => {
  const context = {};
  vm.runInNewContext(coverUpload, context);
  const coverInput = { id: "upload-cover", className: "semi-upload-hidden-input" };
  const replaceInput = { id: "replace-cover", className: "semi-upload-hidden-input-replace" };
  const referenceInput = { id: "reference-image" };
  const selected = context.StoryForgeCoverUpload.pickImageInput({
    allInputs: [coverInput, replaceInput, referenceInput],
    triggerInputs: [coverInput, replaceInput],
    previousInputs: new Set(),
  });
  assert.equal(selected, coverInput);
  assert.match(content, /const dialogClosed=await waitFor\(\(\)=>!document\.contains\(dialog\)/);
  assert.match(content, /封面设置弹窗没有关闭/);
});
