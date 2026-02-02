# LLM Backend Migration - Executable Plan

> **文档类型**: Zero-Decision Executable Plan
> **创建日期**: 2025-02-02
> **状态**: Ready for Execution
> **原则**: 只做增量，不删减，保证可回滚

---

## 执行原则

1. **只增不删**: 所有现有代码保持不变，仅添加新文件/字段
2. **默认行为不变**: `backendMode=direct` 为默认值，现有用户体验零影响
3. **每步可验证**: 每个任务完成后有明确的验收标准
4. **随时可回滚**: 任何阶段都可以通过配置切回直连模式

---

## Phase 0: Python 后端基础框架

### P0-1: 创建后端项目结构

**操作**:
```
backend/
├── main.py
├── config.py
├── requirements.txt
├── api/
│   ├── __init__.py
│   ├── health.py
│   └── chat.py
├── models/
│   ├── __init__.py
│   └── chat.py
├── services/
│   ├── __init__.py
│   └── llm_proxy.py
└── storage/
```

**验收标准**:
- [ ] `pip install -r requirements.txt` 成功
- [ ] `uvicorn main:app --port 8765` 启动无报错
- [ ] `curl http://localhost:8765/api/health` 返回 `{"status":"ok"}`

**回滚**: 删除 `backend/` 目录即可

---

### P0-2: 实现 /v1/chat/completions 端点

**操作**: 在 `backend/api/chat.py` 实现 OpenAI 兼容的聊天端点

**输入格式**:
```json
{
  "model": "gpt-4o",
  "messages": [...],
  "stream": true,
  "provider": {
    "type": "openai",
    "api_key": "sk-xxx",
    "api_url": "https://api.openai.com/v1"
  }
}
```

**验收标准**:
- [ ] 非流式请求返回 `choices[0].message.content`
- [ ] 流式请求返回 SSE 格式，每行 `data: {json}\n\n`
- [ ] 流结束发送 `data: [DONE]\n\n`
- [ ] 错误返回 OpenAI 格式 `{"error":{"message":"..."}}`

**回滚**: 不影响 Flutter 端，后端独立运行

---

### P0-3: 实现 /models 端点

**操作**: 在 `backend/api/chat.py` 添加模型列表端点

**验收标准**:
- [ ] `GET /models` 返回 `{"data":[{"id":"..."}]}`
- [ ] 透传上游 API 的模型列表

**回滚**: 同 P0-2

---

## Phase 1: Flutter 端配置扩展

### P1-1: 添加 BackendMode 枚举

**新建文件**: `lib/models/backend_mode.dart`

```dart
enum BackendMode {
  direct,  // 直连 LLM API（默认）
  proxy,   // 走 Python 后端
  auto,    // 优先后端，失败回退
}
```

**验收标准**:
- [ ] 文件编译通过
- [ ] 无其他文件依赖此文件（暂时独立）

**回滚**: 删除文件

---

### P1-2: 添加 CircuitBreakerConfig 模型

**新建文件**: `lib/models/circuit_breaker_config.dart`

```dart
/// Circuit Breaker 配置（纯 JSON 序列化，与 ProviderConfig 一致）
class CircuitBreakerConfig {
  final int failureThreshold;  // default: 3
  final int windowMs;          // default: 60000
  final int openMs;            // default: 30000
  final int halfOpenMaxCalls;  // default: 2

  const CircuitBreakerConfig({
    this.failureThreshold = 3,
    this.windowMs = 60000,
    this.openMs = 30000,
    this.halfOpenMaxCalls = 2,
  });

  factory CircuitBreakerConfig.fromJson(Map<String, dynamic> json) {
    return CircuitBreakerConfig(
      failureThreshold: json['failureThreshold'] as int? ?? 3,
      windowMs: json['windowMs'] as int? ?? 60000,
      openMs: json['openMs'] as int? ?? 30000,
      halfOpenMaxCalls: json['halfOpenMaxCalls'] as int? ?? 2,
    );
  }

  Map<String, dynamic> toJson() => {
    'failureThreshold': failureThreshold,
    'windowMs': windowMs,
    'openMs': openMs,
    'halfOpenMaxCalls': halfOpenMaxCalls,
  };
}
```

**验收标准**:
- [ ] 文件编译通过
- [ ] 无需 build_runner（纯 JSON 序列化）

**回滚**: 删除文件

---

### P1-3: 扩展 ProviderConfig 模型

**修改文件**: `lib/models/provider_config.dart`

**添加字段** (在现有字段 `description` 之后):
```dart
// Backend routing (新增)
final BackendMode backendMode;
final String? proxyApiUrl;
final String? proxyApiKey;
final Map<String, dynamic>? proxyHeaders;

// Fallback control (新增)
final bool fallbackEnabled;
final int fallbackTimeoutMs;
final CircuitBreakerConfig? circuitBreaker;
```

**构造函数更新**:
```dart
ProviderConfig({
  // ... 现有参数不变 ...
  this.backendMode = BackendMode.direct,  // 默认直连
  this.proxyApiUrl,
  this.proxyApiKey,
  this.proxyHeaders,
  this.fallbackEnabled = true,
  this.fallbackTimeoutMs = 5000,
  this.circuitBreaker,
});
```

**fromJson 更新** (添加新字段解析，缺失时使用默认值):
```dart
backendMode: BackendMode.values.firstWhere(
  (e) => e.name == json['backendMode'],
  orElse: () => BackendMode.direct,
),
proxyApiUrl: json['proxyApiUrl'] as String?,
proxyApiKey: json['proxyApiKey'] as String?,
proxyHeaders: json['proxyHeaders'] != null
    ? Map<String, dynamic>.from(json['proxyHeaders'])
    : null,
fallbackEnabled: json['fallbackEnabled'] as bool? ?? true,
fallbackTimeoutMs: json['fallbackTimeoutMs'] as int? ?? 5000,
circuitBreaker: json['circuitBreaker'] != null
    ? CircuitBreakerConfig.fromJson(json['circuitBreaker'])
    : null,
```

**toJson 更新**:
```dart
'backendMode': backendMode.name,
'proxyApiUrl': proxyApiUrl,
'proxyApiKey': proxyApiKey,
'proxyHeaders': proxyHeaders,
'fallbackEnabled': fallbackEnabled,
'fallbackTimeoutMs': fallbackTimeoutMs,
'circuitBreaker': circuitBreaker?.toJson(),
```

**copyWith 更新**:
```dart
BackendMode? backendMode,
String? proxyApiUrl,
String? proxyApiKey,
Map<String, dynamic>? proxyHeaders,
bool? fallbackEnabled,
int? fallbackTimeoutMs,
CircuitBreakerConfig? circuitBreaker,
```

**验收标准**:
- [ ] 现有配置反序列化成功（缺失字段使用默认值）
- [ ] `backendMode` 默认为 `direct`
- [ ] App 启动正常，Provider 列表加载正常
- [ ] 新建 Provider 配置保存/加载正常

**回滚**: 字段保留但不使用，不影响功能

---

## Phase 2: Flutter 端 Provider 实现

### P2-1: 添加 ProxyOpenAIProvider

**新建文件**: `lib/adapters/proxy_openai_provider.dart`

```dart
class ProxyOpenAIProvider implements AIProvider {
  final ProviderConfig config;
  final Dio _dio;

  ProxyOpenAIProvider(this.config);

  @override
  Stream<String> sendMessageStream({...}) async* {
    // 调用 http://localhost:8765/v1/chat/completions
    // 透传 provider 配置
  }

  @override
  Future<String> sendMessage({...}) async {
    // 非流式版本
  }

  @override
  Future<bool> testConnection() async {
    // 调用 /models 验证连接
  }
}
```

**验收标准**:
- [ ] 文件编译通过
- [ ] 单元测试：mock 后端响应，验证 SSE 解析
- [ ] 集成测试：启动后端，实际调用成功

**回滚**: 删除文件，无其他代码依赖

---

### P2-2: 添加 CircuitBreaker 服务

**新建文件**: `lib/services/circuit_breaker_service.dart`

```dart
enum CircuitState { closed, open, halfOpen }

class CircuitBreaker {
  final CircuitBreakerConfig config;
  CircuitState _state = CircuitState.closed;
  int _failureCount = 0;
  DateTime? _lastFailure;
  DateTime? _openedAt;
  int _halfOpenCalls = 0;

  bool get isOpen => _state == CircuitState.open;
  bool get shouldFallback => isOpen;

  void recordSuccess() { ... }
  void recordFailure() { ... }
}
```

**验收标准**:
- [ ] 单元测试：3 次失败后 isOpen=true
- [ ] 单元测试：30s 后进入 halfOpen
- [ ] 单元测试：探测成功后 closed

**回滚**: 删除文件

---

### P2-3: 添加 FallbackPolicy 服务

**新建文件**: `lib/services/fallback_policy.dart`

```dart
class FallbackPolicy {
  static bool shouldFallback(Object error, bool hasEmittedChunk) {
    if (hasEmittedChunk) return false;  // 已输出则不回退

    if (error is DioException) {
      // 网络错误：回退
      if (error.type == DioExceptionType.connectionTimeout) return true;
      if (error.type == DioExceptionType.connectionError) return true;

      // 服务器错误：回退
      final status = error.response?.statusCode;
      if (status == 502 || status == 503 || status == 504) return true;

      // 认证/客户端错误：不回退
      if (status == 401 || status == 403) return false;
      if (status == 400 || status == 404) return false;
    }

    return false;
  }
}
```

**验收标准**:
- [ ] 单元测试覆盖所有错误类型

**回滚**: 删除文件

---

### P2-4: 添加 BackendRoutingProvider

**新建文件**: `lib/adapters/backend_routing_provider.dart`

```dart
class BackendRoutingProvider implements AIProvider {
  final AIProvider directProvider;
  final AIProvider proxyProvider;
  final CircuitBreaker circuitBreaker;
  final bool fallbackEnabled;

  @override
  Stream<String> sendMessageStream({...}) async* {
    if (circuitBreaker.isOpen && fallbackEnabled) {
      yield* directProvider.sendMessageStream(...);
      return;
    }

    bool hasEmittedChunk = false;

    try {
      await for (final chunk in proxyProvider.sendMessageStream(...)) {
        hasEmittedChunk = true;
        circuitBreaker.recordSuccess();
        yield chunk;
      }
    } catch (e) {
      circuitBreaker.recordFailure();

      if (FallbackPolicy.shouldFallback(e, hasEmittedChunk) && fallbackEnabled) {
        yield* directProvider.sendMessageStream(...);
      } else {
        rethrow;
      }
    }
  }
}
```

**验收标准**:
- [ ] 单元测试：正常情况走 proxy
- [ ] 单元测试：proxy 失败且无 chunk 时走 fallback
- [ ] 单元测试：proxy 失败但有 chunk 时抛错
- [ ] 单元测试：circuit open 时直接走 direct

**回滚**: 删除文件

---

## Phase 3: 集成与路由

### P3-1: 扩展 ProviderFactory

**修改文件**: `lib/adapters/ai_provider.dart`

**添加方法** (不修改现有 createProvider):
```dart
class ProviderFactory {
  // 现有方法保持不变
  static AIProvider createProvider(ProviderConfig config) { ... }

  // 新增：支持后端路由的工厂方法
  static AIProvider createProviderWithRouting(
    ProviderConfig config, {
    CircuitBreaker? circuitBreaker,
  }) {
    final directProvider = createProvider(config);

    switch (config.backendMode) {
      case BackendMode.direct:
        return directProvider;

      case BackendMode.proxy:
        return ProxyOpenAIProvider(config);

      case BackendMode.auto:
        return BackendRoutingProvider(
          directProvider: directProvider,
          proxyProvider: ProxyOpenAIProvider(config),
          circuitBreaker: circuitBreaker ?? CircuitBreaker(
            config.circuitBreaker ?? const CircuitBreakerConfig(),
          ),
          fallbackEnabled: config.fallbackEnabled,
        );
    }
  }
}
```

**验收标准**:
- [ ] 现有 `createProvider` 调用点行为不变
- [ ] 新方法 `backendMode=direct` 时返回与旧方法相同的 provider
- [ ] App 正常启动和聊天

**回滚**: 移除新方法，无影响

---

### P3-2: 添加全局后端开关

**修改文件**: `lib/providers/settings_provider.dart` (或对应设置文件)

**添加字段**:
```dart
// 新增
bool pythonBackendEnabled = false;  // 默认关闭
BackendMode? globalBackendOverride;  // null 表示使用 per-provider 设置
```

**验收标准**:
- [ ] `pythonBackendEnabled=false` 时所有请求走直连
- [ ] 设置可持久化保存/加载

**回滚**: 设置保持 false，功能不激活

---

### P3-3: 集成到聊天调用点

**修改文件**: `lib/controllers/stream_output_controller.dart` 或调用 Provider 的位置

**修改逻辑** (最小化改动):
```dart
// 原代码
final provider = ProviderFactory.createProvider(config);

// 改为
final provider = settings.pythonBackendEnabled
    ? ProviderFactory.createProviderWithRouting(config)
    : ProviderFactory.createProvider(config);
```

**验收标准**:
- [ ] `pythonBackendEnabled=false`：行为与修改前完全一致
- [ ] `pythonBackendEnabled=true` + `backendMode=direct`：行为与修改前一致
- [ ] `pythonBackendEnabled=true` + `backendMode=proxy`：走后端
- [ ] `pythonBackendEnabled=true` + `backendMode=auto`：走后端，失败回退

**回滚**: 改回原代码一行

---

## Phase 4: 验证与测试

### P4-1: 配置兼容性测试

**操作**:
1. 使用旧版 App 创建 Provider 配置
2. 升级到新版 App
3. 验证配置加载正常

**验收标准**:
- [ ] 旧配置无 `backendMode` 字段时默认 `direct`
- [ ] Provider 列表显示正常
- [ ] 聊天功能正常

---

### P4-2: 直连模式验证

**操作**: `pythonBackendEnabled=false` 或 `backendMode=direct`

**验收标准**:
- [ ] 所有 Provider 类型（OpenAI/Claude/Gemini）正常工作
- [ ] 流式输出正常
- [ ] 错误处理正常

---

### P4-3: 代理模式验证

**操作**:
1. 启动 Python 后端
2. 设置 `pythonBackendEnabled=true`, `backendMode=proxy`

**验收标准**:
- [ ] 非流式请求正常
- [ ] 流式请求正常，无明显延迟增加
- [ ] 思考模型 reasoning 字段正确处理
- [ ] 多模态（图片）请求正常

---

### P4-4: 回退模式验证

**操作**:
1. 设置 `backendMode=auto`
2. 关闭 Python 后端
3. 发送消息

**验收标准**:
- [ ] 自动回退到直连
- [ ] 用户无感知（可能有短暂延迟）
- [ ] 日志记录回退事件

---

### P4-5: Circuit Breaker 验证

**操作**:
1. 设置 `backendMode=auto`
2. 模拟后端连续失败 3 次
3. 观察后续请求

**验收标准**:
- [ ] 第 4 次请求直接走直连（不尝试后端）
- [ ] 30s 后尝试探测后端
- [ ] 后端恢复后自动切回

---

## Phase 5: 文档与收尾

### P5-1: 更新 CLAUDE.md

**添加内容**:
- 后端目录结构说明
- 新增 Provider 配置字段说明
- 调试指南（如何切换模式）

---

### P5-2: 添加设置 UI（可选）

**新建文件**: `lib/pages/settings/backend_settings_page.dart`

**功能**:
- 全局后端开关
- 默认 backendMode 选择
- 后端健康状态显示

---

## 回滚检查清单

任何阶段遇到问题，按以下步骤回滚：

### 即时回滚（配置）
- [ ] 设置 `pythonBackendEnabled=false`
- [ ] 或设置所有 Provider 的 `backendMode=direct`

### 代码回滚（如需）
1. `lib/controllers/stream_output_controller.dart` 改回原一行
2. 删除新增文件（不影响编译）:
   - `lib/adapters/proxy_openai_provider.dart`
   - `lib/adapters/backend_routing_provider.dart`
   - `lib/services/circuit_breaker_service.dart`
   - `lib/services/fallback_policy.dart`
3. ProviderConfig 新字段保留（有默认值，不影响功能）

### 后端回滚
- 停止 Python 后端进程
- `backendMode=direct` 或 `pythonBackendEnabled=false` 即可

---

## 依赖关系图

```
Phase 0 (Python Backend)
    │
    ├──────────────────────────────────────────┐
    │                                          │
    ▼                                          ▼
Phase 1 (Config)                          [独立验证]
    │
    ├── P1-1: BackendMode enum
    ├── P1-2: CircuitBreakerConfig
    └── P1-3: ProviderConfig extension
            │
            ▼
Phase 2 (Providers)
    │
    ├── P2-1: ProxyOpenAIProvider
    ├── P2-2: CircuitBreaker service ◄─────┐
    ├── P2-3: FallbackPolicy service       │
    └── P2-4: BackendRoutingProvider ──────┘
            │
            ▼
Phase 3 (Integration)
    │
    ├── P3-1: ProviderFactory extension
    ├── P3-2: Global settings
    └── P3-3: Call site integration
            │
            ▼
Phase 4 (Validation)
    │
    └── P4-1 ~ P4-5: Tests
            │
            ▼
Phase 5 (Documentation)
```

---

## 时间线（参考）

| Phase | 任务数 | 预估 |
|-------|--------|------|
| Phase 0 | 3 | - |
| Phase 1 | 3 | - |
| Phase 2 | 4 | - |
| Phase 3 | 3 | - |
| Phase 4 | 5 | - |
| Phase 5 | 2 | - |
| **Total** | **20** | - |

---

## 相关文档

- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - 原始实施计划
- [CONSTRAINT_SET.md](./CONSTRAINT_SET.md) - 约束集
- [OPENSPEC_PROPOSAL.md](./OPENSPEC_PROPOSAL.md) - 技术提案
