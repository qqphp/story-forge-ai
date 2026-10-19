import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const runtime = readFileSync(new URL("../browser-extension/runtime-api.js", import.meta.url), "utf8");
const popup = readFileSync(new URL("../browser-extension/popup.js", import.meta.url), "utf8");
const settle = () => new Promise(resolve => setImmediate(resolve));

async function openPopup(stored = {}) {
  const nodes = Object.fromEntries(["apiBase", "token", "platform", "status", "task", "taskTitle", "taskBook", "save", "open"].map(id => [id, {
    value: "", listeners: {}, hidden: true,
    addEventListener(name, handler) { this.listeners[name] = handler; },
  }]));
  const state = { stored: { ...stored }, grants: true, contains: true, status: 200, failNetwork: false, saves: [], requested: [], requests: [], tabs: [] };
  const context = {
    URL, Error,
    document: { querySelector: selector => nodes[selector.slice(1)] },
    chrome: {
      storage: { local: {
        get: async () => ({ ...state.stored }),
        set: async value => { state.saves.push(value); Object.assign(state.stored, value); },
      } },
      permissions: {
        request: async value => { state.requested.push(value); return state.grants; },
        contains: async () => state.contains,
      },
      tabs: { create: async value => state.tabs.push(value) },
    },
    StoryForgePlatforms: { openUrl: (platform, id) => `https://creator.example/${platform}?task=${id}` },
    fetch: async (url, options) => {
      state.requests.push({ url, options });
      if (state.failNetwork) throw new Error("网络不可用");
      return { ok: state.status === 200, status: state.status, json: async () => ({ task: null }) };
    },
  };
  vm.createContext(context);
  vm.runInContext(runtime, context);
  vm.runInContext(popup, context);
  await settle();
  state.saves.length = 0;
  state.requests.length = 0;
  return { nodes, state, runtime: context.StoryForgeRuntime };
}

test("Save requests only the selected HTTPS server and preserves its base path", async () => {
  const { nodes, state } = await openPopup();
  nodes.apiBase.value = "https://forge.example:8443/service/";
  nodes.token.value = "test-pairing";
  nodes.platform.value = "douyin";
  nodes.save.listeners.click();
  await settle();
  assert.equal(state.requested.length, 1);
  assert.equal(state.requested[0].origins[0], "https://forge.example:8443/*");
  assert.equal(state.stored.apiBase, "https://forge.example:8443/service");
  assert.equal(state.requests[0].url, "https://forge.example:8443/service/api/publish/extension/tasks/next?platform=douyin");
  assert.equal(state.requests[0].options.headers["X-StoryForge-Token"], "test-pairing");
  assert.equal(nodes.status.textContent, "已连接 StoryForge");
});

test("denied permission, invalid token and failed requests retain the previous settings", async () => {
  for (const failure of ["permission", "token", "network"]) {
    const previous = { apiBase: "http://localhost:8000", storyForgeToken: "previous-test-token", storyForgePlatform: "douyin" };
    const { nodes, state } = await openPopup(previous);
    nodes.apiBase.value = "https://new.example";
    nodes.token.value = "candidate-test-token";
    state.grants = failure !== "permission";
    state.status = failure === "token" ? 401 : 200;
    state.failNetwork = failure === "network";
    nodes.save.listeners.click();
    await settle();
    assert.deepEqual(state.stored, previous);
    assert.equal(state.saves.length, 0);
    assert.equal(nodes.status.className, "status error");
    if (failure === "permission") assert.equal(state.requests.length, 0);
    if (failure === "token") assert.equal(nodes.status.textContent, "配对码无效");
  }
});

test("startup and platform changes never request optional permissions", async () => {
  const { nodes, state } = await openPopup({ apiBase: "https://forge.example", storyForgeToken: "test-pairing" });
  state.contains = false;
  nodes.platform.listeners.change();
  await settle();
  assert.equal(state.requested.length, 0);
  assert.equal(state.saves.length, 0);
  assert.equal(state.requests.length, 0);
  assert.match(nodes.status.textContent, /保存并检测/);
});

test("service addresses allow local HTTP and remote HTTPS, and reject unsafe inputs", async () => {
  const { runtime: client } = await openPopup();
  assert.equal(client.normalizeBase(""), "http://127.0.0.1:8000");
  assert.equal(client.normalizeBase("http://localhost:3000/"), "http://localhost:3000");
  assert.equal(client.normalizeBase("https://forge.example/"), "https://forge.example");
  for (const invalid of ["http://remote.example", "file:///tmp/test", "https://name:password@forge.example", "https://forge.example/?token=test", "https://forge.example/#test"]) {
    assert.throws(() => client.normalizeBase(invalid));
  }
});

test("opening a creator page uses saved settings and stops on an invalid pairing token", async () => {
  const { nodes, state } = await openPopup({ apiBase: "https://saved.example", storyForgeToken: "saved-test-token", storyForgePlatform: "douyin" });
  nodes.apiBase.value = "https://unsaved.example";
  nodes.open.listeners.click();
  await settle();
  assert.match(state.requests[0].url, /^https:\/\/saved\.example\//);
  assert.equal(state.tabs.length, 1);
  state.status = 401;
  nodes.open.listeners.click();
  await settle();
  assert.equal(state.tabs.length, 1);
  assert.equal(nodes.status.className, "status error");
});

test("remote file downloads use the selected server and pairing header without cookies", async () => {
  const calls = [];
  class TestFile { constructor(parts, name, options) { Object.assign(this, { parts, name, type: options.type }); } }
  const context = { URL, File: TestFile, fetch: async (url, options) => {
    calls.push({ url, options });
    return { ok: true, blob: async () => ({ type: "video/mp4" }) };
  } };
  vm.runInNewContext(runtime, context);
  const client = context.StoryForgeRuntime.createApiClient("https://forge.example", "test-pairing");
  const file = await client.fetchFile("/api/publish/extension/tasks/test/video", "video.mp4", "video/mp4");
  assert.equal(calls[0].url, "https://forge.example/api/publish/extension/tasks/test/video");
  assert.equal(calls[0].options.headers["X-StoryForge-Token"], "test-pairing");
  assert.equal(calls[0].options.credentials, "omit");
  assert.equal(file.name, "video.mp4");
});
