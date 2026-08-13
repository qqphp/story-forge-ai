import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } }, { waitUntil() {}, passThroughOnException() {} });
}

test("renders the StoryForge product shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>砚界 · StoryForge AI<\/title>/i);
  assert.match(html, /把一本书，讲给更多人听/);
  assert.match(html, /开始新制作/);
  assert.match(html, /我的作品/);
  assert.doesNotMatch(html, /codex-preview|loading-skeleton/i);
});
