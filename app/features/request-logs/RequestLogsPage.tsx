import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/app/lib/api";
import { formatShanghaiDateTime } from "@/app/lib/date";
import type { RequestLog } from "@/app/features/shared/types";

import { Pagination } from "@/app/shared/ui/Pagination";

type RequestLogsPageProps = { connected: boolean; onToast: (message: string) => void };

export function RequestLogsPage({ connected, onToast }: RequestLogsPageProps) {
  const [items, setItems] = useState<RequestLog[]>([]); const [total, setTotal] = useState(0); const [requestType, setRequestType] = useState("");
  const [startTime, setStartTime] = useState(""); const [endTime, setEndTime] = useState(""); const [expanded, setExpanded] = useState<number | null>(null); const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1); const [reload, setReload] = useState(0); const [clearing, setClearing] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    activeRequest.current?.abort();
    if (!connected) { setItems([]); setTotal(0); return; }
    const controller = new AbortController(); activeRequest.current = controller;
    setLoading(true); setExpanded(null);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "12" });
      if (requestType) params.set("request_type", requestType);
      if (startTime) params.set("start_time", String(Math.floor(new Date(startTime).getTime() / 1000)));
      if (endTime) params.set("end_time", String(Math.floor(new Date(endTime).getTime() / 1000)));
      const response = await fetch(`${API_BASE}/api/request-logs?${params}`, { signal: controller.signal });
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (controller.signal.aborted) return;
      const lastPage = Math.max(1, Math.ceil(data.total / 12));
      if (page > lastPage) { setPage(lastPage); return; }
      setItems(data.items); setTotal(data.total);
    } catch { if (!controller.signal.aborted) onToast("请求日志加载失败，请重试"); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }, [connected, requestType, startTime, endTime, page, onToast]);
  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, 0); return () => { window.clearTimeout(timer); activeRequest.current?.abort(); }; }, [load, reload]);
  const clear = async () => {
    if (!window.confirm("确定永久删除全部请求日志吗？包括当前筛选条件之外的记录。")) return;
    setClearing(true); activeRequest.current?.abort(); setLoading(false);
    try {
      const response = await fetch(`${API_BASE}/api/request-logs`, { method: "DELETE" });
      if (!response.ok) throw new Error();
      setExpanded(null); setPage(1); setReload(value => value + 1); onToast("全部请求日志已删除");
    } catch { onToast("清空日志失败，记录已保留，请重试"); }
    finally { setClearing(false); }
  };
  return <section className="content config-content request-logs-page"><div className="page-section-head"><div><p className="eyebrow">REQUEST HISTORY</p><h1>请求日志</h1><p>查看文稿、封面、配音、视频搜索词和无版权素材服务的本地请求记录。</p></div><button className="danger-outline" disabled={!connected || clearing} onClick={clear}>清空日志</button></div><div className="log-filters"><label>请求类型<select value={requestType} onChange={event => {setRequestType(event.target.value);setPage(1);}}><option value="">全部类型</option><option value="文稿生成">文稿生成</option><option value="标签话题生成">标签话题生成</option><option value="封面生成">封面生成</option><option value="配音生成">配音生成</option><option value="视频搜索词生成">视频搜索词生成</option><option value="无版权视频搜索">无版权视频搜索</option></select></label><label>开始时间<input type="datetime-local" value={startTime} onChange={event => {setStartTime(event.target.value);setPage(1);}} /></label><label>结束时间<input type="datetime-local" value={endTime} onChange={event => {setEndTime(event.target.value);setPage(1);}} /></label><button className="secondary" onClick={() => { setRequestType(""); setStartTime(""); setEndTime(""); setPage(1); }}>重置筛选</button></div><div className="log-list-head"><b>请求记录</b><span>{loading ? "加载中…" : `共 ${total} 条`}</span></div><div className="request-log-list">{items.map(item => <article key={item.id} className={expanded === item.id ? "expanded" : ""}><button className="log-summary" onClick={() => setExpanded(expanded === item.id ? null : item.id)}><span className={`log-type ${item.request_type}`}>{item.request_type}</span><code>{item.request_url}</code><time>{formatShanghaiDateTime(item.created_at)}</time><i>{expanded === item.id ? "收起" : "参数"}</i></button>{expanded === item.id && <div className="log-params"><b>请求参数</b><pre>{JSON.stringify(item.request_params, null, 2)}</pre></div>}</article>)}{!items.length && !loading && <div className="panel-empty">暂无符合条件的请求日志</div>}</div><Pagination page={page} pages={Math.max(1,Math.ceil(total/12))} total={total} onChange={next=>{setExpanded(null);setPage(next);}}/></section>;
}
