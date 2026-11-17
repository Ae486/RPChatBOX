# RPChatBOX

基于 Flutter 和 Python FastAPI 的 AI 聊天与角色扮演应用。

## 主要功能

- 接入 OpenAI、Claude、Gemini、DeepSeek 等模型及 OpenAI 兼容接口。
- 流式聊天、对话历史与消息分支管理。
- Markdown、LaTeX、代码高亮和图片展示。
- MCP 工具接入。
- 角色扮演与长篇故事创作，包含设定引导、记忆检索和 Agent 运行时。

## 本地启动（Windows）

需要 Flutter SDK（Dart `^3.9.2`）、Python 3.12，以及 Visual Studio 的“使用 C++ 的桌面开发”组件。本地验证环境为 Flutter 3.35.6 / Dart 3.9.2 / Python 3.12。

```powershell
git clone https://github.com/Ae486/RPChatBOX.git
cd RPChatBOX
```

先在一个 PowerShell 终端启动后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

后端默认地址为 `http://127.0.0.1:8765`。访问 `http://127.0.0.1:8765/api/health` 可检查运行状态。

再在另一个终端从项目根目录启动客户端：

```powershell
flutter pub get
flutter run -d windows
```

首次使用时，在设置中配置模型服务的 API 地址、API Key 和模型。使用后端代理与角色扮演功能时，开启“Python 后端”并保持后端运行。模型调用需要自行配置供应商账号。

后端配置通过 `CHATBOX_BACKEND_` 前缀的环境变量覆盖，例如端口 `CHATBOX_BACKEND_PORT`、数据目录 `CHATBOX_BACKEND_STORAGE_DIR`。API 文档默认关闭；启动前设置 `$env:CHATBOX_BACKEND_DEBUG = "true"` 可开启 `/docs`。

## 项目结构

| 目录 | 内容 |
| --- | --- |
| `lib/` | Flutter 页面、组件、状态管理与模型适配器 |
| `backend/` | FastAPI 接口、模型代理与数据存储 |
| `backend/rp/` | 角色扮演、故事创作、记忆与 Agent 子系统 |
| `packages/flutter_chat_ui/` | 本地维护的聊天 UI 组件 |
| `test/`、`backend/tests/`、`backend/rp/tests/` | 客户端与后端测试 |
| `.trellis/` | 开发规范与任务记录 |

## 开发检查

```powershell
flutter analyze
flutter test
python -m ruff check backend
cd backend
python -m pytest tests rp/tests
```

真实 MCP 集成测试默认跳过；需通过 `--dart-define=CHATBOX_MCP_TEST_API_KEY=<your-key>` 显式配置后运行，模型调用可能产生费用。

主要入口为 [Flutter 客户端](lib/main.dart)、[FastAPI 后端](backend/main.py) 和 [角色扮演模块](backend/rp/)。

API Key、聊天数据和本地构建产物请保留在本地。仓库尚未声明项目级开源许可证。
