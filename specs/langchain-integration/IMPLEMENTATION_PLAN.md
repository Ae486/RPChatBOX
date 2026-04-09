# LangChain 混合架构实施计划

> 状态: DRAFT
> 创建: 2026-02-04
> 前置文档: CONSTRAINT_SET.md, PROPOSAL.md

---

## 阶段概览

| 阶段 | 目标 | 产出 |
|------|------|------|
| **Phase 1** | 模块提取 | SseParser, ThinkingExtractor |
| **Phase 2** | 混合 Provider | HybridLangChainProvider |
| **Phase 3** | 错误处理完善 | 统一 ApiError 链路 |
| **Phase 4** | 路由切换 | ProviderFactory 集成 |
| **Phase 5** | 测试验证 | Golden tests + 集成测试 |

---

## Phase 1: 模块提取

### 1.1 创建 SSE 解析器

**文件**: `lib/adapters/sse/sse_parser.dart`

**职责**:
- 解析 SSE 行格式 (`data: {...}`)
- 处理 `[DONE]` 结束标记
- JSON 解码和错误检测

**接口设计**:
```dart
/// SSE 行解析结果
sealed class SseEvent {}

class SseDataEvent extends SseEvent {
  final Map<String, dynamic> data;
  SseDataEvent(this.data);
}

class SseDoneEvent extends SseEvent {}

class SseErrorEvent extends SseEvent {
  final String type;
  final String message;
  final String? code;
  SseErrorEvent({required this.type, required this.message, this.code});
}

/// SSE 流解析器
class SseParser {
  /// 将原始字节流转换为 SseEvent 流
  static Stream<SseEvent> parse(Stream<List<int>> byteStream);

  /// 解析单行 SSE 数据
  static SseEvent? parseLine(String line);
}
```

**提取来源**: `openai_provider.dart` 第 158-176 行

---

### 1.2 创建 Thinking 提取器

**文件**: `lib/adapters/sse/thinking_extractor.dart`

**职责**:
- 从 SSE delta 中提取 thinking 内容
- 管理 `<think>` 标签状态
- 支持多种 thinking 字段格式

**接口设计**:
```dart
/// Thinking 内容提取结果
class ThinkingChunk {
  final String text;
  final bool isThinking;  // true = thinking content, false = normal content
  ThinkingChunk(this.text, {required this.isThinking});
}

/// Thinking 内容提取器
class ThinkingExtractor {
  bool _thinkingOpen = false;

  /// 从 SSE delta 提取内容，自动注入 <think> 标签
  Iterable<String> extract(Map<String, dynamic> delta);

  /// 流结束时获取关闭标签（如果需要）
  String? getClosingTag();

  /// 重置状态
  void reset();
}
```

**提取来源**: `openai_provider.dart` 第 184-224 行

**支持的 thinking 字段**:
- `reasoning` (OpenRouter)
- `reasoning_content` (DeepSeek R1)
- `internal_thoughts` (某些模型)
- `thinking` (Claude)

---

### 1.3 创建 Gemini 特殊处理器

**文件**: `lib/adapters/sse/gemini_parser.dart`

**职责**:
- 处理 Gemini candidates 格式
- 处理 Gemini 多 parts 结构

**接口设计**:
```dart
/// Gemini 响应解析器
class GeminiParser {
  bool _reasoningOpen = false;
  bool _emittedBody = false;

  /// 从 Gemini candidates 格式提取内容
  Iterable<String> extractFromCandidates(List<dynamic> candidates);

  /// 获取关闭标签
  String? getClosingTag();

  void reset();
}
```

**提取来源**: `openai_provider.dart` 第 229-276 行

---

## Phase 2: 混合 Provider 实现

### 2.1 创建 HybridLangChainProvider

**文件**: `lib/adapters/hybrid_langchain_provider.dart`

**职责**:
- 消息转换使用 LangChainMessageMapper
- 参数构建使用 LangChain Options
- HTTP 请求使用 Dio (带 CancelToken)
- SSE 解析使用 SseParser + ThinkingExtractor

**接口设计**:
```dart
class HybridLangChainProvider extends AIProvider {
  final Dio _dio;
  CancelToken? _cancelToken;

  HybridLangChainProvider(ProviderConfig config) : super(config);

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async* {
    // 1. 使用 LangChainMessageMapper 转换消息
    final lcMessages = await LangChainMessageMapper.toLangChainMessages(...);

    // 2. 构建请求体 (使用 LangChain options 结构)
    final requestBody = _buildRequestBody(lcMessages, model, parameters);

    // 3. 发送 Dio 请求 (带 CancelToken)
    final response = await _dio.post(...);

    // 4. 使用 SseParser 解析流
    final sseStream = SseParser.parse(response.data.stream);

    // 5. 使用 ThinkingExtractor 提取内容
    final extractor = ThinkingExtractor();
    await for (final event in sseStream) {
      if (event is SseDataEvent) {
        yield* extractor.extract(event.data);
      } else if (event is SseErrorEvent) {
        throw ApiError(...);
      }
    }

    // 6. 关闭 thinking 标签
    final closing = extractor.getClosingTag();
    if (closing != null) yield closing;
  }

  @override
  Future<String> sendMessage(...) async {
    // 非流式实现
  }

  void cancelRequest() {
    _cancelToken?.cancel('用户取消');
  }
}
```

---

### 2.2 请求体构建

**方法**: `_buildRequestBody`

```dart
Map<String, dynamic> _buildRequestBody(
  List<lc.ChatMessage> messages,
  String model,
  ModelParameters parameters,
) {
  final body = <String, dynamic>{
    'model': model,
    'messages': messages.map((m) => _messageToJson(m)).toList(),
    'stream': true,
    'include_reasoning': true,
  };

  // Provider 特定参数
  switch (config.type) {
    case ProviderType.openai:
      _addOpenAIParams(body, parameters);
    case ProviderType.deepseek:
      _addDeepSeekParams(body, parameters);
    case ProviderType.gemini:
      _addGeminiParams(body, parameters);
    case ProviderType.claude:
      _addClaudeParams(body, parameters);
  }

  return body;
}
```

---

## Phase 3: 错误处理完善

### 3.1 统一错误类型

**原则**: 所有错误都抛出 `ApiError`，不再使用 `Exception`

**改动点**:

| 位置 | 当前 | 改为 |
|------|------|------|
| DioException 处理 | `Exception('流式请求失败')` | `ApiError(...)` |
| SSE 内 error 检测 | `Exception('[$type] $msg')` | `ApiError(...)` |
| 取消处理 | `Exception('请求已取消')` | `ApiError(errorCode: 'cancelled')` |
| 通用 catch | `Exception(e.toString())` | `ApiError(errorCode: 'unknown')` |

### 3.2 SseParser 错误处理

```dart
class SseParser {
  static Stream<SseEvent> parse(Stream<List<int>> byteStream) async* {
    await for (final line in byteStream
        .transform(utf8.decoder)
        .transform(const LineSplitter())) {
      final trimmed = line.trim();
      if (trimmed.isEmpty) continue;

      final event = parseLine(trimmed);
      if (event != null) yield event;
    }
  }

  static SseEvent? parseLine(String line) {
    if (!line.startsWith('data: ')) return null;

    final data = line.substring(6);
    if (data == '[DONE]') return SseDoneEvent();

    try {
      final json = jsonDecode(data) as Map<String, dynamic>;

      // 检测错误响应
      final error = json['error'] as Map<String, dynamic>?;
      if (error != null) {
        return SseErrorEvent(
          type: error['type']?.toString() ?? 'error',
          message: error['message']?.toString() ?? 'Unknown error',
          code: error['code']?.toString(),
        );
      }

      return SseDataEvent(json);
    } catch (e) {
      // JSON 解析失败，跳过
      return null;
    }
  }
}
```

### 3.3 HybridProvider 错误处理

```dart
Stream<String> sendMessageStream(...) async* {
  _cancelToken = CancelToken();

  try {
    final response = await _dio.post(
      config.actualApiUrl,
      data: requestBody,
      options: Options(responseType: ResponseType.stream),
      cancelToken: _cancelToken,
    );

    if (response.statusCode != 200) {
      throw ApiErrorParser.parseFromResponse(
        statusCode: response.statusCode!,
        responseBody: response.data.toString(),
      );
    }

    final sseStream = SseParser.parse(response.data.stream);
    final extractor = ThinkingExtractor();

    await for (final event in sseStream) {
      switch (event) {
        case SseDataEvent(:final data):
          for (final chunk in extractor.extract(data)) {
            yield chunk;
          }
        case SseErrorEvent(:final type, :final message, :final code):
          throw ApiError(
            statusCode: 200,  // SSE 内错误
            message: message,
            errorCode: code ?? type,
          );
        case SseDoneEvent():
          break;
      }
    }

    final closing = extractor.getClosingTag();
    if (closing != null) yield closing;

  } on DioException catch (e) {
    if (e.type == DioExceptionType.cancel) {
      throw ApiError(statusCode: 0, message: '请求已取消', errorCode: 'cancelled');
    }
    if (e.response != null) {
      throw ApiErrorParser.parseFromResponse(
        statusCode: e.response!.statusCode ?? 500,
        responseBody: e.response!.data?.toString() ?? '',
      );
    }
    throw ApiError(statusCode: 0, message: e.message ?? '网络错误', errorCode: 'network_error');
  } on ApiError {
    rethrow;
  } catch (e) {
    throw ApiError(statusCode: 0, message: e.toString(), errorCode: 'unknown');
  } finally {
    _cancelToken = null;
  }
}
```

---

## Phase 4: 路由切换

### 4.1 修改 ProviderFactory

**文件**: `lib/adapters/ai_provider.dart`

```dart
class ProviderFactory {
  /// 使用混合 LangChain 实现
  static bool useHybridLangChain = true;  // 新开关

  static AIProvider createProvider(ProviderConfig config) {
    if (useHybridLangChain) {
      return HybridLangChainProvider(config);
    }

    // 回退到原实现
    return OpenAIProvider(config);
  }
}
```

### 4.2 保留原实现作为 Fallback

- `OpenAIProvider` 保持不变
- 通过 `useHybridLangChain` 开关控制
- 出问题时可快速回滚

---

## Phase 5: 测试验证

### 5.1 单元测试

**文件**: `test/unit/adapters/sse_parser_test.dart`

```dart
void main() {
  group('SseParser', () {
    test('解析正常数据行', () {
      final event = SseParser.parseLine('data: {"choices":[{"delta":{"content":"hello"}}]}');
      expect(event, isA<SseDataEvent>());
    });

    test('解析 [DONE] 标记', () {
      final event = SseParser.parseLine('data: [DONE]');
      expect(event, isA<SseDoneEvent>());
    });

    test('解析错误响应', () {
      final event = SseParser.parseLine('data: {"error":{"message":"Invalid API key","type":"auth_error"}}');
      expect(event, isA<SseErrorEvent>());
      expect((event as SseErrorEvent).message, equals('Invalid API key'));
    });

    test('忽略空行', () {
      final event = SseParser.parseLine('');
      expect(event, isNull);
    });
  });
}
```

**文件**: `test/unit/adapters/thinking_extractor_test.dart`

```dart
void main() {
  group('ThinkingExtractor', () {
    late ThinkingExtractor extractor;

    setUp(() {
      extractor = ThinkingExtractor();
    });

    test('提取 reasoning_content', () {
      final delta = {'reasoning_content': '让我思考一下'};
      final chunks = extractor.extract(delta).toList();
      expect(chunks, equals(['<think>', '让我思考一下']));
    });

    test('切换到 content 时关闭 think 标签', () {
      extractor.extract({'reasoning_content': '思考中'}).toList();
      final chunks = extractor.extract({'content': '答案是'}).toList();
      expect(chunks, equals(['</think>', '答案是']));
    });

    test('流结束时获取关闭标签', () {
      extractor.extract({'reasoning_content': '思考'}).toList();
      expect(extractor.getClosingTag(), equals('</think>'));
    });
  });
}
```

### 5.2 Golden Tests (SSE Fixtures)

**目录**: `test/fixtures/sse/`

```
test/fixtures/sse/
├── openai_normal.txt           # 普通 OpenAI 响应
├── deepseek_r1_reasoning.txt   # DeepSeek R1 带 reasoning
├── claude_thinking.txt         # Claude extended thinking
├── gemini_candidates.txt       # Gemini candidates 格式
├── error_invalid_key.txt       # API Key 错误
├── error_rate_limit.txt        # 速率限制错误
└── partial_json.txt            # 不完整 JSON (边缘情况)
```

**示例 fixture** (`deepseek_r1_reasoning.txt`):
```
data: {"choices":[{"delta":{"reasoning_content":"让我分析这个问题"}}]}

data: {"choices":[{"delta":{"reasoning_content":"首先考虑..."}}]}

data: {"choices":[{"delta":{"content":"根据分析，答案是"}}]}

data: {"choices":[{"delta":{"content":"42"}}]}

data: [DONE]
```

### 5.3 集成测试

**文件**: `test/integration/hybrid_provider_test.dart`

```dart
void main() {
  group('HybridLangChainProvider Integration', () {
    test('DeepSeek R1 reasoning 正确提取', () async {
      // Mock Dio 返回 fixture
      final provider = HybridLangChainProvider(testConfig);
      final chunks = <String>[];

      await for (final chunk in provider.sendMessageStream(...)) {
        chunks.add(chunk);
      }

      expect(chunks.join(''), contains('<think>'));
      expect(chunks.join(''), contains('</think>'));
    });

    test('请求取消正确清理', () async {
      final provider = HybridLangChainProvider(testConfig);

      // 启动流
      final future = provider.sendMessageStream(...).toList();

      // 立即取消
      provider.cancelRequest();

      // 应该抛出 ApiError
      expect(future, throwsA(isA<ApiError>()));
    });

    test('API 错误正确解析', () async {
      // Mock 返回错误响应
      final provider = HybridLangChainProvider(testConfig);

      expect(
        () => provider.sendMessageStream(...).toList(),
        throwsA(predicate<ApiError>((e) => e.statusCode == 401)),
      );
    });
  });
}
```

---

## 任务清单

### Phase 1: 模块提取 (预计 2-3 小时)

- [ ] 1.1 创建 `lib/adapters/sse/sse_parser.dart`
- [ ] 1.2 创建 `lib/adapters/sse/thinking_extractor.dart`
- [ ] 1.3 创建 `lib/adapters/sse/gemini_parser.dart`
- [ ] 1.4 编写 SseParser 单元测试
- [ ] 1.5 编写 ThinkingExtractor 单元测试

### Phase 2: 混合 Provider (预计 2-3 小时)

- [ ] 2.1 创建 `lib/adapters/hybrid_langchain_provider.dart`
- [ ] 2.2 实现 sendMessageStream 方法
- [ ] 2.3 实现 sendMessage 方法
- [ ] 2.4 实现 cancelRequest 方法
- [ ] 2.5 实现 testConnection 和 listAvailableModels

### Phase 3: 错误处理完善 (预计 1-2 小时)

- [ ] 3.1 SseParser 添加错误事件类型
- [ ] 3.2 HybridProvider 统一使用 ApiError
- [ ] 3.3 添加错误处理测试用例

### Phase 4: 路由切换 (预计 30 分钟)

- [ ] 4.1 修改 ProviderFactory 添加开关
- [ ] 4.2 更新相关导入

### Phase 5: 测试验证 (预计 2-3 小时)

- [ ] 5.1 创建 SSE fixture 文件
- [ ] 5.2 编写 golden tests
- [ ] 5.3 编写集成测试
- [ ] 5.4 手动测试所有 provider 类型

---

## 回滚计划

如果出现问题，立即回滚方案：

```dart
// 在 ProviderFactory 中
static bool useHybridLangChain = false;  // 改为 false 即可回滚
```

原有 `OpenAIProvider` 保持不变，随时可切回。

---

## 验收标准

| 场景 | 预期行为 |
|------|---------|
| 普通 OpenAI 聊天 | 正常流式输出，无 thinking 标签 |
| DeepSeek R1 | 输出包含 `<think>...</think>` |
| Claude extended thinking | 输出包含 `<think>...</think>` |
| Gemini 2.0 thinking | 输出包含 `<think>...</think>` |
| API Key 错误 | 抛出 ApiError，statusCode=401 |
| 网络超时 | 抛出 ApiError，errorCode=timeout |
| 请求取消 | 立即停止，抛出 ApiError，errorCode=cancelled |
| 速率限制 | 抛出 ApiError，statusCode=429，isRetryable=true |
