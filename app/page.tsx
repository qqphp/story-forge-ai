"use client";
/* eslint-disable @next/next/no-img-element, jsx-a11y/media-has-caption, jsx-a11y/label-has-associated-control */

import { FormEvent, useEffect, useMemo, useState } from "react";

type PromptTemplate = { id: string; kind: "writing" | "cover"; name: string; text: string };
type Asset = { url: string; voice?: string; prompt?: string; draft_id?: string };
type Draft = { id: string; prompt: string; text: string };
type Workflow = {
  id: string; book_title: string; author: string; edition: string; status: string;
  step: number; progress: number; created_at: number; description?: string; error?: string;
  original_drafts?: Draft[]; polished_drafts?: Draft[]; covers?: Asset[]; audio?: Asset[]; videos?: Asset[];
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const stages = ["理解书籍", "撰写文案", "自然化优化", "生成配音", "创作封面", "合成视频"];

const seedTasks: Workflow[] = [
  { id: "sample-1", book_title: "悉达多", author: "赫尔曼·黑塞", edition: "", status: "completed", step: 6, progress: 100, created_at: Math.floor(Date.now()/1000)-6800, description: "一个关于寻找、经历与自我抵达的故事。", original_drafts: [], polished_drafts: [], covers: [], audio: [], videos: [] },
  { id: "sample-2", book_title: "局外人", author: "阿尔贝·加缪", edition: "上海译文版", status: "running", step: 4, progress: 68, created_at: Math.floor(Date.now()/1000)-900, description: "", original_drafts: [], polished_drafts: [], covers: [], audio: [], videos: [] },
];

export default function Home() {
  const [tasks, setTasks] = useState<Workflow[]>(seedTasks);
  const [selected, setSelected] = useState<Workflow | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPrompts, setShowPrompts] = useState(false);
  const [toast, setToast] = useState("");
  const [connected, setConnected] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  async function loadTasks() {
    try {
      const res = await fetch(`${API}/api/workflows`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setConnected(true);
      setTasks(data.length ? data : []);
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

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setSelected(null)} aria-label="返回工作台">
          <span className="brand-mark">砚</span><span><b>砚界</b><small>STORYFORGE AI</small></span>
        </button>
        <div className="top-actions">
          <span className={`connection ${connected ? "online" : ""}`}><i />{connected ? "服务已连接" : "演示模式"}</span>
          <button className="library-button" onClick={() => setShowPrompts(true)}>提示词库</button>
          <button className="icon-button" onClick={() => setShowSettings(true)} aria-label="打开设置">⚙</button>
          <button className="avatar" aria-label="账户">舟</button>
        </div>
      </header>

      <section className="content">
        <div className="hero-row">
          <div><p className="eyebrow">创作工作台</p><h1>把一本书，讲给更多人听。</h1><p className="subtitle">从书籍信息到文案、配音、封面与视频，一次输入，自动完成。</p></div>
          <button className="primary" onClick={() => setShowCreate(true)}><span>＋</span> 开始新制作</button>
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
          </div>
        </div>

        {shown.length ? <div className="task-grid">{shown.map(task => <TaskCard key={task.id} task={task} onOpen={() => setSelected(task)} />)}</div> : <div className="empty"><span>册</span><h3>还没有作品</h3><p>从一本打动你的书开始。</p><button className="primary" onClick={() => setShowCreate(true)}>开始新制作</button></div>}
      </section>

      {showCreate && <CreateDialog connected={connected} onClose={() => setShowCreate(false)} onSubmit={createWorkflow} />}
      {showPrompts && <PromptLibraryDialog connected={connected} onClose={() => setShowPrompts(false)} onSaved={() => setToast("提示词库已更新")} />}
      {showSettings && <SettingsDialog connected={connected} onClose={() => setShowSettings(false)} onSaved={() => { setToast("配置已保存"); setShowSettings(false); loadTasks(); }} />}
      {selected && <DetailPanel task={selected} onClose={() => setSelected(null)} onRetry={async () => { await fetch(`${API}/api/workflows/${selected.id}/retry`, {method:"POST"}); setToast("已重新开始制作"); }} />}
      {toast && <div className="toast" role="status" onAnimationEnd={() => setToast("")}>{toast}</div>}
    </main>
  );
}

function TaskCard({ task, onOpen }: { task: Workflow; onOpen: () => void }) {
  const date = new Date(task.created_at * 1000).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  return <button className="task-card" onClick={onOpen}>
    <div className="book-cover"><span>{task.book_title.slice(0, 8)}</span><small>{task.author || "佚名"}</small></div>
    <div className="task-body"><div className="task-title"><div><h3>{task.book_title}</h3><p>{task.author || "未填写作者"}</p></div><Status value={task.status} /></div>
      {task.status === "running" || task.status === "queued" ? <><div className="stage-label"><span>{stages[Math.max(0, task.step - 1)] || "准备中"}</span><b>{task.progress}%</b></div><div className="progress"><i style={{width:`${task.progress}%`}} /></div></> : <p className="desc">{task.description || "文案、配音、封面与视频已准备就绪"}</p>}
      <div className="task-foot"><span>{date}</span><b>查看作品 →</b></div>
    </div>
  </button>;
}

function Status({ value }: { value: string }) {
  const map: Record<string,string> = { completed:"已完成", running:"制作中", queued:"排队中", failed:"需处理" };
  return <span className={`status ${value}`}>{map[value] || value}</span>;
}

function CreateDialog({ connected, onClose, onSubmit }: { connected: boolean; onClose: () => void; onSubmit: (data: Record<string, unknown>) => Promise<void> }) {
  const [title, setTitle] = useState(""); const [author, setAuthor] = useState(""); const [edition, setEdition] = useState("");
  const fallback: PromptTemplate[] = [{id:"writing-short-video",kind:"writing",name:"短视频口播",text:"适合 2 分钟短视频口播，有真实阅读感受"},{id:"writing-insight",kind:"writing",name:"反常识洞见",text:"从一个反常识观点切入，避免剧透"},{id:"cover-literary",kind:"cover",name:"文学质感",text:"克制的文学感，竖版构图，无文字"}];
  const [templates, setTemplates] = useState<PromptTemplate[]>(fallback);
  const [selectedIds, setSelectedIds] = useState<string[]>(fallback.map(x=>x.id));
  const [busy, setBusy] = useState(false);
  useEffect(()=>{if(connected) fetch(`${API}/api/prompts`).then(r=>r.json()).then((items:PromptTemplate[])=>{setTemplates(items);setSelectedIds(items.map(x=>x.id));}).catch(()=>{});},[connected]);
  const submit = async (e: FormEvent) => { e.preventDefault(); if (!title.trim()) return; setBusy(true); try { await onSubmit({book_title:title.trim(),author:author.trim(),edition:edition.trim(),writing_prompt_ids:templates.filter(x=>x.kind==="writing"&&selectedIds.includes(x.id)).map(x=>x.id),cover_prompt_ids:templates.filter(x=>x.kind==="cover"&&selectedIds.includes(x.id)).map(x=>x.id)}); } finally { setBusy(false); } };
  return <div className="modal-backdrop" role="presentation" onMouseDown={e => e.target === e.currentTarget && onClose()}><form className="modal create-modal" onSubmit={submit}>
    <div className="modal-head"><div><p className="eyebrow">新建工作流</p><h2>从哪一本书开始？</h2></div><button type="button" className="close" onClick={onClose}>×</button></div>
    <div className="form-grid"><label className="wide">书籍名称 <em>必填</em><input required value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：百年孤独" /></label><label>作者 <small>选填</small><input value={author} onChange={e=>setAuthor(e.target.value)} placeholder="加西亚·马尔克斯" /></label><label>版本 <small>选填</small><input value={edition} onChange={e=>setEdition(e.target.value)} placeholder="例如：2017 纪念版" /></label></div>
    <TemplatePicker title="分享稿提示词" hint="勾选几个，就生成几篇独立分享稿" kind="writing" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/>
    <TemplatePicker title="封面提示词" hint="勾选几个，就生成几张不同封面" kind="cover" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/>
    <div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>取消</button><button className="primary" disabled={busy || !title.trim() || selectedIds.length===0}>{busy ? "正在创建…" : "开始自动制作 →"}</button></div>
  </form></div>;
}

function TemplatePicker({title,hint,kind,templates,selected,setSelected}:{title:string;hint:string;kind:"writing"|"cover";templates:PromptTemplate[];selected:string[];setSelected:(v:string[])=>void}) {
  const items=templates.filter(x=>x.kind===kind);
  return <section className="prompt-editor"><div><h3>{title}</h3><p>{hint}</p></div><div className="template-picker">{items.map(item=><label key={item.id} className={selected.includes(item.id)?"picked":""}><input type="checkbox" checked={selected.includes(item.id)} onChange={e=>setSelected(e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/><span><b>{item.name}</b><small>{item.text}</small></span></label>)}</div>{!items.length&&<p className="empty-hint">请先到提示词库添加配置</p>}</section>;
}

function PromptLibraryDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [kind,setKind]=useState<"writing"|"cover">("writing");
  const [items,setItems]=useState<PromptTemplate[]>([]); const [name,setName]=useState(""); const [text,setText]=useState("");
  const load=()=>connected&&fetch(`${API}/api/prompts`).then(r=>r.json()).then(setItems).catch(()=>{});
  useEffect(()=>{if(connected) void fetch(`${API}/api/prompts`).then(r=>r.json()).then(setItems).catch(()=>{});},[connected]);
  const add=async()=>{if(!name.trim()||!text.trim())return;const res=await fetch(`${API}/api/prompts`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind,name,text})});if(res.ok){setName("");setText("");load();onSaved();}};
  const update=async(item:PromptTemplate)=>{await fetch(`${API}/api/prompts/${item.id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:item.name,text:item.text})});load();onSaved();};
  const remove=async(id:string)=>{await fetch(`${API}/api/prompts/${id}`,{method:"DELETE"});load();onSaved();};
  const visible=items.filter(x=>x.kind===kind);
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal prompt-library"><div className="modal-head"><div><p className="eyebrow">全局配置</p><h2>提示词库</h2><p className="modal-subtitle">集中维护模板，新建工作流时直接勾选</p></div><button className="close" onClick={onClose}>×</button></div><div className="library-tabs"><button className={kind==="writing"?"active":""} onClick={()=>setKind("writing")}>分享稿提示词</button><button className={kind==="cover"?"active":""} onClick={()=>setKind("cover")}>封面提示词</button></div><div className="template-list">{visible.map((item,index)=><article key={item.id}><span className="template-number">{String(index+1).padStart(2,"0")}</span><div><input aria-label="提示词名称" value={item.name} onChange={e=>setItems(items.map(x=>x.id===item.id?{...x,name:e.target.value}:x))}/><textarea aria-label="提示词内容" value={item.text} onChange={e=>setItems(items.map(x=>x.id===item.id?{...x,text:e.target.value}:x))}/><div className="template-actions"><button onClick={()=>remove(item.id)}>删除</button><button className="save-prompt" onClick={()=>update(item)}>保存修改</button></div></div></article>)}</div><section className="new-template"><h3>添加新模板</h3><input value={name} onChange={e=>setName(e.target.value)} placeholder="模板名称"/><textarea value={text} onChange={e=>setText(e.target.value)} placeholder={kind==="writing"?"描述分享稿的语气、结构和长度要求":"描述封面的风格、构图和色彩要求"}/><button className="primary" disabled={!connected||!name.trim()||!text.trim()} onClick={add}>＋ 添加到提示词库</button></section></div></div>;
}

function DetailPanel({task,onClose,onRetry}:{task:Workflow;onClose:()=>void;onRetry:()=>void}) {
  const [tab,setTab]=useState("overview"); const [compare,setCompare]=useState(0);
  const tabs=[['overview','概览'],['drafts','分享稿'],['covers','封面'],['audio','配音'],['videos','视频']];
  return <div className="drawer-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><aside className="drawer">
    <div className="drawer-head"><button className="close" onClick={onClose}>×</button><div><p className="eyebrow">作品详情</p><h2>{task.book_title}</h2><p>{task.author}{task.edition ? ` · ${task.edition}`:""}</p></div><Status value={task.status}/></div>
    <nav className="tabs">{tabs.map(([id,label])=><button key={id} className={tab===id?"active":""} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    <div className="drawer-content">
      {task.status!=="completed"&&<div className="pipeline"><div className="pipeline-head"><span>{task.status==="failed"?"制作遇到问题":`正在${stages[Math.max(0,task.step-1)]||"准备"}`}</span><b>{task.progress}%</b></div><div className="progress"><i style={{width:`${task.progress}%`}}/></div><div className="steps">{stages.map((s,i)=><span className={i<task.step?"done":i===task.step?"now":""} key={s}>{i<task.step?"✓":i+1}<small>{s}</small></span>)}</div>{task.error&&<p className="error">{task.error} <button onClick={onRetry}>重试</button></p>}</div>}
      {tab==="overview"&&<section className="result-section"><h3>书籍简介</h3><div className="paper">{task.description||"简介将在书籍解析完成后出现。"}</div><h3>产出清单</h3><div className="asset-summary"><span><b>{task.polished_drafts?.length||0}</b> 篇分享稿</span><span><b>{task.audio?.length||0}</b> 份配音</span><span><b>{task.covers?.length||0}</b> 张封面</span><span><b>{task.videos?.length||0}</b> 条视频</span></div></section>}
      {tab==="drafts"&&<section className="result-section"><div className="section-inline"><h3>分享稿对比</h3>{(task.polished_drafts?.length||0)>1&&<select value={compare} onChange={e=>setCompare(+e.target.value)}>{task.polished_drafts?.map((d,i)=><option key={d.id} value={i}>版本 {i+1}</option>)}</select>}</div><div className="compare"><article><label>原始稿</label><p>{task.original_drafts?.[compare]?.text||"尚未生成"}</p></article><article className="polished"><label>自然化优化稿</label><p>{task.polished_drafts?.[compare]?.text||"尚未生成"}</p></article></div></section>}
      {tab==="covers"&&<section className="media-grid">{task.covers?.length?<>{task.covers.map((a,i)=><figure key={i}><img src={`${API}${a.url}`} alt={`${task.book_title}封面 ${i+1}`}/><figcaption>{a.prompt}</figcaption></figure>)}</>:<EmptyMedia text="封面尚未生成"/>}</section>}
      {tab==="audio"&&<section className="audio-list">{task.audio?.length?task.audio.map((a,i)=><article key={i}><span>声</span><div><b>{a.voice}</b><small>分享稿 {i+1}</small></div><audio controls preload="none" src={`${API}${a.url}`}/></article>):<EmptyMedia text="配音尚未生成"/>}</section>}
      {tab==="videos"&&<section className="video-grid">{task.videos?.length?task.videos.map((a,i)=><figure key={i}><video controls preload="metadata" src={`${API}${a.url}`}/><figcaption>{a.voice} · 分享稿 {i+1}</figcaption></figure>):<EmptyMedia text="视频尚未生成"/>}</section>}
    </div>
  </aside></div>;
}

function EmptyMedia({text}:{text:string}) { return <div className="empty-media"><span>◇</span><p>{text}</p></div> }

function SettingsDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [form,setForm]=useState({api_base:"https://api.teamorouter.com/v1",model:"gpt-5.4-mini",image_model:"gpt-image-2",api_key:"",azure_speech_key:"",azure_speech_region:"eastus",voice_format:"audio-24khz-48kbitrate-mono-mp3",voices:["zh-CN-XiaoxiaoNeural"]});
  const [models,setModels]=useState<string[]>([]); const [voiceList,setVoiceList]=useState<string[]>(["zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural","zh-CN-XiaoyiNeural"]); const [saving,setSaving]=useState(false);
  useEffect(()=>{if(connected){fetch(`${API}/api/settings`).then(r=>r.json()).then(setForm).catch(()=>{});fetch(`${API}/api/voices`).then(r=>r.json()).then(d=>setVoiceList(d.voices)).catch(()=>{});fetch(`${API}/api/models`).then(r=>r.json()).then(d=>setModels(d.models)).catch(()=>{});}},[connected]);
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);try{await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});onSaved();}finally{setSaving(false)}};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal settings-modal"><div className="modal-head"><div><p className="eyebrow">创作引擎</p><h2>接口与声音设置</h2></div><button className="close" onClick={onClose}>×</button></div><div className="settings-block"><h3>TeamoRouter · OpenAI 兼容接口</h3><label>API 地址<input value={form.api_base} onChange={e=>setForm({...form,api_base:e.target.value})}/></label><div className="form-grid"><label>文案模型{models.length?<select value={form.model} onChange={e=>setForm({...form,model:e.target.value})}>{models.filter(m=>m!=="gpt-image-2").map(m=><option key={m}>{m}</option>)}</select>:<input value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/>}</label><label>图片模型<input value={form.image_model} onChange={e=>setForm({...form,image_model:e.target.value})}/></label><label>API 密钥<input type="password" value={form.api_key} onChange={e=>setForm({...form,api_key:e.target.value})} placeholder="已优先读取 .env"/></label></div></div><div className="settings-block"><h3>微软语音服务</h3><div className="form-grid"><label>区域<input value={form.azure_speech_region} onChange={e=>setForm({...form,azure_speech_region:e.target.value})}/></label><label>Speech 密钥<input type="password" value={form.azure_speech_key} onChange={e=>setForm({...form,azure_speech_key:e.target.value})} placeholder="已优先读取 .env"/></label></div><label>音频格式<select value={form.voice_format} onChange={e=>setForm({...form,voice_format:e.target.value})}><option>audio-24khz-48kbitrate-mono-mp3</option><option>audio-16khz-32kbitrate-mono-mp3</option><option>riff-24khz-16bit-mono-pcm</option></select></label><div className="choice-field"><span>默认音色（可多选）</span><div className="voice-choices">{voiceList.map(v=><button type="button" aria-pressed={form.voices.includes(v)} className={form.voices.includes(v)?"selected":""} key={v} onClick={()=>setForm({...form,voices:form.voices.includes(v)?form.voices.filter(x=>x!==v):[...form.voices,v]})}>{form.voices.includes(v)?"✓ ":""}{v}</button>)}</div></div></div><p className="privacy-note">密钥从本机 .env 自动读取，不会发送到前端或写入源码。</p><div className="modal-actions"><button className="secondary" onClick={onClose}>取消</button><button className="primary" onClick={save} disabled={saving}>{saving?"保存中…":"保存设置"}</button></div></div></div>;
}
