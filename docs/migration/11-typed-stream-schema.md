# Typed Stream Schema

## 1. Scope

本文定义当前基础 LLM 请求链使用的 typed SSE 协议。

目标：

- 固定 backend -> Flutter 的事件契约
- 为后续 tool / MCP backendization 预留稳定接口
- 不改变当前 UI 外观和渲染结构

不在本文范围：

- RP / agent planner / RAG
- 完整 MCP runtime 实现
- UI 重构

## 2. Transport

传输方式继续使用 `SSE (text/event-stream)`。

区别只在 `data:` 内的 payload：

- `legacy`
  - 继续输出 `<think>...</think>` 兼容文本块
- `typed`
  - 输出结构化事件 payload

## 3. Current Typed Event Schema

### 3.1 Required Envelope

所有 typed SSE payload 都必须包含：

- `type: string`

推荐后续补充：

- `version: 1`
- `request_id`
- `timestamp`

当前阶段先不强制这三个字段，以避免扩大改动面。

### 3.2 Event Types

#### `thinking_delta`

```json
{
  "type": "thinking_delta",
  "delta": "先分析用户问题"
}
```

语义：

- assistant thinking 增量

前端行为：

- 进入 thinking 气泡

#### `text_delta`

```json
{
  "type": "text_delta",
  "delta": "最终回答正文"
}
```

语义：

- assistant 正文增量

前端行为：

- 进入正文 markdown 渲染链

#### `tool_call`

```json
{
  "type": "tool_call",
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "web_search",
        "arguments": "{\"q\":\"tokyo\"}"
      }
    }
  ]
}
```

语义：

- LLM 发起工具调用请求

前端行为：

- 创建 pending 工具气泡

#### `tool_started`

```json
{
  "type": "tool_started",
  "call_id": "call_123",
  "tool_name": "web_search"
}
```

语义：

- backend 已开始执行该工具

前端行为：

- 对应工具气泡切到 `running`

#### `tool_result`

```json
{
  "type": "tool_result",
  "call_id": "call_123",
  "tool_name": "web_search",
  "result": "搜索结果摘要..."
}
```

语义：

- backend 工具执行成功

前端行为：

- 对应工具气泡切到 `success`
- 记录结果文本

#### `tool_error`

```json
{
  "type": "tool_error",
  "call_id": "call_123",
  "tool_name": "web_search",
  "error": "timeout"
}
```

语义：

- backend 工具执行失败

前端行为：

- 对应工具气泡切到 `error`
- 记录错误文本

#### `error`

```json
{
  "type": "error",
  "error": {
    "message": "upstream failed",
    "type": "api_error"
  }
}
```

语义：

- 流级错误

前端行为：

- 走现有错误链

#### `done`

```json
{
  "type": "done"
}
```

语义：

- 流结束

前端行为：

- 结束当前流

### 3.3 Transitional Event

#### `raw`

```json
{
  "type": "raw",
  "chunk": { "...": "..." }
}
```

说明：

- 仅作为迁移期 debug/兜底事件
- UI 不应依赖它做主逻辑

## 4. Frontend Handling Rules

### 4.1 Stable Rules

必须保持：

- thinking 继续渲染到现有 thinking bubble
- text 继续走现有 markdown / stable reveal
- tool 继续渲染到现有 tool bubble
- 不中断当前 legacy 回滚路径

### 4.2 Tool Lifecycle Rules

工具生命周期规则：

1. `tool_call`
   - 创建 pending tool call
2. `tool_started`
   - 切到 running
3. `tool_result`
   - 切到 success
4. `tool_error`
   - 切到 error

允许容错：

- 如果 `tool_started / tool_result / tool_error` 先于 `tool_call` 到达，
  前端可基于 `call_id` 补建占位 tool call，再更新状态。

## 5. Backend Responsibilities

backend 应负责：

- provider-specific stream parsing
- typed event extraction
- tool lifecycle event emission
- MCP/tool runtime orchestration

backend 不应继续长期承担：

- 把结构化语义重新压成字符串标签作为主协议

## 6. Migration Notes

当前阶段：

- typed SSE 与 legacy SSE 双轨并存
- Flutter UI 外观不变
- tool lifecycle 事件先接通协议和状态层
- 完整 MCP runtime backendization 作为后续阶段
