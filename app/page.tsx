/* eslint-disable jsx-a11y/media-has-caption, jsx-a11y/label-has-associated-control */

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE as API } from "@/app/lib/api";
import type { AppSettings, Asset, BackgroundMusic, PromptTemplate, VoiceItem, Workflow, WorkspacePage } from "@/app/features/shared/types";
import { Pagination } from "@/app/shared/ui/Pagination";
import { Status, TaskCard, TaskList } from "@/app/features/workflows/WorkflowList";
import { RequestLogsPage } from "@/app/features/request-logs/RequestLogsPage";
import { coverSizeGroups } from "@/app/features/prompts/cover-size-groups";
import { FormatSelect, ModelSelect, SpeechRateControl, VoiceControl } from "@/app/features/settings/SelectionControls";
import { defaultSettings, speechFormats } from "@/app/features/settings/defaults";
import { VoiceCenter } from "@/app/features/voices/VoiceCenter";
import { normalizeVoiceItem } from "@/app/features/voices/voice-catalog";
import { useMusicSelection } from "@/app/features/workflows/useMusicSelection";
import { SubtitleSettings } from "@/app/features/settings/SubtitleSettings";
const stages = ["理解书籍", "撰写文案", "自然化优化", "生成配音", "生成字幕", "生成标签和话题", "创作封面", "合成视频"];

const seedTasks: Workflow[] = [
  { id: "sample-1", book_title: "悉达多", author: "赫尔曼·黑塞", edition: "", status: "completed", step: 7, progress: 100, created_at: 1787364000, description: "一个关于寻找、经历与自我抵达的故事。", tags: ["文学","成长"], topics: ["读书","好书推荐"], original_drafts: [], polished_drafts: [], covers: [], audio: [], videos: [] },
  { id: "sample-2", book_title: "局外人", author: "阿尔贝·加缪", edition: "上海译文版", status: "running", step: 4, progress: 68, created_at: 1787369400, description: "", original_drafts: [], polished_drafts: [], covers: [], audio: [], videos: [] },
];

export default function Home() {
  const [tasks, setTasks] = useState<Workflow[]>(seedTasks);
  const [selected, setSelected] = useState<Workflow | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [activePage,setActivePage]=useState<WorkspacePage>("workspace");
  const [toast, setToast] = useState("");
  const [connected, setConnected] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [workView,setWorkView]=useState<"cards"|"list">("cards");
  const [checkedTaskIds,setCheckedTaskIds]=useState<string[]>([]);

  async function loadTasks() {
    try {
      const res = await fetch(`${API}/api/workflows`, {signal: AbortSignal.timeout(10000)});
      if (!res.ok) throw new Error();
      const data = await res.json();
      setConnected(true);
      setTasks(data.length ? data : []);
      setCheckedTaskIds(ids=>ids.filter(id=>data.some((task:Workflow)=>task.id===id)));
      if (selected) {
        const fresh = data.find((t: Workflow) => t.id === selected.id);
        if (fresh) setSelected(fresh);
      }
    } catch { setConnected(false); }
  }

  useEffect(() => {
    const initial = window.setTimeout(loadTasks, 0);
    const timer = window.setInterval(loadTasks, 2500);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id]);

  const shown = useMemo(() => tasks.filter(t => {
    const hit = `${t.book_title}${t.author}`.toLowerCase().includes(query.toLowerCase());
    return hit && (filter === "all" || t.status === filter);
  }), [tasks, query, filter]);
  const running = tasks.filter(t => t.status === "running" || t.status === "queued").length;
  const completed = tasks.filter(t => t.status === "completed").length;
  const allShownChecked=shown.length>0&&shown.every(task=>checkedTaskIds.includes(task.id));

  async function deleteCheckedTasks() {
    if(!checkedTaskIds.length||!window.confirm(`确定删除选中的 ${checkedTaskIds.length} 个作品及其全部产物吗？`))return;
    const ids=[...checkedTaskIds];
    if(!connected){setTasks(items=>items.filter(task=>!ids.includes(task.id)));setCheckedTaskIds([]);setToast(`已删除 ${ids.length} 个作品`);return;}
    const results=await Promise.all(ids.map(id=>fetch(`${API}/api/workflows/${id}`,{method:"DELETE"})));
    if(results.some(response=>!response.ok)){setToast("部分作品删除失败，请重试");await loadTasks();return;}
    setCheckedTaskIds([]);setToast(`已删除 ${ids.length} 个作品及相关产物`);await loadTasks();
  }

  async function createWorkflow(payload: Record<string, unknown>) {
    if (!connected) {
      const task: Workflow = { id: crypto.randomUUID().slice(0, 8), book_title: String(payload.book_title), author: String(payload.author || ""), edition: String(payload.edition || ""), status: "running", step: 1, progress: 12, created_at: Math.floor(Date.now()/1000) };
      setTasks(v => [task, ...v]); setShowCreate(false); setToast("演示任务已开始，启动 Python 服务后可生成真实文件");
      return;
    }
    const res = await fetch(`${API}/api/workflows`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error("创建失败");
    setShowCreate(false); setToast("制作任务已加入队列"); loadTasks();
  }

  async function createBatch(payload: Record<string, unknown>) {
    const books = payload.books as Array<{book_title:string;author:string;edition:string}>;
    if (!connected) {
      const demos = books.map(book=>({id:crypto.randomUUID().slice(0,8),...book,status:"running",step:1,progress:12,created_at:Math.floor(Date.now()/1000)} as Workflow));
      setTasks(v=>[...demos,...v]);setShowBatch(false);setToast(`已创建 ${demos.length} 个演示任务`);return;
    }
    const res=await fetch(`${API}/api/workflows/batch`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if(!res.ok)throw new Error("批量创建失败");const result=await res.json();setShowBatch(false);setToast(`已加入 ${result.count} 个制作任务`);loadTasks();
  }

  return (
    <main className="app-shell">
      <aside className="side-nav">
        <button className="brand" onClick={()=>{setActivePage("workspace");setSelected(null)}} aria-label="返回工作台"><span className="brand-mark">砚</span><span><b>砚界</b><small>STORYFORGE AI</small></span></button>
        <nav aria-label="主导航">
          <button className={activePage==="workspace"?"active":""} onClick={()=>setActivePage("workspace")}><span>册</span>创作工作台</button>
          <button className={activePage==="prompts"?"active":""} onClick={()=>setActivePage("prompts")}><span>✦</span>提示词库</button>
          <button className={activePage==="models"?"active":""} onClick={()=>setActivePage("models")}><span>AI</span>模型配置</button>
          <button className={activePage==="voice"?"active":""} onClick={()=>setActivePage("voice")}><span>声</span>语音设置</button>
          <button className={activePage==="video"?"active":""} onClick={()=>setActivePage("video")}><span>影</span>视频设置</button>
          <button className={activePage==="logs"?"active":""} onClick={()=>setActivePage("logs")}><span>录</span>请求日志</button>
        </nav>
        <span className={`side-connection ${connected?"online":""}`}><i/>{connected?"服务已连接":"服务未连接"}</span>
      </aside>
      <section className="workspace-main">
      <header className="topbar">
        <div className="page-heading"><b>{{workspace:"创作工作台",prompts:"提示词库",models:"模型配置",voice:"语音设置",video:"视频设置",logs:"请求日志"}[activePage]}</b><small>创作与生成配置中心</small></div>
        <div className="top-actions">
          <span className={`connection ${connected ? "online" : ""}`}><i />{connected ? "服务已连接" : "演示模式"}</span>
        </div>
      </header>

      {activePage==="workspace"&&<section className="content">
        <div className="hero-row">
          <div><p className="eyebrow">创作工作台</p><h1>把一本书，讲给更多人听。</h1><p className="subtitle">从书籍信息到文案、配音、封面与视频，一次输入，自动完成。</p></div>
          <div className="hero-actions"><button className="primary" onClick={() => setShowCreate(true)}><span>＋</span> 开始新制作</button><button className="primary batch-launch" onClick={()=>setShowBatch(true)}><span aria-hidden="true">▦</span> 批量制作</button></div>
        </div>

        <div className="metrics">
          <article><span className="metric-icon ink">册</span><div><strong>{tasks.length}</strong><small>全部作品</small></div></article>
          <article><span className="metric-icon amber">酿</span><div><strong>{running}</strong><small>正在制作</small></div><em>可并行处理</em></article>
          <article><span className="metric-icon green">成</span><div><strong>{completed}</strong><small>制作完成</small></div></article>
        </div>

        <div className="section-head">
          <div><h2>我的作品</h2><p>每一本书，都是一段正在发生的故事</p></div>
          <div className="tools"><label className="search"><span>⌕</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索书名或作者" /></label>
            <select value={filter} onChange={e => setFilter(e.target.value)} aria-label="筛选任务"><option value="all">全部状态</option><option value="running">制作中</option><option value="completed">已完成</option><option value="failed">失败</option></select>
            <div className="view-switch" aria-label="作品显示方式"><button className={workView==="cards"?"active":""} onClick={()=>setWorkView("cards")} title="卡片视图">▦</button><button className={workView==="list"?"active":""} onClick={()=>setWorkView("list")} title="列表视图">☷</button></div>
          </div>
        </div>

        {shown.length ? workView==="cards"?<div className="task-grid">{shown.map(task => <TaskCard key={task.id} task={task} stages={stages} onOpen={() => setSelected(task)} />)}</div>:<TaskList tasks={shown} checkedIds={checkedTaskIds} allChecked={allShownChecked} onToggleAll={()=>setCheckedTaskIds(allShownChecked?checkedTaskIds.filter(id=>!shown.some(task=>task.id===id)):[...new Set([...checkedTaskIds,...shown.map(task=>task.id)])])} onToggle={id=>setCheckedTaskIds(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id])} onOpen={setSelected} onDelete={deleteCheckedTasks}/>:<div className="empty"><span>册</span><h3>还没有作品</h3><p>从一本打动你的书开始。</p><button className="primary" onClick={() => setShowCreate(true)}>开始新制作</button></div>}
      </section>}
      {activePage==="prompts"&&<section className="config-page"><PromptLibraryDialog connected={connected} onClose={()=>setActivePage("workspace")} onSaved={()=>setToast("提示词库已更新")}/></section>}
      {activePage==="models"&&<section className="config-page"><SettingsDialog connected={connected} onClose={()=>setActivePage("workspace")} onSaved={()=>{setToast("配置已保存");loadTasks()}}/></section>}
      {activePage==="voice"&&<section className="config-page"><VoiceSettingsDialog connected={connected} onClose={()=>setActivePage("workspace")} onSaved={()=>setToast("语音配置已保存")}/></section>}
      {activePage==="video"&&<section className="config-page"><VideoSettingsPage connected={connected} onSaved={()=>setToast("视频配置已保存")}/></section>}
      {activePage==="logs"&&<RequestLogsPage connected={connected} onToast={setToast}/>}

      {showCreate && <CreateDialog connected={connected} onClose={() => setShowCreate(false)} onSubmit={createWorkflow} />}
      {showBatch && <BatchCreateDialog connected={connected} onClose={()=>setShowBatch(false)} onSubmit={createBatch}/>}
      {selected && <DetailPanel key={selected.id} task={selected} onClose={() => setSelected(null)} onRetry={async () => { await fetch(`${API}/api/workflows/${selected.id}/retry`, {method:"POST"}); setToast("已重新开始制作"); }} onDelete={async()=>{const res=await fetch(`${API}/api/workflows/${selected.id}`,{method:"DELETE"});if(!res.ok)throw new Error("删除失败");setSelected(null);setToast("作品及相关产物已删除");await loadTasks();}} onRegenerateVideo={async()=>{if(!connected)throw new Error("请先连接服务后再重新生成视频");const res=await fetch(`${API}/api/workflows/${selected.id}/regenerate-video`,{method:"POST"});if(!res.ok){const data=await res.json().catch(()=>({}));const detail=data.detail;throw new Error(typeof detail==="string"?detail:"重新生成失败，请稍后重试")}setToast("已按当前视频设置开始重新生成");await loadTasks();}} onRegenerateAudio={async(voice)=>{if(!connected)throw new Error("请先连接服务后再重新生成配音");const res=await fetch(`${API}/api/workflows/${selected.id}/regenerate-audio`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({voice})});if(!res.ok){const data=await res.json().catch(()=>({}));const detail=data.detail;throw new Error(typeof detail==="string"?detail:"重新生成配音失败，请稍后重试")}setToast("已开始重新生成配音和字幕");await loadTasks();}} />}
      {toast && <div className="toast" role="status" onAnimationEnd={() => setToast("")}>{toast}</div>}
      </section>
    </main>
  );
}

function CreateDialog({ connected, onClose, onSubmit }: { connected: boolean; onClose: () => void; onSubmit: (data: Record<string, unknown>) => Promise<void> }) {
  const [title, setTitle] = useState(""); const [author, setAuthor] = useState(""); const [edition, setEdition] = useState("");
  const fallback: PromptTemplate[] = [{id:"writing-short-video",kind:"writing",name:"短视频口播",text:"适合 2 分钟短视频口播，有真实阅读感受"},{id:"writing-insight",kind:"writing",name:"反常识洞见",text:"从一个反常识观点切入，避免剧透"},{id:"cover-literary",kind:"cover",name:"文学质感",text:"克制的文学感，竖版构图，无文字"}];
  const [templates, setTemplates] = useState<PromptTemplate[]>(fallback);
  const [selectedIds, setSelectedIds] = useState<string[]>(fallback.map(x=>x.id));
  const [voiceList,setVoiceList]=useState<string[]>(["zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural","zh-CN-XiaoyiNeural"]);
  const [voice,setVoice]=useState("zh-CN-XiaoxiaoNeural"); const [speechRate,setSpeechRate]=useState(0);
  const {music,musicId,setMusicId,musicLoading}=useMusicSelection(connected); const [localCover,setLocalCover]=useState(false); const [musicVolume,setMusicVolume]=useState(0.1); const [fadeIn,setFadeIn]=useState(3); const [fadeOut,setFadeOut]=useState(3);
  const [busy, setBusy] = useState(false);
  useEffect(()=>{if(connected){fetch(`${API}/api/prompts`).then(r=>r.json()).then((items:PromptTemplate[])=>{setTemplates(items);setSelectedIds(items.map(x=>x.id));}).catch(()=>{});fetch(`${API}/api/settings`).then(r=>r.json()).then(settings=>{setVoice(settings.voices?.[0]||"zh-CN-XiaoxiaoNeural");setSpeechRate(settings.speech_rate??0)}).catch(()=>{});fetch(`${API}/api/voices`).then(r=>r.json()).then(data=>setVoiceList(data.voices)).catch(()=>{});}},[connected]);
  const submit = async (e: FormEvent) => { e.preventDefault(); if (!title.trim()) return; setBusy(true); try { await onSubmit({book_title:title.trim(),author:author.trim(),edition:edition.trim(),writing_prompt_ids:templates.filter(x=>x.kind==="writing"&&selectedIds.includes(x.id)).map(x=>x.id),local_cover:localCover,cover_prompt_ids:templates.filter(x=>x.kind==="cover"&&selectedIds.includes(x.id)).map(x=>x.id),voice,speech_rate:speechRate,background_music_id:musicId||null,background_music_volume:musicVolume,background_music_fade_in:fadeIn,background_music_fade_out:fadeOut}); } finally { setBusy(false); } };
  return <div className="modal-backdrop" role="presentation" onMouseDown={e => e.target === e.currentTarget && onClose()}><form className="modal config-modal create-modal" onSubmit={submit}>
    <div className="modal-head"><div><p className="eyebrow">新建工作流</p><h2>从哪一本书开始？</h2></div><button type="button" className="close" onClick={onClose}>×</button></div>
    <div className="form-grid"><label className="wide">书籍名称 <em>必填</em><input required value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：百年孤独" /></label><label>作者 <small>选填</small><input value={author} onChange={e=>setAuthor(e.target.value)} placeholder="加西亚·马尔克斯" /></label><label>版本 <small>选填</small><input value={edition} onChange={e=>setEdition(e.target.value)} placeholder="例如：2017 纪念版" /></label></div>
    <section className="workflow-speech"><div><h3>配音设置</h3><p>默认沿用接口设置，可为本次作品单独调整</p></div><div className="workflow-speech-grid"><VoiceControl label="配音音色" voices={voiceList} value={voice} onChange={setVoice}/><SpeechRateControl value={speechRate} onChange={setSpeechRate}/></div></section>
    <MusicMixControl musicLoading={musicLoading} music={music} musicId={musicId} setMusicId={setMusicId} volume={musicVolume} setVolume={setMusicVolume} fadeIn={fadeIn} setFadeIn={setFadeIn} fadeOut={fadeOut} setFadeOut={setFadeOut}/>
    <TemplatePicker title="分享稿提示词" hint="勾选几个，就生成几篇独立分享稿" kind="writing" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/>
    <fieldset className="cover-prompt-fieldset" disabled={localCover}><TemplatePicker title="封面提示词" hint="勾选几个，就生成几张不同封面" kind="cover" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/></fieldset><label className={`local-cover-option${localCover ? " selected" : ""}`}><input type="checkbox" checked={localCover} onChange={event=>setLocalCover(event.target.checked)}/><span><b>本地生成封面</b><small>随机使用内置模板，生成方形、横版和竖版各一张，自动插入书名与作者，不调用图片模型。</small></span><i>{localCover ? "已启用" : "无需图片模型"}</i></label>
    <div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>取消</button><button className="primary" disabled={busy || musicLoading || !title.trim() || !templates.some(x=>x.kind==="writing"&&selectedIds.includes(x.id))}>{busy ? "正在创建…" : "开始自动制作 →"}</button></div>
  </form></div>;
}

function MusicMixControl({musicLoading,music,musicId,setMusicId,volume,setVolume,fadeIn,setFadeIn,fadeOut,setFadeOut}:{musicLoading:boolean;music:BackgroundMusic[];musicId:string;setMusicId:(id:string)=>void;volume:number;setVolume:(value:number)=>void;fadeIn:number;setFadeIn:(value:number)=>void;fadeOut:number;setFadeOut:(value:number)=>void}) {
  return <section className="workflow-music"><div><h3>背景音乐</h3><p>选填，通过微软 SSML 与配音同时合成</p></div><label>选择背景音乐<select disabled={musicLoading} value={musicId} onChange={e=>setMusicId(e.target.value)}><option value="">不使用背景音乐</option>{music.map(item=><option key={item.id} value={item.id}>{item.name}{item.category?` · ${item.category}`:""}</option>)}</select></label>{musicId&&<div className="music-mix-grid"><label><span>音量 <b>{volume.toFixed(2)}</b></span><input type="range" min="0" max="1" step="0.05" value={volume} onChange={e=>setVolume(Number(e.target.value))}/></label><label><span>淡入时间 <b>{fadeIn} 秒</b></span><input type="range" min="0" max="10" step="0.5" value={fadeIn} onChange={e=>setFadeIn(Number(e.target.value))}/></label><label><span>淡出时间 <b>{fadeOut} 秒</b></span><input type="range" min="0" max="10" step="0.5" value={fadeOut} onChange={e=>setFadeOut(Number(e.target.value))}/></label></div>}</section>;
}

function BatchCreateDialog({connected,onClose,onSubmit}:{connected:boolean;onClose:()=>void;onSubmit:(data:Record<string,unknown>)=>Promise<void>}) {
  const [step,setStep]=useState(1); const [rows,setRows]=useState(()=>Array.from({length:6},(_,i)=>({id:`row-${i+1}`,book_title:"",author:"",edition:""}))); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
  const fallback:PromptTemplate[]=[{id:"writing-short-video",kind:"writing",name:"短视频口播",text:"适合 2 分钟短视频口播，有真实阅读感受"},{id:"writing-insight",kind:"writing",name:"反常识洞见",text:"从一个反常识观点切入，避免剧透"},{id:"cover-literary",kind:"cover",name:"文学质感",text:"克制的文学感，竖版构图，无文字"}];
  const [templates,setTemplates]=useState<PromptTemplate[]>(fallback);const [selectedIds,setSelectedIds]=useState<string[]>(fallback.map(x=>x.id));const [voiceList,setVoiceList]=useState<string[]>(["zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural"]);const [voice,setVoice]=useState("zh-CN-XiaoxiaoNeural");const [speechRate,setSpeechRate]=useState(0);const {music,musicId,setMusicId,musicLoading}=useMusicSelection(connected);const [localCover,setLocalCover]=useState(false);const [musicVolume,setMusicVolume]=useState(0.1);const [fadeIn,setFadeIn]=useState(3);const [fadeOut,setFadeOut]=useState(3);
  useEffect(()=>{if(!connected)return;fetch(`${API}/api/prompts`).then(r=>r.json()).then((items:PromptTemplate[])=>{setTemplates(items);setSelectedIds(items.map(x=>x.id))}).catch(()=>{});fetch(`${API}/api/settings`).then(r=>r.json()).then(settings=>{setVoice(settings.voices?.[0]||"zh-CN-XiaoxiaoNeural");setSpeechRate(settings.speech_rate??0)}).catch(()=>{});fetch(`${API}/api/voices`).then(r=>r.json()).then(data=>setVoiceList(data.voices)).catch(()=>{});},[connected]);
  const usedRows=rows.filter(row=>row.book_title.trim()||row.author.trim()||row.edition.trim());
  const updateRow=(id:string,field:"book_title"|"author"|"edition",value:string)=>setRows(items=>items.map(row=>row.id===id?{...row,[field]:value}:row));
  const next=()=>{if(!usedRows.length){setError("请至少填写一本书");return;}if(usedRows.some(row=>!row.book_title.trim())){setError("已填写的每一行都需要书籍名称");return;}setError("");setStep(2)};
  const submit=async()=>{if(!templates.some(x=>x.kind==="writing"&&selectedIds.includes(x.id)))return;setBusy(true);try{await onSubmit({books:usedRows.map(({book_title,author,edition})=>({book_title:book_title.trim(),author:author.trim(),edition:edition.trim()})),writing_prompt_ids:templates.filter(x=>x.kind==="writing"&&selectedIds.includes(x.id)).map(x=>x.id),local_cover:localCover,cover_prompt_ids:templates.filter(x=>x.kind==="cover"&&selectedIds.includes(x.id)).map(x=>x.id),voice,speech_rate:speechRate,background_music_id:musicId||null,background_music_volume:musicVolume,background_music_fade_in:fadeIn,background_music_fade_out:fadeOut})}finally{setBusy(false)}};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal config-modal batch-modal"><div className="modal-head"><div><p className="eyebrow">批量制作 · 第 {step} 步 / 2</p><h2>{step===1?"添加书籍信息":"设置共用生成配置"}</h2><p className="modal-subtitle">{step===1?"空白行会自动忽略，可继续添加更多书籍":"以下配置将应用到本批次全部书籍"}</p></div><button className="close" onClick={onClose}>×</button></div>{step===1?<><div className="batch-table"><div className="batch-table-head"><span>序号</span><span>书籍名称 *</span><span>作者</span><span>版本</span><span/></div>{rows.map((row,index)=><div className="batch-row" key={row.id}><b>{String(index+1).padStart(2,"0")}</b><input value={row.book_title} onChange={e=>updateRow(row.id,"book_title",e.target.value)} placeholder="例如：百年孤独"/><input value={row.author} onChange={e=>updateRow(row.id,"author",e.target.value)} placeholder="作者（选填）"/><input value={row.edition} onChange={e=>updateRow(row.id,"edition",e.target.value)} placeholder="版本（选填）"/><button disabled={rows.length===1} onClick={()=>setRows(items=>items.filter(item=>item.id!==row.id))}>删除</button></div>)}</div><button className="add-batch-row" onClick={()=>setRows(items=>[...items,{id:`row-${Date.now()}`,book_title:"",author:"",edition:""}])}>＋ 添加一行</button>{error&&<p className="batch-error">{error}</p>}</>:<><section className="workflow-speech batch-shared"><div><h3>共用配音设置</h3><p>{usedRows.length} 本书将使用相同音色与语速</p></div><div className="workflow-speech-grid"><VoiceControl label="配音音色" voices={voiceList} value={voice} onChange={setVoice}/><SpeechRateControl value={speechRate} onChange={setSpeechRate}/></div></section><MusicMixControl musicLoading={musicLoading} music={music} musicId={musicId} setMusicId={setMusicId} volume={musicVolume} setVolume={setMusicVolume} fadeIn={fadeIn} setFadeIn={setFadeIn} fadeOut={fadeOut} setFadeOut={setFadeOut}/><TemplatePicker title="共用分享稿提示词" hint="每本书按勾选模板分别生成" kind="writing" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/><fieldset className="cover-prompt-fieldset" disabled={localCover}><TemplatePicker title="共用封面提示词" hint="每本书按勾选模板分别生成" kind="cover" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/></fieldset><label className={`local-cover-option${localCover ? " selected" : ""}`}><input type="checkbox" checked={localCover} onChange={event=>setLocalCover(event.target.checked)}/><span><b>本地生成封面</b><small>随机使用内置模板，生成方形、横版和竖版各一张，自动插入书名与作者，不调用图片模型。</small></span><i>{localCover ? "已启用" : "无需图片模型"}</i></label></>}<div className="modal-actions">{step===2&&<button className="secondary" onClick={()=>setStep(1)}>上一步</button>}<button className="secondary" onClick={onClose}>取消</button>{step===1?<button className="primary" onClick={next}>下一步 →</button>:<button className="primary" disabled={busy||musicLoading||!templates.some(x=>x.kind==="writing"&&selectedIds.includes(x.id))} onClick={submit}>{busy?"正在创建…":`开始自动制作 ${usedRows.length} 本`}</button>}</div></div></div>;
}

function TemplatePicker({title,hint,kind,templates,selected,setSelected}:{title:string;hint:string;kind:"writing"|"cover";templates:PromptTemplate[];selected:string[];setSelected:(v:string[])=>void}) {
  const items=templates.filter(x=>x.kind===kind);
  return <section className="prompt-editor"><div><h3>{title}</h3><p>{hint}</p></div><div className="template-picker title-only">{items.map(item=><label key={item.id} className={selected.includes(item.id)?"picked":""}><input type="checkbox" checked={selected.includes(item.id)} onChange={e=>setSelected(e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/><b>{item.name}</b><span className="check-mark">✓</span></label>)}</div>{!items.length&&<p className="empty-hint">请先到提示词库添加配置</p>}</section>;
}

function ImageSizePicker({value,onChange}:{value:string[];onChange:(value:string[])=>void}) {
  const hasRequiredVideoCoverSizes=["1:1","16:9","9:16"].every(size=>value.includes(size));
  return <fieldset className="image-size-picker"><legend>图片尺寸 <em>*</em></legend><p>可多选；每个比例将单独生成一张封面图片</p><div>{coverSizeGroups.map(group=><section key={group.label}><b>{group.label}</b><div>{group.options.map(([size,label])=><label key={size}><input type="checkbox" disabled={["1:1","16:9","9:16"].includes(size)} checked={value.includes(size)} onChange={event=>onChange(event.target.checked?[...value,size]:value.filter(item=>item!==size))}/><span>{label}{["1:1","16:9","9:16"].includes(size)?" · 必选":""}</span></label>)}</div></section>)}</div>{!hasRequiredVideoCoverSizes&&<small className="image-size-required">请同时选择 1:1、16:9 和 9:16 图片尺寸</small>}<small className="image-size-note">程序会将所选图片比例写入提示词并分别调用图片服务；实际图片尺寸由服务返回，页面按返回结果显示。</small><small className="image-size-note">1:1 用于唱片封套，16:9、9:16 分别用于横竖版背景。</small></fieldset>;
}

function PromptLibraryDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [kind,setKind]=useState<"writing"|"cover">("writing");
  const [items,setItems]=useState<PromptTemplate[]>([]); const [name,setName]=useState(""); const [text,setText]=useState(""); const [imageSizes,setImageSizes]=useState<string[]>(["1:1","16:9","9:16"]);
  const [editingId,setEditingId]=useState<string|null>(null); const [saving,setSaving]=useState(false);
  const load=()=>connected&&fetch(`${API}/api/prompts`).then(r=>r.json()).then(setItems).catch(()=>{});
  useEffect(()=>{if(connected) void fetch(`${API}/api/prompts`).then(r=>r.json()).then(setItems).catch(()=>{});},[connected]);
  const clearEditor=()=>{setName("");setText("");setImageSizes(["1:1","16:9","9:16"]);setEditingId(null)};
  const hasRequiredCoverSizes=["1:1","16:9","9:16"].every(size=>imageSizes.includes(size));
  const saveTemplate=async()=>{if(!name.trim()||!text.trim()||(kind==="cover"&&!hasRequiredCoverSizes))return;setSaving(true);try{const url=editingId?`${API}/api/prompts/${editingId}`:`${API}/api/prompts`;const payload={name,text,image_sizes:imageSizes};const res=await fetch(url,{method:editingId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(editingId?payload:{kind,...payload})});if(res.ok){clearEditor();load();onSaved();}}finally{setSaving(false)}};
  const edit=(item:PromptTemplate)=>{setEditingId(item.id);setName(item.name);setText(item.text);setImageSizes([...new Set([...(item.image_sizes||[]),"1:1","16:9","9:16"])])};
  const remove=async(id:string)=>{await fetch(`${API}/api/prompts/${id}`,{method:"DELETE"});load();onSaved();};
  const visible=items.filter(x=>x.kind===kind);
  const switchKind=(next:"writing"|"cover")=>{setKind(next);clearEditor()};
  const writingCount=items.filter(item=>item.kind==="writing").length;
  const coverCount=items.filter(item=>item.kind==="cover").length;
  return <div className="modal-backdrop" role="presentation" onMouseDown={event=>event.target===event.currentTarget&&onClose()}>
    <div className="modal config-modal prompt-library">
      <div className="modal-head"><div><p className="eyebrow">全局配置</p><h2>提示词库</h2></div><button className="close" onClick={onClose}>×</button></div>
      <nav className="settings-tabs prompt-tabs" aria-label="提示词分类">
        <button className={kind==="writing"?"active":""} onClick={()=>switchKind("writing")}><span aria-hidden="true">文</span><div><b>分享稿提示词 <em>{writingCount}</em></b><small>定义分享稿结构、语气与长度</small></div></button>
        <button className={kind==="cover"?"active":""} onClick={()=>switchKind("cover")}><span aria-hidden="true">画</span><div><b>封面提示词 <em>{coverCount}</em></b><small>定义封面风格、构图与色彩</small></div></button>
      </nav>
      <div className="library-layout">
        <section className="template-list"><div className="list-caption"><span>已添加模板</span><small>{visible.length} 个</small></div>{visible.map((item,index)=><article className={editingId===item.id?"editing":""} key={item.id}><span className="template-number">{String(index+1).padStart(2,"0")}</span><div className="template-copy"><b>{item.name}</b><p>{item.text}</p></div><div className="template-actions"><button onClick={()=>edit(item)}>编辑</button><button className="danger-link" onClick={()=>remove(item.id)}>删除</button></div></article>)}{!visible.length&&<div className="empty-template"><span>◇</span><p>还没有模板，添加第一个模板吧</p></div>}</section>
        <section className="template-composer"><div className="composer-title"><span>{editingId?"编":"＋"}</span><div><h3>{editingId?"编辑模板":"添加新模板"}</h3><p>{kind==="writing"?"定义文案的结构、语气与长度":"定义封面的风格、构图与色彩"}</p></div></div><label>模板名称<input value={name} onChange={event=>setName(event.target.value)} placeholder={kind==="writing"?"例如：知识型口播":"例如：复古油画"}/></label><label>提示词内容<textarea value={text} onChange={event=>setText(event.target.value)} placeholder={kind==="writing"?"描述分享稿的语气、结构和长度要求":"描述封面的风格、构图和色彩要求"}/></label>{kind==="cover"&&<ImageSizePicker value={imageSizes} onChange={setImageSizes}/>}<div className="composer-actions">{editingId&&<button className="secondary" onClick={clearEditor}>取消编辑</button>}<button className="primary action-button" disabled={!connected||!name.trim()||!text.trim()||(kind==="cover"&&!hasRequiredCoverSizes)||saving} onClick={saveTemplate}><span aria-hidden="true">{editingId?"✓":"＋"}</span>{saving?"保存中…":editingId?"保存修改":"添加模板"}</button></div></section>
      </div>
    </div>
  </div>;
}

function CoverGallery({covers,bookTitle,coverPrompts}:{covers:Asset[];bookTitle:string;coverPrompts?:PromptTemplate[]}) {
  const [active,setActive]=useState(0); const selected=covers[Math.min(active,covers.length-1)];
  if(!selected)return <EmptyMedia text="封面尚未生成"/>;
  const promptName=selected.prompt_name||coverPrompts?.find(prompt=>prompt.text===selected.prompt)?.name||`封面提示词 ${active+1}`;
  return <section className="cover-gallery"><figure className="cover-stage"><img src={`${API}${selected.url}`} alt={`${bookTitle}封面 ${active+1}`}/><figcaption><b>{promptName}</b><span>比例 {selected.image_ratio||"未记录"} · 分辨率 {selected.resolution||"未记录"}</span></figcaption></figure><div className="cover-thumbnails">{covers.map((cover,index)=><button type="button" key={cover.url} className={index===active?"active":""} onClick={()=>setActive(index)} aria-label={`切换到第 ${index+1} 张封面`}><img src={`${API}${cover.url}`} alt=""/><span>第 {index+1} 张</span><small>{cover.image_ratio||"未记录"} · {cover.resolution||"未记录"}</small></button>)}</div><p className="cover-gallery-summary">共生成 <b>{covers.length}</b> 张图片 · 当前第 {active+1} 张</p></section>;
}

function DetailPanel({task,onClose,onRetry,onDelete,onRegenerateVideo,onRegenerateAudio}:{task:Workflow;onClose:()=>void;onRetry:()=>void;onDelete:()=>Promise<void>;onRegenerateVideo:()=>Promise<void>;onRegenerateAudio:(voice:string)=>Promise<void>}) {
  const [tab,setTab]=useState("overview"); const [compare,setCompare]=useState(0); const [confirmDelete,setConfirmDelete]=useState(false); const [deleting,setDeleting]=useState(false); const [deleteError,setDeleteError]=useState("");
  const [videoBusy,setVideoBusy]=useState(false); const [videoMessage,setVideoMessage]=useState("");
  const [audioBusy,setAudioBusy]=useState(false); const [audioMessage,setAudioMessage]=useState("");
  const [voices,setVoices]=useState<string[]>([]); const [voice,setVoice]=useState(task.audio?.[0]?.voice||"zh-CN-XiaoxiaoNeural");
  useEffect(()=>{let cancelled=false;fetch(`${API}/api/voices`).then(r=>r.json()).then(data=>{if(cancelled)return;const names=(data.items||[]).map((item:VoiceItem)=>item.short_name).filter(Boolean);const list=names.length?names:(data.voices||[]);if(list.length)setVoices(list)}).catch(()=>{});return()=>{cancelled=true}},[]);
  const videoRegenerating=videoBusy||!!task.video_regenerating;
  const audioRegenerating=audioBusy||!!task.audio_regenerating;
  const voiceChoices=voices.includes(voice)?voices:[voice,...voices];
  const regenerateVideo=async()=>{setVideoBusy(true);setVideoMessage("");try{await onRegenerateVideo()}catch(error){setVideoMessage(error instanceof Error?error.message:"重新生成失败，请稍后重试")}finally{setVideoBusy(false)}};
  const regenerateAudio=async()=>{setAudioBusy(true);setAudioMessage("");try{await onRegenerateAudio(voice)}catch(error){setAudioMessage(error instanceof Error?error.message:"重新生成配音失败，请稍后重试")}finally{setAudioBusy(false)}};
  const remove=async()=>{setDeleting(true);setDeleteError("");try{await onDelete()}catch{setDeleteError("删除失败，请稍后重试");setDeleting(false)}};
  const tabs=[['overview','概览'],['drafts','分享稿'],['audio','配音'],['subtitles','字幕'],['covers','封面'],['videos','视频']];
  const pipelineStep=Math.max(0,task.step-1);
  const pipelineFailed=task.status==="failed";
  return <div className="drawer-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><aside className="drawer">
    <div className="drawer-head"><button className="close" onClick={onClose}>×</button><div><p className="eyebrow">作品详情</p><h2>{task.book_title}</h2><p>{task.author}{task.edition ? ` · ${task.edition}`:""}</p></div><div className="drawer-status-actions"><Status value={task.status}/><button className="delete-work" onClick={()=>setConfirmDelete(true)}><span className="delete-icon" aria-hidden="true"/>删除作品</button></div></div>
    <nav className="tabs">{tabs.map(([id,label])=><button key={id} className={tab===id?"active":""} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    <div className="drawer-content">
      {task.status!=="completed"&&<div className="pipeline"><div className="pipeline-head"><span>{pipelineFailed?"制作遇到问题":`正在${stages[pipelineStep]||"准备"}`}</span><b>{task.progress}%</b></div><div className="progress"><i style={{width:`${task.progress}%`}}/></div><div className="steps">{stages.map((s,i)=><span className={i<pipelineStep?"done":i===pipelineStep?(pipelineFailed?"failed":"now"):""} key={s}>{i<pipelineStep?"✓":i+1}<small>{s}</small></span>)}</div>{pipelineFailed&&<p className="error">{task.error||"制作失败，但没有记录到具体原因。"} <button onClick={onRetry}>重试</button></p>}</div>}
      {tab==="overview"&&<section className="result-section"><h3>书籍简介</h3><div className="paper">{task.description||"简介将在书籍解析完成后出现。"}</div><h3>标签和话题</h3><div className="taxonomy-panel"><div><b>标签</b><p>{task.tags?.length?task.tags.map(tag=><span key={tag}>{tag}</span>):<small>标签尚未生成</small>}</p></div><div><b>话题</b><p>{task.topics?.length?task.topics.map(topic=><span key={topic}>#{topic}</span>):<small>话题尚未生成</small>}</p></div></div><h3>产出清单</h3><div className="asset-summary"><span><b>{task.polished_drafts?.length||0}</b> 篇分享稿</span><span><b>{task.audio?.length||0}</b> 份配音</span><span><b>{task.subtitles?.length||0}</b> 份字幕</span><span><b>{task.covers?.length||0}</b> 张封面</span><span><b>{task.videos?.length||0}</b> 条视频</span></div></section>}
      {tab==="drafts"&&<section className="result-section"><div className="section-inline"><h3>分享稿对比</h3>{(task.polished_drafts?.length||0)>1&&<select value={compare} onChange={e=>setCompare(+e.target.value)}>{task.polished_drafts?.map((d,i)=><option key={d.id} value={i}>版本 {i+1}</option>)}</select>}</div><div className="compare"><article><label>原始稿</label><p>{task.original_drafts?.[compare]?.text||"尚未生成"}</p></article><article className="polished"><label>自然化优化稿</label><p>{task.polished_drafts?.[compare]?.text||"尚未生成"}</p></article></div></section>}
      {tab==="covers"&&<CoverGallery covers={task.covers||[]} bookTitle={task.book_title} coverPrompts={task.cover_prompts}/>}
      {tab==="audio"&&<section className="audio-panel" aria-busy={audioRegenerating}>{task.status==="completed"&&<div className="audio-regenerate"><div><b>重新生成配音</b><p>按所选音色重新合成全部配音，并同时重新生成字幕。语速和背景音乐保持不变。视频页的「重新生成视频」会使用这里最新的配音和字幕。</p><VoiceControl label="配音音色" voices={voiceChoices} value={voice} onChange={setVoice} disabled={audioRegenerating||videoRegenerating}/>{(audioMessage||task.audio_error)&&<p className="audio-regenerate-error" role="alert">{audioMessage||task.audio_error}</p>}</div><button type="button" className="primary" disabled={audioRegenerating||videoRegenerating||!voice.trim()} onClick={regenerateAudio}>{audioRegenerating?"正在重新生成配音和字幕…":"重新生成配音"}</button></div>}<div className="audio-list">{task.audio?.length?task.audio.map((a,i)=><article key={`${a.url}-${task.updated_at||0}`}><span>声</span><div><b>{a.voice}</b><small>分享稿 {i+1} · 语速 {a.speech_rate===0||a.speech_rate===undefined?"正常":`${a.speech_rate>0?"+":""}${a.speech_rate}%`}</small></div><audio controls preload="none" src={`${API}${a.url}?v=${task.updated_at||0}`}/></article>):<EmptyMedia text="配音尚未生成"/>}</div></section>}
      {tab==="subtitles"&&<section className="audio-list">{task.subtitles?.length?task.subtitles.map((item,i)=><article key={item.srt_url}><span>字</span><div><b>{item.voice}</b><small>分享稿 {i+1}</small><div className="subtitle-downloads"><a href={`${API}${item.srt_url}`} download>下载 SRT</a><a href={`${API}${item.txt_url}`} download>下载 TXT</a><a href={`${API}${item.json_url}`} download>下载 JSON</a></div></div></article>):<EmptyMedia text="字幕尚未生成"/>}</section>}
      {tab==="videos"&&<section className="video-panel" aria-busy={videoRegenerating}>{task.status==="completed"&&<div className="video-regenerate"><div><b>按视频设置重新生成</b><p>使用最新配音，清理字幕后同时生成横竖两版播放器视频。</p>{(videoMessage||task.video_error)&&<p className="video-regenerate-error" role="alert">{videoMessage||task.video_error}</p>}</div><button type="button" className="primary" disabled={videoRegenerating||audioRegenerating} onClick={regenerateVideo}>{videoRegenerating?"正在重新生成…":"重新生成视频"}</button></div>}<div className="video-grid">{task.videos?.length?task.videos.map(a=><figure key={`${a.url}-${task.updated_at||0}`}><video className={a.orientation||"portrait"} controls preload="metadata" src={`${API}${a.url}?v=${task.updated_at||0}`}/><figcaption><b>{a.voice} · 分享稿 {Math.max(0,(task.polished_drafts||[]).findIndex(d=>d.id===a.draft_id))+1} · {a.orientation==="landscape"?"横版 16:9":"竖版 9:16"}</b><a href={`${API}${a.url}`} download>下载视频</a><span>分辨率：{a.resolution||"未记录"}</span><span>视频时长：{formatVideoDuration(a.duration)}</span></figcaption></figure>):<EmptyMedia text="视频尚未生成"/>}</div></section>}
    </div>{confirmDelete&&<div className="confirm-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&!deleting&&setConfirmDelete(false)}><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title"><span className="danger-mark">删</span><h3 id="delete-title">确定删除《{task.book_title}》？</h3><p>该作品的简介、分享稿、封面、配音和视频都会被永久删除，此操作无法撤销。</p>{deleteError&&<small>{deleteError}</small>}<div><button className="secondary" disabled={deleting} onClick={()=>setConfirmDelete(false)}>取消</button><button className="danger-button" disabled={deleting} onClick={remove}>{deleting?"正在删除…":"确认永久删除"}</button></div></section></div>}
  </aside></div>;
}

function EmptyMedia({text}:{text:string}) { return <div className="empty-media"><span>◇</span><p>{text}</p></div> }

function formatVideoDuration(value?:number) {
  if(value===undefined||value===null||!Number.isFinite(value))return "未记录";
  const seconds=Math.max(0,Math.round(value));
  const hours=Math.floor(seconds/3600); const minutes=Math.floor((seconds%3600)/60); const remaining=seconds%60;
  return hours?`${hours}:${String(minutes).padStart(2,"0")}:${String(remaining).padStart(2,"0")}`:`${minutes}:${String(remaining).padStart(2,"0")}`;
}

function SettingsDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  type Provider = "text" | "image";
  type ModelListState = {models:string[];loading:boolean;error:string;message:string};
  const [form,setForm]=useState<AppSettings>(defaultSettings); const [saving,setSaving]=useState(false); const [error,setError]=useState(""); const [settingsTab,setSettingsTab]=useState<"model"|"help">("model");
  const [lists,setLists]=useState<Record<Provider,ModelListState>>({text:{models:[],loading:false,error:"",message:""},image:{models:[],loading:false,error:"",message:""}});
  useEffect(()=>{if(connected)fetch(`${API}/api/settings`).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(setForm).catch(()=>setError("模型配置加载失败，请稍后重新打开页面"));},[connected]);
  const updateApi=(provider:Provider,field:"api_base"|"api_key",value:string)=>{
    setForm(current=>({...current,[`${provider}_${field}`]:value,[provider==="text"?"model":"image_model"]:""}));
    setLists(current=>({...current,[provider]:{models:[],loading:false,error:"",message:""}}));
  };
  const getModels=async(provider:Provider)=>{
    setLists(current=>({...current,[provider]:{models:[],loading:true,error:"",message:""}}));
    try{
      const response=await fetch(`${API}/api/models`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({provider,api_base:form[`${provider}_api_base`],api_key:form[`${provider}_api_key`]})});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:data.detail?.[0]?.msg||"获取模型失败，请检查配置后重试");
      const models:string[]=data.models;
      setLists(current=>({...current,[provider]:{models,loading:false,error:"",message:models.length?`已获取 ${models.length} 个模型，请在下拉框中选择`:'该服务未返回可选模型，请检查 API 地址或账号权限'}}));
      const modelField=provider==="text"?"model":"image_model";
      setForm(current=>({...current,[modelField]:models.includes(current[modelField])?current[modelField]:""}));
    }catch(reason){setLists(current=>({...current,[provider]:{models:[],loading:false,error:reason instanceof Error?reason.message:"获取模型失败，请稍后重试",message:""}}));}
  };
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);setError("");try{const response=await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});if(!response.ok)throw new Error("保存失败，请稍后重试");setForm(await response.json());onSaved();}catch(reason){setError(reason instanceof Error?reason.message:"保存失败");}finally{setSaving(false)}};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal config-modal settings-modal">
    <div className="modal-head"><div><p className="eyebrow">创作引擎</p><h2>模型配置</h2></div><button className="close" onClick={onClose}>×</button></div>
    <nav className="settings-tabs" aria-label="模型配置分类"><button className={settingsTab==="model"?"active":""} onClick={()=>setSettingsTab("model")}><span>AI</span><div><b>OpenAI 兼容接口</b><small>文本与图片生成</small></div></button><button className={settingsTab==="help"?"active":""} onClick={()=>setSettingsTab("help")}><span>?</span><div><b>配置说明</b><small>填写 → 获取 → 选择 → 保存</small></div></button></nav>
    <div className="settings-pane">{settingsTab==="model"?(["text","image"] as const).map(provider=>{
      const label=provider==="text"?"文本":"图片"; const modelField=provider==="text"?"model":"image_model"; const list=lists[provider]; const disabled=saving||list.loading;
      return <div className="settings-block" key={provider}><h3>{label}模型</h3>
        <div className="form-grid model-api-fields"><label>{label} API 地址<input value={form[`${provider}_api_base`]} onChange={e=>updateApi(provider,"api_base",e.target.value)} disabled={disabled} spellCheck={false}/></label><label>{label} API 密钥<input type="password" value={form[`${provider}_api_key`]} onChange={e=>updateApi(provider,"api_key",e.target.value)} disabled={disabled} placeholder={`从 ${provider.toUpperCase()}_API_KEY 读取或在此填写`}/></label></div>
        <div className="model-picker-row"><div className="model-picker-field"><span>{label}模型</span><ModelSelect label={`${label}模型`} models={list.models} value={form[modelField]} disabled={disabled||!list.models.length} onChange={model=>setForm(current=>({...current,[modelField]:model}))}/></div><button type="button" className="secondary get-models-button" disabled={!connected||disabled} onClick={()=>void getModels(provider)}>{list.loading?"获取中…":"获取模型"}</button></div>
        {list.error&&<p className="settings-error" role="alert">{list.error}</p>}{list.message&&<p className="model-fetch-message" role="status">{list.message}</p>}
      </div>;
    }):<section className="config-help model-config-help" aria-label="模型配置使用说明">
      <article><span>01</span><div><b>填写地址与密钥</b><p>分别填写文本、图片服务的 API 根地址和密钥，两侧可以使用不同服务。</p><p>地址示例：<code>https://api.example.com/v1</code>。保留服务商要求的 /v1 或自定义前缀。图片服务也可填写以 /images/generations 结尾的完整地址，获取模型时会自动访问同一服务的 /models。</p></div></article>
      <article><span>02</span><div><b>获取模型，再选择</b><p>点击对应的“获取模型”，从下拉框选择一个模型，最后点击“保存设置”。新配置默认不预选模型。</p><p>获取使用当前输入，不必先保存；打开页面和保存设置时不会自动获取。修改地址或密钥后，请重新获取并选择。</p></div></article>
      <article><span>03</span><div><b>保存与环境变量</b><p><strong>页面保存值 → 对应环境变量 → 默认值</strong>，按此顺序生效；已保存的选择再次打开时会保留。</p><dl><dt>文本服务</dt><dd><code>TEXT_API_BASE</code> · <code>TEXT_API_KEY</code> · <code>MODEL_NAME</code></dd><dt>图片服务</dt><dd><code>IMAGE_API_BASE</code> · <code>IMAGE_API_KEY</code> · <code>IMAGE_MODEL_NAME</code></dd></dl><p>密钥由服务端保存，圆点表示已配置。清空密钥并保存可停用该侧远程调用；没有密钥或未选择模型时，使用演示文案或本地封面。</p></div></article>
      <article><span>?</span><div><b>遇到问题时</b><ul><li><strong>鉴权失败：</strong>检查密钥是否正确、是否有访问该服务的权限。</li><li><strong>无法获取或列表为空：</strong>确认根地址正确，且服务支持 /models；检查网络和账号权限。</li><li><strong>尚未启动后端：</strong>页面可浏览，获取真实模型需先启动 Python 服务。</li></ul></div></article>
    </section>}</div>
    {error&&<p className="settings-error" role="alert">{error}</p>}<p className="privacy-note">两组密钥分别保存在服务端并脱敏显示，不会写入前端源码。</p>
    <div className="modal-actions"><button className="secondary action-button" onClick={onClose}><span aria-hidden="true">×</span>取消</button><button className="primary action-button" onClick={save} disabled={saving||lists.text.loading||lists.image.loading}><span aria-hidden="true">✓</span>{saving?"保存中…":"保存设置"}</button></div>
  </div></div>;
}

function VideoSettingsPage({connected,onSaved}:{connected:boolean;onSaved:()=>void}) {
  const [form,setForm]=useState<AppSettings>(defaultSettings); const [saving,setSaving]=useState(false); const [error,setError]=useState(""); const [showApiKey,setShowApiKey]=useState(false); const [videoTab,setVideoTab]=useState<"video"|"subtitles">("video");
  useEffect(()=>{if(connected)fetch(`${API}/api/settings`).then(r=>r.json()).then(data=>setForm({...defaultSettings(),...data})).catch(()=>setError("视频设置加载失败"));},[connected]);
  const [labelUploading,setLabelUploading]=useState(false);
  const labelInput=useRef<HTMLInputElement>(null);
  const [labelMessage,setLabelMessage]=useState("");
  const [labelError,setLabelError]=useState("");
  const uploadLabel=async(file?:File)=>{if(!file)return;setLabelUploading(true);setLabelError("");setLabelMessage("");try{if(file.size>10*1024*1024)throw new Error("图片不能超过 10MB");const res=await fetch(`${API}/api/video/record-label-images`,{method:"POST",headers:{"Content-Type":file.type},body:file});const data=await res.json();if(!res.ok)throw new Error(data.detail||"上传失败");setForm(current=>({...current,record_label_image_id:data.id}));setLabelMessage(`${file.name} 已上传，保存视频设置后生效`);}catch(e){setLabelError(e instanceof Error?e.message:"上传失败")}finally{setLabelUploading(false)}};
  const provider=form.stock_video_provider; const apiBase=provider==="pexels"?form.pexels_api_base:form.pixabay_api_base; const apiKey=provider==="pexels"?form.pexels_api_key:form.pixabay_api_key;
  const setProviderField=(field:"base"|"key",value:string)=>setForm(current=>provider==="pexels"?{...current,[field==="base"?"pexels_api_base":"pexels_api_key"]:value}:{...current,[field==="base"?"pixabay_api_base":"pixabay_api_key"]:value});
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);setError("");try{const response=await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});if(!response.ok){const detail=await response.json().catch(()=>null);throw new Error(detail?.detail?.[0]?.msg||"保存失败");}setForm(await response.json());setLabelMessage("");onSaved();}catch(reason){setError(reason instanceof Error?reason.message:"保存失败");}finally{setSaving(false)}};
  return <div className="video-settings-page"><div className="page-section-head"><div><p className="eyebrow">VIDEO WORKFLOW</p><h1>视频设置</h1><p>统一控制横竖双版的播放器布局、字幕和背景素材。新启动的工作流会使用这里的配置；已完成作品也可以在详情的视频页按这里的配置重新生成视频。</p></div></div>
    <nav className="settings-tabs video-settings-tabs" aria-label="视频设置分类"><button className={videoTab==="video"?"active":""} onClick={()=>setVideoTab("video")}>视频生成</button><button className={videoTab==="subtitles"?"active":""} onClick={()=>setVideoTab("subtitles")}>字幕烧录</button></nav>{videoTab==="subtitles"&&<SubtitleSettings form={form} onChange={setForm} connected={connected}/>}
    <section className="settings-pane video-settings-pane" hidden={videoTab!=="video"}>
      <div className="settings-block record-label-settings"><div><h3>唱片中心图片</h3><p>中心头像保持正向。选择图片后可预览，保存视频设置后用于新生成的视频。</p><div className="record-label-upload" aria-busy={labelUploading}><span className="record-upload-icon" aria-hidden="true">↑</span><div><b>为唱片添加专属头像</b><small>支持 PNG、JPEG、WebP，最大 10MB</small><input ref={labelInput} className="record-label-file" type="file" accept="image/png,image/jpeg,image/webp" aria-label="选择唱片中心图片" disabled={!connected||labelUploading||saving} onChange={e=>{void uploadLabel(e.target.files?.[0]);e.target.value=""}}/><div className="record-label-buttons"><button type="button" className="primary" disabled={!connected||labelUploading||saving} onClick={()=>labelInput.current?.click()}>{labelUploading?"正在上传…":"选择 / 更换图片"}</button><button type="button" className="secondary" disabled={labelUploading||saving} onClick={()=>{setForm({...form,record_label_image_id:null});setLabelError("");setLabelMessage("已恢复默认图片，保存视频设置后生效")}}>恢复默认图片</button></div></div></div>{labelMessage&&<p className="record-label-status" role="status">{labelMessage}</p>}{labelError&&<p className="settings-error" role="alert">{labelError}</p>}</div><figure className="record-label-preview"><img src={`${API}/api/video/record-label-images/${form.record_label_image_id||"default"}`} alt="唱片中心图片圆形预览"/><figcaption>圆形显示效果</figcaption></figure></div>
      <div className="settings-block background-overlay-settings"><h3>背景效果</h3><label className="background-overlay-toggle"><input type="checkbox" checked={form.background_overlay_enabled} onChange={e=>setForm({...form,background_overlay_enabled:e.target.checked})}/><span><b>启用背景暗罩</b><small>仅压暗背景图片或视频，突出唱片与字幕</small></span><i>{form.background_overlay_enabled?"已开启":"已关闭"}</i></label><label className="background-overlay-slider" htmlFor="background-overlay-opacity"><span>遮罩不透明度 <b>{Math.round(form.background_overlay_opacity*100)}%</b></span><input id="background-overlay-opacity" type="range" min="0" max="100" step="1" disabled={!form.background_overlay_enabled} value={Math.round(form.background_overlay_opacity*100)} onChange={e=>setForm({...form,background_overlay_opacity:Number(e.target.value)/100})}/><small>0% 不压暗 · 100% 纯黑背景；保存视频设置后生效</small></label>
        <label className="background-overlay-toggle background-blur-toggle"><input type="checkbox" checked={form.background_blur_enabled} onChange={e=>setForm({...form,background_blur_enabled:e.target.checked})}/><span><b>启用背景虚化</b><small>仅虚化背景图片或视频，封面、唱片和字幕保持清晰</small></span><i>{form.background_blur_enabled?"已开启":"已关闭"}</i></label>
        <label className="background-overlay-slider" htmlFor="background-blur-strength"><span>虚化强度 <b>{form.background_blur_strength}%</b></span><input id="background-blur-strength" type="range" min="0" max="100" step="1" disabled={!form.background_blur_enabled} value={form.background_blur_strength} onChange={e=>setForm({...form,background_blur_strength:Number(e.target.value)})}/><small>0% 不虚化 · 100% 最强虚化；可与背景暗罩独立使用，保存视频设置后生效</small></label>
      </div>
      <div className="settings-block"><h3>同时输出横版和竖版</h3><p>每份配音生成横版输出 1920 × 1080，竖版输出 1080 × 1920，分别适配书封、唱片、字幕及播放器位置。</p></div>

      <div className="settings-block"><h3>生成方式</h3><div className="video-option-grid">
        <label className={form.video_generation_method==="local"?"selected":""}><input type="radio" name="video-method" checked={form.video_generation_method==="local"} onChange={()=>setForm({...form,video_generation_method:"local"})}/><span><b>本地生成</b><small>对应方向封面背景、书封唱片与音频频谱</small></span></label>
        <label className={form.video_generation_method==="stock"?"selected":""}><input type="radio" name="video-method" checked={form.video_generation_method==="stock"} onChange={()=>setForm({...form,video_generation_method:"stock"})}/><span><b>引用无版权视频</b><small>使用压暗的风景视频作为播放器背景</small></span></label>
      </div></div>
      {form.video_generation_method==="stock"&&<div className="settings-block stock-provider-settings"><h3>无版权视频站点</h3><div className="video-option-grid compact">
        <label className={provider==="pexels"?"selected":""}><input type="radio" name="stock-provider" checked={provider==="pexels"} onChange={()=>setForm({...form,stock_video_provider:"pexels"})}/><span><b>Pexels</b><small>自然风光视频搜索</small></span></label>
        <label className={provider==="pixabay"?"selected":""}><input type="radio" name="stock-provider" checked={provider==="pixabay"} onChange={()=>setForm({...form,stock_video_provider:"pixabay"})}/><span><b>Pixabay</b><small>安全搜索的视频素材</small></span></label>
      </div><div className="stock-credential-panel"><header className="stock-credential-head"><span aria-hidden="true">API</span><div><b>{provider==="pexels"?"Pexels":"Pixabay"} 接口配置</b><small>用于检索和下载 1080p 视频素材</small></div><em className={apiKey?"configured":""}>{apiKey?"密钥已配置":"等待配置"}</em></header><div className="stock-api-fields"><label><span>API 地址<small>HTTPS Endpoint</small></span><div className="stock-input-shell"><i aria-hidden="true">址</i><input value={apiBase} onChange={e=>setProviderField("base",e.target.value)} spellCheck={false}/></div></label><label><span>API 密钥<small>{provider==="pexels"?"PEXELS_KEY":"PIXABAY_KEY"}</small></span><div className="stock-input-shell secret"><i aria-hidden="true">钥</i><input type={showApiKey?"text":"password"} value={apiKey} onChange={e=>setProviderField("key",e.target.value)} placeholder={`从 .env 读取或在此填写`}/><button type="button" onClick={()=>setShowApiKey(value=>!value)} aria-label={showApiKey?"隐藏 API 密钥":"显示 API 密钥"}>{showApiKey?"隐藏":"显示"}</button></div></label></div><div className="stock-security-note"><span aria-hidden="true">盾</span><p><b>凭证保存在服务端</b>密钥优先从 .env 读取并脱敏显示；搜索词由模型根据书籍简介生成，仅使用自然风光、环境与氛围关键词。</p></div></div></div>}
    </section>{error&&<p className="settings-error" role="alert">{error}</p>}<div className="video-settings-actions"><button className="primary action-button" onClick={save} disabled={saving||labelUploading}><span aria-hidden="true">✓</span>{saving?"保存中…":"保存视频设置"}</button></div>
  </div>;
}

function VoiceSettingsDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [tab,setTab]=useState<"speech"|"voices"|"music">("speech"); const [form,setForm]=useState<AppSettings>(defaultSettings); const [voices,setVoices]=useState<VoiceItem[]>([]); const [saving,setSaving]=useState(false); const [download,setDownload]=useState({status:"idle",total:0,completed:0,failed:0});
  const [music,setMusic]=useState<BackgroundMusic[]>([]); const [musicTotal,setMusicTotal]=useState(0); const [musicPage,setMusicPage]=useState(1); const [musicQuery,setMusicQuery]=useState(""); const [musicForm,setMusicForm]=useState({name:"",url:"",category:""}); const [musicError,setMusicError]=useState(""); const [editingMusicId,setEditingMusicId]=useState<string|null>(null); const [playingMusic,setPlayingMusic]=useState<BackgroundMusic|null>(null);
  const musicPageSize=6;
  const loadVoices=useCallback(()=>connected&&fetch(`${API}/api/voices`).then(r=>r.json()).then(d=>setVoices((d.items||d.voices.map((short_name:string)=>({short_name}))).map(normalizeVoiceItem).filter((item:VoiceItem)=>item.short_name))).catch(()=>{}),[connected]);
  const loadMusic=useCallback(()=>connected&&fetch(`${API}/api/background-music?q=${encodeURIComponent(musicQuery)}&page=${musicPage}&page_size=${musicPageSize}`).then(r=>r.json()).then(d=>{setMusic(d.items);setMusicTotal(d.total)}).catch(()=>{}),[connected,musicPage,musicQuery]);
  useEffect(()=>{if(connected){fetch(`${API}/api/settings`).then(r=>r.json()).then(setForm).catch(()=>{});void loadVoices();fetch(`${API}/api/voices/download-all/status`).then(r=>r.json()).then(setDownload).catch(()=>{});}},[connected,loadVoices]);
  useEffect(()=>{void loadMusic();},[loadMusic]);
  useEffect(()=>{if(download.status!=="queued"&&download.status!=="running")return;const timer=window.setInterval(()=>fetch(`${API}/api/voices/download-all/status`).then(r=>r.json()).then(setDownload).catch(()=>{}),1200);return()=>window.clearInterval(timer);},[download.status]);
  const musicPages=Math.max(1,Math.ceil(musicTotal/musicPageSize));
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);try{const response=await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});if(!response.ok)throw new Error("保存失败");onSaved();}finally{setSaving(false)}};
  const downloadAll=async()=>{const response=await fetch(`${API}/api/voices/download-all`,{method:"POST"});setDownload(await response.json())};
  const saveMusic=async()=>{setMusicError("");if(!musicForm.name.trim()){setMusicError("请填写背景音乐名称");return;}if(!/^https:\/\/[^/]+/i.test(musicForm.url.trim())){setMusicError("请输入有效的 HTTPS 音频地址");return;}const response=await fetch(editingMusicId?`${API}/api/background-music/${editingMusicId}`:`${API}/api/background-music`,{method:editingMusicId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(musicForm)});if(!response.ok){setMusicError("保存失败，请检查填写内容");return;}const saved=await response.json() as BackgroundMusic;if(playingMusic?.id===saved.id)setPlayingMusic(saved);setMusicForm({name:"",url:"",category:""});setEditingMusicId(null);setMusicPage(1);void loadMusic()};
  const [defaultMusicBusy,setDefaultMusicBusy]=useState(false);
  const toggleDefaultMusic=async(item:BackgroundMusic)=>{setDefaultMusicBusy(true);setMusicError("");try{const response=await fetch(`${API}/api/background-music/${item.id}/default`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({is_default:!item.is_default})});if(!response.ok)throw new Error("默认音乐设置失败，请重试");await loadMusic();}catch(reason){setMusicError(reason instanceof Error?reason.message:"默认音乐设置失败");}finally{setDefaultMusicBusy(false)}};
  const editMusic=(item:BackgroundMusic)=>{setEditingMusicId(item.id);setMusicForm({name:item.name,url:item.url,category:item.category});setMusicError("")};
  const cancelMusicEdit=()=>{setEditingMusicId(null);setMusicForm({name:"",url:"",category:""});setMusicError("")};
  const removeMusic=async(id:string)=>{await fetch(`${API}/api/background-music/${id}`,{method:"DELETE"});if(playingMusic?.id===id)setPlayingMusic(null);if(editingMusicId===id)cancelMusicEdit();void loadMusic()};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal config-modal settings-modal voice-settings-modal"><div className="modal-head"><div><p className="eyebrow">声音工作台</p><h2>语音设置</h2></div><button className="close" onClick={onClose}>×</button></div><nav className="settings-tabs voice-settings-tabs" aria-label="语音设置分类"><button className={tab==="speech"?"active":""} onClick={()=>setTab("speech")}><span>声</span><div><b>微软语音服务</b><small>接口与默认合成参数</small></div></button><button className={tab==="voices"?"active":""} onClick={()=>setTab("voices")}><span>库</span><div><b>音色中心</b><small>搜索、试听与离线下载</small></div></button><button className={tab==="music"?"active":""} onClick={()=>setTab("music")}><span>乐</span><div><b>背景音乐</b><small>管理在线音频素材</small></div></button></nav><div className="settings-pane voice-settings-pane">
    {tab==="speech"&&<div className="settings-block speech-pane"><h3>微软语音服务</h3><div className="form-grid"><label>语音 API 地址<input value={form.azure_speech_base} onChange={e=>setForm({...form,azure_speech_base:e.target.value})} placeholder="https://eastus.tts.speech.microsoft.com"/></label><label>Speech 密钥<input type="password" value={form.azure_speech_key} onChange={e=>setForm({...form,azure_speech_key:e.target.value})} placeholder="已优先读取 .env"/></label></div><div className="format-control"><span>音频格式</span><FormatSelect formats={speechFormats} value={form.voice_format} onChange={voice_format=>setForm({...form,voice_format})}/></div><VoiceControl label="默认音色" voices={voices.map(v=>v.short_name)} value={form.voices[0]||""} onChange={voice=>setForm({...form,voices:[voice]})}/><SpeechRateControl value={form.speech_rate} onChange={speech_rate=>setForm({...form,speech_rate})}/></div>}
    {tab==="voices"&&<VoiceCenter voices={voices} connected={connected} download={download} onDownload={downloadAll}/>}
    {tab==="music"&&<section className="music-center"><div className="music-layout"><div className="music-composer"><h3>{editingMusicId?"编辑背景音乐":"添加背景音乐"}</h3><label>音乐名称 <em>必填</em><input value={musicForm.name} onChange={e=>setMusicForm({...musicForm,name:e.target.value})} placeholder="例如：安静的阅读时光"/></label><label>HTTPS 音频地址 <em>必填</em><input value={musicForm.url} onChange={e=>setMusicForm({...musicForm,url:e.target.value})} placeholder="https://example.com/music.mp3"/></label><label>分类 <small>选填</small><input value={musicForm.category} onChange={e=>setMusicForm({...musicForm,category:e.target.value})} placeholder="例如：治愈 / 悬疑"/></label>{musicError&&<p className="form-error">{musicError}</p>}<div className="music-form-actions">{editingMusicId&&<button className="secondary" onClick={cancelMusicEdit}>取消编辑</button>}<button className="primary" disabled={!connected} onClick={saveMusic}>{editingMusicId?"保存修改":"添加音乐"}</button></div></div><div className="music-library"><div className="panel-toolbar"><div><h3>已添加音乐</h3><p>{musicTotal} 条在线素材</p></div></div><label className="panel-search"><span>⌕</span><input value={musicQuery} onChange={e=>{setMusicQuery(e.target.value);setMusicPage(1)}} placeholder="搜索名称或分类"/></label><div className="music-list">{music.map(item=><article key={item.id}><div><b>{item.name}{item.is_default&&<em className="default-music-badge">默认</em>}</b><small>{item.category||"未分类"}</small></div><div className="music-actions"><button disabled={!connected||defaultMusicBusy} onClick={()=>void toggleDefaultMusic(item)}>{item.is_default?"取消默认":"设置默认"}</button><button onClick={()=>setPlayingMusic(item)}>试听</button><button onClick={()=>editMusic(item)}>编辑</button><button className="danger-link" onClick={()=>removeMusic(item.id)}>删除</button></div></article>)}{!music.length&&<div className="panel-empty">还没有背景音乐</div>}</div><Pagination page={musicPage} pages={musicPages} total={musicTotal} onChange={setMusicPage}/></div></div><div className="music-player"><div><b>{playingMusic?.name||"背景音乐播放器"}</b><small>{playingMusic?playingMusic.category||"未分类":"点击列表中的试听按钮开始播放"}</small></div><audio key={playingMusic?.id||"empty"} controls autoPlay={Boolean(playingMusic)} src={playingMusic?.url}/></div></section>}
  </div>{tab==="speech"&&<p className="privacy-note">密钥从服务端 .env 自动读取；声音合成使用 SSML，并应用所选音色与语速。</p>}<div className="modal-actions"><button className="secondary action-button" onClick={onClose}><span aria-hidden="true">×</span>取消</button>{tab==="speech"&&<button className="primary action-button" onClick={save} disabled={saving}><span aria-hidden="true">✓</span>{saving?"保存中…":"保存语音设置"}</button>}</div></div></div>;
}
