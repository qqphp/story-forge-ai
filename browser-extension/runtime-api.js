/* global chrome */
globalThis.StoryForgeRuntime = {
  normalizeBase(value) {
    const url = new URL(value?.trim() || 'http://127.0.0.1:8000');
    const local = ['localhost', '127.0.0.1'].includes(url.hostname);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) {
      throw new Error('远程服务需要 HTTPS 地址；本机服务可使用 HTTP');
    }
    if (url.username || url.password || url.search || url.hash) {
      throw new Error('服务地址不能包含账号、密码、查询参数或片段');
    }
    return url.href.replace(/\/+$/, '');
  },

  async loadSettings() {
    const settings = await chrome.storage.local.get(['apiBase', 'storyForgeToken']);
    return {
      apiBase: this.normalizeBase(settings.apiBase),
      token: settings.storyForgeToken || ''
    };
  },

  createApiClient(apiBase, token) {
    apiBase = this.normalizeBase(apiBase);
    const request = async (path, options = {}) => {
      const response = await fetch(`${apiBase}${path}`, {
        ...options,
        credentials: 'omit',
        headers: {
          'Content-Type': 'application/json',
          'X-StoryForge-Token': token,
          ...(options.headers || {})
        }
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `服务返回 ${response.status}`);
      }
      return response;
    };

    const fetchFile = async (path, fallback, type) => {
      const response = await fetch(`${apiBase}${path}`, {
        credentials: 'omit',
        headers: { 'X-StoryForge-Token': token }
      });
      if (!response.ok) throw new Error(`无法读取${fallback}`);
      const blob = await response.blob();
      return new File([blob], fallback, { type: blob.type || type });
    };

    return { request, fetchFile };
  }
};
