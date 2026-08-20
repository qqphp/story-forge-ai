/* global StoryForgePlatforms, StoryForgeCoverUpload, StoryForgeRuntime, StoryForgePublishPanel */
(async () => {
  if (document.querySelector('#storyforge-publish-assistant')) return;
  const platform = Object.entries(StoryForgePlatforms).find(([id, definition]) => id !== 'douyin' && definition?.uploadUrl && location.hostname.includes(new URL(definition.uploadUrl).hostname))?.[0];
  if (!platform) return;
  const { apiBase, token } = await StoryForgeRuntime.loadSettings();
  const { request: api, fetchFile } = StoryForgeRuntime.createApiClient(apiBase, token);
  const requestedTaskId = new URLSearchParams(location.search).get('storyforge_task') || '';
  let task = null;
  const { taskTitle, meta, message, fillButton, completeButton } = StoryForgePublishPanel.create(`砚界 · ${StoryForgePlatforms[platform].label}发布助手`);
  const show = (text, error = false) => {
    message.textContent = text;
    message.className = `sf-message${error ? ' error' : ''}`;
  };
  const usable = (element) => {
    if (!element) return false;
    const style = getComputedStyle(element);
    return !element.disabled && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const waitFor = async (finder, timeout = 60000) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      const value = finder();
      if (value) return value;
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
    return null;
  };
  const findField = (kind) => {
    const selectors = kind === 'title' ? ["input[placeholder*='标题']", "textarea[placeholder*='标题']", "input[aria-label*='标题']", "[contenteditable='true'][placeholder*='标题']", "[contenteditable='true'][data-placeholder*='标题']"] : ['#work-description-edit', "textarea[placeholder*='简介']", "textarea[placeholder*='描述']", "textarea[placeholder*='正文']", "[contenteditable='true'][placeholder*='简介']", "[contenteditable='true'][placeholder*='描述']", "[contenteditable='true'][placeholder*='正文']", "[contenteditable='true'][data-placeholder*='简介']", "[contenteditable='true'][data-placeholder*='描述']", "[contenteditable='true'][data-placeholder*='正文']", "[contenteditable='true'][aria-label*='正文']"];
    for (const selector of selectors) {
      const element = [...document.querySelectorAll(selector)].find(usable);
      if (element) return element;
    }
    return null;
  };
  const setValue = (element, value) => {
    element.focus();
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(element, value);
    } else {
      element.textContent = value;
    }
    element.dispatchEvent(
      new InputEvent('input', {
        bubbles: true,
        inputType: 'insertText',
        data: value
      })
    );
    element.dispatchEvent(new Event('change', { bubbles: true }));
    element.blur();
  };
  const assignFile = (input, file) => {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const update = async (status, error = '') => {
    task = await (
      await api(`/api/publish/extension/tasks/${task.id}`, {
        method: 'PUT',
        body: JSON.stringify({ status, error })
      })
    ).json();
  };
  const attachVideo = async () => {
    const input = await waitFor(() => [...document.querySelectorAll("input[type='file']")].find((candidate) => /video|mp4|mov/i.test(candidate.accept || '')) || null, 30000);
    if (!input) return false;
    assignFile(input, await fetchFile(`/api/publish/extension/tasks/${task.id}/video`, 'storyforge-video.mp4', 'video/mp4'));
    return true;
  };
  const attachCover = async () => {
    if (!task.covers?.length) return false;
    const input = [...document.querySelectorAll("input[type='file']")].find((candidate) => /image|png|jpe?g/i.test(candidate.accept || ''));
    if (!input) return false;
    assignFile(input, await fetchFile(`/api/publish/extension/tasks/${task.id}/covers/0`, 'storyforge-cover.png', 'image/png'));
    return true;
  };
  const exactTextElements = (text, scope = document) => [...scope.querySelectorAll('button,a,div,span,p')].filter((element) => usable(element) && element.textContent?.trim() === text);
  const kuaishouCoverTrigger = () => document.querySelector("[class*='_cover-full-editor_']") || exactTextElements('封面设置').find((element) => element.className?.includes('_cover-full-editor_')) || null;
  const kuaishouCoverDialog = () => [...document.querySelectorAll("[role='dialog'],[role='document'].ant-modal,.ant-modal,.modal")].find((element) => usable(element) && /上传封面|封面截取/.test(element.textContent || '')) || null;
  const ratioButton = (dialog, ratio) => [...dialog.querySelectorAll("[class*='_ratio-item_']")].find((element) => usable(element) && element.textContent?.trim().startsWith(ratio)) || [...dialog.querySelectorAll('button,div,span')].find((element) => usable(element) && element.textContent?.trim() === ratio) || null;
  const appendKuaishouTopics = async (field, topics) => {
    for (const topic of topics || []) {
      const tag = topic.trim().replace(/^#+/, '');
      if (!tag) continue;
      const text = ` #${tag} `;
      for (const character of text) {
        field.focus();
        const selection = window.getSelection(),
          range = document.createRange();
        range.selectNodeContents(field);
        range.collapse(false);
        selection?.removeAllRanges();
        selection?.addRange(range);
        field.dispatchEvent(
          new KeyboardEvent('keydown', {
            bubbles: true,
            cancelable: true,
            key: character
          })
        );
        field.dispatchEvent(
          new InputEvent('beforeinput', {
            bubbles: true,
            cancelable: true,
            inputType: 'insertText',
            data: character
          })
        );
        if (!document.execCommand('insertText', false, character)) field.append(document.createTextNode(character));
        field.dispatchEvent(
          new InputEvent('input', {
            bubbles: true,
            inputType: 'insertText',
            data: character
          })
        );
        field.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: character }));
        await new Promise((resolve) => setTimeout(resolve, 35));
      }
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  };
  const imageInputNear = (trigger, dialog) => {
    const candidates = [...document.querySelectorAll("input[type='file']")].filter((input) => /image|png|jpe?g/i.test(input.accept || ''));
    return candidates.find((input) => dialog.contains(input) || trigger?.parentElement?.contains(input)) || candidates.at(-1) || null;
  };
  const kuaishouConfirmButton = (dialog) =>
    [...dialog.querySelectorAll('button')].find((button) => usable(button) && button.textContent?.trim() === '确认') ||
    exactTextElements('确认', dialog)
      .map((element) => element.closest('button') || element)
      .find(usable) ||
    null;
  const kuaishouCovers = async () => {
    const cover = (task.covers || []).map((item, index) => ({ ...item, index })).find((item) => item.image_ratio === '3:4');
    if (!cover) return { uploaded: [], skipped: [] };
    const trigger = await waitFor(kuaishouCoverTrigger, 30000);
    if (!trigger) return { uploaded: [], skipped: [cover.image_ratio] };
    trigger.click();
    const dialog = await waitFor(kuaishouCoverDialog, 15000);
    if (!dialog) return { uploaded: [], skipped: [cover.image_ratio] };
    const uploadTab = [...dialog.querySelectorAll("[class*='_header-title-item_']")].find((element) => usable(element) && element.textContent?.trim() === '上传封面') || exactTextElements('上传封面', dialog).at(-1);
    if (!uploadTab) return { uploaded: [], skipped: [cover.image_ratio] };
    uploadTab.click();
    const ratio = ratioButton(dialog, cover.image_ratio);
    if (ratio) ratio.click();
    const input = await waitFor(() => imageInputNear(uploadTab, dialog), 10000);
    if (!input) return { uploaded: [], skipped: [cover.image_ratio] };
    assignFile(input, await fetchFile(`/api/publish/extension/tasks/${task.id}/covers/${cover.index}`, 'storyforge-cover-3x4.png', 'image/png'));
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const confirm = await waitFor(() => kuaishouConfirmButton(dialog), 15000);
    if (!confirm) return { uploaded: [], skipped: [cover.image_ratio] };
    confirm.click();
    const closed = await waitFor(() => !document.contains(dialog) || !usable(dialog), 15000);
    if (!closed) return { uploaded: [], skipped: [cover.image_ratio] };
    return { uploaded: [cover.image_ratio], skipped: [] };
  };
  const compactText = (value) => (value || '').replace(/\s+/g, '');
  const bilibiliTextElement = (text, scope = document) => [...scope.querySelectorAll('button,a,div,span,p')].find((element) => usable(element) && compactText(element.textContent) === compactText(text)) || null;
  const containingAncestor = (element, texts) => {
    for (let current = element; current && current !== document.body; current = current.parentElement) {
      const value = compactText(current.textContent);
      if (texts.every((text) => value.includes(compactText(text)))) return current;
    }
    return null;
  };
  const bilibiliDescriptionField = () => [...document.querySelectorAll(".ql-editor[contenteditable='true']")].find((element) => usable(element) && /填写更全面的相关信息/.test(element.dataset.placeholder || '')) || null;
  const setBilibiliDescription = (field, value) => {
    field.focus();
    const selection = window.getSelection(),
      range = document.createRange();
    range.selectNodeContents(field);
    selection?.removeAllRanges();
    selection?.addRange(range);
    if (!document.execCommand('insertText', false, value)) {
      const paragraph = document.createElement('p');
      paragraph.textContent = value;
      field.replaceChildren(paragraph);
    }
    field.classList.remove('ql-blank');
    field.dispatchEvent(
      new InputEvent('input', {
        bubbles: true,
        inputType: 'insertText',
        data: value
      })
    );
    field.dispatchEvent(new Event('change', { bubbles: true }));
    field.blur();
  };
  const bilibiliTagContainer = () => document.querySelector('#tag-container');
  const clearBilibiliTags = async () => {
    const container = bilibiliTagContainer();
    if (!container) return false;
    for (let count = 0; count < 12; count += 1) {
      const close = container.querySelector('.tag-pre-wrp .label-item-v2-container .close');
      if (!close) break;
      close
        .closest('.label-item-v2-container')
        ?.querySelector('.close')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
    return !container.querySelector('.tag-pre-wrp .label-item-v2-container');
  };
  const setBilibiliTagInput = (input, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, value);
    input.dispatchEvent(
      new InputEvent('input', {
        bubbles: true,
        inputType: 'insertText',
        data: value
      })
    );
    input.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const fillBilibiliTags = async () => {
    const container = await waitFor(bilibiliTagContainer, 15000);
    if (!container) return false;
    await clearBilibiliTags();
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const input = container.querySelector("input[placeholder*='Enter']");
    if (!input) return false;
    for (const rawTag of (task.tags || []).slice(0, 10)) {
      const tag = rawTag.trim().replace(/^#+/, '');
      if (!tag) continue;
      input.focus();
      setBilibiliTagInput(input, tag);
      input.dispatchEvent(
        new KeyboardEvent('keydown', {
          bubbles: true,
          cancelable: true,
          key: 'Enter',
          code: 'Enter',
          keyCode: 13,
          which: 13
        })
      );
      input.dispatchEvent(
        new KeyboardEvent('keypress', {
          bubbles: true,
          cancelable: true,
          key: 'Enter',
          code: 'Enter',
          keyCode: 13,
          which: 13
        })
      );
      input.dispatchEvent(
        new KeyboardEvent('keyup', {
          bubbles: true,
          cancelable: true,
          key: 'Enter',
          code: 'Enter',
          keyCode: 13,
          which: 13
        })
      );
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    input.blur();
    return true;
  };
  const bilibiliCoverTrigger = () => document.querySelector('.add-text')?.parentElement || bilibiliTextElement('添加封面')?.parentElement || null;
  const bilibiliCoverDialog = () => {
    const home = bilibiliTextElement('首页推荐封面（4:3）');
    return containingAncestor(home, ['首页推荐封面（4:3）', '个人空间封面（16:9）', '上传封面', '完成']);
  };
  const bilibiliCoverSelectors = {
    '4:3': '.editor_4_3',
    '16:9': '.editor_16_9'
  };
  const bilibiliCoverRegion = (dialog, ratio) => {
    const selector = bilibiliCoverSelectors[ratio];
    if (!selector) return null;
    const region = dialog.querySelector(selector);
    return region?.closest('.active,.inactive')?.querySelector(selector) || null;
  };
  const bilibiliClick = (element) => {
    if (!element) return false;
    element.click();
    return true;
  };
  const isBilibiliImageInput = (input) => input instanceof HTMLInputElement && input.type === 'file' && !/video|mp4|mov|txt|zip/i.test(input.accept || '');
  const bilibiliImageInputs = () => [...document.querySelectorAll("input[type='file']")].filter(isBilibiliImageInput);
  const captureBilibiliImageInput = async (uploadButton) => {
    const before = new Set(bilibiliImageInputs());
    let captured = null;
    const intercept = (event) => {
      const input = isBilibiliImageInput(event.target) ? event.target : null;
      if (!input) return;
      captured = input;
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    document.addEventListener('click', intercept, true);
    try {
      if (!bilibiliClick(uploadButton)) return null;
      await new Promise((resolve) => setTimeout(resolve, 600));
    } finally {
      document.removeEventListener('click', intercept, true);
    }
    return await waitFor(() => captured || bilibiliImageInputs().find((candidate) => !before.has(candidate)) || bilibiliImageInputs().at(-1) || null, 10000);
  };
  const uploadBilibiliCover = async (dialog, item, uploaded, skipped) => {
    if (!item.cover) return false;
    const region = await waitFor(() => bilibiliCoverRegion(dialog, item.ratio), 10000);
    if (!region || !StoryForgeCoverUpload.activateBilibiliCoverRegion(region)) {
      skipped.push(item.ratio);
      return false;
    }
    const activated = await waitFor(() => region.closest('.active,.inactive')?.classList.contains('active'), 3000);
    if (!activated) {
      skipped.push(item.ratio);
      return false;
    }
    const uploadButton = bilibiliTextElement('上传封面', dialog);
    const input = uploadButton ? await captureBilibiliImageInput(uploadButton) : null;
    if (!input) {
      skipped.push(item.ratio);
      return false;
    }
    assignFile(input, await fetchFile(`/api/publish/extension/tasks/${task.id}/covers/${item.cover.index}`, item.filename, 'image/png'));
    uploaded.push(item.ratio);
    return true;
  };
  const bilibiliCovers = async () => {
    const requested = [
      {
        ratio: '4:3',
        label: '首页推荐封面（4:3）',
        filename: 'storyforge-bilibili-home-4x3.png'
      },
      {
        ratio: '16:9',
        label: '个人空间封面（16:9）',
        filename: 'storyforge-bilibili-space-16x9.png'
      }
    ];
    const covers = (task.covers || []).map((item, index) => ({
      ...item,
      index
    }));
    const selected = requested.map((item) => ({
      ...item,
      cover: covers.find((cover) => cover.image_ratio === item.ratio)
    }));
    if (!selected.some((item) => item.cover)) return { uploaded: [], skipped: [] };
    const trigger = await waitFor(bilibiliCoverTrigger, 30000);
    if (!trigger)
      return {
        uploaded: [],
        skipped: selected.filter((item) => item.cover).map((item) => item.ratio)
      };
    trigger.click();
    const dialog = await waitFor(bilibiliCoverDialog, 15000);
    if (!dialog)
      return {
        uploaded: [],
        skipped: selected.filter((item) => item.cover).map((item) => item.ratio)
      };
    const uploaded = [],
      skipped = [],
      home = selected[0],
      space = selected[1];
    await uploadBilibiliCover(dialog, home, uploaded, skipped);
    if (uploaded.includes('4:3')) await new Promise((resolve) => setTimeout(resolve, 2000));
    await uploadBilibiliCover(dialog, space, uploaded, skipped);
    if (uploaded.includes('16:9')) await new Promise((resolve) => setTimeout(resolve, 2000));
    const complete =
      exactTextElements('完成', dialog)
        .map((element) => element.closest('button') || element)
        .find(usable) || bilibiliTextElement('完成', dialog);
    if (complete) complete.click();
    else if (uploaded.length) skipped.push('确认');
    return { uploaded, skipped };
  };
  async function fill() {
    fillButton.disabled = true;
    try {
      if (task.status === 'prepared' || task.status === 'failed') await update('filling');
      show('正在识别发布表单并上传素材…');
      const videoAttached = await attachVideo();
      const field = await waitFor(() => (platform === 'kuaishou' ? findField('description') : findField('title') || findField('description') || bilibiliDescriptionField()), 120000);
      if (!field) throw new Error(platform === 'kuaishou' ? '没有找到作品描述输入框，请确认处于发布页并已登录' : '没有找到标题或正文输入框，请确认处于发布页并已登录');
      const title = findField('title'),
        description = platform === 'bilibili' ? await waitFor(bilibiliDescriptionField, 15000) : findField('description');
      if (platform !== 'kuaishou' && title) setValue(title, task.title);
      if (platform === 'bilibili') {
        if (!description) throw new Error('没有找到哔哩哔哩简介输入框');
        setBilibiliDescription(description, task.description);
        if (!(await fillBilibiliTags())) throw new Error('没有找到哔哩哔哩标签输入框');
      } else if (description) {
        setValue(description, task.description);
        if (platform === 'kuaishou') await appendKuaishouTopics(description, task.topics);
        else if (task.topics?.length) setValue(description, [task.description, ...task.topics.map((topic) => `#${topic}`)].filter(Boolean).join('\n'));
      }
      const coverResult = platform === 'kuaishou' ? await kuaishouCovers() : platform === 'bilibili' ? await bilibiliCovers() : { uploaded: (await attachCover()) ? ['封面'] : [], skipped: [] };
      if (task.status === 'filling') await update('ready');
      completeButton.hidden = false;
      const manual = [];
      if (!videoAttached) manual.push('视频');
      if (coverResult.skipped.length) manual.push(`封面（${coverResult.skipped.join('、')}）`);
      if (!coverResult.uploaded.length && task.covers?.length) manual.push('封面');
      const fields = platform === 'kuaishou' ? '作品简介和话题' : platform === 'bilibili' ? '标题、作品简介和标签' : '标题、正文和话题';
      show(`已填写${fields}${videoAttached ? '，已选择视频' : ''}${coverResult.uploaded.length ? `，已上传${coverResult.uploaded.join('、')}封面` : ''}${manual.length ? `；请手动补充${manual.join('、')}` : ''}。请检查平台必填设置后亲自点击发布按钮。`, manual.length > 0);
    } catch (error) {
      const text = error instanceof Error ? error.message : '填充失败';
      try {
        await update('failed', text);
      } catch {}
      show(text, true);
    } finally {
      fillButton.disabled = false;
    }
  }
  async function load() {
    if (!token) {
      taskTitle.textContent = '尚未配对';
      show('请打开扩展，填写发布中心提供的本地配对码。', true);
      fillButton.disabled = true;
      return;
    }
    try {
      const query = new URLSearchParams({ platform });
      if (requestedTaskId) query.set('task_id', requestedTaskId);
      task = (await (await api(`/api/publish/extension/tasks/next?${query}`)).json()).task;
      if (!task) {
        taskTitle.textContent = '没有待发布任务';
        show(`请先在 StoryForge 发布中心准备${StoryForgePlatforms[platform].label}发布任务。`);
        fillButton.disabled = true;
        return;
      }
      taskTitle.textContent = task.title;
      const taxonomy = platform === 'bilibili' ? task.tags : task.topics;
      meta.textContent = `《${task.book_title}》 · ${(taxonomy || []).map((item) => `#${item}`).join(' ') || '无标签/话题'}`;
      show('任务已就绪。扩展会填写内容和可识别的上传控件，不会自动点击最终发布按钮。');
    } catch (error) {
      taskTitle.textContent = '连接失败';
      show(error instanceof Error ? error.message : '无法连接 StoryForge', true);
      fillButton.disabled = true;
    }
  }
  fillButton.addEventListener('click', () => void fill());
  completeButton.addEventListener('click', async () => {
    completeButton.disabled = true;
    try {
      await update('completed');
      show('已记录为发布完成。你可以关闭这个提示框。');
      fillButton.hidden = true;
      completeButton.hidden = true;
    } catch (error) {
      show(error instanceof Error ? error.message : '状态更新失败', true);
      completeButton.disabled = false;
    }
  });
  await load();
})();
