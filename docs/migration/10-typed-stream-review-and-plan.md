# Typed Stream Review And Plan

## 1. Scope

本文只复审当前基础 LLM 请求链里的 typed stream / typed state 设计，不讨论 RP、RAG、agent planner。

重点对象：

- backend internal stream events
- backend external typed SSE
- Flutter proxy typed consumer
- Flutter state/render boundary
- tool call / MCP 接口边界

## 2. Current Architecture Snapshot

当前真实链路已经变成：

```text
upstream SSE / SDK stream
  -> backend StreamNormalizationService.extract_events()
  -> backend internal StreamEvent
  -> backend SSE output
     - legacy: <think> text chunks
     - typed: thinking_delta / text_delta / tool_call / error / done
  -> Flutter ProxyOpenAIProvider
  -> AIStreamEvent
  -> StreamOutputController
  -> conversation_view_v2
  -> StreamManager
  -> OwuiAssistantMessage / OwuiThinkBubble / OwuiToolCallBubble / Markdown
```

当前已经做到：

- backend 不再只依赖 `<think>` 文本协议
- frontend thinking/tool 状态已经开始直接消费 typed event
- frontend text 已 typed-aware，但仍复用现有 `ChunkBuffer + stable reveal`
- UI 外观未重构

## 3. Backend Review

### 3.1 Current Responsibilities

#### `backend/models/stream_event.py`

职责：

- backend 内部统一事件模型

当前事件：

- `thinking`
- `text`
- `tool_call`
- `error`
- `raw`

评价：

- 方向正确
- 但事件集合还不完整，不足以长期支撑 tool / MCP 生命周期

#### `backend/services/stream_normalization.py`

职责：

- 从 upstream chunk 中提取内部事件
- 将内部事件转成：
  - legacy 兼容 chunk
  - typed SSE payload

当前优点：

- provider-specific 解析已经从“全前端处理”迁到 backend
- OpenAI-compatible / OpenAI Responses / Gemini native / Anthropic native 都已有一定覆盖
- typed / legacy 双轨已经落地

当前问题：

1. typed payload schema 还不是完整协议
2. `tool_call` 只有创建，没有生命周期
3. `raw` 仍然暴露在对外协议里，说明 schema 还没完全收口

### 3.2 Findings

#### F1. Typed SSE schema is still partial

当前 typed SSE 只有：

- `thinking_delta`
- `text_delta`
- `tool_call`
- `error`
- `raw`
- `done`

缺失的高价值事件：

- `tool_started`
- `tool_result`
- `tool_error`
- `usage`
- `finish_reason`
- `image`
- `citation`

结论：

- 现在这套 schema 适合继续推进聊天主链
- 还不适合直接作为 agent/tool/MCP 长期协议

#### F2. `raw` should be considered transitional only

`raw` 的存在说明：

- backend 仍有“识别不了就透传”的兜底分支

这在迁移期合理，但长期不是好边界。

建议：

- `raw` 保留给 debug
- 不建议未来让 UI 逻辑依赖 `raw`

#### F3. Tool contract is not closed-loop yet

当前 backend 到 frontend 只发 `tool_call`。

这意味着：

- UI 可以显示“有个工具要跑”
- 但无法表达：
  - 已开始
  - 已完成
  - 返回了什么
  - 出错了什么

这对 MCP/agent 是明显不够的。

## 4. Frontend Review

### 4.1 Current Responsibilities

#### `lib/adapters/ai_provider.dart`

职责：

- provider 抽象接口
- 当前已新增 `sendMessageEventStream()`

问题：

- 默认实现只是把旧字符串流包装成 `text` 事件
- 所以它还是过渡接口，不是强约束 typed interface

#### `lib/adapters/proxy_openai_provider.dart`

职责：

- proxy 请求发起
- typed SSE 解析
- legacy SSE 兼容

问题：

1. 当前仍保留两个公开入口：
   - `parse()`
   - `parseEvents()`
2. 但 typed parser 的源逻辑已经收口到一套内部 typed payload 解析结果
3. 更危险的“请求发起 + SSE 读取 + JSON/错误处理写两遍”也已收口到公共底层流读取函数

结论：

- 这是当前前端最明显的实现冗余点
- 当前已基本收口完成
- 剩余的是迁移期保留的 legacy 视图，不再是两套独立语义规则

#### `lib/controllers/stream_output_controller.dart`

职责：

- 订阅 provider 事件流
- 对 text 事件继续触发现有 `onChunk`
- 对 typed 事件触发 `onEvent`

评价：

- 这是一个合理的过渡层
- 把“事件流”和“老 UI chunk 回调”解耦开了

#### `lib/widgets/stream_manager.dart`

职责：

- 当前同时支持：
  - 旧字符串协议 `append()`
  - typed thinking `appendThinking()`
  - typed body `appendText()`
  - tool call 状态

问题：

- 现在存在三套入口
- 说明仍处于迁移态，而不是最终态

但这一步是合理的：

- 因为当前还要保留回滚和双轨兼容

#### `lib/widgets/conversation_view_v2/streaming.dart`

职责：

- 连接 controller / chunk buffer / stream manager / placeholder UI 更新

当前状态：

- typed `thinking/tool` 直接更新 `StreamManager`
- typed text 仍然复用 `ChunkBuffer`
- flush 后进入 `StreamManager.appendText()`

评价：

- 当前策略是对的
- 因为它保住了原有 stable reveal
- 同时又去掉了 typed text 对 `<think>` 字符串协议的依赖

### 4.2 Findings

#### F4. UI is still stable, which is good

当前 UI 组件：

- `OwuiThinkBubble`
- `OwuiToolCallBubble`
- `OwuiMarkdown`

仍然消费 `StreamManager` 的状态容器，而不是直接消费 backend payload。

这在当前阶段是优点，不是缺点。

原因：

- 风险更低
- 更容易回滚
- 不会把“协议切换”和“UI 重构”绑在一起

#### F5. Current weak point is not UI, but duplicated bridge code

目前真正需要优先处理的不是 UI 组件，而是：

- `ProxyOpenAIProvider` 双实现
- typed/legacy parser 双实现
- incomplete tool lifecycle

## 5. Tool / MCP Review

### 5.1 Current Project Status

当前项目里：

- Flutter 侧已经有 MCP 连接和工具调用逻辑
- proxy typed chain 现在只做到 `tool_call`
- backend 还没有真正接管 MCP tool lifecycle

也就是说：

- “工具调用入口语义”已经开始后端化
- “完整 MCP/tool runtime”还没有后端化完成

### 5.2 Can backend take over tool / MCP?

结论：可以，而且应该。

原因：

1. MCP 本质上就是标准化工具协议
2. 当前 backend 已经有 typed event 基础
3. 只要补齐 tool lifecycle contract，backend 完全可以接管：
   - tool registration
   - tool call dispatch
   - MCP client/server communication
   - tool result / tool error events

### 5.3 Is Python ecosystem capable?

结论：是，能力明确比 Flutter 生态强。

Python 侧已有可直接利用的基础：

- 官方 MCP Python SDK
- OpenAI Agents SDK 的 MCP 集成
- 各模型 SDK / framework 的 tool calling 能力
- LangChain / LangGraph / agent frameworks 的 tool abstraction

设计注记：

- 后续 backend MCP runtime 应优先使用：
  - 官方 MCP Python SDK
  - `Streamable HTTP` 或 `stdio` 传输
- 不建议继续围绕旧前端式 SSE 工具链做主实现
- SSE 在当前项目里仍适合做 LLM 输出流，但不应再作为 MCP 新集成的首选传输

因此后续方向应是：

- Flutter 保留 UI 与渲染
- backend 统一承接 tool / MCP / agent runtime

## 6. Recommended Next Plan

### Phase A. Protocol Freeze

先写死 typed stream schema，至少明确：

- version
- event enum
- required fields
- optional fields
- frontend handling rules
- legacy compatibility rules

当前推荐的下一版 schema：

- `thinking_delta`
- `text_delta`
- `tool_call`
- `tool_started`
- `tool_result`
- `tool_error`
- `error`
- `done`

### Phase B. Frontend Bridge Simplification

收口：

- `parse()`
- `parseEvents()`

目标：

- 保留一个底层 SSE reader
- 一个 typed parser
- 一个 legacy adapter

当前状态：

- 已完成：
  - 公共 SSE reader
  - 公共 JSON/错误处理
  - typed payload 源逻辑统一
- 当前仍保留：
  - `parse()` legacy 视图
  - `parseEvents()` typed 视图
  这是迁移期兼容边界，不再属于高风险重复实现

### Phase C. Tool Lifecycle Completion

在 backend 和 frontend 两侧补齐：

- `tool_started`
- `tool_result`
- `tool_error`

这样 tool/MCP 才能真正闭环。

### Phase D. MCP Runtime Backendization

完成：

- backend MCP client management
- backend tool registry
- backend tool execution and typed event emission

Flutter 只保留：

- tool bubble UI
- event rendering

## 7. Final Judgment

当前 typed state 设计结论：

1. 方向正确
2. 当前稳定性可接受
3. UI 外观不应优先改
4. 下一步最该收口的是：
   - typed schema
   - proxy bridge 冗余
   - tool lifecycle

不建议现在优先做：

- 让 UI 组件直接消费 backend payload
- 删除全部 legacy 回滚链
- 在协议未定型前直接做复杂 MCP agent 编排
