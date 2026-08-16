"use client";
/* eslint-disable @next/next/no-img-element, jsx-a11y/media-has-caption, jsx-a11y/label-has-associated-control */

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type PromptTemplate = { id: string; kind: "writing" | "cover"; name: string; text: string; image_sizes?: string[] };
type Asset = { url: string; voice?: string; speech_rate?: number; prompt?: string; prompt_name?: string; image_ratio?: string; resolution?: string; draft_id?: string };
type Draft = { id: string; prompt: string; text: string };
type VoiceItem = { short_name:string; locale:string; local_name:string; display_name:string; gender:string };
type BackgroundMusic = { id:string; name:string; url:string; category:string; created_at:number };
type RequestLog = { id:number; request_type:string; request_url:string; request_params:Record<string,unknown>; created_at:number };
type PublishPlatform = "douyin"|"kuaishou"|"bilibili"|"xiaohongshu"|"baijiahao";
type PublishTask = { id:string; workflow_id:string; book_title:string; platform:PublishPlatform; status:string; title:string; description:string; tags:string[]; topics:string[]; video_url:string; cover_url:string; covers:Asset[]; created_at:number; updated_at:number; error:string };
type WorkspacePage = "workspace" | "publish" | "prompts" | "models" | "voice" | "logs";
type AppSettings = { api_base:string; model:string; image_model:string; api_key:string; azure_speech_key:string; azure_speech_region:string; voice_format:string; voices:string[]; speech_rate:number };
type Workflow = {
  id: string; book_title: string; author: string; edition: string; status: string;
  step: number; progress: number; created_at: number; description?: string; error?: string;
  output_dir?: string; tags?: string[]; topics?: string[]; original_drafts?: Draft[]; polished_drafts?: Draft[]; covers?: Asset[]; audio?: Asset[]; videos?: Asset[]; cover_prompts?: PromptTemplate[];
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const stages = ["理解书籍", "撰写文案", "自然化优化", "生成配音", "生成标签和话题", "创作封面", "合成视频"];
const publishPlatforms:{id:PublishPlatform;name:string;mark:string;hint:string;url:string}[]=[
  {id:"douyin",name:"抖音",mark:"音",hint:"视频、标题、简介、话题与封面",url:"https://creator.douyin.com/creator-micro/content/upload"},
  {id:"kuaishou",name:"快手",mark:"快",hint:"视频、标题、描述与话题",url:"https://cp.kuaishou.com/article/publish/video"},
  {id:"bilibili",name:"哔哩哔哩",mark:"B",hint:"视频、标题、简介与标签",url:"https://member.bilibili.com/platform/upload/video/frame"},
  {id:"xiaohongshu",name:"小红书",mark:"红",hint:"视频、标题、正文与话题",url:"https://creator.xiaohongshu.com/publish/publish?source=storyforge"},
  {id:"baijiahao",name:"百家号",mark:"百",hint:"视频、标题、正文与话题",url:"https://baijiahao.baidu.com/builder/rc/home"},
];
const speechFormats = ["amr-wb-16000hz","audio-16khz-16bit-32kbps-mono-opus","audio-16khz-32kbitrate-mono-mp3","audio-16khz-64kbitrate-mono-mp3","audio-16khz-128kbitrate-mono-mp3","audio-24khz-16bit-24kbps-mono-opus","audio-24khz-16bit-48kbps-mono-opus","audio-24khz-48kbitrate-mono-mp3","audio-24khz-96kbitrate-mono-mp3","audio-24khz-160kbitrate-mono-mp3","audio-48khz-96kbitrate-mono-mp3","audio-48khz-192kbitrate-mono-mp3","g722-16khz-64kbps","ogg-16khz-16bit-mono-opus","ogg-24khz-16bit-mono-opus","ogg-48khz-16bit-mono-opus","raw-8khz-8bit-mono-alaw","raw-8khz-8bit-mono-mulaw","raw-8khz-16bit-mono-pcm","raw-16khz-16bit-mono-pcm","raw-16khz-16bit-mono-truesilk","raw-22050hz-16bit-mono-pcm","raw-24khz-16bit-mono-pcm","raw-24khz-16bit-mono-truesilk","raw-44100hz-16bit-mono-pcm","raw-48khz-16bit-mono-pcm","webm-16khz-16bit-mono-opus","webm-24khz-16bit-24kbps-mono-opus","webm-24khz-16bit-mono-opus"];
const defaultSettings = (): AppSettings => ({api_base:"https://api.teamorouter.com/v1",model:"gpt-5.4-mini",image_model:"gpt-image-2",api_key:"",azure_speech_key:"",azure_speech_region:"eastus",voice_format:"audio-24khz-48kbitrate-mono-mp3",voices:["zh-CN-XiaoxiaoNeural"],speech_rate:0});

const seedTasks: Workflow[] = [
  { id: "sample-1", book_title: "悉达多", author: "赫尔曼·黑塞", edition: "", status: "completed", step: 7, progress: 100, created_at: Math.floor(Date.now()/1000)-6800, description: "一个关于寻找、经历与自我抵达的故事。", tags: ["文学","成长"], topics: ["读书","好书推荐"], original_drafts: [], polished_drafts: [], covers: [], audio: [], videos: [] },
  { id: "sample-2", book_title: "局外人", author: "阿尔贝·加缪", edition: "上海译文版", status: "running", step: 4, progress: 68, created_at: Math.floor(Date.now()/1000)-900, description: "", original_drafts: [], polished_drafts: [], covers: [], audio: [], videos: [] },
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
      const res = await fetch(`${API}/api/workflows`);
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
          <button className={activePage==="publish"?"active":""} onClick={()=>setActivePage("publish")}><span>发</span>发布中心</button>
          <button className={activePage==="prompts"?"active":""} onClick={()=>setActivePage("prompts")}><span>✦</span>提示词库</button>
          <button className={activePage==="models"?"active":""} onClick={()=>setActivePage("models")}><span>AI</span>模型配置</button>
          <button className={activePage==="voice"?"active":""} onClick={()=>setActivePage("voice")}><span>声</span>语音设置</button>
          <button className={activePage==="logs"?"active":""} onClick={()=>setActivePage("logs")}><span>录</span>请求日志</button>
        </nav>
        <span className={`side-connection ${connected?"online":""}`}><i/>{connected?"本地服务已连接":"本地服务未连接"}</span>
      </aside>
      <section className="workspace-main">
      <header className="topbar">
        <div className="page-heading"><b>{{workspace:"创作工作台",publish:"发布中心",prompts:"提示词库",models:"模型配置",voice:"语音设置",logs:"请求日志"}[activePage]}</b><small>本地创作与生成配置中心</small></div>
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

        {shown.length ? workView==="cards"?<div className="task-grid">{shown.map(task => <TaskCard key={task.id} task={task} onOpen={() => setSelected(task)} />)}</div>:<TaskList tasks={shown} checkedIds={checkedTaskIds} allChecked={allShownChecked} onToggleAll={()=>setCheckedTaskIds(allShownChecked?checkedTaskIds.filter(id=>!shown.some(task=>task.id===id)):[...new Set([...checkedTaskIds,...shown.map(task=>task.id)])])} onToggle={id=>setCheckedTaskIds(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id])} onOpen={setSelected} onDelete={deleteCheckedTasks}/>:<div className="empty"><span>册</span><h3>还没有作品</h3><p>从一本打动你的书开始。</p><button className="primary" onClick={() => setShowCreate(true)}>开始新制作</button></div>}
      </section>}
      {activePage==="publish"&&<MultiPublishCenterPage connected={connected} workflows={tasks} onToast={setToast}/>}
      {activePage==="prompts"&&<section className="config-page"><PromptLibraryDialog connected={connected} onClose={()=>setActivePage("workspace")} onSaved={()=>setToast("提示词库已更新")}/></section>}
      {activePage==="models"&&<section className="config-page"><SettingsDialog connected={connected} onClose={()=>setActivePage("workspace")} onSaved={()=>{setToast("配置已保存");loadTasks()}}/></section>}
      {activePage==="voice"&&<section className="config-page"><VoiceSettingsDialog connected={connected} onClose={()=>setActivePage("workspace")} onSaved={()=>setToast("语音配置已保存")}/></section>}
      {activePage==="logs"&&<RequestLogsPage connected={connected} onToast={setToast}/>}

      {showCreate && <CreateDialog connected={connected} onClose={() => setShowCreate(false)} onSubmit={createWorkflow} />}
      {showBatch && <BatchCreateDialog connected={connected} onClose={()=>setShowBatch(false)} onSubmit={createBatch}/>}
      {selected && <DetailPanel task={selected} onClose={() => setSelected(null)} onRetry={async () => { await fetch(`${API}/api/workflows/${selected.id}/retry`, {method:"POST"}); setToast("已重新开始制作"); }} onDelete={async()=>{const res=await fetch(`${API}/api/workflows/${selected.id}`,{method:"DELETE"});if(!res.ok)throw new Error("删除失败");setSelected(null);setToast("作品及相关产物已删除");await loadTasks();}} />}
      {toast && <div className="toast" role="status" onAnimationEnd={() => setToast("")}>{toast}</div>}
      </section>
    </main>
  );
}

const DOUYIN_UPLOAD_URL="https://creator.douyin.com/creator-micro/content/upload";

function PublishCenterPage({connected,workflows,onToast}:{connected:boolean;workflows:Workflow[];onToast:(message:string)=>void}) {
  const eligible=useMemo(()=>workflows.filter(workflow=>workflow.status==="completed"&&(workflow.videos?.length||0)>0),[workflows]);
  const [workflowId,setWorkflowId]=useState(""); const [title,setTitle]=useState(""); const [description,setDescription]=useState(""); const [topics,setTopics]=useState("");
  const [videoUrl,setVideoUrl]=useState(""); const [coverUrls,setCoverUrls]=useState<string[]>([]); const [tasks,setTasks]=useState<PublishTask[]>([]); const [pairingToken,setPairingToken]=useState(""); const [saving,setSaving]=useState(false);
  const selectedWorkflowRecord=eligible.find(workflow=>workflow.id===workflowId);
  const selectedWorkflow=selectedWorkflowRecord?{...selectedWorkflowRecord,covers:(selectedWorkflowRecord.covers||[]).filter(asset=>asset.image_ratio==="3:4"||asset.image_ratio==="4:3")}:undefined;
  const load=useCallback(async()=>{if(!connected){setTasks([]);setPairingToken("");return;}const [taskResponse,pairingResponse]=await Promise.all([fetch(`${API}/api/publish/tasks?platform=douyin`),fetch(`${API}/api/publish/pairing`)]);if(taskResponse.ok)setTasks(await taskResponse.json());if(pairingResponse.ok)setPairingToken((await pairingResponse.json()).token)},[connected]);
  useEffect(()=>{const initial=window.setTimeout(()=>{void load()},0);const timer=window.setInterval(()=>{void load()},3000);return()=>{window.clearTimeout(initial);window.clearInterval(timer)}},[load]);
  const applyWorkflow=useCallback((workflow:Workflow)=>{setWorkflowId(workflow.id);setTitle(`《${workflow.book_title}》读书分享`);setDescription(workflow.description||"");setTopics((workflow.topics||[]).join(", "));setVideoUrl(workflow.videos?.[0]?.url||"");setCoverUrls((workflow.covers||[]).filter(asset=>asset.image_ratio==="3:4"||asset.image_ratio==="4:3").map(asset=>asset.url))},[]);
  const chooseWorkflow=(id:string)=>{const workflow=eligible.find(item=>item.id===id);if(!workflow){setWorkflowId("");setTitle("");setDescription("");setTopics("");setVideoUrl("");setCoverUrls([]);return;}applyWorkflow(workflow)};
  useEffect(()=>{if(workflowId||!eligible[0])return;const timer=window.setTimeout(()=>applyWorkflow(eligible[0]),0);return()=>window.clearTimeout(timer)},[applyWorkflow,eligible,workflowId]);
  const createTask=async()=>{if(!selectedWorkflow||!videoUrl||!title.trim())return;setSaving(true);try{const response=await fetch(`${API}/api/publish/tasks`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({workflow_id:selectedWorkflow.id,platform:"douyin",title:title.trim(),description:description.trim(),topics:topics.split(/[,，\n]/).map(topic=>topic.trim()).filter(Boolean).slice(0,5),video_url:videoUrl,cover_urls:coverUrls})});if(!response.ok){const detail=await response.json().catch(()=>({detail:"创建发布任务失败"}));throw new Error(detail.detail||"创建发布任务失败")}await load();onToast("抖音发布任务已准备好，请打开创作页") }catch(error){onToast(error instanceof Error?error.message:"创建发布任务失败")}finally{setSaving(false)}};
  const removeTask=async(id:string)=>{if(!window.confirm("确定删除这条发布任务吗？"))return;const response=await fetch(`${API}/api/publish/tasks/${id}`,{method:"DELETE"});if(response.ok){await load();onToast("发布任务已删除")}};
  const rotateToken=async()=>{if(!window.confirm("更新配对码后，浏览器扩展需要重新填写。确定继续吗？"))return;const response=await fetch(`${API}/api/publish/pairing/rotate`,{method:"POST"});if(response.ok){setPairingToken((await response.json()).token);onToast("配对码已更新")}};
  const statusText:Record<string,string>={prepared:"等待填充",filling:"正在填充",ready:"等待手动发布",completed:"已发布",failed:"填充失败",cancelled:"已取消"};
  return <section className="content config-content publish-center"><div className="page-section-head"><div><p className="eyebrow">LOCAL PUBLISH ASSISTANT</p><h1>发布中心</h1><p>一次整理素材，由本地扩展填充抖音创作页；最终发布由你确认。</p></div><span className="platform-chip"><i>音</i>抖音已接入</span></div>
    <div className="publish-grid"><section className="publish-composer"><div className="publish-card-head"><span>01</span><div><h2>准备抖音发布信息</h2><p>选择已完成并生成视频的作品</p></div></div>{eligible.length?<div className="publish-form"><label>选择作品<select value={workflowId} onChange={event=>chooseWorkflow(event.target.value)}>{eligible.map(workflow=><option value={workflow.id} key={workflow.id}>{workflow.book_title} · {workflow.videos?.length||0} 个视频</option>)}</select></label><label>发布标题 <small>{title.length}/100</small><input value={title} maxLength={100} onChange={event=>setTitle(event.target.value)} placeholder="填写抖音作品标题"/></label><label>作品简介 <small>{description.length}/2000</small><textarea value={description} maxLength={2000} onChange={event=>setDescription(event.target.value)} placeholder="调用作品生成的书籍简介"/></label><label>话题 <small>来自作品话题字段，可编辑，最多10个</small><input value={topics} onChange={event=>setTopics(event.target.value)} placeholder="读书, 好书推荐"/></label><div className="publish-assets single"><label>发布视频<select value={videoUrl} onChange={event=>setVideoUrl(event.target.value)}>{selectedWorkflow?.videos?.map((asset,index)=><option value={asset.url} key={asset.url}>视频 {index+1}{asset.voice?` · ${asset.voice}`:""}</option>)}</select></label></div><fieldset className="publish-cover-picker"><legend>封面参考 <small>可多选</small></legend><div>{selectedWorkflow?.covers?.map((asset,index)=><label key={asset.url} className={coverUrls.includes(asset.url)?"checked":""}><input type="checkbox" checked={coverUrls.includes(asset.url)} onChange={event=>setCoverUrls(values=>event.target.checked?[...values,asset.url]:values.filter(url=>url!==asset.url))}/><img src={`${API}${asset.url}`} alt=""/><span><b>封面 {index+1}</b><small>{asset.image_ratio||"未记录比例"}{asset.resolution?` · ${asset.resolution}`:""}</small></span></label>)}</div>{!selectedWorkflow?.covers?.length&&<p>当前作品没有可选封面</p>}<p className="publish-cover-hint">抖音默认竖封面 3:4、横封面 4:3；扩展仅将相同比例的勾选图片上传到对应位置。</p></fieldset><button className="primary publish-prepare" disabled={!connected||!workflowId||!videoUrl||!title.trim()||saving} onClick={createTask}>{saving?"正在准备…":"准备抖音发布任务"}</button></div>:<div className="panel-empty publish-empty">暂无可发布作品。请先完成一个包含视频的书籍工作流。</div>}</section>
      <aside className="extension-setup"><div className="publish-card-head"><span>02</span><div><h2>连接本地扩展</h2><p>首次使用只需配置一次</p></div></div><ol><li>在 Chrome/Edge 扩展页开启开发者模式</li><li>加载项目中的 <code>browser-extension</code> 目录</li><li>打开扩展，将下方配对码粘贴并保存</li></ol><label>本地配对码<div className="pairing-code"><code>{pairingToken||"请先启动本地服务"}</code><button disabled={!pairingToken} onClick={()=>{void navigator.clipboard.writeText(pairingToken);onToast("配对码已复制")}}>复制</button></div></label><button className="text-button" disabled={!connected} onClick={rotateToken}>更新配对码</button><p className="safe-note">扩展只访问本机 StoryForge 和抖音创作页，不读取、导出或上传 Cookie，也不会点击最终发布按钮。</p></aside>
    </div>
    <section className="publish-queue"><div className="publish-queue-head"><div><h2>抖音发布队列</h2><p>打开创作页后，扩展会读取对应任务并等待你点击填充。</p></div><button className="secondary" onClick={()=>void load()}>刷新状态</button></div><div className="publish-task-list">{tasks.map(task=><article key={task.id}><div className="publish-task-main"><span className="douyin-mark">音</span><div><b>{task.title}</b><p>《{task.book_title}》 · {task.topics.map(topic=>`#${topic}`).join(" ")||"无话题"} · {task.covers.map(cover=>cover.image_ratio).filter(Boolean).join(" / ")||"未选封面"}</p></div></div><span className={`publish-status ${task.status}`}>{statusText[task.status]||task.status}</span><time>{new Date(task.created_at*1000).toLocaleString("zh-CN")}</time><div className="publish-task-actions">{["prepared","filling","failed"].includes(task.status)&&<a href={`${DOUYIN_UPLOAD_URL}?storyforge_task=${encodeURIComponent(task.id)}`} target="_blank" rel="noreferrer">{task.status==="failed"?"重新打开":"打开抖音创作页"}</a>}<button onClick={()=>removeTask(task.id)}>删除</button></div>{task.error&&<p className="publish-error">{task.error}</p>}</article>)}{!tasks.length&&<div className="panel-empty">还没有发布任务</div>}</div></section>
  </section>;
}

function MultiPublishCenterPage({connected,workflows,onToast}:{connected:boolean;workflows:Workflow[];onToast:(message:string)=>void}) {
  const eligible=useMemo(()=>workflows.filter(workflow=>workflow.status==="completed"&&(workflow.videos?.length||0)>0),[workflows]);
  const [workflowId,setWorkflowId]=useState("");const [title,setTitle]=useState("");const [description,setDescription]=useState("");const [topics,setTopics]=useState("");const [videoUrl,setVideoUrl]=useState("");const [coverUrls,setCoverUrls]=useState<string[]>([]);const [targets,setTargets]=useState<PublishPlatform[]>(["douyin"]);const [tasks,setTasks]=useState<PublishTask[]>([]);const [pairingToken,setPairingToken]=useState("");const [saving,setSaving]=useState(false);
  const selected=eligible.find(workflow=>workflow.id===workflowId);const platformFor=(id:PublishPlatform)=>publishPlatforms.find(platform=>platform.id===id)!;
  const load=useCallback(async()=>{if(!connected){setTasks([]);setPairingToken("");return}const [taskResponse,pairingResponse]=await Promise.all([fetch(`${API}/api/publish/tasks`),fetch(`${API}/api/publish/pairing`)]);if(taskResponse.ok)setTasks(await taskResponse.json());if(pairingResponse.ok)setPairingToken((await pairingResponse.json()).token)},[connected]);
  useEffect(()=>{const initial=window.setTimeout(()=>void load(),0);const timer=window.setInterval(()=>void load(),3000);return()=>{window.clearTimeout(initial);window.clearInterval(timer)}},[load]);
  const applyWorkflow=useCallback((workflow:Workflow)=>{setWorkflowId(workflow.id);setTitle(`《${workflow.book_title}》读书分享`);setDescription(workflow.description||"");setTopics((workflow.topics||[]).join(", "));setVideoUrl(workflow.videos?.[0]?.url||"");setCoverUrls((workflow.covers||[]).filter(asset=>asset.image_ratio==="3:4"||asset.image_ratio==="4:3").map(asset=>asset.url))},[]);
  useEffect(()=>{if(!workflowId&&eligible[0]){const timer=window.setTimeout(()=>applyWorkflow(eligible[0]),0);return()=>window.clearTimeout(timer)}},[applyWorkflow,eligible,workflowId]);
  const chooseWorkflow=(id:string)=>{const workflow=eligible.find(item=>item.id===id);if(workflow)applyWorkflow(workflow)};const toggleTarget=(platform:PublishPlatform)=>setTargets(values=>values.includes(platform)?values.filter(value=>value!==platform):[...values,platform]);
  const requiresTitle=targets.some(platform=>platform!=="kuaishou");const createTasks=async()=>{if(!selected||!(requiresTitle?title.trim():true)||!videoUrl||!targets.length)return;setSaving(true);try{const payload={workflow_id:selected.id,title:title.trim(),description:description.trim(),topics:topics.split(/[,，\n]/).map(topic=>topic.trim()).filter(Boolean),video_url:videoUrl,cover_urls:coverUrls};const responses=await Promise.all(targets.map(platform=>{const topicLimit=platform==="kuaishou"?4:platform==="douyin"?5:payload.topics.length;return fetch(`${API}/api/publish/tasks`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...payload,platform,topics:payload.topics.slice(0,topicLimit)})});}));const failed=responses.filter(response=>!response.ok);if(failed.length){const data=await failed[0].json().catch(()=>({detail:"创建发布任务失败"}));throw new Error(data.detail||"创建发布任务失败")}await load();onToast(`已准备 ${targets.length} 个平台发布任务`)}catch(error){onToast(error instanceof Error?error.message:"创建发布任务失败")}finally{setSaving(false)}};
  const removeTask=async(id:string)=>{if(!window.confirm("确定删除这条发布任务吗？"))return;const response=await fetch(`${API}/api/publish/tasks/${id}`,{method:"DELETE"});if(response.ok){await load();onToast("发布任务已删除")}};const rotateToken=async()=>{if(!window.confirm("更新配对码后，浏览器扩展需要重新填写。确定继续吗？"))return;const response=await fetch(`${API}/api/publish/pairing/rotate`,{method:"POST"});if(response.ok){setPairingToken((await response.json()).token);onToast("配对码已更新")}};
  const statusText:Record<string,string>={prepared:"等待填充",filling:"正在填充",ready:"等待手动发布",completed:"已发布",failed:"填充失败",cancelled:"已取消"};const openUrl=(task:PublishTask)=>{const url=new URL(platformFor(task.platform).url);url.searchParams.set("storyforge_task",task.id);return url.toString()};
  return <section className="content config-content publish-center"><div className="page-section-head"><div><p className="eyebrow">MULTI-PLATFORM PUBLISH ASSISTANT</p><h1>发布中心</h1><p>一次准备内容，按平台独立填写；最终发布始终由你确认。</p></div><div className="platform-summary">已接入 {publishPlatforms.map(platform=><span key={platform.id}>{platform.mark}</span>)}</div></div><div className="publish-grid"><section className="publish-composer"><div className="publish-card-head"><span>01</span><div><h2>准备多平台发布内容</h2><p>通用内容只填一次，平台任务独立创建</p></div></div>{eligible.length?<div className="publish-form"><label>选择作品<select value={workflowId} onChange={event=>chooseWorkflow(event.target.value)}>{eligible.map(workflow=><option value={workflow.id} key={workflow.id}>{workflow.book_title} · {workflow.videos?.length||0} 个视频</option>)}</select></label>{requiresTitle&&<label>发布标题 <small>{title.length}/100</small><input value={title} maxLength={100} onChange={event=>setTitle(event.target.value)} /></label>}<label>作品简介 <small>{description.length}/2000</small><textarea value={description} maxLength={2000} onChange={event=>setDescription(event.target.value)} /></label><label>话题 <small>使用逗号分隔</small><input value={topics} onChange={event=>setTopics(event.target.value)} placeholder="读书, 好书推荐" /></label><p className="publish-topic-hint">快手平台支持视频关联 4 个话题，抖音平台支持视频关联 5 个话题；程序会自动截取各平台所支持的话题数量。</p><div className="publish-assets single"><label>发布视频<select value={videoUrl} onChange={event=>setVideoUrl(event.target.value)}>{selected?.videos?.map((asset,index)=><option value={asset.url} key={asset.url}>视频 {index+1}{asset.voice?` · ${asset.voice}`:""}</option>)}</select></label></div><fieldset className="publish-destinations"><legend>发布到 <small>可多选</small></legend><div>{publishPlatforms.map(platform=><label className={targets.includes(platform.id)?"selected":""} key={platform.id}><input type="checkbox" checked={targets.includes(platform.id)} onChange={()=>toggleTarget(platform.id)} /><span className={`platform-mark ${platform.id}`}>{platform.mark}</span><span><b>{platform.name}</b><small>{platform.hint}</small></span></label>)}</div></fieldset><fieldset className="publish-cover-picker"><legend>封面素材 <small>可多选</small></legend><div>{selected?.covers?.map((asset,index)=><label key={asset.url} className={coverUrls.includes(asset.url)?"checked":""}><input type="checkbox" checked={coverUrls.includes(asset.url)} onChange={event=>setCoverUrls(values=>event.target.checked?[...values,asset.url]:values.filter(url=>url!==asset.url))}/><img src={`${API}${asset.url}`} alt=""/><span><b>封面 {index+1}</b><small>{asset.image_ratio||"未记录比例"}</small></span></label>)}</div><p className="publish-cover-hint">抖音仅会接收 3:4 或 4:3 原图；其他平台由扩展识别可用上传控件，无法匹配时会提示你手动补充。</p><p className="publish-cover-hint">快手视频发布使用一张3:4的图片即可，需要勾选3:4图片尺寸。</p></fieldset><button className="primary publish-prepare" disabled={!connected||!workflowId||!videoUrl||!(requiresTitle?title.trim():true)||!targets.length||saving} onClick={createTasks}>{saving?"正在准备…":`准备 ${targets.length} 个平台发布任务`}</button></div>:<div className="panel-empty publish-empty">暂无可发布作品。请先完成一个包含视频的书籍工作流。</div>}</section><aside className="extension-setup"><div className="publish-card-head"><span>02</span><div><h2>连接本地扩展</h2><p>一个扩展支持全部平台</p></div></div><ol><li>下载并解压下方 ZIP 文件</li><li>在 Chrome/Edge 扩展页开启开发者模式</li><li>选择“加载已解压的扩展程序”，并加载 browser-extension 目录</li><li>打开扩展，粘贴配对码后选择要发布的平台</li></ol><label>本地配对码<div className="pairing-code"><code>{pairingToken||"请先启动本地服务"}</code><button disabled={!pairingToken} onClick={()=>{void navigator.clipboard.writeText(pairingToken);onToast("配对码已复制")}}>复制</button></div></label><button className="text-button" disabled={!connected} onClick={rotateToken}>更新配对码</button><p className="safe-note">扩展仅填写已打开平台的内容和可识别上传控件，不读取 Cookie、不绕过登录或验证码，也不会点击最终发布按钮。</p><a className="primary extension-download" href={`${API}/api/publish/extension/download`}>下载浏览器扩展 ZIP</a></aside></div><section className="publish-queue"><div className="publish-queue-head"><div><h2>多平台发布队列</h2><p>每个平台有一条独立任务；填写完成后请你在对应平台亲自发布。</p></div><button className="secondary" onClick={()=>void load()}>刷新状态</button></div><div className="publish-task-list">{tasks.map(task=>{const platform=platformFor(task.platform);return <article key={task.id}><div className="publish-task-main"><span className={`platform-mark ${task.platform}`}>{platform.mark}</span><div><b>{platform.name}{task.title?` · ${task.title}`:""}</b><p>《{task.book_title}》 · {task.topics.map(topic=>`#${topic}`).join(" ")||"无话题"}</p></div></div><span className={`publish-status ${task.status}`}>{statusText[task.status]||task.status}</span><time>{new Date(task.created_at*1000).toLocaleString("zh-CN")}</time><div className="publish-task-actions">{["prepared","filling","failed"].includes(task.status)&&<a href={openUrl(task)} target="_blank" rel="noreferrer">{task.status==="failed"?"重新打开":"打开创作页"}</a>}<button onClick={()=>removeTask(task.id)}>删除</button></div>{task.error&&<p className="publish-error">{task.error}</p>}</article>})}{!tasks.length&&<div className="panel-empty">还没有发布任务</div>}</div></section></section>;
}

function RequestLogsPage({connected,onToast}:{connected:boolean;onToast:(message:string)=>void}) {
  const [items,setItems]=useState<RequestLog[]>([]); const [total,setTotal]=useState(0); const [requestType,setRequestType]=useState("");
  const [startTime,setStartTime]=useState(""); const [endTime,setEndTime]=useState(""); const [expanded,setExpanded]=useState<number|null>(null); const [loading,setLoading]=useState(false);
  const load=useCallback(async()=>{if(!connected){setItems([]);setTotal(0);return;}setLoading(true);try{const params=new URLSearchParams({page_size:"100"});if(requestType)params.set("request_type",requestType);if(startTime)params.set("start_time",String(Math.floor(new Date(startTime).getTime()/1000)));if(endTime)params.set("end_time",String(Math.floor(new Date(endTime).getTime()/1000)));const response=await fetch(`${API}/api/request-logs?${params}`);if(!response.ok)throw new Error();const data=await response.json();setItems(data.items);setTotal(data.total)}finally{setLoading(false)}},[connected,requestType,startTime,endTime]);
  useEffect(()=>{const timer=window.setTimeout(()=>{void load()},0);return()=>window.clearTimeout(timer)},[load]);
  const clear=async()=>{if(!window.confirm("确定清空全部请求日志吗？"))return;const response=await fetch(`${API}/api/request-logs`,{method:"DELETE"});if(!response.ok)return;setItems([]);setTotal(0);setExpanded(null);onToast("请求日志已清空")};
  return <section className="content config-content request-logs-page"><div className="page-section-head"><div><p className="eyebrow">REQUEST HISTORY</p><h1>请求日志</h1><p>查看文稿、标签话题、封面和配音服务的本地请求记录。</p></div><button className="danger-outline" disabled={!connected||!total} onClick={clear}>清空日志</button></div><div className="log-filters"><label>请求类型<select value={requestType} onChange={event=>setRequestType(event.target.value)}><option value="">全部类型</option><option value="文稿生成">文稿生成</option><option value="标签话题生成">标签话题生成</option><option value="封面生成">封面生成</option><option value="配音生成">配音生成</option></select></label><label>开始时间<input type="datetime-local" value={startTime} onChange={event=>setStartTime(event.target.value)}/></label><label>结束时间<input type="datetime-local" value={endTime} onChange={event=>setEndTime(event.target.value)}/></label><button className="secondary" onClick={()=>{setRequestType("");setStartTime("");setEndTime("")}}>重置筛选</button></div><div className="log-list-head"><b>请求记录</b><span>{loading?"加载中…":`共 ${total} 条`}</span></div><div className="request-log-list">{items.map(item=><article key={item.id} className={expanded===item.id?"expanded":""}><button className="log-summary" onClick={()=>setExpanded(expanded===item.id?null:item.id)}><span className={`log-type ${item.request_type}`}>{item.request_type}</span><code>{item.request_url}</code><time>{new Date(item.created_at*1000).toLocaleString("zh-CN")}</time><i>{expanded===item.id?"收起":"参数"}</i></button>{expanded===item.id&&<div className="log-params"><b>请求参数</b><pre>{JSON.stringify(item.request_params,null,2)}</pre></div>}</article>)}{!items.length&&!loading&&<div className="panel-empty">暂无符合条件的请求日志</div>}</div></section>;
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

function TaskList({tasks,checkedIds,allChecked,onToggleAll,onToggle,onOpen,onDelete}:{tasks:Workflow[];checkedIds:string[];allChecked:boolean;onToggleAll:()=>void;onToggle:(id:string)=>void;onOpen:(task:Workflow)=>void;onDelete:()=>void}) {
  return <section className="task-list-panel"><div className="task-list-actions"><label><input type="checkbox" checked={allChecked} onChange={onToggleAll}/>全选当前结果</label><span>已选择 {checkedIds.length} 项</span><button className="danger-outline" disabled={!checkedIds.length} onClick={onDelete}>删除所选</button></div><div className="task-list-scroll"><table className="task-list"><thead><tr><th aria-label="选择"/><th>作品</th><th>状态</th><th>进度</th><th>创建时间</th><th/></tr></thead><tbody>{tasks.map(task=><tr key={task.id}><td><input type="checkbox" checked={checkedIds.includes(task.id)} onChange={()=>onToggle(task.id)} aria-label={`选择《${task.book_title}》`}/></td><td><button className="task-list-title" onClick={()=>onOpen(task)}><b>{task.book_title}</b><small>{task.author||"未填写作者"}</small></button></td><td><Status value={task.status}/></td><td><span className="list-progress"><i style={{width:`${task.progress}%`}}/></span><small>{task.progress}%</small></td><td>{new Date(task.created_at*1000).toLocaleString("zh-CN")}</td><td><button className="list-open" onClick={()=>onOpen(task)}>查看 →</button></td></tr>)}</tbody></table></div></section>;
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
  const [voiceList,setVoiceList]=useState<string[]>(["zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural","zh-CN-XiaoyiNeural"]);
  const [voice,setVoice]=useState("zh-CN-XiaoxiaoNeural"); const [speechRate,setSpeechRate]=useState(0);
  const [music,setMusic]=useState<BackgroundMusic[]>([]); const [musicId,setMusicId]=useState(""); const [musicVolume,setMusicVolume]=useState(0.2); const [fadeIn,setFadeIn]=useState(2); const [fadeOut,setFadeOut]=useState(2);
  const [busy, setBusy] = useState(false);
  useEffect(()=>{if(connected){fetch(`${API}/api/prompts`).then(r=>r.json()).then((items:PromptTemplate[])=>{setTemplates(items);setSelectedIds(items.map(x=>x.id));}).catch(()=>{});fetch(`${API}/api/settings`).then(r=>r.json()).then(settings=>{setVoice(settings.voices?.[0]||"zh-CN-XiaoxiaoNeural");setSpeechRate(settings.speech_rate??0)}).catch(()=>{});fetch(`${API}/api/voices`).then(r=>r.json()).then(data=>setVoiceList(data.voices)).catch(()=>{});fetch(`${API}/api/background-music?page_size=50`).then(r=>r.json()).then(data=>setMusic(data.items)).catch(()=>{})}},[connected]);
  const submit = async (e: FormEvent) => { e.preventDefault(); if (!title.trim()) return; setBusy(true); try { await onSubmit({book_title:title.trim(),author:author.trim(),edition:edition.trim(),writing_prompt_ids:templates.filter(x=>x.kind==="writing"&&selectedIds.includes(x.id)).map(x=>x.id),cover_prompt_ids:templates.filter(x=>x.kind==="cover"&&selectedIds.includes(x.id)).map(x=>x.id),voice,speech_rate:speechRate,background_music_id:musicId||null,background_music_volume:musicVolume,background_music_fade_in:fadeIn,background_music_fade_out:fadeOut}); } finally { setBusy(false); } };
  return <div className="modal-backdrop" role="presentation" onMouseDown={e => e.target === e.currentTarget && onClose()}><form className="modal config-modal create-modal" onSubmit={submit}>
    <div className="modal-head"><div><p className="eyebrow">新建工作流</p><h2>从哪一本书开始？</h2></div><button type="button" className="close" onClick={onClose}>×</button></div>
    <div className="form-grid"><label className="wide">书籍名称 <em>必填</em><input required value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：百年孤独" /></label><label>作者 <small>选填</small><input value={author} onChange={e=>setAuthor(e.target.value)} placeholder="加西亚·马尔克斯" /></label><label>版本 <small>选填</small><input value={edition} onChange={e=>setEdition(e.target.value)} placeholder="例如：2017 纪念版" /></label></div>
    <section className="workflow-speech"><div><h3>配音设置</h3><p>默认沿用接口设置，可为本次作品单独调整</p></div><div className="workflow-speech-grid"><VoiceControl label="配音音色" voices={voiceList} value={voice} onChange={setVoice}/><SpeechRateControl value={speechRate} onChange={setSpeechRate}/></div></section>
    <MusicMixControl music={music} musicId={musicId} setMusicId={setMusicId} volume={musicVolume} setVolume={setMusicVolume} fadeIn={fadeIn} setFadeIn={setFadeIn} fadeOut={fadeOut} setFadeOut={setFadeOut}/>
    <TemplatePicker title="分享稿提示词" hint="勾选几个，就生成几篇独立分享稿" kind="writing" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/>
    <TemplatePicker title="封面提示词" hint="勾选几个，就生成几张不同封面" kind="cover" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/>
    <div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>取消</button><button className="primary" disabled={busy || !title.trim() || selectedIds.length===0}>{busy ? "正在创建…" : "开始自动制作 →"}</button></div>
  </form></div>;
}

function MusicMixControl({music,musicId,setMusicId,volume,setVolume,fadeIn,setFadeIn,fadeOut,setFadeOut}:{music:BackgroundMusic[];musicId:string;setMusicId:(id:string)=>void;volume:number;setVolume:(value:number)=>void;fadeIn:number;setFadeIn:(value:number)=>void;fadeOut:number;setFadeOut:(value:number)=>void}) {
  return <section className="workflow-music"><div><h3>背景音乐</h3><p>选填，通过微软 SSML 与配音同时合成</p></div><label>选择背景音乐<select value={musicId} onChange={e=>setMusicId(e.target.value)}><option value="">不使用背景音乐</option>{music.map(item=><option key={item.id} value={item.id}>{item.name}{item.category?` · ${item.category}`:""}</option>)}</select></label>{musicId&&<div className="music-mix-grid"><label><span>音量 <b>{volume.toFixed(2)}</b></span><input type="range" min="0" max="1" step="0.05" value={volume} onChange={e=>setVolume(Number(e.target.value))}/></label><label><span>淡入时间 <b>{fadeIn} 秒</b></span><input type="range" min="0" max="10" step="0.5" value={fadeIn} onChange={e=>setFadeIn(Number(e.target.value))}/></label><label><span>淡出时间 <b>{fadeOut} 秒</b></span><input type="range" min="0" max="10" step="0.5" value={fadeOut} onChange={e=>setFadeOut(Number(e.target.value))}/></label></div>}</section>;
}

function BatchCreateDialog({connected,onClose,onSubmit}:{connected:boolean;onClose:()=>void;onSubmit:(data:Record<string,unknown>)=>Promise<void>}) {
  const [step,setStep]=useState(1); const [rows,setRows]=useState(()=>Array.from({length:6},(_,i)=>({id:`row-${i+1}`,book_title:"",author:"",edition:""}))); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
  const fallback:PromptTemplate[]=[{id:"writing-short-video",kind:"writing",name:"短视频口播",text:"适合 2 分钟短视频口播，有真实阅读感受"},{id:"writing-insight",kind:"writing",name:"反常识洞见",text:"从一个反常识观点切入，避免剧透"},{id:"cover-literary",kind:"cover",name:"文学质感",text:"克制的文学感，竖版构图，无文字"}];
  const [templates,setTemplates]=useState<PromptTemplate[]>(fallback);const [selectedIds,setSelectedIds]=useState<string[]>(fallback.map(x=>x.id));const [voiceList,setVoiceList]=useState<string[]>(["zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural"]);const [voice,setVoice]=useState("zh-CN-XiaoxiaoNeural");const [speechRate,setSpeechRate]=useState(0);const [music,setMusic]=useState<BackgroundMusic[]>([]);const [musicId,setMusicId]=useState("");const [musicVolume,setMusicVolume]=useState(0.2);const [fadeIn,setFadeIn]=useState(2);const [fadeOut,setFadeOut]=useState(2);
  useEffect(()=>{if(!connected)return;fetch(`${API}/api/prompts`).then(r=>r.json()).then((items:PromptTemplate[])=>{setTemplates(items);setSelectedIds(items.map(x=>x.id))}).catch(()=>{});fetch(`${API}/api/settings`).then(r=>r.json()).then(settings=>{setVoice(settings.voices?.[0]||"zh-CN-XiaoxiaoNeural");setSpeechRate(settings.speech_rate??0)}).catch(()=>{});fetch(`${API}/api/voices`).then(r=>r.json()).then(data=>setVoiceList(data.voices)).catch(()=>{});fetch(`${API}/api/background-music?page_size=50`).then(r=>r.json()).then(data=>setMusic(data.items)).catch(()=>{})},[connected]);
  const usedRows=rows.filter(row=>row.book_title.trim()||row.author.trim()||row.edition.trim());
  const updateRow=(id:string,field:"book_title"|"author"|"edition",value:string)=>setRows(items=>items.map(row=>row.id===id?{...row,[field]:value}:row));
  const next=()=>{if(!usedRows.length){setError("请至少填写一本书");return;}if(usedRows.some(row=>!row.book_title.trim())){setError("已填写的每一行都需要书籍名称");return;}setError("");setStep(2)};
  const submit=async()=>{if(!selectedIds.length)return;setBusy(true);try{await onSubmit({books:usedRows.map(({book_title,author,edition})=>({book_title:book_title.trim(),author:author.trim(),edition:edition.trim()})),writing_prompt_ids:templates.filter(x=>x.kind==="writing"&&selectedIds.includes(x.id)).map(x=>x.id),cover_prompt_ids:templates.filter(x=>x.kind==="cover"&&selectedIds.includes(x.id)).map(x=>x.id),voice,speech_rate:speechRate,background_music_id:musicId||null,background_music_volume:musicVolume,background_music_fade_in:fadeIn,background_music_fade_out:fadeOut})}finally{setBusy(false)}};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal config-modal batch-modal"><div className="modal-head"><div><p className="eyebrow">批量制作 · 第 {step} 步 / 2</p><h2>{step===1?"添加书籍信息":"设置共用生成配置"}</h2><p className="modal-subtitle">{step===1?"空白行会自动忽略，可继续添加更多书籍":"以下配置将应用到本批次全部书籍"}</p></div><button className="close" onClick={onClose}>×</button></div>{step===1?<><div className="batch-table"><div className="batch-table-head"><span>序号</span><span>书籍名称 *</span><span>作者</span><span>版本</span><span/></div>{rows.map((row,index)=><div className="batch-row" key={row.id}><b>{String(index+1).padStart(2,"0")}</b><input value={row.book_title} onChange={e=>updateRow(row.id,"book_title",e.target.value)} placeholder="例如：百年孤独"/><input value={row.author} onChange={e=>updateRow(row.id,"author",e.target.value)} placeholder="作者（选填）"/><input value={row.edition} onChange={e=>updateRow(row.id,"edition",e.target.value)} placeholder="版本（选填）"/><button disabled={rows.length===1} onClick={()=>setRows(items=>items.filter(item=>item.id!==row.id))}>删除</button></div>)}</div><button className="add-batch-row" onClick={()=>setRows(items=>[...items,{id:`row-${Date.now()}`,book_title:"",author:"",edition:""}])}>＋ 添加一行</button>{error&&<p className="batch-error">{error}</p>}</>:<><section className="workflow-speech batch-shared"><div><h3>共用配音设置</h3><p>{usedRows.length} 本书将使用相同音色与语速</p></div><div className="workflow-speech-grid"><VoiceControl label="配音音色" voices={voiceList} value={voice} onChange={setVoice}/><SpeechRateControl value={speechRate} onChange={setSpeechRate}/></div></section><MusicMixControl music={music} musicId={musicId} setMusicId={setMusicId} volume={musicVolume} setVolume={setMusicVolume} fadeIn={fadeIn} setFadeIn={setFadeIn} fadeOut={fadeOut} setFadeOut={setFadeOut}/><TemplatePicker title="共用分享稿提示词" hint="每本书按勾选模板分别生成" kind="writing" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/><TemplatePicker title="共用封面提示词" hint="每本书按勾选模板分别生成" kind="cover" templates={templates} selected={selectedIds} setSelected={setSelectedIds}/></>}<div className="modal-actions">{step===2&&<button className="secondary" onClick={()=>setStep(1)}>上一步</button>}<button className="secondary" onClick={onClose}>取消</button>{step===1?<button className="primary" onClick={next}>下一步 →</button>:<button className="primary" disabled={busy||!selectedIds.length} onClick={submit}>{busy?"正在创建…":`开始自动制作 ${usedRows.length} 本`}</button>}</div></div></div>;
}

function TemplatePicker({title,hint,kind,templates,selected,setSelected}:{title:string;hint:string;kind:"writing"|"cover";templates:PromptTemplate[];selected:string[];setSelected:(v:string[])=>void}) {
  const items=templates.filter(x=>x.kind===kind);
  return <section className="prompt-editor"><div><h3>{title}</h3><p>{hint}</p></div><div className="template-picker title-only">{items.map(item=><label key={item.id} className={selected.includes(item.id)?"picked":""}><input type="checkbox" checked={selected.includes(item.id)} onChange={e=>setSelected(e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/><b>{item.name}</b><span className="check-mark">✓</span></label>)}</div>{!items.length&&<p className="empty-hint">请先到提示词库添加配置</p>}</section>;
}

const coverSizeGroups = [
  {label:"正方形", options:[["1:1","1:1"]]},
  {label:"横版", options:[["1.91:1","1.91:1"],["2.35:1","2.35:1"],["3:2","3:2"],["4:3","4:3"],["16:9","16:9"]]},
  {label:"竖版", options:[["4:5","4:5"],["2:3","2:3"],["3:4","3:4"],["9:16","9:16"],["6:7","6:7"]]},
] as const;

function ImageSizePicker({value,onChange}:{value:string[];onChange:(value:string[])=>void}) {
  return <fieldset className="image-size-picker"><legend>图片尺寸 <em>*</em></legend><p>可多选；每个比例将单独生成一张封面图片</p><div>{coverSizeGroups.map(group=><section key={group.label}><b>{group.label}</b><div>{group.options.map(([size,label])=><label key={size}><input type="checkbox" checked={value.includes(size)} onChange={event=>onChange(event.target.checked?[...value,size]:value.filter(item=>item!==size))}/><span>{label}</span></label>)}</div></section>)}</div>{!value.length&&<small className="image-size-required">请至少选择一个图片尺寸</small>}<small className="image-size-note">由于中转站的 gpt-image-2 接口实际调用 gpt-image-2-codex，同一条提示词需按比例分别调用一次接口才能生成一张图片；该接口不支持设置分辨率参数，仅会在提示词中追加图片比例。</small></fieldset>;
}

function PromptLibraryDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [kind,setKind]=useState<"writing"|"cover">("writing");
  const [items,setItems]=useState<PromptTemplate[]>([]); const [name,setName]=useState(""); const [text,setText]=useState(""); const [imageSizes,setImageSizes]=useState<string[]>(["2:3"]);
  const [editingId,setEditingId]=useState<string|null>(null); const [saving,setSaving]=useState(false);
  const load=()=>connected&&fetch(`${API}/api/prompts`).then(r=>r.json()).then(setItems).catch(()=>{});
  useEffect(()=>{if(connected) void fetch(`${API}/api/prompts`).then(r=>r.json()).then(setItems).catch(()=>{});},[connected]);
  const clearEditor=()=>{setName("");setText("");setImageSizes(["2:3"]);setEditingId(null)};
  const saveTemplate=async()=>{if(!name.trim()||!text.trim()||(kind==="cover"&&!imageSizes.length))return;setSaving(true);try{const url=editingId?`${API}/api/prompts/${editingId}`:`${API}/api/prompts`;const payload={name,text,image_sizes:imageSizes};const res=await fetch(url,{method:editingId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(editingId?payload:{kind,...payload})});if(res.ok){clearEditor();load();onSaved();}}finally{setSaving(false)}};
  const edit=(item:PromptTemplate)=>{setEditingId(item.id);setName(item.name);setText(item.text);setImageSizes(item.image_sizes||["2:3"])};
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
        <section className="template-composer"><div className="composer-title"><span>{editingId?"编":"＋"}</span><div><h3>{editingId?"编辑模板":"添加新模板"}</h3><p>{kind==="writing"?"定义文案的结构、语气与长度":"定义封面的风格、构图与色彩"}</p></div></div><label>模板名称<input value={name} onChange={event=>setName(event.target.value)} placeholder={kind==="writing"?"例如：知识型口播":"例如：复古油画"}/></label><label>提示词内容<textarea value={text} onChange={event=>setText(event.target.value)} placeholder={kind==="writing"?"描述分享稿的语气、结构和长度要求":"描述封面的风格、构图和色彩要求"}/></label>{kind==="cover"&&<ImageSizePicker value={imageSizes} onChange={setImageSizes}/>}<div className="composer-actions">{editingId&&<button className="secondary" onClick={clearEditor}>取消编辑</button>}<button className="primary action-button" disabled={!connected||!name.trim()||!text.trim()||(kind==="cover"&&!imageSizes.length)||saving} onClick={saveTemplate}><span aria-hidden="true">{editingId?"✓":"＋"}</span>{saving?"保存中…":editingId?"保存修改":"添加模板"}</button></div></section>
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

function DetailPanel({task,onClose,onRetry,onDelete}:{task:Workflow;onClose:()=>void;onRetry:()=>void;onDelete:()=>Promise<void>}) {
  const [tab,setTab]=useState("overview"); const [compare,setCompare]=useState(0); const [confirmDelete,setConfirmDelete]=useState(false); const [deleting,setDeleting]=useState(false); const [deleteError,setDeleteError]=useState("");
  const remove=async()=>{setDeleting(true);setDeleteError("");try{await onDelete()}catch{setDeleteError("删除失败，请稍后重试");setDeleting(false)}};
  const tabs=[['overview','概览'],['drafts','分享稿'],['covers','封面'],['audio','配音'],['videos','视频']];
  return <div className="drawer-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><aside className="drawer">
    <div className="drawer-head"><button className="close" onClick={onClose}>×</button><div><p className="eyebrow">作品详情</p><h2>{task.book_title}</h2><p>{task.author}{task.edition ? ` · ${task.edition}`:""}</p></div><div className="drawer-status-actions"><Status value={task.status}/><button className="delete-work" onClick={()=>setConfirmDelete(true)}><span className="delete-icon" aria-hidden="true"/>删除作品</button></div></div>
    <nav className="tabs">{tabs.map(([id,label])=><button key={id} className={tab===id?"active":""} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    <div className="drawer-content">
      {task.status!=="completed"&&<div className="pipeline"><div className="pipeline-head"><span>{task.status==="failed"?"制作遇到问题":`正在${stages[Math.max(0,task.step-1)]||"准备"}`}</span><b>{task.progress}%</b></div><div className="progress"><i style={{width:`${task.progress}%`}}/></div><div className="steps">{stages.map((s,i)=><span className={i<task.step?"done":i===task.step?"now":""} key={s}>{i<task.step?"✓":i+1}<small>{s}</small></span>)}</div>{task.error&&<p className="error">{task.error} <button onClick={onRetry}>重试</button></p>}</div>}
      {tab==="overview"&&<section className="result-section"><h3>书籍简介</h3><div className="paper">{task.description||"简介将在书籍解析完成后出现。"}</div><h3>标签和话题</h3><div className="taxonomy-panel"><div><b>标签</b><p>{task.tags?.length?task.tags.map(tag=><span key={tag}>{tag}</span>):<small>标签尚未生成</small>}</p></div><div><b>话题</b><p>{task.topics?.length?task.topics.map(topic=><span key={topic}>#{topic}</span>):<small>话题尚未生成</small>}</p></div></div><h3>产出清单</h3><div className="asset-summary"><span><b>{task.polished_drafts?.length||0}</b> 篇分享稿</span><span><b>{task.audio?.length||0}</b> 份配音</span><span><b>{task.covers?.length||0}</b> 张封面</span><span><b>{task.videos?.length||0}</b> 条视频</span></div></section>}
      {tab==="drafts"&&<section className="result-section"><div className="section-inline"><h3>分享稿对比</h3>{(task.polished_drafts?.length||0)>1&&<select value={compare} onChange={e=>setCompare(+e.target.value)}>{task.polished_drafts?.map((d,i)=><option key={d.id} value={i}>版本 {i+1}</option>)}</select>}</div><div className="compare"><article><label>原始稿</label><p>{task.original_drafts?.[compare]?.text||"尚未生成"}</p></article><article className="polished"><label>自然化优化稿</label><p>{task.polished_drafts?.[compare]?.text||"尚未生成"}</p></article></div></section>}
      {tab==="covers"&&<CoverGallery covers={task.covers||[]} bookTitle={task.book_title} coverPrompts={task.cover_prompts}/>}
      {tab==="audio"&&<section className="audio-list">{task.audio?.length?task.audio.map((a,i)=><article key={i}><span>声</span><div><b>{a.voice}</b><small>分享稿 {i+1} · 语速 {a.speech_rate===0||a.speech_rate===undefined?"正常":`${a.speech_rate>0?"+":""}${a.speech_rate}%`}</small></div><audio controls preload="none" src={`${API}${a.url}`}/></article>):<EmptyMedia text="配音尚未生成"/>}</section>}
      {tab==="videos"&&<section className="video-grid">{task.videos?.length?task.videos.map((a,i)=><figure key={i}><video controls preload="metadata" src={`${API}${a.url}`}/><figcaption>{a.voice} · 分享稿 {i+1}</figcaption></figure>):<EmptyMedia text="视频尚未生成"/>}</section>}
    </div>{confirmDelete&&<div className="confirm-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&!deleting&&setConfirmDelete(false)}><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title"><span className="danger-mark">删</span><h3 id="delete-title">确定删除《{task.book_title}》？</h3><p>该作品的简介、分享稿、封面、配音和视频都会被永久删除，此操作无法撤销。</p>{deleteError&&<small>{deleteError}</small>}<div><button className="secondary" disabled={deleting} onClick={()=>setConfirmDelete(false)}>取消</button><button className="danger-button" disabled={deleting} onClick={remove}>{deleting?"正在删除…":"确认永久删除"}</button></div></section></div>}
  </aside></div>;
}

function EmptyMedia({text}:{text:string}) { return <div className="empty-media"><span>◇</span><p>{text}</p></div> }

function SearchableVoiceSelect({voices,value,onChange}:{voices:string[];value:string;onChange:(voice:string)=>void}) {
  const [query,setQuery]=useState(""); const [open,setOpen]=useState(false);
  const filtered=voices.filter(voice=>voice.toLowerCase().includes(query.trim().toLowerCase())).slice(0,40);
  return <div className="voice-select"><button type="button" className="voice-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}><span><small>当前音色</small><b>{value||"请选择默认音色"}</b></span><i>{open?"▴":"▾"}</i></button>{open&&<div className="voice-dropdown"><label className="voice-search"><span>⌕</span><input role="combobox" aria-expanded="true" aria-controls="voice-options" value={query} onChange={e=>setQuery(e.target.value)} placeholder="输入名称模糊搜索，如 Xiaoxiao"/></label><div id="voice-options" role="listbox" className="voice-options">{filtered.map(voice=><button type="button" role="option" aria-selected={voice===value} className={voice===value?"selected":""} key={voice} onClick={()=>{onChange(voice);setOpen(false);setQuery("")}}><span>{voice===value?"✓":"声"}</span><b>{voice}</b></button>)}{!filtered.length&&<p>没有匹配的音色</p>}</div><small className="voice-result">显示 {filtered.length} / {voices.length} 个音色</small></div>}</div>;
}

function VoiceControl({label,voices,value,onChange}:{label:string;voices:string[];value:string;onChange:(voice:string)=>void}) {
  return <div className="voice-control"><span>{label}</span><SearchableVoiceSelect voices={voices} value={value} onChange={onChange}/></div>;
}

function ModelSelect({models,value,onChange}:{models:string[];value:string;onChange:(model:string)=>void}) {
  const [query,setQuery]=useState(""); const [open,setOpen]=useState(false);
  const choices=models.filter(model=>model!=="gpt-image-2"&&model.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="model-select"><button type="button" className="model-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}><b>{value||"请选择文案模型"}</b><i>{open?"▴":"▾"}</i></button>{open&&<div className="model-dropdown"><div className="model-search"><span>⌕</span><input role="combobox" aria-expanded="true" aria-controls="model-options" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索模型名称"/></div><div id="model-options" role="listbox" className="model-options">{choices.map(model=><button type="button" role="option" aria-selected={model===value} className={model===value?"selected":""} key={model} onClick={()=>{onChange(model);setOpen(false);setQuery("")}}><span>{model===value?"✓":""}</span><b>{model}</b></button>)}{!choices.length&&<p>没有匹配的模型</p>}</div><small className="model-result">显示 {choices.length} / {models.filter(model=>model!=="gpt-image-2").length} 个模型</small></div>}</div>;
}

function FormatSelect({formats,value,onChange}:{formats:string[];value:string;onChange:(format:string)=>void}) {
  const [query,setQuery]=useState(""); const [open,setOpen]=useState(false);
  const choices=formats.filter(format=>format.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="model-select format-select"><button type="button" className="model-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(!open)}><b>{value}</b><i>{open?"▴":"▾"}</i></button>{open&&<div className="model-dropdown"><div className="model-search"><span>⌕</span><input role="combobox" aria-expanded="true" aria-controls="format-options" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索音频格式"/></div><div id="format-options" role="listbox" className="model-options">{choices.map(format=><button type="button" role="option" aria-selected={format===value} className={format===value?"selected":""} key={format} onClick={()=>{onChange(format);setOpen(false);setQuery("")}}><span>{format===value?"✓":""}</span><b>{format}</b></button>)}{!choices.length&&<p>没有匹配的音频格式</p>}</div><small className="model-result">显示 {choices.length} / {formats.length} 个格式</small></div>}</div>;
}

function SpeechRateControl({value,onChange}:{value:number;onChange:(rate:number)=>void}) {
  const label=value===0?"正常":`${value>0?"+":""}${value}%`;
  return <label className="rate-control"><span>语速 <b>{label}</b></span><input type="range" min="-50" max="100" step="5" value={value} onChange={e=>onChange(Number(e.target.value))}/><small><span>慢 -50%</span><span>正常</span><span>快 +100%</span></small></label>;
}

function SettingsDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [form,setForm]=useState<AppSettings>(defaultSettings); const [models,setModels]=useState<string[]>([]); const [saving,setSaving]=useState(false); const [settingsTab,setSettingsTab]=useState<"model"|"help">("model");
  useEffect(()=>{if(connected){fetch(`${API}/api/settings`).then(r=>r.json()).then(setForm).catch(()=>{});fetch(`${API}/api/models`).then(r=>r.json()).then(d=>setModels(d.models)).catch(()=>{});}},[connected]);
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);try{const response=await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});if(!response.ok)throw new Error("保存失败");onSaved();}finally{setSaving(false)}};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal config-modal settings-modal"><div className="modal-head"><div><p className="eyebrow">创作引擎</p><h2>模型配置</h2></div><button className="close" onClick={onClose}>×</button></div><nav className="settings-tabs" aria-label="模型配置分类"><button className={settingsTab==="model"?"active":""} onClick={()=>setSettingsTab("model")}><span>AI</span><div><b>OpenAI 兼容接口</b><small>模型与图片生成</small></div></button><button className={settingsTab==="help"?"active":""} onClick={()=>setSettingsTab("help")}><span>?</span><div><b>配置说明</b><small>地址、密钥与加载规则</small></div></button></nav><div className="settings-pane">{settingsTab==="model"?<div className="settings-block"><h3>OpenAI 兼容接口</h3><label>API 地址<input value={form.api_base} onChange={e=>setForm({...form,api_base:e.target.value})}/></label><div className="form-grid model-fields"><label>文案模型{models.length?<ModelSelect models={models} value={form.model} onChange={model=>setForm({...form,model})}/>:<input value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/>}</label><label>图片模型<input value={form.image_model} onChange={e=>setForm({...form,image_model:e.target.value})}/></label><label className="wide">API 密钥<input type="password" value={form.api_key} onChange={e=>setForm({...form,api_key:e.target.value})} placeholder="已优先读取 .env"/></label></div></div>:<section className="config-help"><article><span>01</span><div><b>填写兼容地址</b><p>API 地址应指向 OpenAI 兼容服务的 /v1 根路径。</p></div></article><article><span>02</span><div><b>自动读取模型</b><p>配置密钥后会通过 /models 加载文案模型；图片模型可直接填写服务支持的名称。</p></div></article><article><span>03</span><div><b>本机配置优先</b><p>.env 中的 MODEL_API_BASE、MODEL_API_KEY 与模型名称会优先生效，页面只显示脱敏密钥。</p></div></article></section>}</div><p className="privacy-note">密钥从本机 .env 自动读取，不会写入前端源码。</p><div className="modal-actions"><button className="secondary action-button" onClick={onClose}><span aria-hidden="true">×</span>取消</button><button className="primary action-button" onClick={save} disabled={saving}><span aria-hidden="true">✓</span>{saving?"保存中…":"保存设置"}</button></div></div></div>;
}

function VoiceSettingsDialog({connected,onClose,onSaved}:{connected:boolean;onClose:()=>void;onSaved:()=>void}) {
  const [tab,setTab]=useState<"speech"|"voices"|"music">("speech"); const [form,setForm]=useState<AppSettings>(defaultSettings); const [voices,setVoices]=useState<VoiceItem[]>([]); const [saving,setSaving]=useState(false); const [voiceQuery,setVoiceQuery]=useState(""); const [voicePage,setVoicePage]=useState(1); const [previewing,setPreviewing]=useState(""); const [download,setDownload]=useState({status:"idle",total:0,completed:0,failed:0});
  const [music,setMusic]=useState<BackgroundMusic[]>([]); const [musicTotal,setMusicTotal]=useState(0); const [musicPage,setMusicPage]=useState(1); const [musicQuery,setMusicQuery]=useState(""); const [musicForm,setMusicForm]=useState({name:"",url:"",category:""}); const [musicError,setMusicError]=useState(""); const [editingMusicId,setEditingMusicId]=useState<string|null>(null); const [playingMusic,setPlayingMusic]=useState<BackgroundMusic|null>(null);
  const voicePageSize=8; const musicPageSize=6;
  const loadVoices=useCallback(()=>connected&&fetch(`${API}/api/voices`).then(r=>r.json()).then(d=>setVoices((d.items||d.voices.map((short_name:string)=>({short_name,locale:"",local_name:short_name,display_name:short_name,gender:""}))) as VoiceItem[])).catch(()=>{}),[connected]);
  const loadMusic=useCallback(()=>connected&&fetch(`${API}/api/background-music?q=${encodeURIComponent(musicQuery)}&page=${musicPage}&page_size=${musicPageSize}`).then(r=>r.json()).then(d=>{setMusic(d.items);setMusicTotal(d.total)}).catch(()=>{}),[connected,musicPage,musicQuery]);
  useEffect(()=>{if(connected){fetch(`${API}/api/settings`).then(r=>r.json()).then(setForm).catch(()=>{});void loadVoices();fetch(`${API}/api/voices/download-all/status`).then(r=>r.json()).then(setDownload).catch(()=>{});}},[connected,loadVoices]);
  useEffect(()=>{void loadMusic();},[loadMusic]);
  useEffect(()=>{if(download.status!=="queued"&&download.status!=="running")return;const timer=window.setInterval(()=>fetch(`${API}/api/voices/download-all/status`).then(r=>r.json()).then(setDownload).catch(()=>{}),1200);return()=>window.clearInterval(timer);},[download.status]);
  const filteredVoices=useMemo(()=>{const needle=voiceQuery.trim().toLowerCase();return voices.filter(v=>`${v.short_name} ${v.locale} ${v.local_name} ${v.display_name} ${v.gender}`.toLowerCase().includes(needle));},[voices,voiceQuery]);
  const voicePages=Math.max(1,Math.ceil(filteredVoices.length/voicePageSize)); const visibleVoices=filteredVoices.slice((voicePage-1)*voicePageSize,voicePage*voicePageSize); const musicPages=Math.max(1,Math.ceil(musicTotal/musicPageSize));
  const save=async()=>{if(!connected){onSaved();return;}setSaving(true);try{const response=await fetch(`${API}/api/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});if(!response.ok)throw new Error("保存失败");onSaved();}finally{setSaving(false)}};
  const preview=async(item:VoiceItem)=>{setPreviewing(item.short_name);try{const audio=new Audio(`${API}/api/voices/${encodeURIComponent(item.short_name)}/preview?locale=${encodeURIComponent(item.locale)}`);await audio.play();audio.onended=()=>setPreviewing("");audio.onerror=()=>setPreviewing("");}catch{setPreviewing("")}};
  const downloadAll=async()=>{const response=await fetch(`${API}/api/voices/download-all`,{method:"POST"});setDownload(await response.json())};
  const saveMusic=async()=>{setMusicError("");if(!musicForm.name.trim()){setMusicError("请填写背景音乐名称");return;}if(!/^https:\/\/[^/]+/i.test(musicForm.url.trim())){setMusicError("请输入有效的 HTTPS 音频地址");return;}const response=await fetch(editingMusicId?`${API}/api/background-music/${editingMusicId}`:`${API}/api/background-music`,{method:editingMusicId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(musicForm)});if(!response.ok){setMusicError("保存失败，请检查填写内容");return;}const saved=await response.json() as BackgroundMusic;if(playingMusic?.id===saved.id)setPlayingMusic(saved);setMusicForm({name:"",url:"",category:""});setEditingMusicId(null);setMusicPage(1);void loadMusic()};
  const editMusic=(item:BackgroundMusic)=>{setEditingMusicId(item.id);setMusicForm({name:item.name,url:item.url,category:item.category});setMusicError("")};
  const cancelMusicEdit=()=>{setEditingMusicId(null);setMusicForm({name:"",url:"",category:""});setMusicError("")};
  const removeMusic=async(id:string)=>{await fetch(`${API}/api/background-music/${id}`,{method:"DELETE"});if(playingMusic?.id===id)setPlayingMusic(null);if(editingMusicId===id)cancelMusicEdit();void loadMusic()};
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="modal config-modal settings-modal voice-settings-modal"><div className="modal-head"><div><p className="eyebrow">声音工作台</p><h2>语音设置</h2></div><button className="close" onClick={onClose}>×</button></div><nav className="settings-tabs voice-settings-tabs" aria-label="语音设置分类"><button className={tab==="speech"?"active":""} onClick={()=>setTab("speech")}><span>声</span><div><b>微软语音服务</b><small>接口与默认合成参数</small></div></button><button className={tab==="voices"?"active":""} onClick={()=>setTab("voices")}><span>库</span><div><b>音色中心</b><small>搜索、试听与离线下载</small></div></button><button className={tab==="music"?"active":""} onClick={()=>setTab("music")}><span>乐</span><div><b>背景音乐</b><small>管理在线音频素材</small></div></button></nav><div className="settings-pane voice-settings-pane">
    {tab==="speech"&&<div className="settings-block speech-pane"><h3>微软语音服务</h3><div className="form-grid"><label>区域<input value={form.azure_speech_region} onChange={e=>setForm({...form,azure_speech_region:e.target.value})}/></label><label>Speech 密钥<input type="password" value={form.azure_speech_key} onChange={e=>setForm({...form,azure_speech_key:e.target.value})} placeholder="已优先读取 .env"/></label></div><div className="format-control"><span>音频格式</span><FormatSelect formats={speechFormats} value={form.voice_format} onChange={voice_format=>setForm({...form,voice_format})}/></div><VoiceControl label="默认音色" voices={voices.map(v=>v.short_name)} value={form.voices[0]||""} onChange={voice=>setForm({...form,voices:[voice]})}/><SpeechRateControl value={form.speech_rate} onChange={speech_rate=>setForm({...form,speech_rate})}/></div>}
    {tab==="voices"&&<section className="voice-center"><div className="panel-toolbar"><div><h3>音色中心</h3><p>微软返回的全部语言音色，共 {voices.length} 个</p></div><button className="secondary download-button" disabled={!connected||download.status==="queued"||download.status==="running"} onClick={downloadAll}>⇩ {download.status==="queued"||download.status==="running"?"正在离线下载":"离线下载全部"}</button></div><label className="panel-search"><span>⌕</span><input value={voiceQuery} onChange={e=>{setVoiceQuery(e.target.value);setVoicePage(1)}} placeholder="搜索音色、语言、地区或性别"/></label>{(download.status!=="idle")&&<div className="download-progress"><span><i style={{width:`${download.total?Math.round((download.completed+download.failed)/download.total*100):0}%`}}/></span><small>{download.status==="completed"?"下载完成":"下载进度"}：{download.completed} / {download.total}{download.failed?`，失败 ${download.failed}`:""} · 保存到 data/voice_samples</small></div>}<div className="voice-card-grid">{visibleVoices.map(v=><article className="voice-card" key={v.short_name}><div className="voice-avatar">{v.gender==="Female"?"女":v.gender==="Male"?"男":"声"}</div><div><b>{v.local_name||v.display_name||v.short_name}</b><p title={v.short_name}>{v.short_name}</p><small>{[v.locale,v.gender].filter(Boolean).join(" · ")}</small></div><button onClick={()=>preview(v)} disabled={previewing===v.short_name}>{previewing===v.short_name?"加载中":"▶ 试听"}</button></article>)}{!visibleVoices.length&&<div className="panel-empty">没有匹配的音色</div>}</div><Pagination page={voicePage} pages={voicePages} total={filteredVoices.length} onChange={setVoicePage}/><p className="sample-copy">试听会根据音色所属国家或地区，自动翻译并生成对应语言。</p></section>}
    {tab==="music"&&<section className="music-center"><div className="music-layout"><div className="music-composer"><h3>{editingMusicId?"编辑背景音乐":"添加背景音乐"}</h3><label>音乐名称 <em>必填</em><input value={musicForm.name} onChange={e=>setMusicForm({...musicForm,name:e.target.value})} placeholder="例如：安静的阅读时光"/></label><label>HTTPS 音频地址 <em>必填</em><input value={musicForm.url} onChange={e=>setMusicForm({...musicForm,url:e.target.value})} placeholder="https://example.com/music.mp3"/></label><label>分类 <small>选填</small><input value={musicForm.category} onChange={e=>setMusicForm({...musicForm,category:e.target.value})} placeholder="例如：治愈 / 悬疑"/></label>{musicError&&<p className="form-error">{musicError}</p>}<div className="music-form-actions">{editingMusicId&&<button className="secondary" onClick={cancelMusicEdit}>取消编辑</button>}<button className="primary" disabled={!connected} onClick={saveMusic}>{editingMusicId?"保存修改":"添加音乐"}</button></div></div><div className="music-library"><div className="panel-toolbar"><div><h3>已添加音乐</h3><p>{musicTotal} 条在线素材</p></div></div><label className="panel-search"><span>⌕</span><input value={musicQuery} onChange={e=>{setMusicQuery(e.target.value);setMusicPage(1)}} placeholder="搜索名称或分类"/></label><div className="music-list">{music.map(item=><article key={item.id}><div><b>{item.name}</b><small>{item.category||"未分类"}</small></div><div className="music-actions"><button onClick={()=>setPlayingMusic(item)}>试听</button><button onClick={()=>editMusic(item)}>编辑</button><button className="danger-link" onClick={()=>removeMusic(item.id)}>删除</button></div></article>)}{!music.length&&<div className="panel-empty">还没有背景音乐</div>}</div><Pagination page={musicPage} pages={musicPages} total={musicTotal} onChange={setMusicPage}/></div></div><div className="music-player"><div><b>{playingMusic?.name||"背景音乐播放器"}</b><small>{playingMusic?playingMusic.category||"未分类":"点击列表中的试听按钮开始播放"}</small></div><audio key={playingMusic?.id||"empty"} controls autoPlay={Boolean(playingMusic)} src={playingMusic?.url}/></div></section>}
  </div>{tab==="speech"&&<p className="privacy-note">密钥从本机 .env 自动读取；声音合成使用 SSML，并应用所选音色与语速。</p>}<div className="modal-actions"><button className="secondary action-button" onClick={onClose}><span aria-hidden="true">×</span>取消</button>{tab==="speech"&&<button className="primary action-button" onClick={save} disabled={saving}><span aria-hidden="true">✓</span>{saving?"保存中…":"保存语音设置"}</button>}</div></div></div>;
}

function Pagination({page,pages,total,onChange}:{page:number;pages:number;total:number;onChange:(page:number)=>void}) {
  return <div className="pagination"><small>共 {total} 条 · 第 {page} / {pages} 页</small><div><button disabled={page<=1} onClick={()=>onChange(page-1)}>上一页</button><button disabled={page>=pages} onClick={()=>onChange(page+1)}>下一页</button></div></div>;
}
