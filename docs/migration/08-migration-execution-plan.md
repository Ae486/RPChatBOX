# 基础 LLM 请求链迁移实施计划

## 0. 当前落地状态

截至 `2026-04-07`，已完成：

1. `Phase 0` 首批基线测试
   - Flutter 路由特征测试
   - Flutter `<think>` 解析测试
   - backend health/chat contract 测试
   - backend SSE replay tests
2. `Phase 1A` 最小切片
   - backend 新增请求规范化层
   - `LiteLLMService` 已接入请求规范化
   - `LLMProxyService` 已接入请求规范化
   - httpx 路径的 `extra_body` 语义已修正为保留 `extra_body` 字段，而不是错误展开
3. `Phase 1B` 最小切片
   - backend 新增流语义归一层
   - backend 现在会把 provider-specific reasoning / candidates 流转成兼容的 OpenAI-style `delta.content` chunk
   - reasoning/thinking 仍以 `<think>...</think>` 兼容协议向 Flutter 传递
4. `Phase 1C` 第一刀
   - `ProxyOpenAIProvider` 主路径已优先消费 backend 标准化后的 `choices[0].delta.content`
   - 保留 legacy fallback，兼容旧 backend 仍可能返回的 `reasoning* / candidates` 风格流
   - 新增 Flutter 单测固定 proxy parser 行为，覆盖 normalized path 与 legacy path
5. `Phase 1C` 第二刀
   - 已补 direct/proxy 请求体特征测试，固定当前文本与附件边界
   - 已补 direct/proxy 文本与附件链路的特征测试，不再以“复刻 direct 每个细节”为目标
6. `Phase 1.5` 最小切片
   - backend 已新增附件消息转换层，负责把 `files` 转成模型可消费的多模态 `messages`
   - 文档附件优先使用 `MarkItDown` 解析；未安装时退回基础文本读取
   - 图片附件在 backend 转为 `data:` URL 的 `image_url` 内容
   - `ProxyOpenAIProvider` 已开始显式上传 `files` 元数据到 backend
   - UI 侧”有附件强制直连”的临时保护已移除，附件主链改为可走 backend proxy
   - 附件协议已从”本地文件路径过渡态”升级为”远程上传协议”：
     - `AttachedFile` 新增 `data` 字段（base64 编码文件内容），`path` 改为可选
     - Flutter 发送附件时读取文件字节并 base64 编码放入 `data` 字段
     - backend 优先从 `data` 解码，无 `data` 时回退 `path`（桌面本地兼容）
     - 移动端连远程 backend 时附件链路可用
7. `Phase 2` 第一刀
   - `ProxyOpenAIProvider` 已补前端侧 `CancelToken`
   - UI 点击停止时，proxy 链已能真正取消 Flutter -> backend 的 HTTP 请求
8. `Phase 2` 第二刀
   - `LiteLLMService` 已切到官方 `LiteLLM Router`
   - backend 默认在 LiteLLM 路径上接手 `retries / request timeout / first-chunk timeout`
   - `Router` 以单 deployment 缓存模式构建，保留当前 Flutter 契约，不提前引入 provider registry
9. `Phase 2` 第三刀
   - backend `/v1/chat/completions` 流出口已补客户端断开守卫
   - 当前端中止 proxy 请求时，backend 会主动关闭上游 async generator，而不是继续悬挂等待
   - 保持现有 `text/event-stream` 与 `<think>` 兼容契约不变
10. backend 启动入口已重构为可安全 import 的 app factory，便于后续 contract/integration tests
11. `Phase 3` 第一刀
   - backend 已新增 provider registry：
     - `PUT /api/providers/{id}`
     - `GET /api/providers`
     - `GET /api/providers/{id}`
     - `DELETE /api/providers/{id}`
   - backend `/v1/chat/completions` 与 `POST /models` 已支持 `provider_id` 解引用
   - `ProxyOpenAIProvider` 在 backend 模式下会先把 provider 同步到 backend registry，再以 `provider_id` 调用聊天和模型探测接口
   - `ModelServiceManager` 已补 best-effort backend provider sync / delete
   - `AddModelDialog` 在 backend 模式下已改为走当前主路由选择，而不是强制直连
12. `Phase 3` 流式语义基建第一刀
   - backend 已新增内部结构化流事件模型：
     - `thinking`
     - `text`
     - `tool_call`
     - `error`
     - `raw`
   - `StreamNormalizationService` 现在先提取内部事件，再发射当前 Flutter 兼容的 SSE chunk
   - 这一步不改变 Flutter 现有 `<think>...</think>` 渲染契约
   - Gemini 原生 `parts[]` 中的 `thought / text / function_call` 已开始按结构化语义处理
   - 仅对“无显式语义标记的旧 Gemini 兼容流”保留首个 part 视为 thinking 的过渡兼容分支
13. `Phase 3` 流式语义基建第二刀
   - backend 已补 Typed/Native 上游结构支持：
     - OpenAI Responses 风格 `type=response.*` stream events
     - Anthropic 原生 `content_block_* / thinking_delta / tool_use` 事件序列
   - 当前这些结构仍会先进入 backend 内部事件层，再降到现有 Flutter 兼容输出
   - 这一步的目标是补齐 backend 对“上游/框架返回结构”的理解，而不是立即切外部 typed events 协议
14. `Phase 3` Gemini Native Route
   - backend 已新增官方 `google-genai` SDK 路由：
     - `backend/services/gemini_native_service.py`
   - 当前仅在以下条件下启用：
     - `provider.type == gemini`
     - backend 路由模式为 `auto`
     - provider URL 为 Gemini native 风格，而不是 `/openai` 兼容端点
   - 请求会先被转换为 Gemini 原生 `Content/Part/GenerateContentConfig`
   - 返回会先进入 backend 内部事件层，再转换为当前 Flutter 兼容 SSE 输出
   - native 路由失败时，会安全退回当前 `LiteLLM -> httpx` 链
15. `Phase 3` OpenAI-Compatible / Responses 强化
   - backend 已补 OpenAI Responses 更完整的 typed stream event 支持：
     - `response.reasoning_text.delta/done`
     - `response.reasoning_summary_text.delta/done`
     - `response.function_call_arguments.delta/done`
     - `response.output_item.added/done` 的工具调用收口
   - backend 已补 OpenAI-compatible 混合 chunk 场景：
     - `reasoning_content + tool_calls` 同 chunk 共存
   - 当前真实主验证路径已切到：
     - OpenAI-compatible 端口
     - OpenAI Responses 风格流
   - 这也是后续对外 typed events 协议切换的第一优先级基础
16. `Phase 3` External Typed SSE Dual-Track
   - backend 已在现有 `text/event-stream` 传输方式上新增 typed SSE 输出
   - 请求扩展字段：
     - `stream_event_mode = "legacy" | "typed"`
   - `legacy`：
     - 保持当前 `<think>...</think>` 兼容流
     - 仍以 `data: [DONE]` 结束
   - `typed`：
     - 输出结构化 payload：
       - `thinking_delta`
       - `text_delta`
       - `tool_call`
       - `error`
       - `raw`
       - `done`
     - 不再输出 `<think>` 标签和 `data: [DONE]`
   - 当前仅 backend 落地，Flutter 主链尚未切换到 typed 消费模式
17. `Phase 3` Flutter Typed Consumer Bridge
   - Flutter `ProxyOpenAIProvider` 已开始为流式请求发送：
     - `stream_event_mode: typed`
   - 当前前端采用“部分状态层升级 + UI 外观不变”的方式：
     - `AIProvider` 新增可选事件流接口
     - `StreamOutputController` 现在可消费结构化事件流
     - `ProxyOpenAIProvider` 会把 backend typed SSE 转成 `thinking/text/toolCall` 事件
     - `conversation_view_v2` 将 typed `thinking/tool` 直接写入 `StreamManager`
     - 文本正文仍走 `ChunkBuffer` + 现有渐进渲染路径
     - 但 typed text flush 进入 `StreamManager.appendText()`，不再重新走旧 `<think>` 协议解析
   - 因此当前 UI 视觉和渲染行为保持不变，但 thinking/tool 状态已经不必完全依赖旧 `<think>` 文本协议
   - 保留代码级回滚开关，必要时可切回 legacy stream request
18. `Phase 3` Typed Tool Lifecycle Contract
   - 已新增迁移文档：
     - `docs/migration/11-typed-stream-schema.md`
   - typed SSE 协议当前已冻结的工具事件包括：
     - `tool_call`
     - `tool_started`
     - `tool_result`
     - `tool_error`
   - backend 内部 `StreamEvent` 已扩展：
     - `tool_started`
     - `tool_result`
     - `tool_error`
   - backend typed SSE 发射层已支持对应 payload 输出
   - Flutter typed parser 已支持解析这些事件
   - `conversation_view_v2` 已将这些事件映射到现有 `ToolCallBubble` 状态链：
     - `pending`
     - `running`
     - `success`
     - `error`
   - 当前这一步只完成协议与状态层打底：
     - 还没有实现完整 backend MCP runtime
     - 但后续 backend 接管工具/MCP 时，不需要再回头重改流协议和前端气泡状态链
19. `Phase 3` Proxy Stream Bridge Simplification
   - `ProxyOpenAIProvider` 已先完成第一阶段收口：
     - `sendMessageStream()` 与 `sendMessageEventStream()` 已改为共用同一套底层：
       - request build
       - SSE line reading
       - JSON decode
       - upstream/backend error extraction
   - `ProxyStreamChunkParser` 也已完成第二阶段收口：
     - `parse()` 与 `parseEvents()` 仍保留两个公开视图
     - 但 typed payload 的源逻辑已统一到单一内部解析结果
   - 这一步不改变：
     - typed/legacy 协议
     - UI 行为
     - 回滚开关
   - 因此当前剩下的是迁移期兼容视图，而不是高风险的双实现债
20. `Phase 3` Model Registry Foundation
   - backend 已新增 provider-scoped model registry：
     - `GET /api/providers/{provider_id}/models`
     - `GET /api/providers/{provider_id}/models/{model_id}`
     - `PUT /api/providers/{provider_id}/models/{model_id}`
     - `DELETE /api/providers/{provider_id}/models/{model_id}`
   - backend 已新增独立持久化：
     - `storage/models.json`
   - provider 删除时，backend 会级联删除关联 model registry entries
   - Flutter 已新增 `BackendModelRegistryService`
   - `ModelServiceManager` 已开始：
     - add/update/delete model -> best-effort sync to backend
     - `syncModelsToBackend()`
     - `refreshModelMirrorsFromBackend()`
   - backend 模式下，模型服务页加载时会先：
     - sync providers
     - sync models
     - refresh provider mirrors
     - refresh model mirrors
   - 当前仍是保守迁移态：
     - Flutter 本地 model 仍保留为镜像/回滚层
     - backend 未返回的本地 model 暂不主动删除

当前仍待完成：

1. `Phase 0` 剩余保护网
   - 文本主链已无新的硬缺口；若进入 Phase 1.5，再补 backend 附件链对应测试
2. `Phase 1C`
   - 文本主链差异已基本收口
   - 文本链路当前不再阻塞下一阶段
3. `Phase 1.5`
   - 仍需做真实手工回归，重点确认 docx/pdf/image 在 backend 模式下的行为
   - 当前实现仍是“本机文件路径”过渡态，不是远程上传协议
4. `Phase 2`
   - backend 已接住 LiteLLM 路径上的重试/超时，并已补客户端断开时的流关闭
   - 但还没有接管 route selection / fallback policy / cancel observability
   - backend -> upstream 的取消已完成最小收敛，但完整观测与更高层回退策略仍未完成
5. 更高层验证
   - backend 模式下的真实手工回归
   - 移动端/桌面端实际链路验证
6. `Phase 3`
   - backend 现在已具备 provider + model registry 基础，但 Flutter 仍保留本地 provider/model 配置作为回滚镜像，不是最终态
   - 当前 provider 同步是“lazy ensure + best-effort sync”过渡态，不是最终的事务化配置中心
   - `ProxyOpenAIProvider` 的高风险双实现债已基本收口，当前保留的是迁移期兼容视图
   - backend 仍未真正接管 MCP client / tool execution runtime
   - Flutter selector / conversation settings / provider detail 读路径还未完全切到 backend 真源语义

## 1. 文档目标

本文档不是重复描述架构原则，而是把已有分析收敛成可执行的迁移计划，回答 5 个问题：

1. 现在能不能开始迁移
2. 先迁什么，后迁什么
3. 每一阶段具体改哪些链路
4. 每一阶段如何验证
5. 出问题如何快速回滚

本文只覆盖基础 LLM 请求链，不包含 RP 相关功能。

## 2. 已确认前提

本计划基于以下已确认前提：

1. 当前默认直连主链是 `HybridLangChainProvider`，不是 `OpenAIProvider`
2. backend 已经跑通 `/api/health`、`/models`、`/v1/chat/completions`
3. 当前 backend 是“可用的代理执行层 MVP”，但还不是运行时真源
4. 当前 Flutter 同时承担：
   - 发送入口
   - provider 路由选择
   - 请求体拼装
   - thinking/reasoning 语义提取
   - UI 流状态解释
5. Phase 1 可以只做文本主链
6. 如果 Python 生态中有成熟轮子，可以直接上位替代 Flutter 里的粗糙实现
7. direct mode 保留，作为回滚通道
8. 第一阶段保留 `<think>...</think>` 兼容协议，不改前端 UI 消费边界
9. `direct` 链只作为现状基线与兼容参考，不是要求 backend 逐细节复刻的目标实现

## 3. 当前真实执行链

### 3.1 Flutter 主链

当前文本聊天主链为：

```text
streaming.dart
  -> _startAssistantResponse()
  -> ModelServiceManager.createProviderInstance()
  -> ProviderFactory.createProviderWithRouting()
  -> HybridLangChainProvider / ProxyOpenAIProvider
  -> StreamOutputController.startStreaming()
  -> StreamManager.append()
  -> UI thinking/body 渲染
```

关键位置：

- `lib/widgets/conversation_view_v2/streaming.dart`
- `lib/services/model_service_manager.dart`
- `lib/adapters/ai_provider.dart`
- `lib/adapters/hybrid_langchain_provider.dart`
- `lib/adapters/proxy_openai_provider.dart`
- `lib/controllers/stream_output_controller.dart`
- `lib/widgets/stream_manager.dart`

### 3.2 backend 主链

当前 backend 主链为：

```text
/v1/chat/completions
  -> backend/api/chat.py
  -> LiteLLMService 或 LLMProxyService
  -> upstream provider
  -> SSE relay
  -> Flutter ProxyOpenAIProvider
```

关键位置：

- `backend/main.py`
- `backend/api/chat.py`
- `backend/services/litellm_service.py`
- `backend/services/llm_proxy.py`
- `backend/models/chat.py`

### 3.3 当前最关键的迁移事实

1. backend 已能发请求，但 Flutter 仍然控制“怎么发”
2. proxy 链与 direct 链当前不等价，尤其是：
   - 请求体规范化
   - thinking/reasoning 提取
   - 附件处理
   - 取消行为
3. 所以后续迁移的核心不是“把请求搬过去”，也不是“机械复制 direct 细节”，而是**逐步把运行时语义和控制权从 Flutter 收口到 backend，并在可行处使用更成熟的 Python 实现上位替代**
4. 当前 backend 已接住附件最小链路，但实现仍是过渡态：Flutter 上传本机文件元数据，backend 本地读取并转换，不是最终的跨设备上传协议
5. 当前 backend 在 LiteLLM 路径上已开始使用官方 `Router` 收口 `retries / timeout`，但还未接管真正的 provider 路由与 fallback 真源

## 4. 迁移总策略

### 4.1 总原则

按以下顺序推进：

1. 先冻结现状
2. 再迁执行语义
3. 再迁路由与韧性策略
4. 最后迁配置真源

禁止同一阶段同时做三件事：

1. 改 Flutter -> backend 请求契约
2. 改 backend -> Flutter 流契约
3. 改 backend 内部执行实现

这三件事同轮一起做，排错会失控。

### 4.2 迁移边界

Flutter 保留：

- UI 渲染
- Markdown / 代码块 / LaTeX 等展示能力
- StreamManager 现有显示态逻辑
- direct mode 回滚能力
- 本地会话展示状态

backend 逐步接手：

- 请求规范化
- 上游执行
- thinking/reasoning 语义归一
- 路由选择
- fallback / retry / circuit breaker
- cancel protocol
- 后续 provider registry / key custody

### 4.3 Phase 1 的成功标准

如果满足以下条件，就算 Phase 1 成功：

1. backend 模式下，文本主链稳定可用
2. Flutter 的 thinking/body UI 表现与当前基本一致
3. direct 与 proxy 的文本行为差异明显收敛
4. 有可回归测试，不再完全依赖手测
5. 出问题时可以一键切回 direct mode

## 5. 分阶段实施计划

## 5.1 Phase 0：基线冻结与测试脚手架

### 目标

把“当前到底怎么工作”固定下来，避免后续把行为修正和行为回归混在一起。

### 具体工作

1. 固定当前路由真相
   - 记录 `pythonBackendEnabled = false` 时走 `HybridLangChainProvider`
   - 记录 `pythonBackendEnabled = true` 时走 `ProxyOpenAIProvider`
   - 记录当前 `backendMode` 在主链中被忽略

2. 固定 direct / proxy 请求体差异
   - `HybridLangChainProvider._buildRequestBody()`
   - `HybridLangChainProvider._convertMessages()`
   - `ProxyOpenAIProvider._buildRequestBody()`
   - 当前已由 `test/unit/adapters/request_body_characterization_test.dart` 固定关键差异样本

3. 固定 thinking 展示协议
   - `StreamManager.append()`
   - `StreamManager._parseThinkingContent()`

4. 固定 backend contract
   - `GET /api/health`
   - `GET /models`
   - `POST /models`
   - `POST /v1/chat/completions`

5. 收集 SSE fixture
   - 正常正文流
   - reasoning 流
   - Gemini thinking 风格流
   - mid-stream error
   - `[DONE]`

### 推荐测试

1. Characterization tests
2. API contract tests
3. SSE replay fixtures

### 本阶段不做

- 不改运行逻辑
- 不改 Flutter UI
- 不改 backend 契约

### 验收标准

1. 当前主链行为可被测试描述
2. thinking 协议行为有回归基线
3. backend chat contract 有固定样本

## 5.2 Phase 1：backend 接管文本主链执行语义

### 目标

让 backend 不再只是 SSE 中继，而是接管文本主链的请求规范化和流语义归一，同时保持 Flutter 现有 UI 契约基本不变。

### Slice 1A：backend 请求规范化

#### backend 侧工作

新增或重构 backend 内部规范化层，负责：

1. 统一解释 Flutter 发来的 `messages`
2. 统一解释 `temperature / max_tokens / top_p / penalty` 参数
3. provider 特殊字段补齐
4. Gemini thinking 参数补齐
5. 空 system 消息过滤

优先复用：

- `LiteLLMService`
- 自定义 `ChatService` / `RequestNormalizationService`

而不是把 Flutter 的 body 拼装逻辑逐行翻译到 Python。

#### Flutter 侧工作

首阶段尽量不改请求契约，只保留：

- 继续调用 `/v1/chat/completions`
- 继续发送现有 request body 形状

#### 主要风险

1. backend 规范化与当前直连链行为不一致
2. provider 特殊参数被吃掉或误改

#### 推荐测试

1. 针对 normalization 的 backend 单测
2. direct / proxy body snapshot 对比测试
3. provider matrix 测试：
   - OpenAI
   - DeepSeek
   - Claude
   - Gemini

#### 验收标准

1. backend 能统一生成稳定的上游调用参数
2. 文本主链在 proxy 模式下和当前 direct 模式基本对齐

### Slice 1B：backend 流语义归一

#### backend 侧工作

让 backend 从“转发原始 SSE”升级为“边读边解析、边解析边输出”，负责：

1. 提取正文内容
2. 提取 reasoning/thinking 内容
3. 兼容多 provider 的流字段差异
4. 输出 Flutter 可继续消费的文本 chunk

首阶段继续输出：

- 正文文本
- `<think>`
- `</think>`

#### Flutter 侧工作

继续保留：

- `StreamManager._parseThinkingContent()`
- thinking/body 分离渲染
- 当前消息流 UI

#### 主要风险

1. 后端如果先缓存整段再发，会破坏流式体验
2. `<think>` 边界错位会直接影响 UI
3. 丢 chunk、重 chunk、DONE 处理错误会导致显示异常

#### 推荐测试

1. SSE replay tests
2. stream contract tests
3. UI 手工回归：
   - 有思考块
   - 无思考块
   - 思考后接正文
   - mid-stream error

#### 验收标准

1. backend 模式下 thinking/body 能正确分离显示
2. 流式显示观感不明显劣化
3. 正文不丢字、不重字

### Slice 1C：补齐文本主链 direct / proxy 差异

#### 目标

把当前“能聊但不等价”的问题收敛到可接受范围。

#### 最低对齐项

1. 空 system 消息过滤
2. 参数裁剪和默认值处理
3. Gemini thinking 相关字段
4. 文本消息结构规范化

#### 附件策略

本阶段默认策略：

1. 如果 Python 侧有成熟轮子且接入成本可控，可纳入 Phase 1.5
2. 如果复杂度偏高，Phase 1 先只做文本主链，不阻塞主迁移

#### 验收标准

1. backend 模式不再明显弱于 current direct 文本链
2. 附件若未纳入，文档和开关边界明确

#### 当前状态

截至 `2026-04-06`：

1. 已完成 proxy 文本流解析收口的第一刀
   - 主路径：优先消费 backend 已标准化的 `delta.content`
   - 兼容路径：保留 legacy reasoning / Gemini candidates fallback
2. 已新增 Flutter 单测：
   - `test/unit/adapters/proxy_openai_provider_test.dart`
   - 覆盖 normalized path、legacy reasoning close-before-body、legacy Gemini candidates
3. 已新增 Flutter 请求体特征测试：
   - `test/unit/adapters/request_body_characterization_test.dart`
   - 固定了 direct/proxy 文本与附件边界样本
4. 已新增附件保护边界：
   - 该临时边界已被 Phase 1.5 backend 附件链替代，不再是当前主链行为
5. 仍未完成：
   - 文本主链真实手工回归
   - proxy 取消链修复
   - 附件链的远程上传协议与跨设备形态

## 5.3 Phase 1.5：附件/多模态过渡收口

### 进入条件

只有在以下条件满足时才进入：

1. 文本主链已稳定
2. 已找到成熟 Python 轮子或明确的简化实现
3. 不会拖慢文本主链交付

### 目标

优先把“文件解析为模型可消费内容”放到 backend，而不是复制 Flutter 侧实现。

### 原则

1. 用成熟轮子，不复刻粗糙实现
2. 先覆盖常用格式，不追求一次吃全
3. 验收看能力覆盖，不要求与 Flutter 旧实现逐字节一致

### 当前落地状态

截至 `2026-04-06`：

1. backend 已新增附件消息转换层
   - `backend/services/attachment_message_service.py`
2. `RequestNormalizationService` 已接入附件转换
   - `files` 会在 backend 侧被并入最后一条 user message
   - 并在规范化后从 request 中清除，避免继续向上游透传无意义字段
3. 文档附件优先使用 `MarkItDown`
   - 目标是替代 Flutter 侧零散文档解析逻辑
4. 图片附件在 backend 转为 `image_url` + `data:` URL
5. Flutter proxy 请求已开始显式发送 `files`
   - `ProxyOpenAIProvider` 不再忽略附件
6. UI 层临时“附件强制直连”保护已移除

### 当前边界

1. 这是桌面本机 backend 的过渡态实现
2. 当前传输的是本机文件路径元数据，不是跨设备上传协议
3. 因此前端桌面链路可以工作，但移动端连远程 backend 时不能直接复用这套文件路径协议
4. 真正的远程上传/持久化协议应放到更后面的阶段单独设计

### 当前验收重点

1. `txt/md/json/docx/pdf` 这类文档在 backend 模式下能否稳定转成模型可消费文本
2. 图片在 backend 模式下能否正常作为 `image_url` 传给上游
3. thinking/body 渲染是否保持不变
4. 出问题时仍可切回 direct mode

## 5.4 Phase 2：backend 接管路由与韧性策略

### 目标

让 backend 成为真正的运行时调度中心，而不是仅执行 Flutter 的决定。

### 具体工作

1. backend 接管 route selection
2. backend 接管 fallback policy
3. backend 接管 circuit breaker
4. backend 补齐 retry / timeout 策略
5. backend 补齐 cancel protocol

### 当前代码对照

当前 Flutter 侧已有但未接入主链的逻辑：

- `lib/adapters/backend_routing_provider.dart`
- `lib/services/fallback_policy.dart`
- `lib/services/circuit_breaker_service.dart`

本阶段不建议“原样搬运”这些实现，而应：

1. 先保留其策略语义
2. 再在 backend 用更合适的 Python 实现重建

### cancel protocol 说明

这里的取消，指的是用户在生成过程中点击“停止”后：

1. 前端停止接收
2. backend 停止继续处理
3. upstream 请求也尽量被真正取消

### 当前状态

截至 `2026-04-06`：

1. `ProxyOpenAIProvider` 已补前端侧 `CancelToken`
2. UI 点击停止时，proxy 链已能真正取消 Flutter -> backend 的 HTTP 请求
3. `LiteLLMService` 已切到官方 `LiteLLM Router`
4. backend 当前已接住：
   - `num_retries`
   - `timeout`
   - `stream_timeout`（first-chunk timeout）
5. 但这还不等于“完整 Phase 2”已经完成
6. backend `/v1/chat/completions` 已在流出口使用 disconnect guard：
   - 客户端断开时取消当前 `anext()` 等待
   - 关闭上游 async generator
   - 避免 backend 在客户端已停止后继续悬挂流式读取
7. backend 当前已补最小观测日志，手工验证停止生成时应至少能看到以下标志：
   - `[OBS] stream_request_started`
   - `[OBS] stream_first_chunk`
   - `[OBS] stream_cancelled`（用户中断）
   - `[OBS] stream_task_cancelled`（Starlette/response task 级取消，也视为用户中断通过）
   - `[OBS] stream_completed`（自然结束）
   - `[OBS] stream_iteration_error` / `[OBS] request_failed`（异常）
8. 已补“首包前取消”回归保护：
   - 如果用户在首个 chunk 到达前点击停止，backend 不应再抛出 `aclose(): asynchronous generator is already running`
   - 此场景现在应出现 `stream_request_started` + `stream_cancelled` 或 `stream_task_cancelled`
9. backend 当前已补内部运行时回退：
   - 当前主路径为 `LiteLLMService`
   - 首包前遇到可回退错误时，backend 会在内部切换到 `LLMProxyService`
   - 这是 backend 内部回退，不是 Flutter `auto -> direct` 回退
10. 当前回退策略是保守版：
   - 仅在未产生可见 chunk 时允许
   - 仅对连接错误 / 超时 / 503 类错误允许
   - 认证错误 / 429 / 4xx / 已有 chunk 后错误不回退
11. 真正完整的 provider 级 route selection / fallback policy，仍属于本阶段后续工作
12. backend 已开始接收“显式路由意图”作为过渡态：
   - `ProxyOpenAIProvider` 仅在 provider 显式设为 `auto / proxy` 时，才把 `backend_mode` 等提示透传给 backend
   - 未显式配置的历史数据继续保持当前默认行为，不会因为 `ProviderConfig.backendMode` 默认值是 `direct` 而突然切换执行路径
13. backend 当前对显式路由意图的处理：
   - `backend_mode=auto`：LiteLLM 为主路径，允许按策略回退到 httpx
   - `backend_mode=proxy`：只走 LiteLLM，不允许 backend 内部 httpx 回退
   - `backend_mode=direct`：只走 httpx（当前仍属于过渡态能力，不是最终真源设计）
14. backend 已开始消费 provider 级的 LiteLLM Router override：
   - `fallback_timeout_ms` -> `stream_timeout`
   - `circuit_breaker.failure_threshold` -> `allowed_fails`
   - `circuit_breaker.open_ms` -> `cooldown_time`
15. 当前对 circuit breaker 的映射是“轮子优先”的近似实现：
   - 复用 LiteLLM Router 的 cooldown 机制
   - 不复刻 Flutter 旧 `half-open` 状态机
   - `window_ms / half_open_max_calls` 目前未做 1:1 后端实现

### 当前阶段关于“后续 agent 重试/切换/降级”的决策

结论：

1. 当前阶段要为后续 agent 留基建
2. 但不把“自动切换模型 / 自动降级 / 面向用户的复杂重试策略”做成主聊天能力

当前阶段应完成的“预留”只有：

1. 保持 backend 统一执行入口稳定
   - 后续 agent 应复用现有 backend service 边界，不再绕回 Flutter 直连
2. 保持执行提示位可扩展
   - 例如 `backend_mode`、timeout、fallback enable、有限的 resilience hints
   - 当前只服务基础请求链，未来可扩展给 agent runtime
3. 继续补齐错误分类与可观测性
   - 这样后续 agent 才能按错误类型决定 retry / switch / degrade
4. 保持 cancel 语义贯通
   - 后续 agent 的后台执行和子任务编排同样依赖这层基础设施

当前阶段明确不做：

1. 主聊天默认自动换模型
2. 主聊天默认自动降级
3. 面向用户开放复杂 fallback / policy 配置
4. 为主聊天提前引入完整 agent scheduler / policy engine

原因：

1. 当前迁移目标是“稳定 backend 主链”，不是“提前产品化 agent 策略”
2. 多模型切换/降级的合理策略依赖后续 agent 设计：
   - 哪些任务允许低价模型
   - 哪些步骤可后台异步完成
   - 哪些失败允许自动重试
   - 哪些结果允许降级
3. 这些策略应在 RP agent 阶段统一定义，否则会在主聊天阶段引入过多不必要变量

### 验收标准

1. 正常情况下由 backend 决定 direct / proxy / fallback 行为
2. 用户中断生成时，不只是 UI 停止，链路也能收敛
3. Flutter 仍保留回滚开关

## 5.5 Phase 3：provider registry 与 key custody 后端化

### 目标

backend 成为 provider 配置和密钥真源。

### 具体工作

1. provider 配置后端化
2. API key 不再由 Flutter 每次请求上传
3. model listing 由 backend 基于 provider registry 提供

### 注意

这一步会改大边界，不应提前进入。

如果前面两阶段不稳定，先不要碰这一步。

### 当前第一刀状态

截至 `2026-04-07`：

1. backend 已落地最小 provider registry
   - 存储位置：`storage/providers.json`
   - 当前实现：文件型 registry，不是数据库
2. backend chat/models 链已支持 `provider_id`
   - `/v1/chat/completions`
   - `POST /models`
   - 若请求只带 `provider_id`，backend 会从 registry 解引用真实 provider 配置
3. Flutter proxy 主链已开始按“先注册、再引用”执行
   - 发送聊天前：先 `PUT /api/providers/{id}`
   - 真正聊天请求：只发 `provider_id`
   - 模型探测请求：只发 `provider_id`
4. 当前切片的价值：
   - chat/models 主请求不再每次重复上传 provider 密钥
   - backend 已开始具备 provider 真源能力
   - direct 回滚链不受影响

### 当前边界

1. 这还不是最终 Phase 3 完成态
2. 当前仍保留 Flutter 本地 provider/model 配置：
   - 用于 UI 编辑
   - 用于回滚
   - 用于 backend 不可用时的兼容
3. 当前 backend 化的是 provider registry，不是完整 model registry
4. 当前同步策略是保守过渡态：
   - `ModelServiceManager` 做 best-effort sync
   - `ProxyOpenAIProvider` 做 lazy ensure
   - 目标是降低迁移风险，而不是一次切成“严格后端单真源”

### 当前第二刀状态

截至 `2026-04-07`：

1. Flutter 配置侧的 provider 测试链已开始与主聊天链对齐
   - `ModelServiceManager.testProvider()`
   - `ModelServiceManager.testProviderWithModel()`
   - 在 backend 模式下，这两条路径现在也会走 `createProviderWithRouting()`
2. 这意味着设置页中的“测连接 / 测模型”不再偷偷绕回直连链
3. 同时已修正 `ApiUrlHelper` 的 endpoint 重复补全问题
   - 避免 provider registry 被错误写入重复的 `/v1/chat/completions` 后缀

### 当前第三刀状态

截至 `2026-04-07`：

1. Flutter 已开始消费 backend provider summary 作为“校准源”
   - `ModelServicesPage` 加载时，在 backend 模式下会尝试先从 backend 拉 provider summary
   - 然后把 backend summary 合并回本地 provider 镜像
2. 当前合并策略是保守版：
   - 只更新本地已存在的 provider
   - 不导入 backend 中未知的新 provider
   - 保留本地 secret / proxy 配置作为回滚镜像
3. 这一步的价值：
   - 列表页不再永远只看本地旧值
   - Flutter 开始具备“从 backend 读回真相”的能力
   - 仍不破坏当前 direct 回滚结构

### 为什么“对外 typed events”仍不是下一步

1. 对外 typed events 会同时改：
   - backend 输出协议
   - Flutter 消费协议
   - `StreamManager` / Markdown 渲染边界
2. 当前项目刚完成 provider registry 的第一、二刀，backend 真源边界还在继续收口
3. 现阶段更高 ROI 的工作仍然是：
   - 继续完成 Phase 3 的 source-of-truth 收紧
   - 让配置侧、探测侧、聊天主链完全对齐
4. typed events 应放在 backend 真源边界稳定后再做，否则排错维度会明显增多

### 为什么 backend 内部结构化事件层要先做

1. 当前最大问题不是厂商协议不结构化，而是 backend 把原始结构化结果降级成了 `<think>` 文本协议
2. 先做 backend 内部事件层，可以：
   - 保持 Flutter 渲染契约不变
   - 先去掉 backend 内部“猜标签拼字符串”的核心问题
   - 为后续真正的 typed events / tool 渲染 / agent 复用保留正确边界
3. 当前策略是：
   - backend 内部：结构化事件
   - backend 对外：继续兼容当前 Flutter SSE 文本契约
   - Flutter：暂不改消费方式

### 当前建议的下一步顺序

1. 先继续 Phase 3
   - 明确 provider 列表、模型列表、测试链、聊天链的真源与同步策略
2. 再决定是否进入“backend 读路径真源化”
   - 例如 Flutter 是否开始从 backend 拉 provider summary / model summary
3. 最后再评估 typed events
   - 到那时它才是“升级协议”，而不是“同时修架构和协议”

### 下一步切片

Phase 3 后续更合理的顺序是：

1. 手工验证 provider registry 主链
   - backend 模式发送聊天
   - backend 模式检测模型
   - 编辑 provider 后再次聊天
   - 删除 provider 后确认 backend registry 清理行为
2. 再决定是否进入 model registry / provider source-of-truth 收口
3. 最后再考虑真正移除“每次请求携带完整 provider 配置”的所有兼容分支

## 6. 测试与验证计划

## 6.1 必做自动化测试

### A. Flutter characterization tests

覆盖：

1. `ProviderFactory.createProviderWithRouting()`
2. `StreamManager._parseThinkingContent()`
3. direct/proxy 请求体快照差异
4. backend 模式下带附件请求的 direct 回退边界

### B. backend contract tests

覆盖：

1. `/api/health`
2. `GET /models`
3. `POST /models`
4. `/v1/chat/completions` non-stream
5. `/v1/chat/completions` stream

### C. SSE replay tests

覆盖：

1. 正常正文 delta
2. reasoning delta
3. Gemini 风格 thinking delta
4. mid-stream error
5. done 结束

### D. integration tests

使用 mock upstream 覆盖：

1. timeout
2. 401/403
3. 429
4. 5xx
5. malformed chunk
6. 半路断流

## 6.2 必做手工回归

每个切片完成后至少手工验证：

1. direct mode 可用
2. backend mode 可用
3. 文本流逐步显示正常
4. thinking/body 分离正常
5. 错误态正常落地
6. 停止生成行为符合预期

## 6.3 验证顺序

建议固定顺序：

1. 先跑 backend 单测
2. 再跑 backend contract / replay
3. 再跑 Flutter characterization
4. 最后做手工回归

不要反过来只靠手测。

## 7. 回滚设计

## 7.1 回滚开关

必须保留：

1. `ProviderFactory.pythonBackendEnabled`
2. direct mode 旧路径
3. backend 内部新语义实现的独立开关

## 7.2 回滚层级

### 层级 A：关闭 backend 新语义实现

适用：

- backend 语义归一出问题

效果：

- backend 回到纯 relay

### 层级 B：关闭 backend 模式

适用：

- backend 执行主链不稳定

效果：

- Flutter 全量切回 direct mode

### 层级 C：暂停 Phase 2/3 演进

适用：

- 文本主链尚未稳定

效果：

- 先冻结在已稳定的 Phase 1

## 8. 建议的实施顺序

按稳妥程度，建议这样推进：

1. 先完成 Phase 0 测试基线
2. 再做 Phase 1A backend 请求规范化
3. 再做 Phase 1B backend 流语义归一
4. 再做 Phase 1C direct/proxy 文本差异收口
5. 视复杂度决定是否进入 Phase 1.5 附件
6. 文本主链稳定后再进入 Phase 2
7. 最后再碰 Phase 3

## 9. 当前是否可以开始

可以。

当前已有的信息、代码理解和文档沉淀，已经足够开始：

1. Phase 0 基线冻结
2. Phase 1 文本主链迁移

但不建议直接跳到：

1. provider registry 后端化
2. typed events
3. 完整附件链
4. agent / RAG

## 10. 下一步建议

如果进入实施准备，下一步应只做两件事：

1. 先补齐 Phase 0 所需的 characterization tests 和 SSE replay fixtures
2. 再进入 Phase 1A 的 backend 请求规范化实现

## 11. 2026-04-06 Additional Progress

### 11.1 Manual Abort UX Polish

在完成 Phase 2 最小取消链后，前端又补了一刀“截断可视反馈”优化：

1. 手动点击停止时，不再把它当成“无结果直接删除占位消息”。
2. stop 路径现在会复用现有 `<error>...</error>` 提示框，错误内容固定为 `Request was aborted`。
3. 因此：
   - 首包前截断：保留 assistant header，并在 header 下显示错误提示框
   - 已有正文后截断：在正文末尾追加同一个错误提示框
4. 这次改动不改变 Flutter 现有的 Markdown / thinking / `<think>` 渲染链，也不引入 typed events。

### 11.2 Current Implementation Boundary

这次前端优化只处理“用户主动截断”的 finalize 行为：

1. `streaming.dart::_stopStreaming()` 现在会传入统一的 abort 错误对象
2. `streaming.dart::_finalizeStreamingMessage()` 继续复用既有错误标签落盘链路
3. 真正决定是否保留 placeholder 的逻辑仍然是：
   - 有可渲染内容（正文 / thinking / error block）则保留并 finalize
   - 完全空内容才移除占位消息

### 11.3 Regression Coverage

已补的定向回归包括：

1. `test/unit/utils/error_formatter_test.dart`
   - 固定 `Request was aborted` 错误对象与标签输出
2. `test/unit/utils/streaming_message_content_test.dart`
   - 固定“首包前截断保留错误块”
   - 固定“正文后截断追加错误块”
   - 固定“thinking + body + error”的最终拼接顺序
3. `test/unit/widgets/stream_manager_test.dart`
   - 继续作为 `<think>` 解析安全网
