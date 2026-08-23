import type { Workflow } from "@/app/features/shared/types";
import { formatShanghaiDateTime, formatShanghaiShortDate } from "@/app/lib/date";

type TaskCardProps = { task: Workflow; stages: string[]; onOpen: () => void };

export function TaskCard({ task, stages, onOpen }: TaskCardProps) {
  const date = formatShanghaiShortDate(task.created_at);
  return <button className="task-card" onClick={onOpen}>
    <div className="book-cover"><span>{task.book_title.slice(0, 8)}</span><small>{task.author || "佚名"}</small></div>
    <div className="task-body"><div className="task-title"><div><h3>{task.book_title}</h3><p>{task.author || "未填写作者"}</p></div><Status value={task.status} /></div>
      {task.status === "running" || task.status === "queued" ? <><div className="stage-label"><span>{stages[Math.max(0, task.step - 1)] || "准备中"}</span><b>{task.progress}%</b></div><div className="progress"><i style={{ width: `${task.progress}%` }} /></div></> : <p className="desc">{task.description || "文案、配音、封面与视频已准备就绪"}</p>}
      <div className="task-foot"><span>{date}</span><b>查看作品 →</b></div>
    </div>
  </button>;
}

type TaskListProps = {
  tasks: Workflow[]; checkedIds: string[]; allChecked: boolean;
  onToggleAll: () => void; onToggle: (id: string) => void;
  onOpen: (task: Workflow) => void; onDelete: () => void;
};

export function TaskList({ tasks, checkedIds, allChecked, onToggleAll, onToggle, onOpen, onDelete }: TaskListProps) {
  return <section className="task-list-panel"><div className="task-list-actions"><label><input type="checkbox" checked={allChecked} onChange={onToggleAll} />全选当前结果</label><span>已选择 {checkedIds.length} 项</span><button className="danger-outline" disabled={!checkedIds.length} onClick={onDelete}>删除所选</button></div><div className="task-list-scroll"><table className="task-list"><thead><tr><th aria-label="选择" /><th>作品</th><th>状态</th><th>进度</th><th>创建时间</th><th /></tr></thead><tbody>{tasks.map(task => <tr key={task.id}><td><input type="checkbox" checked={checkedIds.includes(task.id)} onChange={() => onToggle(task.id)} aria-label={`选择《${task.book_title}》`} /></td><td><button className="task-list-title" onClick={() => onOpen(task)}><b>{task.book_title}</b><small>{task.author || "未填写作者"}</small></button></td><td><Status value={task.status} /></td><td><span className="list-progress"><i style={{ width: `${task.progress}%` }} /></span><small>{task.progress}%</small></td><td>{formatShanghaiDateTime(task.created_at)}</td><td><button className="list-open" onClick={() => onOpen(task)}>查看 →</button></td></tr>)}</tbody></table></div></section>;
}

export function Status({ value }: { value: string }) {
  const map: Record<string, string> = { completed: "已完成", running: "制作中", queued: "排队中", failed: "需处理" };
  return <span className={`status ${value}`}>{map[value] || value}</span>;
}
