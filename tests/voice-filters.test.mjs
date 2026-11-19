import assert from "node:assert/strict";
import test from "node:test";
import {
  emptyVoiceFilters,
  filterVoices,
  localeLabel,
  normalizeVoiceItem,
  voiceFilterDefinitions,
  voiceTags,
} from "../app/features/voices/voice-catalog.ts";

const xiaoxiao = normalizeVoiceItem({
  short_name: "zh-CN-XiaoxiaoNeural",
  locale: "zh-CN",
  locale_name: "Chinese (Mandarin, Simplified)",
  local_name: "晓晓",
  display_name: "Xiaoxiao",
  gender: "Female",
  voice_type: "Neural",
  status: "GA",
  sample_rate_hertz: "48000",
  styles: ["chat", "newscast"],
  roles: ["YoungAdultFemale"],
  secondary_locales: ["en-US"],
  scenarios: ["Chat", "News"],
  personalities: ["Warm"],
});
const yunxi = normalizeVoiceItem({
  short_name: "zh-CN-YunxiNeural",
  locale: "zh-CN",
  local_name: "云希",
  gender: "Male",
  voice_type: "Neural",
  status: "GA",
  sample_rate_hertz: "24000",
});
const jenny = normalizeVoiceItem({
  short_name: "en-US-JennyNeural",
  locale: "en-US",
  local_name: "Jenny",
  gender: "Female",
  voice_type: "Neural",
  status: "Preview",
  styles: ["chat"],
  scenarios: ["Chat"],
  personalities: ["Friendly"],
  sample_rate_hertz: "48000",
});
const hamedDragonLatest = normalizeVoiceItem({
  short_name: "ar-SA-Hamed:DragonLatestNeural",
  locale: "ar-SA",
  local_name: "Hamed Dragon Latest",
  gender: "Male",
  voice_type: "Neural",
  secondary_locales: ["en-US", "zh-CN", "zh-TW"],
});
const voices = [xiaoxiao, yunxi, jenny, hamedDragonLatest];

test("voice filters combine language, region, gender, style and translated search", () => {
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, language: "zh", gender: "Female" }).map(voice => voice.short_name), ["zh-CN-XiaoxiaoNeural"]);
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, style: "newscast" }).map(voice => voice.short_name), ["zh-CN-XiaoxiaoNeural"]);
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, query: "女声 新闻" }).map(voice => voice.short_name), ["zh-CN-XiaoxiaoNeural"]);
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, language: "en" }).map(voice => voice.short_name), ["en-US-JennyNeural"]);
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, locale: "en-US" }).map(voice => voice.short_name), ["en-US-JennyNeural"]);
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, language: "zh", locale: "zh-TW" }), []);
});

test("locale labels keep Chinese dialects distinct", () => {
  assert.match(localeLabel("zh-CN-sichuan"), /四川话/);
  assert.match(localeLabel("zh-CN-sichuan"), /zh-CN-sichuan/);
  assert.match(localeLabel("en-GB"), /英语（英国）/);
  assert.match(localeLabel("sr-Latn-RS"), /塞尔维亚语（塞尔维亚，拉丁字母）/);
});

test("filter choices describe the returned voice metadata and keep independent counts", () => {
  const definitions = voiceFilterDefinitions(voices, { ...emptyVoiceFilters, gender: "Female", language: "zh" });
  const gender = definitions.find(item => item.key === "gender");
  const locale = definitions.find(item => item.key === "locale");
  assert.equal(gender.options.find(option => option.value === "Male").label, "男声");
  assert.equal(gender.options.find(option => option.value === "Male").count, 1);
  assert.equal(gender.options.find(option => option.value === "Female").count, 1);
  assert.ok(locale.options.every(option => option.value.startsWith("zh-")));
  assert.equal(definitions.some(item => item.key === "voiceType"), false);
  assert.equal(definitions.some(item => item.key === "sampleRate"), true);
  assert.equal(definitions.some(item => item.key === "style"), true);

  const styled = voiceFilterDefinitions(voices, { ...emptyVoiceFilters, style: "newscast" });
  const styles = styled.find(item => item.key === "style");
  const rates = styled.find(item => item.key === "sampleRate");
  assert.equal(styles.options.find(option => option.value === "chat").count, 2);
  assert.equal(styles.options.find(option => option.value === "newscast").label, "新闻播报");
  assert.equal(rates.options.find(option => option.value === "48000").label, "48 kHz");
  assert.deepEqual(filterVoices(voices, { ...emptyVoiceFilters, style: "newscast" }).map(voice => voice.short_name), ["zh-CN-XiaoxiaoNeural"]);
});

test("voice cards expose translated personalities, scenarios, styles and roles", () => {
  assert.deepEqual(voiceTags(xiaoxiao), ["温暖", "聊天", "新闻", "新闻播报", "青年女性"]);
});

test("incomplete voice records still filter without missing fields", () => {
  const item = normalizeVoiceItem({ short_name: "demo" });
  assert.equal(item.gender, "");
  assert.deepEqual(item.styles, []);
  assert.deepEqual(item.secondary_locales, []);
  assert.equal(filterVoices([item], emptyVoiceFilters).length, 1);
  assert.equal(voiceFilterDefinitions([item], emptyVoiceFilters).some(definition => definition.key === "gender"), false);
});
