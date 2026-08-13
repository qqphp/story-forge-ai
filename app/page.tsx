"use client";
/* eslint-disable @next/next/no-img-element, jsx-a11y/media-has-caption, jsx-a11y/label-has-associated-control */

import { FormEvent, useEffect, useMemo, useState } from "react";

type Prompt = { text: string; enabled: boolean };
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

      {showCreate && <CreateDialog onClose={() => setShowCreate(false)} onSubmit={createWorkflow} />}
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

function CreateDialog({ onClose, onSubmit }: { onClose: () => void; onSubmit: (data: Record<string, unknown>) => Promise<void> }) {
  const [title, setTitle] = useState(""); const [author, setAuthor] = useState(""); const [edition, setEdition] = useState("");
  const [writing, setWriting] = useState<Prompt[]>([{text:"适合 2 分钟短视频口播，有真实阅读感受",enabled:true},{text:"从一个反常识观点切入，避免剧透",enabled:true}]);
  const [covers, setCovers] = useState<Prompt[]>([{text:"克制的文学感，竖版构图，留出标题空间",enabled:true}]);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => { e.preventDefault(); if (!title.trim()) return; setBusy(true); try { await onSubmit({book_title:title.trim(),author:author.trim(),edition:edition.trim(),writing_prompts:writing,cover_prompts:covers}); } finally { setBusy(false); } };
  return <div className="modal-backdrop" role="presentation" onMouseDown={e => e.target === e.currentTarget && onClose()}><form className="modal create-modal" onSubmit={submit}>
    <div className="modal-head"><div><p className="eyebrow">新建工作流</p><h2>从哪一本书开始？</h2></div><button type="button" className="close" onClick={onClose}>×</button></div>
    <div className="form-grid"><label className="wide">书籍名称 <em>必填</em><input required value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：百年孤独" /></label><label>作者 <small>选填</small><input value={author} onChange={e=>setAuthor(e.target.value)} placeholder="加西亚·马尔克斯" /></label><label>版本 <small>选填</small><input value={edition} onChange={e=>setEdition(e.target.value)} placeholder="例如：2017 纪念版" /></label></div>
    <PromptEditor title="分享稿提示词" hint="每个已启用提示词会生成一篇独立分享稿" items={writing} setItems={setWriting} />
    <PromptEditor title="封面提示词" hint="每个已启用提示词会生成一张封面" items={covers} setItems={setCovers} />
    <div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>取消</button><button className="primary" disabled={busy || !title.trim()}>{busy ? "正在创建…" : "开始自动制作 →"}</button></div>
  </form></div>;
}

function PromptEditor({title,hint,items,setItems}:{title:string;hint:string;items:Prompt[];setItems:(v:Prompt[])=>void}) {
  return <section className="prompt-editor"><div><h3>{title}</h3><p>{hint}</p></div>{items.map((item,i)=><div className="prompt-row" key={i}><input type="checkbox" checked={item.enabled} onChange={e=>setItems(items.map((x,j)=>j===i?{...x,enabled:e.target.checked}:x))}/><input value={item.text} onChange={e=>setItems(items.map((x,j)=>j===i?{...x,text:e.target.value}:x))}/><button type="button" onClick={()=>setItems(items.filter((_,j)=>j!==i))}>×</button></div>)}<button type="button" className="add-prompt" onClick={()=>setItems([...items,{text:"",enabled:true}])}>＋ 添加提示词</button></section>;
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
  const [form,setForm]=useState({api_base:"https://api.openai.com/v1",model:"gpt-4o-mini",api_key:"",azure_speech_key:"",azure_speech_region:"eastus",voice_format:"audio-24khz-48kbitrate-mono-mp3",voices:["zh-CN-XiaoxiaoNeural"]});
  const [voiceList,setVoiceList]=useState<string[]>(["zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural","zh-CN-XiaoyiNeural"]); const [saving,setSaving]=useState(false);
  useEffect(()=>{if(connected){fetch(`${API}/api/settings`).then(r=>r.json()).then(setForm).catch(()=>{});fetch(`${API}/api/voices`).then(r=>r.json()).then(d=>setVoiceList(d.voices)).catch(()=>{});}},[connected]);
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);try{await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});onSaved();}finally{setSaving(false)}};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal settings-modal"><div className="modal-head"><div><p className="eyebrow">创作引擎</p><h2>接口与声音设置</h2></div><button className="close" onClick={onClose}>×</button></div><div className="settings-block"><h3>大模型接口</h3><label>API 地址<input value={form.api_base} onChange={e=>setForm({...form,api_base:e.target.value})}/></label><div className="form-grid"><label>模型<input value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/></label><label>API 密钥<input type="password" value={form.api_key} onChange={e=>setForm({...form,api_key:e.target.value})} placeholder="sk-…"/></label></div></div><div className="settings-block"><h3>微软语音服务</h3><div className="form-grid"><label>区域<input value={form.azure_speech_region} onChange={e=>setForm({...form,azure_speech_region:e.target.value})}/></label><label>Speech 密钥<input type="password" value={form.azure_speech_key} onChange={e=>setForm({...form,azure_speech_key:e.target.value})}/></label></div><label>音频格式<select value={form.voice_format} onChange={e=>setForm({...form,voice_format:e.target.value})}><option>audio-24khz-48kbitrate-mono-mp3</option><option>audio-16khz-32kbitrate-mono-mp3</option><option>riff-24khz-16bit-mono-pcm</option></select></label><div className="choice-field"><span>默认音色（可多选）</span><div className="voice-choices">{voiceList.map(v=><button type="button" aria-pressed={form.voices.includes(v)} className={form.voices.includes(v)?"selected":""} key={v} onClick={()=>setForm({...form,voices:form.voices.includes(v)?form.voices.filter(x=>x!==v):[...form.voices,v]})}>{form.voices.includes(v)?"✓ ":""}{v}</button>)}</div></div></div><p className="privacy-note">密钥仅保存在本机数据库中。未配置密钥时，系统会使用演示内容跑通完整流程。</p><div className="modal-actions"><button className="secondary" onClick={onClose}>取消</button><button className="primary" onClick={save} disabled={saving}>{saving?"保存中…":"保存设置"}</button></div></div></div>;
}
