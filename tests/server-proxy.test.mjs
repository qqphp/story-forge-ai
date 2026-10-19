import assert from "node:assert/strict";
import { createServer as httpServer, get } from "node:http";
import test from "node:test";
import { createServer, loadConfigFromFile, preview } from "vite";

function read(url, headers = {}) {
  return new Promise((resolve, reject) => {
    get(url, { headers }, response => {
      const chunks = [];
      response.on("data", chunk => chunks.push(chunk));
      response.on("end", () => resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks).toString() }));
    }).on("error", reject);
  });
}

async function close(server) {
  server.closeAllConnections();
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}

test("development and build preview proxy API, range media and voice samples on the same origin", async () => {
  const backend = httpServer((request, response) => {
    if (request.url === "/api/health") {
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ ok: true, host: request.headers.host }));
    } else if (request.url === "/media/test.mp4" && request.headers.range === "bytes=2-5") {
      response.writeHead(206, { "Content-Range": "bytes 2-5/10", "Content-Type": "video/mp4" });
      response.end("2345");
    } else if (request.url === "/voice-samples/sample.wav") {
      response.end("voice-sample");
    } else {
      response.writeHead(404, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ detail: "not found" }));
    }
  });
  await new Promise(resolve => backend.listen(0, "127.0.0.1", resolve));
  const target = `http://127.0.0.1:${backend.address().port}`;
  try {
    for (const mode of ["development", "preview"]) {
      const { config } = await loadConfigFromFile({ command: "serve", mode: "test" });
      const section = mode === "development" ? "server" : "preview";
      // Keep the project's actual route list; replace only the upstream for isolation.
      const proxy = Object.fromEntries(Object.entries(config[section].proxy).map(([path, options]) => [path, { ...options, target }]));
      const options = { ...config, configFile: false, logLevel: "silent", [section]: {
        ...config[section], host: "127.0.0.1", port: 0, strictPort: false, proxy,
        ...(section === "server" ? { hmr: false, watch: null } : {}),
      } };
      const server = mode === "development" ? await createServer(options) : await preview(options);
      try {
        if (mode === "development") await server.listen();
        const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
        const health = await read(`${origin}/api/health`);
        assert.equal(health.status, 200, mode);
        assert.deepEqual(JSON.parse(health.body), { ok: true, host: new URL(origin).host });
        const missing = await read(`${origin}/api/missing`);
        assert.equal(missing.status, 404);
        assert.equal(JSON.parse(missing.body).detail, "not found");
        const media = await read(`${origin}/media/test.mp4`, { Range: "bytes=2-5" });
        assert.equal(media.status, 206);
        assert.equal(media.headers["content-range"], "bytes 2-5/10");
        assert.equal(media.body, "2345");
        assert.equal((await read(`${origin}/voice-samples/sample.wav`)).body, "voice-sample");
        assert.match((await read(origin)).body, /<title>砚界 · StoryForge AI<\/title>/);
      } finally {
        if (mode === "development") await server.close();
        else await close(server.httpServer);
      }
    }
  } finally {
    await close(backend);
  }
});
