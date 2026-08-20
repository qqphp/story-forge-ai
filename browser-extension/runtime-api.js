/* global chrome */
globalThis.StoryForgeRuntime = {
  async loadSettings() {
    const settings = await chrome.storage.local.get(['apiBase', 'storyForgeToken']);
    return {
      apiBase: (settings.apiBase || 'http://127.0.0.1:8000').replace(/\/$/, ''),
      token: settings.storyForgeToken || ''
    };
  },

  createApiClient(apiBase, token) {
    const request = async (path, options = {}) => {
      const response = await fetch(`${apiBase}${path}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'X-StoryForge-Token': token,
          ...(options.headers || {})
        }
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `本地服务返回 ${response.status}`);
      }
      return response;
    };

    const fetchFile = async (path, fallback, type) => {
      const response = await fetch(`${apiBase}${path}`, {
        headers: { 'X-StoryForge-Token': token }
      });
      if (!response.ok) throw new Error(`无法读取${fallback}`);
      const blob = await response.blob();
      return new File([blob], fallback, { type: blob.type || type });
    };

    return { request, fetchFile };
  }
};
