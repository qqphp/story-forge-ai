import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import vm from "node:vm";

const appRoot = fileURLToPath(new URL("../app/", import.meta.url));
const backendRoot = fileURLToPath(new URL("../backend/", import.meta.url));
const sourceTree = (root, suffix) => readdirSync(root, { recursive: true })
  .filter(file => file.endsWith(suffix))
  .map(file => readFileSync(join(root, file), "utf8"))
  .join("\n");
const page = sourceTree(appRoot, ".tsx");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const backend = sourceTree(backendRoot, ".py");
const manifest = JSON.parse(readFileSync(new URL("../browser-extension/manifest.json", import.meta.url), "utf8"));
const content = readFileSync(new URL("../browser-extension/content.js", import.meta.url), "utf8");
const coverUpload = readFileSync(new URL("../browser-extension/cover-upload.js", import.meta.url), "utf8");
const editorCaret = readFileSync(new URL("../browser-extension/editor-caret.js", import.meta.url), "utf8");
const platforms = readFileSync(new URL("../browser-extension/platforms.js", import.meta.url), "utf8");
const multiPlatform = readFileSync(new URL("../browser-extension/multi-platform.js", import.meta.url), "utf8");

test("publishing center prepares independent multi-platform tasks", () => {
  assert.match(page, />发布中心<\/button>/);
  assert.match(page, /function MultiPublishCenterPage/);
  assert.match(page, /\/api\/publish\/tasks/);
  assert.match(page, /\/api\/publish\/pairing/);
  for(const platform of ["douyin","kuaishou","bilibili","xiaohongshu","baijiahao"])assert.match(page,new RegExp(`id:\"${platform}\"`));
  assert.match(css, /\.publish-center/);
  assert.match(page, /作品简介/);
  assert.match(page, /className="publish-destinations"/);
  assert.match(page, /className="publish-cover-picker"/);
  assert.match(page, /下载浏览器扩展 ZIP/);
  assert.match(page, /cover_urls:coverUrls/);
  assert.match(page, /topics:topics\.split/);
});

test("extension supports all configured creator platforms without cookie access", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions.sort(), ["storage", "tabs"]);
  assert.ok(!manifest.permissions.includes("cookies"));
  assert.deepEqual(manifest.content_scripts[0].matches, ["https://creator.douyin.com/*"]);
  assert.deepEqual(manifest.content_scripts[0].js, ["platforms.js", "cover-upload.js", "editor-caret.js", "content.js"]);
  assert.deepEqual(manifest.content_scripts[1].matches, ["https://cp.kuaishou.com/*", "https://member.bilibili.com/*", "https://creator.xiaohongshu.com/*", "https://baijiahao.baidu.com/*"]);
  assert.deepEqual(manifest.content_scripts[1].js, ["platforms.js", "cover-upload.js", "multi-platform.js"]);
  assert.match(platforms, /baijiahao/);
  assert.match(multiPlatform, /不会自动点击最终发布按钮/);
  assert.match(multiPlatform, /attachVideo/);
  assert.ok(manifest.host_permissions.includes("http://127.0.0.1:8000/*"));
});

test("kuaishou fills only description and topics, then uploads one 3:4 cover", () => {
  assert.match(multiPlatform, /platform!=="kuaishou"&&title/);
  assert.match(multiPlatform, /\[contenteditable='true'\]\[placeholder\*='描述'\]/);
  assert.match(multiPlatform, /#work-description-edit/);
  assert.match(multiPlatform, /appendKuaishouTopics/);
  assert.match(multiPlatform, /const text=` #\$\{tag\} `;/);
  assert.match(multiPlatform, /new KeyboardEvent\("keydown"/);
  assert.match(multiPlatform, /new InputEvent\("beforeinput"/);
  assert.match(multiPlatform, /setTimeout\(resolve,35\)/);
  assert.match(multiPlatform, /setTimeout\(resolve,700\)/);
  assert.match(multiPlatform, /\[class\*='_cover-full-editor_'\]/);
  assert.match(multiPlatform, /\[class\*='_header-title-item_'\]/);
  assert.match(multiPlatform, /\[class\*='_ratio-item_'\]/);
  assert.match(multiPlatform, /assignFile\(input,await fetchFile[\s\S]*setTimeout\(resolve,2000\)[\s\S]*kuaishouConfirmButton\(dialog\)/);
  assert.match(multiPlatform, /kuaishouConfirmButton/);
  assert.match(multiPlatform, /dialog\.querySelectorAll\("button"\)/);
  assert.match(backend, /topic_limit = \{"kuaishou": 4, "douyin": 5\}/);
  assert.match(page, /platform==="kuaishou"\?4:platform==="douyin"\?5/);
  assert.match(multiPlatform, /kuaishouCovers/);
  assert.match(multiPlatform, /item\.image_ratio==="3:4"/);
  assert.doesNotMatch(multiPlatform, /\["4:3","3:4"\]/);
  assert.match(multiPlatform, /exactTextElements\("上传封面",dialog\)/);
  assert.match(multiPlatform, /exactTextElements\("确认",dialog\)/);
  assert.match(page, /快手视频发布使用一张3:4的图片即可，需要勾选3:4图片尺寸。/);
  assert.match(page, /const requiresTitle=targets\.some\(platform=>platform!=="kuaishou"\)/);
  assert.match(backend, /value\.platform in \{"douyin", "kuaishou"\}/);
});

test("bilibili fills description and at most ten confirmed tags", () => {
  assert.match(page, />标签</);
  assert.match(page, />标签[^<]*<small>[^<]*<\/small><input[^>]*>[\s\S]*?<\/label><p className="publish-topic-hint">哔哩哔哩平台最多支持10个标签。<\/p><label>话题/);
  assert.match(multiPlatform, /bilibiliDescriptionField/);
  assert.match(multiPlatform, /\.ql-editor/);
  assert.match(multiPlatform, /#tag-container/);
  assert.match(multiPlatform, /task\.tags[^;]*slice\(0,10\)/);
  assert.match(multiPlatform, /label-item-v2-container/);
  assert.match(multiPlatform, /await clearBilibiliTags\(\);await new Promise\(resolve=>setTimeout\(resolve,2000\)\)/);
  assert.match(multiPlatform, /new KeyboardEvent\("keydown",\{[^}]*key:"Enter"/);
});

test("bilibili uploads matching covers without opening the system file picker", () => {
  assert.match(multiPlatform, /bilibiliCovers/);
  assert.match(multiPlatform, /ratio:"4:3",label:"首页推荐封面（4:3）"/);
  assert.match(multiPlatform, /ratio:"16:9",label:"个人空间封面（16:9）"/);
  assert.match(multiPlatform, /"4:3":"\.editor_4_3","16:9":"\.editor_16_9"/);
  assert.match(multiPlatform, /closest\("\.active,\.inactive"\)/);
  assert.match(multiPlatform, /await waitFor\(\(\)=>region\.closest\("\.active,\.inactive"\)\?\.classList\.contains\("active"\)/);
  assert.match(multiPlatform, /captureBilibiliImageInput/);
  assert.match(multiPlatform, /event\.preventDefault\(\);event\.stopImmediatePropagation\(\)/);
  assert.match(multiPlatform, /assignFile\(input,await fetchFile/);
  assert.match(multiPlatform, /await uploadBilibiliCover\(dialog,home,uploaded,skipped\);if\(uploaded\.includes\("4:3"\)\)await new Promise\(resolve=>setTimeout\(resolve,2000\)\);await uploadBilibiliCover\(dialog,space,uploaded,skipped\)/);
  assert.match(multiPlatform, /exactTextElements\("完成",dialog\)/);
});

test("bilibili cover activation targets the cropper canvas with a real pointer sequence", () => {
  const events=[];
  const section={classList:{active:false,contains(name){return name==="active"&&this.active;}}};
  const target={dispatchEvent(event){events.push(event.type);if(event.type==="mousedown")section.classList.active=true;return true;}};
  const region={querySelector(selector){return selector===".upper-canvas"?target:null;},closest(){return section;}};
  class TestEvent {constructor(type,options){this.type=type;Object.assign(this,options);}}
  const context={MouseEvent:TestEvent,PointerEvent:TestEvent};
  vm.runInNewContext(coverUpload,context);
  assert.equal(context.StoryForgeCoverUpload.activateBilibiliCoverRegion(region),true);
  assert.deepEqual(events,["pointerdown","mousedown","pointerup","mouseup","click"]);
  assert.equal(section.classList.contains("active"),true);
});

test("first topic insertion targets the final text node of the description", () => {
  const selection={removeAllRanges(){},addRange(range){this.range=range;}};
  const range={selectNodeContents(node){this.selectedNode=node;},setStart(node,offset){this.startContainer=node;this.startOffset=offset;},collapse(){}};
  const finalText={nodeType:3,nodeValue:"作品简介的最后一句"};
  const description={focus(){this.focused=true;},dispatchEvent(){},childNodes:[{nodeType:3,nodeValue:"《西游记》"},finalText]};
  const context={
    getSelection:()=>selection,
    document:{createRange:()=>range,execCommand(){return true;}},
    InputEvent:class InputEvent{},
  };
  vm.runInNewContext(editorCaret,context);
  context.StoryForgeEditorCaret.insertText(description,"再读西游记");
  assert.equal(selection.range.startContainer,finalText);
  assert.equal(selection.range.startOffset,finalText.nodeValue.length);
});

test("topic marker is appended with its first topic instead of preceding the description", () => {
  const selection={removeAllRanges(){},addRange(){}};
  const finalText={nodeType:3,nodeValue:"作品简介"};
  const description={textContent:"作品简介",focus(){},dispatchEvent(){},childNodes:[finalText]};
  const context={
    getSelection:()=>selection,
    document:{createRange:()=>({selectNodeContents(){},setStart(){},collapse(){}}),execCommand(_command,_ui,value){description.textContent+=value;return true;}},
    InputEvent:class InputEvent{},
  };
  vm.runInNewContext(editorCaret,context);
  context.StoryForgeEditorCaret.insertTopic(description,"再读西游记");
  assert.equal(description.textContent,"作品简介#再读西游记");
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
  assert.match(content, /StoryForgeEditorCaret\.insertTopic\(descriptionField,tag\)/);
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
