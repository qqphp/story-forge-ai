import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "@/app/lib/api";
import { Pagination } from "@/app/shared/ui/Pagination";
import {
  avatarText,
  emptyVoiceFilters,
  filterVoices,
  languageCode,
  voiceFilterDefinitions,
  voiceSummary,
  voiceTags,
  type VoiceFilterKey,
  type VoiceFilterState,
  type VoiceItem,
} from "@/app/features/voices/voice-catalog";

type DownloadStatus = { status: string; total: number; completed: number; failed: number };

type VoiceCenterProps = {
  voices: VoiceItem[];
  connected: boolean;
  download: DownloadStatus;
  onDownload: () => void;
};

export function VoiceCenter({ voices, connected, download, onDownload }: VoiceCenterProps) {
  const [filters, setFilters] = useState<VoiceFilterState>(emptyVoiceFilters);
  const [page, setPage] = useState(1);
  const [previewing, setPreviewing] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewToken = useRef(0);
  const voicePageSize = 8;
  const definitions = useMemo(() => voiceFilterDefinitions(voices, filters), [voices, filters]);
  const filtered = useMemo(() => filterVoices(voices, filters), [voices, filters]);
  const pages = Math.max(1, Math.ceil(filtered.length / voicePageSize));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * voicePageSize, currentPage * voicePageSize);
  const filtersActive = Object.values(filters).some(Boolean);
  const downloadActive = download.status === "queued" || download.status === "running";

  useEffect(() => () => { audioRef.current?.pause(); }, []);

  const setFilter = (key: VoiceFilterKey, value: string) => {
    setFilters(current => {
      const next = { ...current, [key]: value };
      if (key === "language" && next.locale && languageCode(next.locale) !== value && value) next.locale = "";
      return next;
    });
    setPage(1);
  };

  const resetFilters = () => {
    setFilters({ ...emptyVoiceFilters });
    setPage(1);
  };

  const preview = async (item: VoiceItem) => {
    const token = ++previewToken.current;
    audioRef.current?.pause();
    setPreviewing(item.short_name);
    try {
      const audio = new Audio(`${API_BASE}/api/voices/${encodeURIComponent(item.short_name)}/preview?locale=${encodeURIComponent(item.locale)}`);
      audioRef.current = audio;
      await audio.play();
      if (previewToken.current !== token) {
        audio.pause();
        return;
      }
      const finish = () => { if (previewToken.current === token) setPreviewing(""); };
      audio.onended = finish;
      audio.onerror = finish;
    } catch {
      if (previewToken.current === token) setPreviewing("");
    }
  };

  return <section className="voice-center">
    <div className="panel-toolbar">
      <div>
        <h3>音色中心</h3>
        <p>微软返回的全部语言音色，共 {voices.length} 个，当前匹配 {filtered.length} 个</p>
      </div>
      <button type="button" className="secondary download-button" disabled={!connected || downloadActive} onClick={onDownload}>⇩ {downloadActive ? "正在离线下载" : "离线下载全部"}</button>
    </div>
    <label className="panel-search">
      <span aria-hidden="true">⌕</span>
      <input aria-label="搜索音色" value={filters.query} onChange={event => { setFilters(current => ({ ...current, query: event.target.value })); setPage(1); }} placeholder="搜索音色、语言、地区或性别" />
    </label>
    {definitions.length > 0 && <div className="voice-filter-panel">
      <div className="voice-filter-head">
        <div>
          <b>筛选条件</b>
          <small>筛选项随本次返回的音色信息变化</small>
        </div>
        <button type="button" className="voice-filter-reset" disabled={!filtersActive} onClick={resetFilters}>重置筛选</button>
      </div>
      <div className="voice-filters">
        {definitions.map(definition => <label key={definition.key}>
          {definition.label}
          <select aria-label={`按${definition.label}筛选`} className={filters[definition.key] ? "active" : ""} value={filters[definition.key]} onChange={event => setFilter(definition.key, event.target.value)}>
            <option value="">{definition.emptyLabel}</option>
            {definition.groups?.length ? definition.groups.map(group => <optgroup key={group.id} label={group.label}>{group.options.map(option => <option key={option.value} value={option.value}>{option.label}（{option.count}）</option>)}</optgroup>) : definition.options.map(option => <option key={option.value} value={option.value}>{option.label}（{option.count}）</option>)}
          </select>
        </label>)}
      </div>
      <p className="voice-filter-summary">当前返回的音色可按{definitions.map(definition => definition.label).join("、")}筛选。</p>
    </div>}
    {download.status !== "idle" && <div className="download-progress"><span><i style={{ width: `${download.total ? Math.round((download.completed + download.failed) / download.total * 100) : 0}%` }} /></span><small>{download.status === "completed" ? "下载完成" : "下载进度"}：{download.completed} / {download.total}{download.failed ? `，失败 ${download.failed}` : ""} · 保存到 data/voice_samples</small></div>}
    <div className="voice-card-grid">
      {visible.map(voice => {
        const tags = voiceTags(voice);
        const summary = voiceSummary(voice);
        return <article className="voice-card" key={voice.short_name}>
          <div className="voice-avatar">{avatarText(voice.gender)}</div>
          <div>
            <b>{voice.local_name || voice.display_name || voice.short_name}</b>
            <p title={voice.short_name}>{voice.short_name}</p>
            <small title={summary}>{summary}</small>
            {tags.length > 0 && <div className="voice-tags" title={tags.join("、")}>{tags.slice(0, 3).map(tag => <em key={tag}>{tag}</em>)}{tags.length > 3 && <em className="more">+{tags.length - 3}</em>}</div>}
          </div>
          <button type="button" onClick={() => preview(voice)} disabled={previewing === voice.short_name}>{previewing === voice.short_name ? "加载中" : "▶ 试听"}</button>
        </article>;
      })}
      {!voices.length && <div className="panel-empty">暂无音色，请先配置微软语音服务</div>}
      {voices.length > 0 && !visible.length && <div className="panel-empty">没有匹配的音色</div>}
    </div>
    <Pagination page={currentPage} pages={pages} total={filtered.length} onChange={setPage} />
    <p className="sample-copy">试听会根据音色所属国家或地区，自动翻译并生成对应语言。</p>
  </section>;
}
