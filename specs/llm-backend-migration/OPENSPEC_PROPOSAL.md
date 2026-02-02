# OpenSpec Proposal: LLM Backend Migration

> **Spec ID**: `llm-backend-migration-001`
> **Version**: 0.1.0
> **Status**: Proposed
> **Created**: 2025-02-02
> **Authors**: Claude (AI), User

---

## Abstract

本提案定义 ChatBoxApp LLM 通信层从 Flutter 直连迁移到 Python 后端代理的技术规范。核心设计原则是**渐进式迁移**：保留现有直连功能作为回滚选项，通过配置开关控制路由策略。

---

## Motivation

### 现状问题

1. **MCP 集成困难**：Flutter 端缺乏成熟的 MCP Host 实现
2. **Tool Call 循环**：多轮 LLM ↔ Tool 交互在 Flutter 端实现复杂
3. **RAG 集成**：设备端向量存储需要 Python 生态（ChromaDB）
4. **Provider 适配**：Python SDK 更新更快，适配新模型更容易

### 迁移收益

- **统一代理层**：所有 LLM 请求经由 Python 后端，便于添加 MCP/RAG 增强
- **简化 Flutter 端**：移除 adapter 层复杂的 SSE 解析逻辑
- **灵活扩展**：后端可独立更新，无需发布 App 新版本

### 保留直连的理由

- **迁移安全**：验证期间可随时回滚
- **调试便利**：直连可排除后端因素
- **降级方案**：后端异常时自动回退

---

## Specification

### 1. Routing Layer

```
┌─────────────────────────────────────────────────────────────┐
│                   RoutingProviderFactory                    │
│                                                             │
│   Input: ProviderConfig (with backendMode)                  │
│   Output: AIProvider instance                               │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                  Routing Logic                       │   │
│   │                                                      │   │
│   │  if (globalBackendOverride != null)                  │   │
│   │    mode = globalBackendOverride                      │   │
│   │  else                                                │   │
│   │    mode = config.backendMode                         │   │
│   │                                                      │   │
│   │  if (mode == direct || !pythonBackendEnabled)        │   │
│   │    return DirectProvider(config)                     │   │
│   │  else if (mode == proxy)                             │   │
│   │    return ProxyProvider(config)                      │   │
│   │  else // auto                                        │   │
│   │    return FallbackProvider(                          │   │
│   │      primary: ProxyProvider(config),                 │   │
│   │      fallback: DirectProvider(config)                │   │
│   │    )                                                 │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2. Provider Implementations

#### 2.1 DirectProvider

现有 `OpenAIProvider` / `LangChainProvider` 的封装，无任何修改。

#### 2.2 ProxyProvider

```dart
class ProxyProvider implements AIProvider {
  final ProviderConfig config;
  final Dio _dio;

  ProxyProvider(this.config) : _dio = Dio(BaseOptions(
    baseUrl: config.proxyApiUrl ?? 'http://localhost:8765',
    connectTimeout: Duration(milliseconds: config.fallbackTimeoutMs),
  ));

  @override
  Stream<String> sendMessageStream({...}) async* {
    final response = await _dio.post(
      '/v1/chat/completions',
      data: _buildRequestBody(model, messages, params, stream: true),
      options: Options(
        responseType: ResponseType.stream,
        headers: _buildHeaders(),
      ),
    );

    yield* _parseSSEStream(response.data.stream);
  }

  Map<String, dynamic> _buildRequestBody(...) {
    return {
      'model': model,
      'messages': _convertMessages(messages),
      'stream': stream,
      ...params.toJson(),
      // 透传 provider 配置供后端路由
      'provider': {
        'type': config.type.name,
        'api_key': config.apiKey,
        'api_url': config.apiUrl,
      },
    };
  }
}
```

#### 2.3 FallbackProvider

```dart
class FallbackProvider implements AIProvider {
  final AIProvider primary;
  final AIProvider fallback;
  final CircuitBreaker _breaker;

  @override
  Stream<String> sendMessageStream({...}) async* {
    if (_breaker.isOpen) {
      yield* fallback.sendMessageStream(...);
      return;
    }

    bool hasEmittedChunk = false;

    try {
      await for (final chunk in primary.sendMessageStream(...)) {
        hasEmittedChunk = true;
        _breaker.recordSuccess();
        yield chunk;
      }
    } on FallbackableError catch (e) {
      _breaker.recordFailure();

      if (!hasEmittedChunk && _breaker.shouldFallback) {
        yield* fallback.sendMessageStream(...);
      } else {
        rethrow;
      }
    }
  }
}
```

### 3. Python Backend API

详见 [CONSTRAINT_SET.md](./CONSTRAINT_SET.md) Section 3-4。

核心端点：
- `GET /api/health` - 健康检查
- `GET /models` - 模型列表
- `POST /v1/chat/completions` - 聊天完成（兼容 OpenAI）

### 4. Configuration Schema

```yaml
# ProviderConfig extension
provider_config:
  # Existing fields...

  # NEW: Backend routing
  backend_mode:
    type: enum
    values: [direct, proxy, auto]
    default: direct
    description: 路由策略

  proxy_api_url:
    type: string
    format: uri
    default: null
    required_when: backend_mode == proxy

  proxy_api_key:
    type: string
    default: null

  # NEW: Fallback control
  fallback_enabled:
    type: boolean
    default: true
    applies_when: backend_mode == auto

  fallback_timeout_ms:
    type: integer
    default: 5000
    min: 1000
    max: 30000

  # NEW: Circuit breaker
  circuit_breaker:
    type: object
    properties:
      failure_threshold:
        type: integer
        default: 3
      window_ms:
        type: integer
        default: 60000
      open_ms:
        type: integer
        default: 30000
      half_open_max_calls:
        type: integer
        default: 2
```

### 5. State Machine: Circuit Breaker

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    ▼                                         │
              ┌──────────┐                                    │
      ────────│  CLOSED  │◄───────────────────────────────────┤
     │        └────┬─────┘                                    │
     │             │                                          │
     │             │ failures >= threshold                    │
     │             │ within window                            │
     │             ▼                                          │
     │        ┌──────────┐                                    │
     │        │   OPEN   │                                    │
     │        └────┬─────┘                                    │
     │             │                                          │
     │             │ timeout elapsed                          │
     │             ▼                                          │
     │        ┌──────────────┐                                │
     │        │  HALF-OPEN   │────────────────────────────────┘
     │        └──────┬───────┘         probe success
     │               │
     │               │ probe failure
     │               ▼
     │          ┌──────────┐
     │          │   OPEN   │
     │          └──────────┘
     │
     └────────────────────────────────────────────────────────
              request success (keep closed)
```

### 6. Error Classification

```dart
enum ErrorCategory {
  // Fallback 触发
  network,       // 连接失败、超时
  serverError,   // 502, 503, 504

  // 不触发 Fallback
  authError,     // 401, 403
  clientError,   // 400, 404, 422
  rateLimitError, // 429
}

bool shouldFallback(ErrorCategory category) {
  return category == ErrorCategory.network ||
         category == ErrorCategory.serverError;
}
```

---

## Migration Path

### Phase 1: Infrastructure
1. 实现 Python 后端基础框架
2. 实现 `/v1/chat/completions` 端点（纯透传模式）
3. 编写 contract tests

### Phase 2: Flutter Integration
1. 扩展 `ProviderConfig` 模型
2. 实现 `ProxyProvider`
3. 实现 `RoutingProviderFactory`
4. 添加全局开关到设置

### Phase 3: Resilience
1. 实现 `FallbackProvider`
2. 实现 Circuit Breaker
3. 错误分类和处理

### Phase 4: Validation
1. 端到端测试
2. 性能基准
3. 灰度发布（默认 direct，opt-in proxy）

### Phase 5: Full Rollout
1. 默认 `auto` 模式
2. 监控和日志
3. 逐步移除直连代码（可选）

---

## Backward Compatibility

| Scenario | Handling |
|----------|----------|
| 旧配置无 `backendMode` | 默认 `direct` |
| 旧配置无 `proxyApiUrl` | `null`，仅 `direct` 可用 |
| Python 后端不可用 | `direct` 模式不受影响 |
| 升级后降级 | 配置字段被忽略，功能正常 |

---

## Security Considerations

1. **API Key 透传**：后端不持久化 key，仅内存中转
2. **localhost 绑定**：后端仅监听 127.0.0.1
3. **无外部暴露**：移动端后端嵌入 App 进程

---

## Performance Budget

| Metric | Budget | Measurement |
|--------|--------|-------------|
| First token latency delta | < 200ms | p95 |
| Per-chunk flush latency | < 50ms | p95 |
| Memory overhead (backend) | < 100MB | Android |
| Cold start time | < 3s | Backend init |

---

## Open Questions

1. **Q**: 是否需要支持多个 proxy endpoint（如区分 MCP 和纯透传）？
   - **A**: 暂不需要，单一端点通过参数区分功能

2. **Q**: Circuit breaker 状态是否需要持久化？
   - **A**: 否，App 重启重置为 Closed

3. **Q**: 是否需要 UI 显示当前路由状态（direct/proxy）？
   - **A**: 可选，建议在开发阶段显示，正式版隐藏

---

## References

- [CONSTRAINT_SET.md](./CONSTRAINT_SET.md) - 详细约束列表
- [Python Backend Spec](../python-backend/API_SPEC.md) - 后端 API 规范
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference/chat) - 兼容格式参考
