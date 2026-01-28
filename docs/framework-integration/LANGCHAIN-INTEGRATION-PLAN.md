# LangChain.dart Integration Plan

> 零决策可执行实施计划
>
> 版本: 1.1 | 日期: 2026-01-24
>
> 多模型分析: Codex (019bef74) + Gemini (294378a3)
>
> **状态: ✅ Phase 0-3 已完成**

---

## 1. 执行摘要

### 1.1 目标
将 Provider 层替换为 LangChain.dart，解决多 Provider 支持问题。

### 1.2 约束
- AIProvider 接口保持不变（返回 `Stream<String>`）
- RP 后端和 UI 不修改
- 零功能回归

### 1.3 预期收益
- 立即支持 7 个 LLM Provider (OpenAI, Anthropic, Google, Mistral, Ollama, etc.)
- 标准化错误处理
- 为 RAG/Tool Calling 铺平道路

---

## 2. 依赖关系图

```
Phase 0 (Dependencies)
    │
    ▼
Phase 1 (Adapter Core)
    ├── Task 1.1: Message Mapper
    ├── Task 1.2: Error Mapper
    └── Task 1.3: LangChainProvider
    │
    ▼
Phase 2 (Factory Integration)
    └── Task 2.1: ProviderFactory 更新
    │
    ▼
Phase 3 (Streaming Verification)
    ├── Task 3.1: Fake ChatModel
    ├── Task 3.2: Provider Tests
    └── Task 3.3: Factory Tests
    │
    ▼
Phase 4 (Error Standardization)
    └── Task 4.1: Error Handling
    │
    ▼
Phase 5 (UI Compatibility) [可选]
    ├── Task 5.1: Empty Chunk Tolerance
    ├── Task 5.2: Thinking Indicator
    └── Task 5.3: Error Message Mapping
    │
    ▼
Phase 6 (Manual Verification)
    └── Task 6.1: E2E Testing
```

---

## 3. Phase 0: Dependencies

### Task 0.1: Add LangChain Dependencies

**文件**: `pubspec.yaml`

**命令**:
```bash
flutter pub add langchain_core langchain_openai langchain_google langchain_anthropic
```

**验收标准**:
- `flutter pub get` 成功
- `flutter analyze` 无错误

**回滚策略**:
```bash
flutter pub remove langchain_core langchain_openai langchain_google langchain_anthropic
```

---

## 4. Phase 1: Adapter Core

### Task 1.1: Message Mapper

**文件**: `lib/adapters/langchain_message_mapper.dart`

**签名**:
```dart
import '../adapters/ai_provider.dart' show ChatMessage, AttachedFileData;
import '../models/provider_config.dart';
import 'package:langchain_core/langchain_core.dart' as lc;

/// 将 AIProvider.ChatMessage 转换为 LangChain ChatMessage
class LangChainMessageMapper {
  /// 转换消息列表
  ///
  /// [messages] - AIProvider 格式的消息
  /// [providerType] - 目标 Provider 类型（影响多模态处理）
  /// [files] - 附件文件（图片等）
  static Future<List<lc.ChatMessage>> toLangChainMessages({
    required List<ChatMessage> messages,
    required ProviderType providerType,
    List<AttachedFileData>? files,
  }) async {
    // Implementation
  }
}
```

**验收标准**:
- 编译通过
- 支持 text-only 和 multimodal 消息
- 单元测试覆盖

**回滚策略**: 删除文件

---

### Task 1.2: Error Mapper

**文件**: `lib/adapters/provider_error_mapper.dart`

**签名**:
```dart
import '../models/api_error.dart';

/// 标准化 Provider 错误
class ProviderErrorMapper {
  /// 将任意错误转换为 ApiError
  ///
  /// [error] - 原始错误
  /// [providerName] - Provider 名称（用于错误消息）
  static ApiError toApiError(Object error, {String? providerName}) {
    // 错误类型映射:
    // - AuthenticationException → statusCode: 401
    // - RateLimitException → statusCode: 429
    // - ToolException → statusCode: 500
    // - OutputParserException → statusCode: 422
    // - Unknown → statusCode: 500
  }
}
```

**验收标准**:
- 所有 LangChain 异常类型都有映射
- ApiError 包含 message 和 statusCode

**回滚策略**: 删除文件

---

### Task 1.3: LangChainProvider

**文件**: `lib/adapters/langchain_provider.dart`

**签名**:
```dart
import '../adapters/ai_provider.dart';
import '../models/provider_config.dart';
import '../models/model_parameters.dart';
import 'package:langchain_core/langchain_core.dart';
import 'package:langchain_openai/langchain_openai.dart';
import 'package:langchain_google/langchain_google.dart';
import 'package:langchain_anthropic/langchain_anthropic.dart';

/// LangChain.dart 适配器
///
/// 实现 AIProvider 接口，内部使用 LangChain ChatModel
class LangChainProvider extends AIProvider {
  LangChainProvider._(ProviderConfig config, this._modelFactory) : super(config);

  final BaseChatModel Function({
    required String model,
    required ModelParameters parameters,
  }) _modelFactory;

  /// 从配置创建 Provider
  factory LangChainProvider.fromConfig(ProviderConfig config) {
    switch (config.type) {
      case ProviderType.openai:
        return LangChainProvider._(config, ({model, parameters}) => ChatOpenAI(
          apiKey: config.apiKey,
          baseUrl: config.baseUrl,
          defaultOptions: ChatOpenAIOptions(
            model: model,
            temperature: parameters.temperature,
            maxTokens: parameters.maxTokens,
          ),
        ));
      case ProviderType.gemini:
        return LangChainProvider._(config, ({model, parameters}) => ChatGoogleGenerativeAI(
          apiKey: config.apiKey,
          defaultOptions: ChatGoogleGenerativeAIOptions(
            model: model,
            temperature: parameters.temperature,
            maxOutputTokens: parameters.maxTokens,
          ),
        ));
      case ProviderType.claude:
        return LangChainProvider._(config, ({model, parameters}) => ChatAnthropic(
          apiKey: config.apiKey,
          defaultOptions: ChatAnthropicOptions(
            model: model,
            temperature: parameters.temperature,
            maxTokens: parameters.maxTokens,
          ),
        ));
      // ... 其他 Provider
    }
  }

  @override
  Future<ProviderTestResult> testConnection() async {
    // 发送简单测试消息验证连接
  }

  @override
  Future<List<String>> listAvailableModels() async {
    // 返回预定义模型列表（LangChain 不支持动态获取）
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async* {
    try {
      final chatModel = _modelFactory(model: model, parameters: parameters);
      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: config.type,
        files: files,
      );

      await for (final chunk in chatModel.stream(PromptValue.chat(lcMessages))) {
        final content = chunk.output.content;
        if (content.isNotEmpty) {
          yield content;
        }
      }
    } catch (e) {
      throw ProviderErrorMapper.toApiError(e, providerName: config.type.name);
    }
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async {
    final buffer = StringBuffer();
    await for (final chunk in sendMessageStream(
      model: model,
      messages: messages,
      parameters: parameters,
      files: files,
    )) {
      buffer.write(chunk);
    }
    return buffer.toString();
  }
}
```

**验收标准**:
- 实现所有 AIProvider 抽象方法
- sendMessageStream 返回增量 chunk
- 错误通过 ProviderErrorMapper 处理

**回滚策略**: 删除文件

---

## 5. Phase 2: Factory Integration

### Task 2.1: Update ProviderFactory

**文件**: `lib/adapters/ai_provider.dart`

**修改位置**: `ProviderFactory.createProvider` 方法

**Before**:
```dart
class ProviderFactory {
  static AIProvider createProvider(ProviderConfig config) {
    switch (config.type) {
      case ProviderType.openai:
        return OpenAIProvider(config);
      case ProviderType.gemini:
        return OpenAIProvider(config); // Temporary
      case ProviderType.deepseek:
        return DeepSeekProvider(config); // UnimplementedError
      case ProviderType.claude:
        return ClaudeProvider(config); // UnimplementedError
    }
  }
}
```

**After**:
```dart
import 'langchain_provider.dart';

class ProviderFactory {
  static AIProvider createProvider(ProviderConfig config) {
    return LangChainProvider.fromConfig(config);
  }
}
```

**验收标准**:
- 所有 ProviderType 返回 LangChainProvider
- 无 UnimplementedError 路径

**回滚策略**: Revert 到原始 switch 逻辑

---

## 6. Phase 3: Streaming Verification

### Task 3.1: Fake ChatModel

**文件**: `test/helpers/fake_langchain_chat_model.dart`

**签名**:
```dart
import 'package:langchain_core/langchain_core.dart';

/// 用于测试的 Fake ChatModel
class FakeChatModel extends BaseChatModel {
  FakeChatModel({
    required this.invokeOutput,
    required this.streamChunks,
  });

  final String invokeOutput;
  final List<String> streamChunks;

  @override
  Future<ChatResult> invoke(PromptValue input, {ChatModelOptions? options}) async {
    return ChatResult(
      id: 'test',
      output: AIChatMessage(content: invokeOutput),
    );
  }

  @override
  Stream<ChatResult> stream(PromptValue input, {ChatModelOptions? options}) async* {
    for (final chunk in streamChunks) {
      yield ChatResult(
        id: 'test',
        output: AIChatMessage(content: chunk),
      );
    }
  }
}
```

---

### Task 3.2: Provider Tests

**文件**: `test/unit/adapters/langchain_provider_test.dart`

**测试用例**:
```dart
group('LangChainProvider', () {
  test('sendMessage returns full content', () async {
    // 验证完整响应
  });

  test('sendMessageStream yields chunks in order', () async {
    // 验证流式 chunk 顺序
  });

  test('sendMessageStream handles empty chunks gracefully', () async {
    // 验证空 chunk 不中断流
  });

  test('errors are mapped to ApiError', () async {
    // 验证错误转换
  });
});
```

---

### Task 3.3: Factory Tests

**文件**: `test/unit/adapters/langchain_provider_test.dart`

**测试用例**:
```dart
group('ProviderFactory', () {
  test('returns LangChainProvider for OpenAI', () {
    final config = ProviderConfig(type: ProviderType.openai, apiKey: 'test');
    expect(ProviderFactory.createProvider(config), isA<LangChainProvider>());
  });

  test('returns LangChainProvider for Gemini', () {
    final config = ProviderConfig(type: ProviderType.gemini, apiKey: 'test');
    expect(ProviderFactory.createProvider(config), isA<LangChainProvider>());
  });

  test('returns LangChainProvider for Claude', () {
    final config = ProviderConfig(type: ProviderType.claude, apiKey: 'test');
    expect(ProviderFactory.createProvider(config), isA<LangChainProvider>());
  });

  // 所有 ProviderType 枚举值
});
```

---

## 7. Phase 4: Error Standardization

### Task 4.1: Error Handling Integration

**文件**: `lib/adapters/openai_provider.dart`（保留用于回滚比较）

**修改**: 确保原有 OpenAIProvider 也使用 ProviderErrorMapper（如果需要 A/B 测试）

---

## 8. Phase 5: UI Compatibility (Optional)

> 基于 Gemini 分析，以下任务在 Phase 1-4 完成后可选执行

### Task 5.1: Empty Chunk Tolerance

**文件**: `lib/controllers/stream_output_controller.dart`

**检查点**: Line ~67 `_accumulatedContent += chunk`

**验证**: 确保空字符串 chunk 不会导致异常

---

### Task 5.2: Thinking Indicator (Future)

**文件**: `lib/widgets/conversation_view_v2.dart`

**建议**: 在 `_startAssistantResponse` 中添加 "Thinking..." 状态

> 此任务可延后到 Agent/Tool Calling 集成时实现

---

### Task 5.3: Error Message Mapping

**建议创建**: `lib/utils/langchain_error_handler.dart`

**映射表**:
| LangChain Exception | 用户友好消息 |
|---------------------|-------------|
| AuthenticationException | "API Key 无效或已过期" |
| RateLimitException | "请求过于频繁，请稍后重试" |
| OutputParserException | "模型响应解析失败" |
| ToolException | "外部工具调用失败" |

---

## 9. Phase 6: Manual Verification

### Task 6.1: E2E Testing

**步骤**:
1. `flutter test` - 验证所有单元测试通过
2. 运行应用，使用 OpenAI API Key 发送消息
3. 验证流式输出正常显示
4. 切换到 Gemini/Claude 配置验证

**验收标准**:
- 所有测试通过
- 流式文本增量显示
- 无 UI 回归

---

## 10. 文件变更清单

| 操作 | 文件 | Phase |
|------|------|-------|
| 修改 | `pubspec.yaml` | 0 |
| 新建 | `lib/adapters/langchain_message_mapper.dart` | 1 |
| 新建 | `lib/adapters/provider_error_mapper.dart` | 1 |
| 新建 | `lib/adapters/langchain_provider.dart` | 1 |
| 修改 | `lib/adapters/ai_provider.dart` | 2 |
| 新建 | `test/helpers/fake_langchain_chat_model.dart` | 3 |
| 新建 | `test/unit/adapters/langchain_provider_test.dart` | 3 |

**不修改**:
- `lib/services/roleplay/**`
- `lib/widgets/**`
- `lib/controllers/stream_output_controller.dart`
- `lib/adapters/openai_provider.dart` (保留用于回滚)

---

## 11. 回滚策略总览

| Phase | 回滚方法 |
|-------|----------|
| 0 | 移除依赖，恢复 pubspec.lock |
| 1 | 删除 3 个新文件 |
| 2 | Revert ProviderFactory 到原始 switch |
| 3-5 | 删除测试文件 |

**完整回滚**:
```bash
git checkout -- pubspec.yaml pubspec.lock lib/adapters/ai_provider.dart
rm lib/adapters/langchain_*.dart lib/adapters/provider_error_mapper.dart
rm test/helpers/fake_langchain_chat_model.dart test/unit/adapters/langchain_provider_test.dart
flutter pub get
```

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-24 | 初版，基于 Codex + Gemini 多模型分析 |
