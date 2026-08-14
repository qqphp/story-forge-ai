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
});
