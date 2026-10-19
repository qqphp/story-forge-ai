/* global chrome, StoryForgePlatforms, StoryForgeRuntime */
const apiBaseInput = document.querySelector('#apiBase');
const tokenInput = document.querySelector('#token');
const platformInput = document.querySelector('#platform');
const statusNode = document.querySelector('#status');
const taskNode = document.querySelector('#task');
const taskTitle = document.querySelector('#taskTitle');
const taskBook = document.querySelector('#taskBook');

function setStatus(message, type = '') {
  statusNode.textContent = message;
  statusNode.className = `status ${type}`.trim();
}

async function checkConnection(requestAccess = false) {
  const token = tokenInput.value.trim();
  const platform = platformInput.value;
  if (!token) {
    setStatus('请填写发布中心显示的配对码', 'error');
    return;
  }
  try {
    const apiBase = StoryForgeRuntime.normalizeBase(apiBaseInput.value);
    const permission = { origins: [`${new URL(apiBase).origin}/*`] };
    // Request optional site access directly from the Save button's user gesture.
    const granted = await (requestAccess
      ? chrome.permissions.request(permission)
      : chrome.permissions.contains(permission));
    if (!granted) throw new Error(requestAccess ? '未获得服务访问授权，连接配置未保存' : '请点击“保存并检测”授权此服务地址');
    setStatus('正在连接服务…');
    const response = await fetch(`${apiBase}/api/publish/extension/tasks/next?platform=${encodeURIComponent(platform)}`, { credentials: 'omit', headers: { 'X-StoryForge-Token': token } });
    if (!response.ok) throw new Error(response.status === 401 ? '配对码无效' : '服务不可用');
    const data = await response.json();
    await chrome.storage.local.set({
      apiBase,
      storyForgeToken: token,
      storyForgePlatform: platform
    });
    apiBaseInput.value = apiBase;
    setStatus('已连接 StoryForge', 'ok');
    if (data.task) {
      taskNode.hidden = false;
      taskTitle.textContent = data.task.title;
      taskBook.textContent = `《${data.task.book_title}》 · ${data.task.status}`;
    } else {
      taskNode.hidden = true;
    }
  } catch (error) {
    taskNode.hidden = true;
    setStatus(error instanceof Error ? error.message : '连接失败', 'error');
  }
}

document.querySelector('#save').addEventListener('click', () => void checkConnection(true));
platformInput.addEventListener('change', () => void checkConnection());
document.querySelector('#open').addEventListener('click', async () => {
  const platform = platformInput.value;
  try {
    const { apiBase, token } = await StoryForgeRuntime.loadSettings();
    if (!token) throw new Error('请先保存并检测连接');
    if (!await chrome.permissions.contains({ origins: [`${new URL(apiBase).origin}/*`] })) {
      throw new Error('请点击“保存并检测”授权此服务地址');
    }
    const client = StoryForgeRuntime.createApiClient(apiBase, token);
    const response = await client.request(`/api/publish/extension/tasks/next?platform=${encodeURIComponent(platform)}`);
    const data = await response.json();
    await chrome.tabs.create({
      url: StoryForgePlatforms.openUrl(platform, data.task?.id || '')
    });
  } catch (error) {
    setStatus(error instanceof Error ? error.message : '无法读取待发布任务', 'error');
  }
});

chrome.storage.local.get(['apiBase', 'storyForgeToken', 'storyForgePlatform']).then((values) => {
  apiBaseInput.value = values.apiBase || 'http://127.0.0.1:8000';
  tokenInput.value = values.storyForgeToken || '';
  platformInput.value = values.storyForgePlatform || 'douyin';
  if (values.storyForgeToken) void checkConnection();
});
