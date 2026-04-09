# ChatBoxApp 需求文档

**版本**: 1.0  
**日期**: 2026-04-07  
**项目**: ChatBoxApp — 跨平台 Flutter LLM 客户端

---

## 1. 项目概述

### 1.1 项目目标

ChatBoxApp 是一款跨平台 AI 对话客户端，目标是为用户提供统一、流畅的多模型 LLM 交互体验，同时支持通过本地 Python 后端代理进行请求路由、企业级定制化部署。

### 1.2 核心价值

- **多提供商统一接入**：OpenAI、Google Gemini、Anthropic Claude、自定义 OpenAI-compatible 端点
- **跨平台支持**：Android、iOS、Windows、macOS、Linux、Web
- **本地后端代理**：Python FastAPI 代理层，支持企业内部部署场景
- **角色扮演系统**：独立的 RP 功能模块，支持复杂故事叙述和角色一致性保障
- **MCP 协议集成**：支持 Model Context Protocol，扩展模型工具调用能力

### 1.3 目标用户

- 个人 AI 重度用户（需要多模型切换、复杂对话管理）

- ~~企业内网部署用户（通过后端代理隔离 API 密钥，统一流量管控）~~

  [^]: 项目对流量统计未到管控层次，且安全性不足，仅为个人本地使用

  

- 创作者/角色扮演用户（使用 RP 模块进行沉浸式叙事创作）

- ~~开发者（通过 MCP 集成扩展模型工具能力）~~

  [^]: 当前项目并非面向开发者，MCP只做调用

---

## 2. 功能需求

### 2.1 对话管理

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 多会话管理 | 支持同时维护多个独立对话，侧边抽屉切换 | P0 |
| 会话持久化 | 所有对话通过 Hive 本地数据库持久化存储 | P0 |
| 会话重命名 | 用户可对任意会话自定义标题 | P1 |
| 会话删除 | 单条删除或批量清除会话 | P1 |
| 会话搜索 | 全文搜索对话内容（SearchPage） | P1 |
| 对话导出 | 支持将对话内容导出为文件（ExportService） | P2 |
| 会话摘要 | 自动或手动生成会话摘要（ConversationSummaryService） | P2 |
| 线程投影 | 支持对话分支/线程视图（ThreadProjection） | P2 |

**验收标准**：
- 新建会话后立即在侧边栏可见
- 切换会话时保持各自独立的滚动位置（IndexedStack 状态保持）
- 会话数据在 App 重启后完整保留

### 2.2 消息输入与发送

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 文本输入 | 多行文本输入框，支持换行 | P0 |
| 流式输出 | 实时逐字显示 AI 响应（SSE 流式传输） | P0 |
| 停止生成 | 随时中断正在生成的 AI 响应 | P0 |
| 文件附件 | 支持上传图片、PDF、Word、文本等文件 | P1 |
| 图片附件 | 图片直接嵌入对话发送（视觉模型支持） | P1 |
| 重新生成 | 对已有 AI 回复触发重新生成 | P1 |
| 消息编辑 | 编辑已发送消息并重新请求 | P2 |

**验收标准**：
- 流式输出延迟 < 200ms（从收到第一个 token 到页面渲染）
- 停止生成后 UI 立即响应，不残留 loading 状态
- 文件附件支持格式：`.txt`, `.pdf`, `.docx`, `.png`, `.jpg`, `.gif`, `.webp`

### 2.3 消息渲染

| 功能 | 描述 | 优先级 |
|------|------|--------|
| Markdown 渲染 | 完整 CommonMark 规范支持 | P0 |
| 代码块高亮 | 多语言语法高亮（flutter_highlight） | P0 |
| LaTeX 数学公式 | 行内公式和块级公式渲染（flutter_math_fork） | P1 |
| Mermaid 图表 | 流程图、时序图等渲染（WebView + SVG 缓存） | P1 |
| Thinking 气泡 | 显示 AI 思考过程（独立 thinking 区块） | P1 |
| 无气泡布局 | AI 响应直接在背景渲染，无气泡包裹 | P0 |
| 代码一键复制 | 代码块右上角复制按钮 | P1 |
| Mermaid 全屏 | 点击 Mermaid 图表进入全屏查看 | P2 |

**验收标准**：
- Markdown 渲染与 CommonMark 规范兼容
- LaTeX 公式正确渲染 `$...$`（行内）和 `$$...$$`（块级）
- Mermaid SVG 结果本地缓存，避免重复渲染开销

### 2.4 模型服务管理

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 添加服务提供商 | 支持 OpenAI、Google、Anthropic、自定义端点 | P0 |
| API Key 配置 | 每个 Provider 独立配置 API Key | P0 |
| 模型列表获取 | 自动从 Provider 拉取可用模型列表 | P0 |
| 连接测试 | 一键测试 Provider 连接状态与响应时延 | P1 |
| 模型参数配置 | Temperature、Max Tokens、Top-P 等参数调整 | P1 |
| 自定义请求头 | 支持为 Provider 添加自定义 HTTP Headers | P2 |
| Provider 排序 | 支持拖拽调整 Provider 显示顺序 | P2 |

**验收标准**：
- 支持的 Provider 类型：OpenAI compatible、Google LangChain、Anthropic、Proxy
- 连接测试结果显示响应时延（毫秒级）
- 模型列表动态刷新，不需要重启 App

### 2.5 后端代理模式

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 直连模式 (direct) | Flutter 直接请求 LLM API | P0 |
| 代理模式 (proxy) | 通过本地 Python 后端转发 | P1 |
| 自动模式 (auto) | 代理优先，失败自动熔断回退直�� | P1 |
| 后端健康检查 | 检测 Python 后端运行状态 | P1 |
| 熔断器 (Circuit Breaker) | 连续失败后自动切换，成功后自动恢复 | P1 |
| 后端生命周期管理 | 桌面/移动端自动启停 Python 后端进程 | P1 |

**后端 API 端点**（OpenAI 兼容规范）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/v1/chat/completions` | POST | 流式/非流式对话 |
| `/v1/models` | GET/POST | 模型列表 |
| `/v1/providers` | GET/POST | 提供商注册表 |

**验收标准**：
- auto 模式下，代理失败后 3 次内自动切换直连
- 熔断恢复时间窗口可配置
- 后端健康状态在设置页实时显示

### 2.6 角色扮演系统 (Roleplay)

| 功能 | 描述 | 优先级 |
|------|------|--------|
| RP 故事管理 | 创建、编辑、删除角色扮演故事（RpStoryMeta） | P1 |
| 角色配置 | 定义角色名、性格、外貌等属性 | P1 |
| 场景管理 | 管理故事场景和背景设定 | P1 |
| 状态追踪 | 自动追踪故事状态变化（StateModule） | P2 |
| 一致性检验 | 多维度验证角色一致性（ConsistencyGate） | P2 |
| 记忆仓库 | 持久化 RP 记忆片段（RpMemoryRepository） | P2 |
| Worker 调度 | 后台 Agent 异步执行 RP 分析任务 | P2 |
| 快照系统 | RP 状态快照与版本管理 | P2 |

**一致性检验维度**：
- 外貌一致性（AppearanceValidator）
- 时间线一致性（TimelineValidator）
- 知识边界（KnowledgeValidator）
- 人物在场（PresenceValidator）
- 状态连续性（StateValidator）

**验收标准**：
- RP 数据存储在独立 Hive box（`rp_*`，TypeId 50-59）
- 不影响普通对话功能（完全隔离命名空间）

### 2.7 MCP 协议支持

| 功能 | 描述 | 优先级 |
|------|------|--------|
| MCP 服务器配置 | 添加、编辑、删除 MCP 服务器连接 | P1 |
| 自动连接 | App 启动时自动连接已启用的 MCP 服务器 | P1 |
| 工具调用集成 | 模型通过 MCP 调用外部工具 | P2 |
| 服务器状态监控 | 实时显示各 MCP 服务器连接状态 | P2 |

**验收标准**：
- 支持标准 MCP 协议（mcp_dart ^1.2.2）
- MCP 服务器配置持久化保存

### 2.8 自定义角色 (Custom Roles)

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 角色预设 | 创建系统 Prompt 角色预设（RolePreset） | P1 |
| 自定义角色库 | 管理用户自定义角色（CustomRolesPage） | P1 |
| 会话角色绑定 | 为特定对话指定默认角色 | P2 |

### 2.9 UI 与外观设置

| 功能 | 描述 | 优先级 |
|------|------|--------|
| 亮色/暗色/跟随系统主题 | 三档主题切换 | P0 |
| UI 缩放 | 0.85x ~ 1.25x 界面缩放 | P1 |
| 字体选择 | 系统字体 / NotoSans / NotoSerif | P1 |
| 代码字体选择 | 系统等宽 / JetBrainsMono / NotoSansMono | P1 |
| 缓存清理 | 清除图片缓存、Mermaid SVG 缓存 | P2 |

---

## 3. 非功能需求

### 3.1 性能

| 指标 | 要求 |
|------|------|
| 流式输出首字延迟 | < 300ms（从请求到 UI 渲染首 token） |
| Markdown 渲染 | 长文本（> 5000 字）渲染 < 500ms |
| 会话列表加载 | 100 条会话列表 < 200ms |
| Mermaid SVG 缓存命中 | 缓存命中时渲染 < 50ms |
| 应用启动时间 | 冷启动 < 3s（含后端进程启动为 < 8s） |

### 3.2 可靠性

- 流式输出中断时，已收到内容不丢失
- SSE 解析符合 OpenAI 规范，JSON 不跨行
- 后端熔断器防止级联故障
- Hive 数据库写入失败时提供用户提示

### 3.3 安全性

- API Key 仅存储在本地（SharedPreferences/Hive），不上传任何服务器
- Python 后端仅监听 `127.0.0.1:8765`（本地回环地址），不对外暴露
- 文件附件内容在会话结束后可清除
- 无遥测/埋点数据上报

### 3.4 平台兼容性

| 平台 | 支持状态 |
|------|----------|
| Android | 支持（WebView 自动初始化） |
| iOS | 支持 |
| Windows | 支持（WebView2 手动初始化） |
| macOS | 支持 |
| Linux | 支持 |
| Web | 支持（后端模式不可用） |

### 3.5 可扩展性

- Provider 适配器通过 `AIProvider` 抽象接口统一，新增 Provider 只需实现接口
- Hive TypeId 按范围分配，避免冲突（核心 0-3，RP 50-59）
- 后端服务通过 Provider Registry 动态注册，支持运行时路由

---

## 4. 技术架构约束

### 4.1 Flutter 客户端层次依赖（必须遵守）

```
UI (pages / widgets / chat_ui/owui)
    ↓
State Management (Provider)
    ↓
Controllers (stream_output_controller)
    ↓
Business Services (conversation, model_service_manager...)
    ↓
Provider Adapters (ai_provider, openai, langchain, proxy...)
    ↓
Data Models (Hive) + Storage
```

**禁止跨层直接调用**（如 UI 直接访问 Adapter）。

### 4.2 SSE 流式传输约束（关键）

- 每条事件格式：`data: {json}\n\n`
- JSON **不得跨行**（LineSplitter 限制）
- 流结束标志：`data: [DONE]\n\n`
- 响应头：`Content-Type: text/event-stream`, `X-Accel-Buffering: no`
- **禁止任何形式的缓冲**，必须逐 chunk 立即 flush

### 4.3 Hive 数据模型约束

- TypeId 0-3：核心模型（Conversation、Message、File 等）
- TypeId 50-59：角色扮演模型
- 新增模型必须申请新的 TypeId 段，不得复用已有范围

### 4.4 后端代理约束

- 后端接口必须兼容 OpenAI API 规范
- 运行时路由（RuntimeRoutingService）根据 Provider 类型分派至对应 Service
- LiteLLM 负责统一多模型接入；Gemini Native Service 处理 Gemini 特殊能力

### 4.5 角色扮演隔离约束

- RP 功能所有数据存储在 `rp_*` 命名的 Hive box
- RP 功能**只扩展**，不修改基础对话层代码
- Worker Agent 异步执行，不阻塞对话主线程

---

## 5. 用户故事

### US-001 多模型切换对话

> 作为一名 AI 重度用户，我希望在同一 App 内无缝切换不同 LLM 服务商（如从 GPT-4o 切换到 Claude 3.5），这样我可以对比不同模型的回答质量，而不需要打开多个应用。

**验收标准**：
- 在会话设置面板中选择 Provider 和 Model
- 切换后新消息使用新模型，历史消息保留
- Provider 连接失败时给出明确错误提示

### US-002 流式阅读长文档分析

> 作为一名研究人员，我希望上传 PDF 文档并实时看到 AI 的分析结果逐字出现，这样我可以在 AI 还在生成时就开始阅读，节省等待时间。

**验收标准**：
- 支持上传 PDF 文件（syncfusion_flutter_pdf 提取文本）
- AI 响应以流式方式逐字渲染
- 中途可点击停止按钮中断生成

### US-003 企业内网隔离部署

> 作为企业 IT 管理员，我希望通过本地 Python 后端代理统一管理 API 密钥和请求日志，这样员工不需要各自持有 API Key，且所有请求经过内部审计。

**验收标准**：
- 开启代理模式后，Flutter 客户端将请求发送至 `localhost:8765`
- Python 后端使用统一的 API Key 转发至上游 LLM API
- 后端进程在桌面端 App 启动时自动运行

### US-004 沉浸式角色扮演创作

> 作为一名创意写作者，我希望定义角色、场景和故事背景，让 AI 扮演角色持续讲述故事，同时系统自动检测角色行为是否与设定一致。

**验收标准**：
- 创建故事时可设置角色属性、场景背景
- 一致性检验在后台异步运行，不影响对话流畅性
- 违规提示以非侵入方式展示（不打断用户阅读）

### US-005 技术助手代码调试

> 作为一名软件开发者，我希望向 AI 发送代码片段，得到带语法高亮的代码分析和 Mermaid 流程图说明，这样我能快速理解复杂系统的调用关系。

**验收标准**：
- 代码块自动识别语言并语法高亮
- Mermaid 图表正确渲染为矢量图
- 点击图表可进入全屏模式查看细节

---

## 6. 数据模型概览

### 6.1 核心模型（TypeId 0-3）

| 模型 | TypeId | 说明 |
|------|--------|------|
| Conversation | 0 | 会话元数据（标题、创建时间、绑定 Provider/Model） |
| Message | 1 | 消息内容（角色、文本、附件、时间戳） |
| AttachedFile | 2 | 附件元数据（路径、类型、大小） |
| ConversationSettings | 3 | 会话级 AI 参数（temperature、maxTokens 等） |

### 6.2 Provider 配置

| 字段 | 类型 | 说明 |
|------|------|------|
| type | ProviderType | openai / langchain / anthropic / proxy |
| apiUrl | String | API 基础 URL |
| apiKey | String | 认证密钥 |
| backendMode | BackendMode | direct / proxy / auto |
| proxyApiUrl | String? | 代理地址（默认 http://localhost:8765） |
| circuitBreaker | CircuitBreakerConfig | 熔断器配置 |

---

## 7. 依赖与集成

### 7.1 主要 Flutter 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| dio | ^5.4.0 | HTTP 请求 |
| hive / hive_flutter | ^2.2.3 | 本地数据库 |
| langchain + langchain_openai/google | ^0.8.x | LLM 编排框架 |
| anthropic_sdk_dart | ^0.3.1 | Anthropic 原生 SDK |
| flutter_chat_ui | ^2.0.0 | 对话 UI 组件（本地 Fork） |
| mcp_dart | ^1.2.2 | MCP 协议客户端 |
| webview_flutter | ^4.4.2 | Mermaid/复杂渲染 |
| markdown_widget | ^2.3.2 | Markdown 渲染 |
| flutter_math_fork | ^0.7.2 | LaTeX 渲染 |
| serious_python | ^0.9.9 | 内嵌 Python 运行时 |

### 7.2 Python 后端依赖

| 包 | 用途 |
|----|------|
| FastAPI + uvicorn | Web 框架 |
| litellm | 多模型统一接入 |
| httpx | 上游 HTTP 请求 |
| pydantic | 数据验证 |

---

## 8. 开发与维护规范

1. 修改 `@HiveType` 模型后必须运行 `flutter pub run build_runner build`
2. 修改文件后更新文件头注释（INPUT/OUTPUT/POS）
3. 修改目录后更新该目录的 `INDEX.md`（如存在）
4. RP 功能只扩展，不改基础层
5. 新增 Hive 模型须在本文档 TypeId 分配表中登记
6. 后端新增 Provider 须同步更新 Provider Registry

---

*本文档基于项目现有代码库分析生成，反映当前已实现或正在实现的功能状态。*
