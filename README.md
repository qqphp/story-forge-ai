# 砚界 · StoryForge AI

把书籍信息自动转化为简介、多个版本的分享稿、自然化优化稿、微软语音配音、竖版封面和可预览视频。每本书对应一个独立工作流，多个工作流可以同时运行。

## 本地运行

需要 Node.js 22+、Python 3.11+ 和 FFmpeg。

```powershell
# 终端 1：前端
npm install
npm run dev

# 终端 2：后端
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

打开前端显示的本地地址。没有配置第三方密钥时，应用会以演示模式生成完整的文案、封面、音频和视频，方便验收整个流程。

## 外部服务配置

在页面右上角打开“接口与声音设置”：

- 大模型支持 OpenAI 兼容的 `/models` 和 `/chat/completions` 接口，可配置中转站地址、模型与密钥。
- 微软语音支持区域、密钥、输出格式和多个默认音色；音色列表通过微软接口查询。
- 分享稿会保留原稿，并单独生成经过 Humanizer-zh 原则优化的自然化版本。

也可以从 `.env.example` 复制环境变量进行配置。密钥不会进入源码；页面保存的设置仅存储在本机 `data/storyforge.db`。

## 验证

```powershell
npm test
python -m unittest discover backend/tests
```
