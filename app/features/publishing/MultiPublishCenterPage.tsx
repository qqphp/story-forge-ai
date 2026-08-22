"use client";
/* eslint-disable @next/next/no-img-element, jsx-a11y/label-has-associated-control */

import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE as API } from "@/app/lib/api";
import type { PublishPlatform, PublishTask, Workflow } from "@/app/features/shared/types";
import { publishPlatforms } from "@/app/features/publishing/platforms";

export function MultiPublishCenterPage({ connected, workflows, onToast }: { connected: boolean; workflows: Workflow[]; onToast: (message: string) => void }) {
  const eligible = useMemo(() => workflows.filter((workflow) => workflow.status === "completed" && (workflow.videos?.length || 0) > 0), [workflows]);
  const [workflowId, setWorkflowId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [topics, setTopics] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [coverUrls, setCoverUrls] = useState<string[]>([]);
  const [targets, setTargets] = useState<PublishPlatform[]>(["douyin"]);
  const [tasks, setTasks] = useState<PublishTask[]>([]);
  const [pairingToken, setPairingToken] = useState("");
  const [saving, setSaving] = useState(false);
  const selected = eligible.find((workflow) => workflow.id === workflowId);
  const platformFor = (id: PublishPlatform) => publishPlatforms.find((platform) => platform.id === id)!;
  const load = useCallback(async () => {
    if (!connected) {
      setTasks([]);
      setPairingToken("");
      return;
    }
    const [taskResponse, pairingResponse] = await Promise.all([fetch(`${API}/api/publish/tasks`), fetch(`${API}/api/publish/pairing`)]);
    if (taskResponse.ok) setTasks(await taskResponse.json());
    if (pairingResponse.ok) setPairingToken((await pairingResponse.json()).token);
  }, [connected]);
  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [load]);
  const applyWorkflow = useCallback((workflow: Workflow) => {
    setWorkflowId(workflow.id);
    setTitle(`《${workflow.book_title}》读书分享`);
    setDescription(workflow.description || "");
    setTags((workflow.tags || []).join(", "));
    setTopics((workflow.topics || []).join(", "));
    setVideoUrl(workflow.videos?.[0]?.url || "");
    setCoverUrls((workflow.covers || []).filter((asset) => ["3:4", "4:3", "16:9"].includes(asset.image_ratio || "")).map((asset) => asset.url));
  }, []);
  useEffect(() => {
    if (!workflowId && eligible[0]) {
      const timer = window.setTimeout(() => applyWorkflow(eligible[0]), 0);
      return () => window.clearTimeout(timer);
    }
  }, [applyWorkflow, eligible, workflowId]);
  const chooseWorkflow = (id: string) => {
    const workflow = eligible.find((item) => item.id === id);
    if (workflow) applyWorkflow(workflow);
  };
  const toggleTarget = (platform: PublishPlatform) => setTargets((values) => (values.includes(platform) ? values.filter((value) => value !== platform) : [...values, platform]));
  const requiresTitle = targets.some((platform) => platform !== "kuaishou");
  const createTasks = async () => {
    if (!selected || !(requiresTitle ? title.trim() : true) || !videoUrl || !targets.length) return;
    setSaving(true);
    try {
      const payload = {
        workflow_id: selected.id,
        title: title.trim(),
        description: description.trim(),
        tags: tags
          .split(/[,，\n]/)
          .map((tag) => tag.trim())
          .filter(Boolean),
        topics: topics
          .split(/[,，\n]/)
          .map((topic) => topic.trim())
          .filter(Boolean),
        video_url: videoUrl,
        cover_urls: coverUrls,
      };
      const responses = await Promise.all(
        targets.map((platform) => {
          const topicLimit = platform === "kuaishou" ? 4 : platform === "douyin" ? 5 : payload.topics.length;
          const platformCoverUrls = payload.cover_urls.filter((url) => {
            const ratio = selected.covers?.find((cover) => cover.url === url)?.image_ratio;
            if (platform === "bilibili") return ratio === "4:3" || ratio === "16:9";
            if (platform === "douyin" || platform === "kuaishou") return ratio === "3:4" || ratio === "4:3";
            return true;
          });
          return fetch(`${API}/api/publish/tasks`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ...payload,
              platform,
              tags: platform === "bilibili" ? payload.tags.slice(0, 10) : payload.tags,
              topics: payload.topics.slice(0, topicLimit),
              cover_urls: platformCoverUrls,
            }),
          });
        }),
      );
      const failed = responses.filter((response) => !response.ok);
      if (failed.length) {
        const data = await failed[0].json().catch(() => ({ detail: "创建发布任务失败" }));
        throw new Error(data.detail || "创建发布任务失败");
      }
      await load();
      onToast(`已准备 ${targets.length} 个平台发布任务`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "创建发布任务失败");
    } finally {
      setSaving(false);
    }
  };
  const removeTask = async (id: string) => {
    if (!window.confirm("确定删除这条发布任务吗？")) return;
    const response = await fetch(`${API}/api/publish/tasks/${id}`, {
      method: "DELETE",
    });
    if (response.ok) {
      await load();
      onToast("发布任务已删除");
    }
  };
  const rotateToken = async () => {
    if (!window.confirm("更新配对码后，浏览器扩展需要重新填写。确定继续吗？")) return;
    const response = await fetch(`${API}/api/publish/pairing/rotate`, {
      method: "POST",
    });
    if (response.ok) {
      setPairingToken((await response.json()).token);
      onToast("配对码已更新");
    }
  };
  const statusText: Record<string, string> = {
    prepared: "等待填充",
    filling: "正在填充",
    ready: "等待手动发布",
    completed: "已发布",
    failed: "填充失败",
    cancelled: "已取消",
  };
  const openUrl = (task: PublishTask) => {
    const url = new URL(platformFor(task.platform).url);
    url.searchParams.set("storyforge_task", task.id);
    return url.toString();
  };
  return (
    <section className="content config-content publish-center">
      <div className="page-section-head">
        <div>
          <p className="eyebrow">MULTI-PLATFORM PUBLISH ASSISTANT</p>
          <h1>发布中心</h1>
          <p>一次准备内容，按平台独立填写；最终发布始终由你确认。</p>
        </div>
      </div>
      <section className="connected-platforms" aria-label="已接入平台">
        <div className="connected-platforms-title">
          <b>已接入平台</b>
          <small>{publishPlatforms.length} 个平台</small>
        </div>
        <div className="connected-platform-list">
          {publishPlatforms.map((platform) => (
            <span className={`connected-platform ${platform.id}`} key={platform.id}>
              <i aria-hidden="true">{platform.mark}</i>
              {platform.name}
            </span>
          ))}
        </div>
      </section>
      <div className="publish-grid">
        <section className="publish-composer">
          <div className="publish-card-head">
            <span>01</span>
            <div>
              <h2>准备多平台发布内容</h2>
              <p>通用内容只填一次，平台任务独立创建</p>
            </div>
          </div>
          {eligible.length ? (
            <div className="publish-form">
              <label>
                选择作品
                <select value={workflowId} onChange={(event) => chooseWorkflow(event.target.value)}>
                  {eligible.map((workflow) => (
                    <option value={workflow.id} key={workflow.id}>
                      {workflow.book_title} · {workflow.videos?.length || 0} 个视频
                    </option>
                  ))}
                </select>
              </label>
              <label>
                发布标题 <small>{title.length}/100</small>
                <input value={title} maxLength={100} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label>
                作品简介 <small>{description.length}/2000</small>
                <textarea value={description} maxLength={2000} onChange={(event) => setDescription(event.target.value)} />
              </label>
              <label>
                标签 <small>使用逗号分隔</small>
                <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="文学, 读书, 名著" />
              </label>
              <p className="publish-topic-hint">哔哩哔哩平台最多支持10个标签。</p>
              <label>
                话题 <small>使用逗号分隔</small>
                <input value={topics} onChange={(event) => setTopics(event.target.value)} placeholder="读书, 好书推荐" />
              </label>
              <p className="publish-topic-hint">快手平台支持视频关联 4 个话题，抖音平台支持视频关联 5 个话题；程序会自动截取各平台所支持的话题数量。</p>
              <div className="publish-assets single">
                <label>
                  发布视频
                  <select value={videoUrl} onChange={(event) => setVideoUrl(event.target.value)}>
                    {selected?.videos?.map((asset, index) => (
                      <option value={asset.url} key={asset.url}>
                        视频 {index + 1}
                        {asset.voice ? ` · ${asset.voice}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <fieldset className="publish-cover-picker">
                <legend>
                  封面素材 <small>可多选</small>
                </legend>
                <div>
                  {selected?.covers?.map((asset, index) => (
                    <label key={asset.url} className={coverUrls.includes(asset.url) ? "checked" : ""}>
                      <input type="checkbox" checked={coverUrls.includes(asset.url)} onChange={(event) => setCoverUrls((values) => (event.target.checked ? [...values, asset.url] : values.filter((url) => url !== asset.url)))} />
                      <img src={`${API}${asset.url}`} alt="" />
                      <span>
                        <b>封面 {index + 1}</b>
                        <small>{asset.image_ratio || "未记录比例"}</small>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="publish-cover-hint">抖音仅会接收 3:4 或 4:3 原图；其他平台由扩展识别可用上传控件，无法匹配时会提示你手动补充。</p>
                <p className="publish-cover-hint">快手视频发布使用一张3:4的图片即可，需要勾选3:4图片尺寸。</p>
                <p className="publish-cover-hint">哔哩哔哩视频发布需要勾选 4:3 和 16:9 两种封面尺寸。</p>
              </fieldset>
              <fieldset className="publish-destinations">
                <legend>
                  发布到 <small>可多选</small>
                </legend>
                <div>
                  {publishPlatforms.map((platform) => (
                    <label className={targets.includes(platform.id) ? "selected" : ""} key={platform.id}>
                      <input type="checkbox" checked={targets.includes(platform.id)} onChange={() => toggleTarget(platform.id)} />
                      <span className={`platform-mark ${platform.id}`}>{platform.mark}</span>
                      <span>
                        <b>{platform.name}</b>
                        <small>{platform.hint}</small>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <button className="primary publish-prepare" disabled={!connected || !workflowId || !videoUrl || !(requiresTitle ? title.trim() : true) || !targets.length || saving} onClick={createTasks}>
                {saving ? "正在准备…" : `准备 ${targets.length} 个平台发布任务`}
              </button>
            </div>
          ) : (
            <div className="panel-empty publish-empty">暂无可发布作品。请先完成一个包含视频的书籍工作流。</div>
          )}
        </section>
        <aside className="extension-setup">
          <div className="publish-card-head">
            <span>02</span>
            <div>
              <h2>连接本地扩展</h2>
              <p>一个扩展支持全部平台</p>
            </div>
          </div>
          <ol>
            <li>下载并解压下方 ZIP 文件</li>
            <li>在 Chrome/Edge 扩展页开启开发者模式</li>
            <li>选择“加载已解压的扩展程序”，并加载 browser-extension 目录</li>
            <li>打开扩展，粘贴配对码后选择要发布的平台</li>
          </ol>
          <label>
            本地配对码
            <div className="pairing-code">
              <code>{pairingToken || "请先启动本地服务"}</code>
              <button
                disabled={!pairingToken}
                onClick={() => {
                  void navigator.clipboard.writeText(pairingToken);
                  onToast("配对码已复制");
                }}
              >
                复制
              </button>
            </div>
          </label>
          <button className="text-button" disabled={!connected} onClick={rotateToken}>
            更新配对码
          </button>
          <p className="safe-note">扩展仅填写已打开平台的内容和可识别上传控件，不读取 Cookie、不绕过登录或验证码，也不会点击最终发布按钮。</p>
          <a className="primary extension-download" href={`${API}/api/publish/extension/download`}>
            下载浏览器扩展 ZIP
          </a>
        </aside>
      </div>
      <section className="publish-queue">
        <div className="publish-queue-head">
          <div>
            <h2>多平台发布队列</h2>
            <p>每个平台有一条独立任务；填写完成后请你在对应平台亲自发布。</p>
          </div>
          <button className="secondary" onClick={() => void load()}>
            刷新状态
          </button>
        </div>
        <div className="publish-task-list">
          {tasks.map((task) => {
            const platform = platformFor(task.platform);
            const taxonomy = task.platform === "bilibili" ? task.tags : task.topics;
            return (
              <article key={task.id}>
                <div className="publish-task-main">
                  <span className={`platform-mark ${task.platform}`}>{platform.mark}</span>
                  <div>
                    <b>
                      {platform.name}
                      {task.title ? ` · ${task.title}` : ""}
                    </b>
                    <p>
                      《{task.book_title}》 · {taxonomy.map((item) => `#${item}`).join(" ") || "无标签/话题"}
                    </p>
                  </div>
                </div>
                <span className={`publish-status ${task.status}`}>{statusText[task.status] || task.status}</span>
                <time>{new Date(task.created_at * 1000).toLocaleString("zh-CN")}</time>
                <div className="publish-task-actions">
                  {["prepared", "filling", "failed"].includes(task.status) && (
                    <a href={openUrl(task)} target="_blank" rel="noreferrer">
                      {task.status === "failed" ? "重新打开" : "打开创作页"}
                    </a>
                  )}
                  <button onClick={() => removeTask(task.id)}>删除</button>
                </div>
                {task.error && <p className="publish-error">{task.error}</p>}
              </article>
            );
          })}
          {!tasks.length && <div className="panel-empty">还没有发布任务</div>}
        </div>
      </section>
    </section>
  );
}
