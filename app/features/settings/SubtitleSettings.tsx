import { useEffect, useState } from "react";
import { API_BASE } from "@/app/lib/api";
import type { AppSettings, SubtitleStyle } from "@/app/features/shared/types";
import { defaultSubtitleStyle } from "./defaults";
import "./subtitle-settings.css";

type Props = { form: AppSettings; onChange: (form: AppSettings) => void; connected: boolean };
type FontOption = { id: SubtitleStyle["font_id"]; name: string; family: string; category: string; license: string; source: string };

export function SubtitleSettings({ form, onChange, connected }: Props) {
  const style = form.subtitle_style || defaultSubtitleStyle();
  const [orientation, setOrientation] = useState<"landscape" | "portrait">(form.video_orientation);
  const [fonts, setFonts] = useState<FontOption[]>([]);
  const [preview, setPreview] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const set = <K extends keyof SubtitleStyle>(key: K, value: SubtitleStyle[K]) => onChange({ ...form, subtitle_style: { ...style, [key]: value } });
  const serialized = JSON.stringify(style);
  const labelImage = form.record_label_image_id;
  const overlayEnabled = form.background_overlay_enabled;
  const overlayOpacity = form.background_overlay_opacity;
  const blurEnabled = form.background_blur_enabled;
  const blurStrength = form.background_blur_strength;
  useEffect(() => {
    if (!connected) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/api/subtitle-fonts`, { signal: controller.signal }).then(r => r.json()).then(data => setFonts(data.items)).catch(() => {});
    return () => controller.abort();
  }, [connected]);
  useEffect(() => {
    if (!connected) return;
    const controller = new AbortController();
    let objectUrl = "";
    const timer = window.setTimeout(async () => {
      setLoading(true); setError("");
      try {
        const response = await fetch(`${API_BASE}/api/subtitle-preview`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ orientation, record_label_image_id:labelImage, background_overlay_enabled:overlayEnabled, background_overlay_opacity:overlayOpacity, background_blur_enabled:blurEnabled, background_blur_strength:blurStrength, style: JSON.parse(serialized) }),
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
        });
        if (!response.ok) { const data = await response.json(); throw new Error(typeof data.detail === "string" ? data.detail : "预览生成失败"); }
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob); setPreview(objectUrl);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "字幕预览失败，请重试");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }, 450);
    return () => { window.clearTimeout(timer); controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [connected, orientation, serialized, labelImage, overlayEnabled, overlayOpacity, blurEnabled, blurStrength]);
  return <section className="subtitle-settings settings-pane">
    <div className="subtitle-style-controls">
      <label className={`subtitle-burn-option${form.burn_subtitles ? " selected" : ""}`} htmlFor="subtitle-burn-enabled"><input id="subtitle-burn-enabled" type="checkbox" checked={form.burn_subtitles} onChange={e => onChange({ ...form, burn_subtitles: e.target.checked })}/><span><b>烧录字幕</b><small>将字幕直接渲染到生成的视频画面中</small></span><i>{form.burn_subtitles ? "已开启" : "已关闭"}</i></label>
      <p className="subtitle-settings-intro">以下样式用于新制作及重新合成的视频，字幕文件统一去除句读标点，保留数字和英文词内符号。</p>
      <div className="subtitle-section-heading"><div><b>字幕样式</b><small>调整字体、位置与背景表现</small></div><span>最多显示两行</span></div>
      <div className="subtitle-control-grid">
        <label>字体<select value={style.font_id} onChange={e => set("font_id", e.target.value as SubtitleStyle["font_id"])}>{fonts.length ? [...new Set(fonts.map(f=>f.category))].map(category=><optgroup key={category} label={category}>{fonts.filter(f=>f.category===category).map(font=><option key={font.id} value={font.id}>{font.name} · {font.family}</option>)}</optgroup>) : <option value={style.font_id}>正在加载字体…</option>}</select></label>
        <label>字号（基准短边 1080px）<input type="number" min="24" max="96" value={style.font_size} onChange={e => set("font_size", Math.min(96, Math.max(24, Number(e.target.value))))}/></label>
        <div className="subtitle-color-field"><span>文字颜色</span><div><input aria-label="文字颜色" type="color" value={style.text_color} onChange={e => set("text_color", e.target.value)}/><label className="subtitle-bold"><input type="checkbox" checked={style.bold} onChange={e => set("bold", e.target.checked)}/>粗体</label></div></div>
        <label>显示方式<select value={style.mode} onChange={e => set("mode", e.target.value as SubtitleStyle["mode"])}><option value="box">背景框</option><option value="outline">文字描边</option></select></label>
        <label>字幕区内位置<select value={style.position} onChange={e => set("position", e.target.value as SubtitleStyle["position"])}><option value="top">顶部居中</option><option value="center">画面居中</option><option value="bottom">底部居中</option></select></label>
        {style.mode === "box" ? <><label>背景颜色<input type="color" value={style.background_color} onChange={e => set("background_color", e.target.value)}/></label><label>背景不透明度 · {Math.round(style.background_opacity * 100)}%<input type="range" min="0" max="1" step="0.05" value={style.background_opacity} onChange={e => set("background_opacity", Number(e.target.value))}/></label></> : <><label>描边颜色<input type="color" value={style.outline_color} onChange={e => set("outline_color", e.target.value)}/></label><label>描边粗细 · {style.outline_width}px<input type="range" min="0" max="8" step="1" value={style.outline_width} onChange={e => set("outline_width", Number(e.target.value))}/></label></>}
        <label>左右边距 · {style.margin_horizontal}px<input type="range" min="0" max="200" value={style.margin_horizontal} onChange={e => set("margin_horizontal", Number(e.target.value))}/></label>
        <label>垂直边距 · {style.margin_vertical === null ? "自动" : `${style.margin_vertical}px`}<input type="range" min="0" max="300" value={style.margin_vertical ?? (orientation === "portrait" ? 154 : 65)} onChange={e => set("margin_vertical", Number(e.target.value))}/></label>
      </div>
      <div className="subtitle-settings-footer"><button type="button" className="secondary" onClick={() => onChange({ ...form, subtitle_style: defaultSubtitleStyle() })}>恢复默认样式</button><p>内置字体均附开源授权，可离线商用。长句会自动分段；Inter 遇到中文时会回退到内置中文字体。</p></div>
    </div>
    <div className="subtitle-preview-panel" aria-busy={loading}>
      <div className="subtitle-preview-toolbar"><b>烧录效果预览</b><select aria-label="预览画面比例" value={orientation} onChange={e => setOrientation(e.target.value as typeof orientation)}><option value="portrait">竖版 9:16</option><option value="landscape">横版 16:9</option></select></div>
      <div className={`subtitle-preview-frame ${orientation}`}>{preview && <img src={preview} alt="使用当前字幕样式的播放器整体效果"/>}{!preview && <span>{connected ? "正在生成预览…" : "连接服务后显示预览"}</span>}</div>
      <p aria-live="polite">{loading ? "正在更新预览…" : "由 FFmpeg 渲染，与视频使用相同字体和排版。"}</p>
      {error && <p role="alert" className="settings-error">{error}</p>}
    </div>
  </section>;
}
