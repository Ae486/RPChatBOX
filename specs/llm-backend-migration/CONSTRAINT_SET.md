# LLM Backend Migration - Constraint Set

> Generated: 2025-02-02
> Status: Draft
> Source: Multi-model research (Codex + Codebase Exploration)

## 1. Overview

将 LLM 通信从 Flutter 直连迁移到 Python 后端代理，同时保留直连作为回滚选项。

### 1.1 Goals

- **G1**: 全量 LLM 请求可通过 Python 后端路由
- **G2**: 保留现有直连功能，支持一键切换
- **G3**: UI 层代码零改动
- **G4**: 流式响应延迟增加 < 100ms

### 1.2 Non-Goals

- 修改现有 Provider UI 配置界面
- 支持非 OpenAI 兼容格式的后端

---

## 2. Architecture Constraints

### 2.1 Current Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                        Flutter App                          │
├─────────────────────────────────────────────────────────────┤
│  ChatPage → StreamOutputController → AIProvider             │
│                                         │                   │
│                    ┌────────────────────┴────────────────┐  │
│                    │         ProviderFactory             │  │
│                    │    (useLangChain global toggle)     │  │
│                    └────────────┬───────────────────────┬┘  │
│                                 │                       │   │
│                    ┌────────────▼──────┐   ┌────────────▼──┐│
│                    │  OpenAIProvider   │   │LangChainProv. ││
│                    │  (DioService)     │   │  (langchain)  ││
│                    └────────────┬──────┘   └───────────────┘│
└─────────────────────────────────┼───────────────────────────┘
                                  │ HTTPS
                                  ▼
                         ┌─────────────────┐
                         │   LLM APIs      │
                         │ (OpenAI/Claude) │
                         └─────────────────┘
```

### 2.2 Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Flutter App                          │
├─────────────────────────────────────────────────────────────┤
│  ChatPage → StreamOutputController → AIProvider (unchanged) │
│                                         │                   │
│                    ┌────────────────────┴────────────────┐  │
│                    │      RoutingProviderFactory         │  │
│                    │  (backendMode: direct|proxy|auto)   │  │
│                    └─────┬──────────────────────┬────────┘  │
│                          │                      │           │
│            ┌─────────────▼──────┐   ┌──────────▼─────────┐  │
│            │   DirectProvider   │   │   ProxyProvider    │  │
│            │ (existing impls)   │   │ (http://localhost) │  │
│            └─────────────┬──────┘   └──────────┬─────────┘  │
└──────────────────────────┼──────────────────────┼───────────┘
                           │                      │
                           │ HTTPS           HTTP │ localhost:8765
                           ▼                      ▼
                  ┌─────────────────┐    ┌─────────────────────┐
                  │   LLM APIs      │    │   Python Backend    │
                  │ (OpenAI/Claude) │    │  (FastAPI + MCP)    │
                  └─────────────────┘    └──────────┬──────────┘
                                                    │ HTTPS
                                                    ▼
                                           ┌─────────────────┐
                                           │   LLM APIs      │
                                           └─────────────────┘
```

### 2.3 Key Constraints

| ID | Constraint | Rationale |
|----|------------|-----------|
| **AC-1** | `AIProvider` 接口不可修改 | UI 层依赖此接口 |
| **AC-2** | `StreamOutputController` 不可修改 | 流式控制逻辑稳定 |
| **AC-3** | 路由决策在 `ProviderFactory` 层完成 | 单一责任原则 |
| **AC-4** | `ProviderConfig` 扩展必须向后兼容 | 现有配置不可丢失 |
| **AC-5** | 后端模式切换不需重启 App | 用户体验要求 |

---

## 3. API Contract Constraints

### 3.1 Endpoint Resolution

| Constraint ID | Description |
|---------------|-------------|
| **API-1** | Python 后端必须暴露 `/v1/chat/completions` 端点 |
| **API-2** | 必须实现 `/models` 端点 (GET) 用于连接测试 |
| **API-3** | URL 后缀规则与 `ApiUrlHelper` 一致：无后缀自动补全，`/` 结尾跳过版本，`#` 结尾强制原样 |

### 3.2 Request Format

```json
{
  "model": "string (required)",
  "messages": [
    {
      "role": "system|user|assistant",
      "content": "string | array<ContentPart>"
    }
  ],
  "stream": "boolean (required)",
  "temperature": "number (optional)",
  "max_tokens": "number (optional)",
  "top_p": "number (optional)",
  "frequency_penalty": "number (optional)",
  "presence_penalty": "number (optional)",
  "include_reasoning": "boolean (optional, for thinking models)",
  "extra_body": "object (optional, pass-through)"
}
```

**ContentPart variants:**
```json
{"type": "text", "text": "..."}
{"type": "image_url", "image_url": {"url": "data:...", "detail": "auto|low|high"}}
```

| Constraint ID | Description |
|---------------|-------------|
| **API-4** | 必须接受 `content` 为 string 或 array 两种格式 |
| **API-5** | 必须接受并忽略未知字段（forward compatibility） |
| **API-6** | `model` 字段必须透传到上游 LLM API |

### 3.3 Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | ✓ | `application/json` |
| `Authorization` | ✓ | `Bearer <token>` (可为占位符) |
| `X-Custom-*` | - | 透传 `customHeaders` |

| Constraint ID | Description |
|---------------|-------------|
| **API-7** | 必须接受 `Authorization` header，可选忽略 |
| **API-8** | 必须透传所有 `customHeaders` 到上游 |

### 3.4 Response Format (Non-Streaming)

```json
{
  "id": "chatcmpl-xxx",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "response text"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 20,
    "total_tokens": 30
  }
}
```

| Constraint ID | Description |
|---------------|-------------|
| **API-9** | `choices[0].message.content` 必须存在且为 string |
| **API-10** | `usage` 字段可选但推荐 |

### 3.5 Error Response Format

必须兼容 `ApiErrorParser`，支持以下任一格式：

```json
// OpenAI style
{"error": {"message": "...", "code": "...", "param": "..."}}

// Claude style
{"message": "...", "type": "...", "status": 400}

// Gemini style
{"errors": [{"message": "...", "code": "..."}]}
```

| Constraint ID | Description |
|---------------|-------------|
| **API-11** | 错误响应必须是 JSON 或纯文本 |
| **API-12** | HTTP 状态码必须反映错误类型 (4xx/5xx) |

---

## 4. Streaming Constraints

### 4.1 SSE Format

```
data: {"choices":[{"delta":{"content":"Hello"}}]}

data: {"choices":[{"delta":{"content":" world"}}]}

data: [DONE]

```

| Constraint ID | Description |
|---------------|-------------|
| **SSE-1** | 每个事件必须是单行 `data: {json}\n\n` |
| **SSE-2** | JSON 不可跨行（`LineSplitter` 限制） |
| **SSE-3** | 流结束必须发送 `data: [DONE]\n\n` |
| **SSE-4** | 禁止 `event:` 或 `:comment` 行 |

### 4.2 Headers

```http
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

| Constraint ID | Description |
|---------------|-------------|
| **SSE-5** | 必须设置 `text/event-stream` |
| **SSE-6** | 必须禁用缓冲 (`X-Accel-Buffering: no`) |
| **SSE-7** | 禁止 gzip 压缩（或确保流式兼容） |

### 4.3 Timing

| Constraint ID | Description |
|---------------|-------------|
| **SSE-8** | 每个 chunk 必须立即 flush |
| **SSE-9** | First token latency < 200ms (相比直连增量) |
| **SSE-10** | Inter-chunk latency < 50ms (proxy overhead) |

### 4.4 Thinking/Reasoning Support

```json
// Supported fields (any one):
{"choices":[{"delta":{"reasoning": "..."}}]}
{"choices":[{"delta":{"reasoning_content": "..."}}]}
{"choices":[{"delta":{"internal_thoughts": "..."}}]}
{"choices":[{"delta":{"thinking": "..."}}]}
```

| Constraint ID | Description |
|---------------|-------------|
| **SSE-11** | 思考内容透传，映射到 `<think>` 标签 |

---

## 5. Configuration Constraints

### 5.1 ProviderConfig Extension

```dart
class ProviderConfig {
  // Existing fields (unchanged)
  String id;
  String name;
  ProviderType type;
  String apiUrl;
  String apiKey;
  bool isEnabled;
  Map<String, dynamic> customHeaders;

  // NEW: Backend routing
  BackendMode backendMode;          // direct | proxy | auto (default: direct)
  String? proxyApiUrl;              // e.g., "http://localhost:8765"
  String? proxyApiKey;              // optional separate auth
  Map<String, dynamic>? proxyHeaders;

  // NEW: Fallback control
  bool fallbackEnabled;             // default: true (only for auto mode)
  int fallbackTimeoutMs;            // default: 5000

  // NEW: Circuit breaker
  CircuitBreakerConfig? circuitBreaker;
}

enum BackendMode { direct, proxy, auto }

class CircuitBreakerConfig {
  int failureThreshold;   // default: 3
  int windowMs;           // default: 60000
  int openMs;             // default: 30000
  int halfOpenMaxCalls;   // default: 2
}
```

| Constraint ID | Description |
|---------------|-------------|
| **CFG-1** | 所有新字段必须有默认值 |
| **CFG-2** | 旧配置反序列化时缺失字段使用默认值 |
| **CFG-3** | `backendMode=proxy` 时 `proxyApiUrl` 必填 |
| **CFG-4** | `backendMode=direct` 时忽略 proxy 相关字段 |

### 5.2 Global Settings

```dart
class AppSettings {
  // NEW: Global backend override
  BackendMode? globalBackendOverride;  // null = per-provider
  bool pythonBackendEnabled;           // master switch
}
```

| Constraint ID | Description |
|---------------|-------------|
| **CFG-5** | 全局开关优先于 per-provider 设置 |
| **CFG-6** | `pythonBackendEnabled=false` 时强制所有请求走直连 |

---

## 6. Fallback Strategy Constraints

### 6.1 Trigger Conditions (Proxy → Direct)

| Condition | Action |
|-----------|--------|
| Connection timeout | Fallback |
| Send timeout | Fallback |
| Receive timeout (before first chunk) | Fallback |
| Connection error | Fallback |
| HTTP 502/503/504 | Fallback |
| HTTP 401/403 | **NO** fallback (auth error) |
| HTTP 400/404/422 | **NO** fallback (client error) |

| Constraint ID | Description |
|---------------|-------------|
| **FB-1** | 仅网络/服务器错误触发回退 |
| **FB-2** | 认证/客户端错误直接抛出 |

### 6.2 Mid-Stream Failure

| Constraint ID | Description |
|---------------|-------------|
| **FB-3** | 已输出 chunk 后不自动回退 |
| **FB-4** | 零 chunk 时允许一次自动回退 |
| **FB-5** | 回退后使用全新 stream |

### 6.3 Circuit Breaker

| State | Behavior |
|-------|----------|
| Closed | 正常路由到 proxy |
| Open | 所有请求直接走 direct |
| Half-Open | 允许 N 个探测请求 |

| Constraint ID | Description |
|---------------|-------------|
| **FB-6** | 60s 内 3 次失败 → Open |
| **FB-7** | Open 状态持续 30s |
| **FB-8** | Half-Open 允许 2 个探测 |
| **FB-9** | 探测成功 → Closed，失败 → Open |
| **FB-10** | 状态按 proxyApiUrl 隔离 |

---

## 7. Testing Constraints

### 7.1 Contract Tests

| Test ID | Description |
|---------|-------------|
| **T-1** | `GET /models` 返回 `{"data":[{"id":"..."}]}` |
| **T-2** | `POST /v1/chat/completions` (stream=false) 返回有效响应 |
| **T-3** | `POST /v1/chat/completions` (stream=true) 返回有效 SSE |
| **T-4** | SSE 每行可被 `LineSplitter` + JSON.decode 解析 |
| **T-5** | 流以 `[DONE]` 结束 |

### 7.2 Error Handling Tests

| Test ID | Description |
|---------|-------------|
| **T-6** | Proxy timeout → fallback 触发 |
| **T-7** | Proxy 503 → fallback 触发 |
| **T-8** | Proxy 401 → 错误直接抛出 |
| **T-9** | Mid-stream disconnect (after chunk) → 错误，无 fallback |

### 7.3 Circuit Breaker Tests

| Test ID | Description |
|---------|-------------|
| **T-10** | 3 次连续失败 → breaker open |
| **T-11** | Open 状态 → 请求走 direct |
| **T-12** | 30s 后 → half-open，探测请求 |

### 7.4 Performance Tests

| Test ID | Description |
|---------|-------------|
| **T-13** | First token latency delta < 200ms |
| **T-14** | Per-chunk flush latency < 50ms |

### 7.5 Compatibility Tests

| Test ID | Description |
|---------|-------------|
| **T-15** | Multimodal content (image_url) 正确透传 |
| **T-16** | Thinking model reasoning 字段正确处理 |
| **T-17** | 大消息 (>1MB) 不超时 |

---

## 8. Implementation Phases

### Phase 1: Infrastructure (Week 1)
- [ ] Python 后端 `/health`, `/models`, `/v1/chat/completions` 端点
- [ ] SSE 流式响应实现
- [ ] 基础 contract tests

### Phase 2: Flutter Integration (Week 2)
- [ ] `ProviderConfig` 扩展
- [ ] `ProxyProvider` 实现
- [ ] `RoutingProviderFactory` 实现
- [ ] 配置 UI（可选，可用设置文件）

### Phase 3: Fallback & Resilience (Week 3)
- [ ] Fallback 逻辑实现
- [ ] Circuit breaker 实现
- [ ] 错误处理测试

### Phase 4: Validation & Rollout (Week 4)
- [ ] 端到端测试
- [ ] 性能基准测试
- [ ] 灰度开关控制

---

## 9. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SSE 解析不兼容 | Medium | High | 严格遵循 constraint，充分测试 |
| Proxy 延迟过高 | Low | Medium | 本地 localhost，flush 优化 |
| 配置迁移问题 | Low | Medium | 向后兼容默认值 |
| Circuit breaker 误触发 | Low | Low | 可调阈值，监控日志 |

---

## 10. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-02-02 | 采用 OpenAI 兼容格式 | 现有 adapter 已支持 |
| 2025-02-02 | 默认 `backendMode=direct` | 保守策略，需显式启用 |
| 2025-02-02 | Circuit breaker per-URL | 避免一个 proxy 失败影响所有 |
