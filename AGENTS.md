# StoryForge AI 开发指南

## 项目概览

- `app/`：React 19 / TypeScript 前端（Vinext）。功能按 `app/features/` 组织，共用 UI 放在 `app/shared/`。
- `backend/`：Python 3.11+ / FastAPI API 与工作流执行逻辑。
- `backend/modules/`：按业务领域拆分的服务、仓储与工作流代码；`backend/integrations/` 封装外部模型、语音、封面和视频服务。
- `db/`、`drizzle/`：Drizzle SQLite schema 与迁移文件。
- `browser-extension/`：抖音发布辅助浏览器扩展，原生 JavaScript，不依赖前端构建产物。
- `tests/` 与 `backend/tests/`：分别为前端构建后行为测试和 Python 单元测试。
- `data/`：本地数据库、生成媒体和运行时状态，禁止提交或手工修改后作为源码依赖。

## 开发环境

需要 Node.js 22+、Python 3.11+ 与 FFmpeg。

```powershell
npm install
npm run dev

python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

前端依赖后端的本地 API；后端未运行时，前端应保持演示模式可用。

## 验证

按改动范围运行最小充分的验证；提交涉及前后端交互或构建配置的改动前，运行全部测试。

```powershell
npm run lint
npm test
python -m unittest discover backend/tests
```

- `npm test` 会先执行生产构建，再执行 `tests/*.test.mjs`。
- 数据库 schema 变动后运行 `npm run db:generate`，并提交生成的 `drizzle/` 迁移文件。

## 编码约定

- TypeScript 启用了严格模式。优先复用 `app/features/shared/types.ts` 中的类型；不要以 `any` 绕过类型检查。
- 遵循邻近代码的格式和命名；不要为了无关格式化制造大范围 diff。
- 前端 API 请求集中使用 `app/lib/api.ts` 的 API 地址约定。新增接口时同步更新前端类型与后端请求/响应模型。
- Python 代码保持类型标注，业务规则放入对应的 `backend/modules/<domain>/`，外部 HTTP/第三方 SDK 调用放入 `backend/integrations/`。
- 浏览器扩展需兼容 Chrome/Edge；发布流程只能辅助填充，绝不读取或导出 Cookie、绕过验证码/风控、或自动点击最终发布按钮。
- 修改封面上传逻辑时，保留对原图实际像素比例的校验；不可偷偷缩放或裁剪图片。

## 数据与安全

- 不要提交 `.env`、API 密钥、语音密钥、Cookie、`data/` 内容、生成媒体或构建产物。
- 配置示例仅更新 `.env.example`，且不得填入真实凭据。
- 日志、错误提示和测试夹具中不得泄露密钥、配对码或用户内容。
- 删除工作流会涉及本地媒体目录：改动清理逻辑时先确认目标局限在该工作流的媒体路径内。

## 变更原则

- 先确认现有实现和测试，采用解决需求所需的最小改动。
- 不重构无关代码，不删除既有功能或运行时数据，除非任务明确要求。
- 修复缺陷时，优先添加能复现问题的测试；新增功能时，为核心成功路径和关键失败路径补充测试。
- 改动接口、数据库、发布流程或媒体生成流程时，在交付说明中写明兼容性影响和已执行的验证。
