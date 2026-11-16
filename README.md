# 砚界 · StoryForge AI

把书籍信息自动转化为简介、多个版本的分享稿、自然化优化稿、微软语音配音、横版或竖版封面和可预览视频。每本书对应一个独立工作流，多个工作流可以同时运行。

## 本地运行

需要 Node.js 24.21.0（24.x）、Python 3.11+ 和 FFmpeg。

```powershell
# 终端 1：前端
npm ci
npm run dev

# 终端 2：后端
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

打开 `http://localhost:3000`。开发和预览端口固定为 3000；前端通过同源的 `/api/`、`/media/` 和 `/voice-samples/` 访问后端，本地由 Vite 转发至 `127.0.0.1:8000`。无需配置前端 API 域名，旧的 `NEXT_PUBLIC_API_URL` 不再使用。

未启动后端时可以浏览演示界面；后端已启动但未配置第三方密钥时，会生成演示文案、封面、音频和视频。

```powershell
npm run build  # 严格类型检查并构建静态 dist/
npm run start  # 在 localhost:3000 本地预览构建结果，仍需单独启动后端
```

`npm run start` 仅用于本地预览，生产环境由 Nginx 提供 `dist/` 静态页面。

## 外部服务配置

通过左侧导航打开对应设置页面：

- 大模型支持 OpenAI 兼容的 `/models` 和 `/chat/completions` 接口，可配置中转站地址、模型与密钥。
- 微软语音支持 API 地址、密钥、输出格式和多个默认音色；音色列表通过微软接口查询。
- 分享稿会保留原稿，并单独生成经过 Humanizer-zh 原则优化的自然化版本。
- 分享稿与封面提示词在独立的“提示词库”集中维护，新建工作流时只需勾选模板。
- 文本模型和图片模型分别配置 API 地址和密钥（桌面端同一行），默认地址均为 `https://api.teamorouter.com/v1`。新配置默认不选择模型；点击对应的“获取模型”，从该侧服务的 `/models` 获取列表后在下拉框选择，再保存设置。获取使用当前输入，无需先保存，也不会写入数据库；打开页面和保存设置不会自动获取模型。修改地址或密钥后，该侧列表与模型选择会清空，需要重新获取。
- “视频设置”可选择横版 16:9 或竖版 9:16，并选择本地 FFmpeg 静态封面合成，或从 Pexels/Pixabay 随机选取三段中等质量的无版权自然风光素材循环合成。
- 无版权视频模式需要 `PEXELS_KEY` 或 `PIXABAY_KEY`；模型会依据书籍简介生成英文自然景观搜索词，搜索词会过滤人物相关词汇。

也可以从 `.env.example` 复制环境变量进行配置。密钥由后端读取，不进入前端构建。页面设置和工作流保存在服务端 `data/storyforge.db`；生成封面、音频、视频在 `data/media/`，语音样本在 `data/voice_samples/`，翻译缓存也在 `data/` 下。

文本 API 使用 `TEXT_API_BASE` / `TEXT_API_KEY`，图片 API 使用 `IMAGE_API_BASE` / `IMAGE_API_KEY`。每个 API 字段优先使用页面已保存值，未保存时读取对应环境变量，最后使用默认值；页面保存的空密钥也会生效，可用于停用对应的远程调用。API 地址应填写完整的兼容服务根地址（保留 `/v1` 或自定义路径前缀），程序不会自动添加 `/v1`。图片 API 也支持完整生成地址，例如 `https://proaiapi.vip/v1/images/generations`：获取模型时请求 `https://proaiapi.vip/v1/models`，生成图片时直接使用完整生成地址，不会重复拼接路径。

微软语音 API 地址使用 `AZURE_SPEECH_BASE`，默认值为 `https://eastus.tts.speech.microsoft.com`。页面保存的地址优先于环境变量；地址填写语音服务根地址，程序会分别追加 `/cognitiveservices/v1`（语音合成）和 `/cognitiveservices/voices/list`（获取音色）。升级时，数据库中已保存的区域值及旧环境变量 `AZURE_SPEECH_REGION` 会转换为对应的语音服务根地址。

升级时不再读取旧 `MODEL_API_BASE` / `MODEL_API_KEY` 环境变量，需要将它们迁移到上述新变量。数据库中已有的共享地址和密钥会在加载时映射到尚未配置的文本、图片设置，保存后写入独立字段，无需修改数据库 schema。模型名称环境变量仍为 `MODEL_NAME` 和 `IMAGE_MODEL_NAME`，仅在页面尚未保存该侧模型选择时读取；已保存的模型选择会保留。没有密钥或没有选择模型时，对应服务使用演示文案或本地封面。

## 验证

```powershell
npm run lint
npm test
python -m unittest discover backend/tests
```

## Linux 自有服务器部署

使用 Debian 12+/Ubuntu 24.04+ 一类支持 systemd 的 Linux。Node.js 24.21.0 用于构建，Python 3.11+、FFmpeg 用于后端运行。生产结构为：Nginx 提供静态页面和 HTTPS，FastAPI 仅监听 `127.0.0.1:8000`，所有业务数据保存在服务器磁盘。

以下命令假定源码已放在 `/opt/storyforge-ai`，由你的部署账号执行。域名 `storyforge.example.com` 是占位值。本项目沿用现有访问方式，没有新增网页登录；服务器侧的访问限制由你配置。

```bash
sudo apt update
sudo apt install python3 python3-venv ffmpeg nginx
cd /opt/storyforge-ai
node --version  # 应为 v24.21.0
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm ci
npm run build

# 仅首次安装时复制；已存在的 .env 必须保留。
test -f .env || cp .env.example .env
```

在 `.env` 中填写后端密钥。创建服务账号并授权运行时目录；源码和 `dist/` 需允许该账号及 Nginx 读取。

```bash
sudo useradd --system --user-group --home-dir /opt/storyforge-ai --shell /usr/sbin/nologin storyforge
sudo install -d -o storyforge -g storyforge -m 0750 /opt/storyforge-ai/data
sudo chown -R storyforge:storyforge /opt/storyforge-ai/data
sudo chown root:storyforge /opt/storyforge-ai/.env
sudo chmod 640 /opt/storyforge-ai/.env
sudo install -m 0644 deploy/storyforge.service /etc/systemd/system/storyforge.service
sudo systemctl daemon-reload
sudo systemctl enable --now storyforge
```

服务使用单个 Uvicorn worker，后台任务状态按单进程维护。`.env` 由应用从项目根目录读取。常用检查：

```bash
sudo systemctl status storyforge
sudo journalctl -u storyforge -n 100 --no-pager
curl http://127.0.0.1:8000/api/health
```

准备真实域名及其 HTTPS 证书，将 `deploy/nginx.conf` 中的域名、证书路径替换为实际值，再安装站点配置：

```bash
sudo install -m 0644 deploy/nginx.conf /etc/nginx/sites-available/storyforge
sudo ln -s /etc/nginx/sites-available/storyforge /etc/nginx/sites-enabled/storyforge
sudo nginx -t
sudo systemctl reload nginx
```

Nginx 会将 API、媒体和语音请求转发给后端并保留 Host/HTTPS 信息。API 错误不会变成前端 HTML，视频范围请求也会交给后端处理。

升级前等待制作任务完成，再停止服务并备份 `data/`；复制 SQLite 文件应在服务停止后进行。更新源码时保留 `.env` 和完整 `data/`，更新依赖、重新构建前端后重启服务。不要使用会删除运行时目录的全目录覆盖或同步选项。
