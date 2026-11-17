import type { VoiceItem } from "../shared/types";

export type { VoiceItem };

export type VoiceFilterKey =
  | "language"
  | "locale"
  | "gender"
  | "voiceType"
  | "status"
  | "style"
  | "scenario"
  | "personality"
  | "role"
  | "sampleRate";

export type VoiceFilterState = {
  query: string;
  language: string;
  locale: string;
  gender: string;
  voiceType: string;
  status: string;
  style: string;
  scenario: string;
  personality: string;
  role: string;
  sampleRate: string;
};

export type VoiceFilterOption = { value: string; label: string; count: number };

export type VoiceFilterGroup = { id: string; label: string; options: VoiceFilterOption[] };

export type VoiceFilterDefinition = {
  key: VoiceFilterKey;
  label: string;
  emptyLabel: string;
  options: VoiceFilterOption[];
  groups?: VoiceFilterGroup[];
};

type VoiceItemInput = {
  short_name?: unknown;
  locale?: unknown;
  locale_name?: unknown;
  local_name?: unknown;
  display_name?: unknown;
  gender?: unknown;
  voice_type?: unknown;
  status?: unknown;
  sample_rate_hertz?: unknown;
  styles?: unknown;
  roles?: unknown;
  secondary_locales?: unknown;
  scenarios?: unknown;
  personalities?: unknown;
};

type FilterSpec = {
  key: VoiceFilterKey;
  label: string;
  emptyLabel: string;
  minValues: number;
  grouped?: boolean;
};

const FILTERS: FilterSpec[] = [
  { key: "language", label: "语言", emptyLabel: "全部语言", minValues: 1 },
  { key: "locale", label: "地区", emptyLabel: "全部地区", minValues: 1, grouped: true },
  { key: "gender", label: "性别", emptyLabel: "全部性别", minValues: 1 },
  { key: "voiceType", label: "类型", emptyLabel: "全部类型", minValues: 2 },
  { key: "status", label: "状态", emptyLabel: "全部状态", minValues: 2 },
  { key: "style", label: "风格", emptyLabel: "全部风格", minValues: 1 },
  { key: "scenario", label: "场景", emptyLabel: "全部场景", minValues: 1 },
  { key: "personality", label: "性格", emptyLabel: "全部性格", minValues: 1 },
  { key: "role", label: "角色", emptyLabel: "全部角色", minValues: 1 },
  { key: "sampleRate", label: "采样率", emptyLabel: "全部采样率", minValues: 2 },
];

const LOCALE_OVERRIDES: Record<string, string> = {
  "zh-CN": "中文（普通话，简体）",
  "zh-CN-henan": "中文（河南话）",
  "zh-CN-liaoning": "中文（辽宁话）",
  "zh-CN-shaanxi": "中文（陕西话）",
  "zh-CN-shandong": "中文（山东话）",
  "zh-CN-sichuan": "中文（四川话）",
  "zh-HK": "中文（粤语，香港）",
  "zh-TW": "中文（台湾普通话）",
  "wuu-CN": "中文（吴语）",
  "yue-CN": "中文（粤语，简体）",
};

const GENDERS: Record<string, string> = { female: "女声", male: "男声", neutral: "中性" };
const VOICE_TYPES: Record<string, string> = { neural: "神经网络", standard: "标准" };
const STATUSES: Record<string, string> = { ga: "正式版", preview: "预览版", deprecated: "已弃用" };
const STYLES: Record<string, string> = {
  advertisementupbeat: "活泼广告",
  affectionate: "亲切",
  angry: "生气",
  assistant: "助理",
  calm: "平静",
  chat: "聊天",
  cheerful: "愉快",
  conversation: "对话",
  customerservice: "客服",
  depressed: "沮丧",
  disgruntled: "不满",
  documentarynarration: "纪录片旁白",
  embarrassed: "尴尬",
  empathetic: "共情",
  envious: "羡慕",
  excited: "兴奋",
  fearful: "害怕",
  friendly: "友好",
  gentle: "温柔",
  hopeful: "充满希望",
  livecommercial: "现场广告",
  lyrical: "抒情",
  narration: "旁白",
  narrationprofessional: "专业旁白",
  narrationrelaxed: "轻松旁白",
  newscast: "新闻播报",
  newscastcasual: "轻松新闻",
  newscastformal: "正式新闻",
  poetryreading: "诗歌朗诵",
  sad: "悲伤",
  serious: "严肃",
  shouting: "喊叫",
  sorry: "抱歉",
  sportscommentary: "体育解说",
  sportscommentaryexcited: "激动解说",
  storytelling: "讲故事",
  terrified: "恐惧",
  unfriendly: "冷淡",
  whispering: "耳语",
};
const SCENARIOS: Record<string, string> = {
  advertisement: "广告",
  assistant: "助理",
  audiobook: "有声书",
  cartoon: "卡通",
  character: "角色扮演",
  chat: "聊天",
  commentary: "解说",
  commercial: "商业",
  conversation: "对话",
  customerservice: "客服",
  dialect: "方言",
  documentary: "纪录片",
  education: "教育",
  entertainment: "娱乐",
  gaming: "游戏",
  general: "通用",
  ivr: "语音导航",
  live: "直播",
  meditation: "冥想",
  narration: "旁白",
  news: "新闻",
  novel: "小说",
  podcast: "播客",
  sports: "体育",
  story: "故事",
  storytelling: "讲故事",
};
const PERSONALITIES: Record<string, string> = {
  animated: "生动",
  approachable: "亲和",
  articulate: "口齿清楚",
  authentic: "真实",
  authoritative: "权威",
  bold: "大胆",
  bright: "明快",
  calm: "平静",
  candid: "坦率",
  caring: "关怀",
  casual: "随意",
  charming: "有魅力",
  cheerful: "开朗",
  clear: "清晰",
  comforting: "安慰",
  compassionate: "富有同情",
  confident: "自信",
  considerate: "体贴",
  conversational: "对话感",
  crisp: "干脆",
  curious: "好奇",
  deep: "低沉",
  determined: "坚定",
  direct: "直接",
  elegant: "优雅",
  emotional: "情绪丰富",
  empathetic: "共情",
  energetic: "有活力",
  engaging: "有感染力",
  expressive: "富有表现力",
  formal: "正式",
  friendly: "友好",
  gentle: "温和",
  graceful: "优美",
  honest: "诚实",
  hopeful: "充满希望",
  humorous: "幽默",
  kind: "友善",
  knowledgeable: "博学",
  lighthearted: "轻松",
  lively: "活泼",
  mature: "成熟",
  natural: "自然",
  optimistic: "乐观",
  passionate: "热情",
  patient: "耐心",
  persuasive: "有说服力",
  playful: "俏皮",
  pleasant: "愉悦",
  polite: "礼貌",
  positive: "积极",
  powerful: "有力",
  professional: "专业",
  quiet: "安静",
  rational: "理性",
  reassuring: "令人安心",
  refined: "精致",
  relatable: "亲近",
  reserved: "内敛",
  serious: "严肃",
  shy: "害羞",
  sincere: "真诚",
  smooth: "流畅",
  soft: "柔和",
  soothing: "舒缓",
  sophisticated: "成熟精致",
  spirited: "有精神",
  strong: "强劲",
  supportive: "支持",
  thoughtful: "周到",
  trustworthy: "可信",
  upbeat: "乐观",
  vibrant: "鲜明",
  warm: "温暖",
  wise: "睿智",
  witty: "机智",
  youthful: "年轻",
};
const ROLES: Record<string, string> = {
  boy: "男孩",
  girl: "女孩",
  narrator: "旁白",
  olderadultfemale: "中年女性",
  olderadultmale: "中年男性",
  seniorfemale: "老年女性",
  seniormale: "老年男性",
  youngadultfemale: "青年女性",
  youngadultmale: "青年男性",
};
const SCRIPT_LABELS: Record<string, string> = { Hans: "简体", Hant: "繁体", Latn: "拉丁字母", Cyrl: "西里尔字母" };

export const emptyVoiceFilters: VoiceFilterState = Object.freeze({
  query: "",
  language: "",
  locale: "",
  gender: "",
  voiceType: "",
  status: "",
  style: "",
  scenario: "",
  personality: "",
  role: "",
  sampleRate: "",
});

const searchText = new WeakMap<VoiceItem, string>();

function createDisplay(type: Intl.DisplayNamesOptions["type"]): Intl.DisplayNames | null {
  try {
    return new Intl.DisplayNames(["zh-CN"], { type });
  } catch {
    return null;
  }
}

const languageDisplay = createDisplay("language");
const regionDisplay = createDisplay("region");
const scriptDisplay = createDisplay("script");

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0).map(item => item.trim());
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function canonical(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function mappedLabel(value: string, labels: Record<string, string>): string {
  return labels[canonical(value)] || value.replace(/[_-]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
}

export function languageCode(locale: string): string {
  const trimmed = locale.trim();
  if (!trimmed) return "";
  try {
    return new Intl.Locale(trimmed).language.toLowerCase();
  } catch {
    return trimmed.split("-")[0].toLowerCase();
  }
}

export function languageLabel(code: string): string {
  if (!code) return "未标明语言";
  return languageDisplay?.of(code) || code;
}

export function localeShortLabel(locale: string): string {
  const override = LOCALE_OVERRIDES[locale];
  if (override) return override;
  try {
    const parsed = new Intl.Locale(locale);
    const language = languageDisplay?.of(parsed.language) || parsed.language;
    const region = parsed.region ? regionDisplay?.of(parsed.region) || parsed.region : "";
    const script = parsed.script ? SCRIPT_LABELS[parsed.script] || scriptDisplay?.of(parsed.script) || parsed.script : "";
    const place = [region, script].filter(Boolean).join("，");
    return place ? `${language}（${place}）` : language;
  } catch {
    return locale;
  }
}

export function localeLabel(locale: string): string {
  if (!locale) return "未标明地区";
  return `${localeShortLabel(locale)} · ${locale}`;
}

export function genderLabel(value: string): string {
  return value ? GENDERS[value.trim().toLowerCase()] || value : "";
}

export function voiceTypeLabel(value: string): string {
  return value ? VOICE_TYPES[value.trim().toLowerCase()] || value : "";
}

export function statusLabel(value: string): string {
  return value ? STATUSES[value.trim().toLowerCase()] || value : "";
}

export function styleLabel(value: string): string {
  return value ? mappedLabel(value, STYLES) : "";
}

export function scenarioLabel(value: string): string {
  return value ? mappedLabel(value, SCENARIOS) : "";
}

export function personalityLabel(value: string): string {
  return value ? mappedLabel(value, PERSONALITIES) : "";
}

export function roleLabel(value: string): string {
  return value ? mappedLabel(value, ROLES) : "";
}

export function sampleRateLabel(value: string): string {
  const rate = Number(value);
  if (!Number.isFinite(rate) || rate <= 0) return value;
  return rate % 1000 === 0 ? `${rate / 1000} kHz` : `${rate} Hz`;
}

export function normalizeVoiceItem(value: VoiceItemInput): VoiceItem {
  return {
    short_name: text(value.short_name),
    locale: text(value.locale),
    locale_name: text(value.locale_name),
    local_name: text(value.local_name),
    display_name: text(value.display_name),
    gender: text(value.gender),
    voice_type: text(value.voice_type),
    status: text(value.status),
    sample_rate_hertz: text(value.sample_rate_hertz),
    styles: stringList(value.styles),
    roles: stringList(value.roles),
    secondary_locales: stringList(value.secondary_locales),
    scenarios: stringList(value.scenarios),
    personalities: stringList(value.personalities),
  };
}

export function voiceSummary(voice: VoiceItem): string {
  return [
    voice.locale ? `${localeShortLabel(voice.locale)} · ${voice.locale}` : "",
    genderLabel(voice.gender),
    voiceTypeLabel(voice.voice_type),
    statusLabel(voice.status),
    voice.sample_rate_hertz ? sampleRateLabel(voice.sample_rate_hertz) : "",
  ].filter(Boolean).join(" · ");
}

export function voiceTags(voice: VoiceItem): string[] {
  return unique([
    ...voice.personalities.map(personalityLabel),
    ...voice.scenarios.map(scenarioLabel),
    ...voice.styles.map(styleLabel),
    ...voice.roles.map(roleLabel),
  ]);
}

export function avatarText(gender: string): string {
  const normalized = gender.trim().toLowerCase();
  if (normalized === "female") return "女";
  if (normalized === "male") return "男";
  return "声";
}

function localesOf(voice: VoiceItem): string[] {
  return unique([voice.locale, ...voice.secondary_locales]);
}

function dimensionValues(voice: VoiceItem, key: VoiceFilterKey, language: string): string[] {
  if (key === "language") return unique(localesOf(voice).map(languageCode));
  if (key === "locale") return localesOf(voice).filter(locale => !language || languageCode(locale) === language);
  if (key === "gender") return voice.gender ? [voice.gender] : [];
  if (key === "voiceType") return voice.voice_type ? [voice.voice_type] : [];
  if (key === "status") return voice.status ? [voice.status] : [];
  if (key === "style") return unique(voice.styles);
  if (key === "scenario") return unique(voice.scenarios);
  if (key === "personality") return unique(voice.personalities);
  if (key === "role") return unique(voice.roles);
  return voice.sample_rate_hertz ? [voice.sample_rate_hertz] : [];
}

function optionLabel(key: VoiceFilterKey, value: string): string {
  if (key === "language") return languageLabel(value);
  if (key === "locale") return localeLabel(value);
  if (key === "gender") return genderLabel(value);
  if (key === "voiceType") return voiceTypeLabel(value);
  if (key === "status") return statusLabel(value);
  if (key === "style") return styleLabel(value);
  if (key === "scenario") return scenarioLabel(value);
  if (key === "personality") return personalityLabel(value);
  if (key === "role") return roleLabel(value);
  return sampleRateLabel(value);
}

function haystack(voice: VoiceItem): string {
  const cached = searchText.get(voice);
  if (cached) return cached;
  const textValue = [
    voice.short_name,
    voice.locale,
    voice.locale_name,
    voice.local_name,
    voice.display_name,
    voice.gender,
    genderLabel(voice.gender),
    voice.voice_type,
    voiceTypeLabel(voice.voice_type),
    voice.status,
    statusLabel(voice.status),
    voice.sample_rate_hertz,
    sampleRateLabel(voice.sample_rate_hertz),
    ...localesOf(voice).flatMap(locale => [locale, localeLabel(locale), languageLabel(languageCode(locale))]),
    ...voice.styles.flatMap(style => [style, styleLabel(style)]),
    ...voice.scenarios.flatMap(scenario => [scenario, scenarioLabel(scenario)]),
    ...voice.personalities.flatMap(personality => [personality, personalityLabel(personality)]),
    ...voice.roles.flatMap(role => [role, roleLabel(role)]),
  ].join(" ").toLowerCase();
  searchText.set(voice, textValue);
  return textValue;
}

function queryMatches(voice: VoiceItem, query: string): boolean {
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const textValue = haystack(voice);
  return tokens.every(token => textValue.includes(token));
}

function voiceMatches(voice: VoiceItem, filters: VoiceFilterState, ignore?: VoiceFilterKey): boolean {
  if (!queryMatches(voice, filters.query)) return false;
  return FILTERS.every(spec => {
    if (spec.key === ignore) return true;
    const selected = filters[spec.key];
    return !selected || dimensionValues(voice, spec.key, filters.language).includes(selected);
  });
}

function compareOptions(key: VoiceFilterKey, left: VoiceFilterOption, right: VoiceFilterOption): number {
  if (key === "language") {
    if (left.value === "zh") return -1;
    if (right.value === "zh") return 1;
  }
  return right.count - left.count || left.label.localeCompare(right.label, "zh-CN");
}

function groupLocales(options: VoiceFilterOption[]): VoiceFilterGroup[] {
  const groups = new Map<string, VoiceFilterGroup>();
  for (const option of options) {
    const id = languageCode(option.value) || "unknown";
    const group = groups.get(id) ?? { id, label: languageLabel(id), options: [] };
    group.options.push(option);
    groups.set(id, group);
  }
  return [...groups.values()].sort((left, right) => {
    if (left.id === "zh") return -1;
    if (right.id === "zh") return 1;
    const leftCount = left.options.reduce((total, option) => total + option.count, 0);
    const rightCount = right.options.reduce((total, option) => total + option.count, 0);
    return rightCount - leftCount || left.label.localeCompare(right.label, "zh-CN");
  });
}

export function filterVoices(voices: VoiceItem[], filters: VoiceFilterState): VoiceItem[] {
  return voices.filter(voice => voiceMatches(voice, filters));
}

export function voiceFilterDefinitions(voices: VoiceItem[], filters: VoiceFilterState): VoiceFilterDefinition[] {
  return FILTERS.flatMap(spec => {
    const available = new Set(voices.flatMap(voice => dimensionValues(voice, spec.key, "")));
    if (available.size < spec.minValues) return [];
    const counts = new Map<string, number>();
    for (const voice of voices) {
      if (!voiceMatches(voice, filters, spec.key)) continue;
      for (const value of dimensionValues(voice, spec.key, filters.language)) {
        counts.set(value, (counts.get(value) ?? 0) + 1);
      }
    }
    const selected = filters[spec.key];
    if (selected && !counts.has(selected)) counts.set(selected, 0);
    const options = [...counts.entries()]
      .map(([value, count]) => ({ value, label: optionLabel(spec.key, value), count }))
      .sort((left, right) => compareOptions(spec.key, left, right));
    return [{
      key: spec.key,
      label: spec.label,
      emptyLabel: spec.emptyLabel,
      options,
      groups: spec.grouped ? groupLocales(options) : undefined,
    }];
  });
}
