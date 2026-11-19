# 砚界 · StoryForge AI

输入书名与作者，自动生成书籍简介、分享稿、自然化优化稿、配音、字幕、封面和视频。支持批量制作，每本书独立管理。

## 本地启动

环境要求：Node.js 24.21.0、Python 3.11+、FFmpeg（加入 PATH）。

首次运行先安装依赖：

```powershell
npm ci
python -m pip install -r backend/requirements.txt
```

在两个终端中分别启动：

```powershell
# 终端 1：前端
npm run dev

# 终端 2：后端
python -m uvicorn backend.main:app --port 8000
```

打开 [http://localhost:3000](http://localhost:3000)。前端固定使用 3000 端口，并将 API 和媒体请求转发到后端 8000 端口，无需单独配置前端 API 地址。

## 使用与配置

在左侧导航完成设置，再回到“创作工作台”新建制作任务：

- **模型配置**：文本和图片服务分别填写 OpenAI 兼容的 API 地址与密钥，点击“获取模型”、选择模型后保存。修改地址或密钥后需重新获取模型。地址须保留 `/v1` 等路径前缀；图片服务也支持完整的 `/images/generations` 地址。
- **语音设置**：填写微软语音服务根地址与密钥，选择音色和输出格式。
- **提示词库**：管理分享稿与封面模板，新建任务时勾选使用。
- **视频设置**：选择横版 16:9 或竖版 9:16，以及静态封面或 Pexels/Pixabay 自然风光素材。素材模式需配置对应服务的密钥。

也可参考 [.env.example](.env.example) 在项目根目录创建 `.env`。配置优先级为：页面已保存值 → 环境变量 → 默认值；页面保存的空密钥同样生效。密钥仅由后端读取。

未启动后端时可浏览演示界面；未配置相应服务时，文案、配音和封面使用演示内容。

## 制作说明

- 分享稿保留原稿与自然化优化稿；已完成作品可在详情页重新生成配音或视频。
- 字幕使用 stable-ts 对齐配音，首次运行需下载 Whisper 模型。字幕任务串行执行，排队和单次生成分别最多等待 15 分钟；超时会终止字幕进程并显示错误。
- 服务重启会将未完成任务标记为中断，并保留已保存的产物。详情页的“重试”会重新执行完整制作流程。

## 本地数据

| 路径 | 内容 |
| --- | --- |
| `data/storyforge.db` | 设置、提示词与制作任务 |
| `data/media/` | 封面、配音、字幕与视频 |
| `data/voice_samples/` | 语音样本 |
| `data/` 下的缓存文件 | 音色翻译等缓存 |

备份时保留 `.env` 和完整 `data/` 目录；复制数据库前先停止后端。

## 常用命令

```powershell
npm run build  # 类型检查并构建到 dist/
npm run start  # 本地预览构建结果，仍需单独启动后端
npm run lint
npm test
python -m unittest discover backend/tests
```
