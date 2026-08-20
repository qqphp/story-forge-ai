globalThis.StoryForgePublishPanel = {
  create(headingText) {
    const panel = document.createElement('aside');
    panel.id = 'storyforge-publish-assistant';
    const header = document.createElement('header');
    const heading = document.createElement('b');
    heading.textContent = headingText;
    const mode = document.createElement('span');
    mode.textContent = '本地半自动';
    header.append(heading, mode);
    const body = document.createElement('div');
    body.className = 'sf-body';
    const taskTitle = document.createElement('p');
    taskTitle.className = 'sf-task';
    const meta = document.createElement('p');
    meta.className = 'sf-meta';
    const message = document.createElement('p');
    message.className = 'sf-message';
    const actions = document.createElement('div');
    actions.className = 'sf-actions';
    const fillButton = document.createElement('button');
    fillButton.textContent = '上传并填充';
    const completeButton = document.createElement('button');
    completeButton.className = 'secondary';
    completeButton.textContent = '我已手动发布';
    completeButton.hidden = true;
    actions.append(fillButton, completeButton);
    body.append(taskTitle, meta, message, actions);
    panel.append(header, body);
    document.body.append(panel);
    return { panel, taskTitle, meta, message, fillButton, completeButton };
  }
};
