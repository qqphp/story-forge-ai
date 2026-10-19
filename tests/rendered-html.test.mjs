import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { createServer } from "vite";

test("build produces a Chinese static HTML entry with local assets", () => {
  const html = readFileSync(new URL("../dist/index.html", import.meta.url), "utf8");
  assert.match(html, /<html lang="zh-CN">/);
  assert.match(html, /<title>砚界 · StoryForge AI<\/title>/);
  assert.match(html, /从一本书到分享文案、配音、封面与视频/);
  assert.match(html, /id="root"/);
  const scripts = [...html.matchAll(/<script[^>]+src="([^"]+)"/g)];
  assert.ok(scripts.length > 0);
  for (const [, src] of scripts) {
    assert.match(src, /^\/assets\/[^/]+\.js$/);
    assert.ok(existsSync(new URL(`../dist${src}`, import.meta.url)));
  }
  assert.ok(existsSync(new URL("../dist/favicon.ico", import.meta.url)));
});

test("renders the StoryForge product shell", async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false, watch: null }, appType: "custom" });
  try {
    const { default: Home } = await server.ssrLoadModule("/app/page.tsx");
    const html = renderToStaticMarkup(createElement(Home));
    assert.match(html, /把一本书，讲给更多人听/);
    assert.match(html, /开始新制作/);
    assert.match(html, /我的作品/);
    assert.doesNotMatch(html, /codex-preview|loading-skeleton/i);
  } finally {
    await server.close();
  }
});
