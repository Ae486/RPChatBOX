# 零决策可执行任务清单

> 基于 Claude + Codex 多模型分析
> 创建: 2026-02-04
> 总任务数: 23
> 预计总时长: 8-10 小时

---

## 执行顺序依赖图

```
Phase 1 (并行)
├── [1.1] SseParser ─────────┐
├── [1.2] ThinkingExtractor ─┼──→ Phase 2 [2.1-2.5]
└── [1.3] GeminiParser ──────┘           │
                                         ↓
                               Phase 3 [3.1-3.3] (错误处理)
                                         │
                                         ↓
                               Phase 4 [4.1-4.2] (路由)
                                         │
                                         ↓
                               Phase 5 [5.1-5.4] (测试)
```

---

## Phase 1: 模块提取

### 1.1 创建 SseParser

**文件**: `lib/adapters/sse/sse_parser.dart`

**任务**:
```
□ 创建文件和目录结构
□ 定义 SseEvent sealed class 及其子类
□ 实现 SseParser.parse() 方法
□ 实现 SseParser.parseLine() 方法
```

**代码规格**:
```dart
// 文件: lib/adapters/sse/sse_parser.dart
import 'dart:async';
import 'dart:convert';

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

class SseParser {
  const SseParser._();

  static Stream<SseEvent> parse(Stream<List<int>> byteStream) async* {
    // 实现: 从 openai_provider.dart 158-176 行提取
  }

  static SseEvent? parseLine(String line) {
    // 实现: 解析单行，处理 data: 前缀、[DONE]、JSON、error
  }
}
```

---

### 1.2 创建 ThinkingExtractor

**文件**: `lib/adapters/sse/thinking_extractor.dart`

**任务**:
```
□ 创建文件
□ 实现 extract() 方法 (从 delta 提取内容)
□ 实现 getClosingTag() 方法
□ 实现 reset() 方法
□ 实现静态辅助方法 _isReasoningType, _extractText
```

**代码规格**:
```dart
// 文件: lib/adapters/sse/thinking_extractor.dart

class ThinkingExtractor {
  bool _thinkingOpen = false;

  /// 从 SSE delta 提取内容，返回带 <think> 标签的文本流
  /// 来源: openai_provider.dart 184-224 行
  Iterable<String> extract(Map<String, dynamic> delta) sync* {
    // 1. 检查 reasoning 字段
    // 2. 检查 content 字段
    // 3. 管理 <think> 标签状态
  }

  String? getClosingTag() => _thinkingOpen ? '</think>' : null;

  void reset() => _thinkingOpen = false;

  static bool _isReasoningType(String type) {
    final lower = type.toLowerCase();
    return lower.contains('reason') || lower.contains('think') || lower.contains('thought');
  }

  static String? _extractText(dynamic v) {
    // 来源: openai_provider.dart 638-649 行
  }
}
```

---

### 1.3 创建 GeminiParser

**文件**: `lib/adapters/sse/gemini_parser.dart`

**任务**:
```
□ 创建文件
□ 实现 extractFromCandidates() 方法
□ 实现 getClosingTag() 方法
□ 实现 reset() 方法
```

**代码规格**:
```dart
// 文件: lib/adapters/sse/gemini_parser.dart

class GeminiParser {
  bool _reasoningOpen = false;
  bool _emittedBody = false;

  /// 从 Gemini candidates 格式提取内容
  /// 来源: openai_provider.dart 229-276 行
  Iterable<String> extractFromCandidates(List<dynamic> candidates) sync* {
    // 实现 Gemini 特殊格式处理
  }

  String? getClosingTag() => _reasoningOpen ? '</think>' : null;

  void reset() {
    _reasoningOpen = false;
    _emittedBody = false;
  }
}
```

---

### 1.4 SseParser 单元测试

**文件**: `test/unit/adapters/sse/sse_parser_test.dart`

**任务**:
```
□ 测试正常数据行解析
□ 测试 [DONE] 标记
□ 测试错误响应解析
□ 测试空行跳过
□ 测试非 JSON 行跳过
□ 测试完整流解析
```

---

### 1.5 ThinkingExtractor 单元测试

**文件**: `test/unit/adapters/sse/thinking_extractor_test.dart`

**任务**:
```
□ 测试 reasoning_content 字段提取
□ 测试 thinking 字段提取
□ 测试 content 切换时关闭标签
□ 测试 finalize 关闭标签
□ 测试混合 reasoning + content 序列
```

---

## Phase 2: 混合 Provider 实现

### 2.1 创建 HybridLangChainProvider 主体

**文件**: `lib/adapters/hybrid_langchain_provider.dart`

**任务**:
```
□ 创建文件和类结构
□ 添加必要的 import
□ 实现构造函数和字段
```

**代码规格**:
```dart
// 文件: lib/adapters/hybrid_langchain_provider.dart

import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:langchain_core/chat_models.dart' as lc;

import 'ai_provider.dart';
import 'langchain_message_mapper.dart';
import 'sse/sse_parser.dart';
import 'sse/thinking_extractor.dart';
import 'sse/gemini_parser.dart';
import '../models/api_error.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/dio_service.dart';

class HybridLangChainProvider extends AIProvider {
  final _dio = DioService().dio;
  CancelToken? _cancelToken;

  HybridLangChainProvider(super.config);

  // ... 方法实现
}
```

---

### 2.2 实现 sendMessageStream

**任务**:
```
□ 使用 LangChainMessageMapper 转换消息
□ 构建请求体 (_buildRequestBody)
□ 发送 Dio 请求
□ 使用 SseParser 解析流
□ 使用 ThinkingExtractor/GeminiParser 提取内容
□ 处理流结束和关闭标签
```

---

### 2.3 实现 sendMessage (非流式)

**任务**:
```
□ 复用 _buildRequestBody (stream: false)
□ 发送 Dio 请求
□ 解析响应提取 content
□ 错误处理
```

---

### 2.4 实现 cancelRequest

**任务**:
```
□ 取消 CancelToken
□ 添加调试日志
```

---

### 2.5 实现 testConnection 和 listAvailableModels

**任务**:
```
□ 从 OpenAIProvider/LangChainProvider 复制实现
□ 保持接口一致
```

---

## Phase 3: 错误处理完善

### 3.1 SseParser 错误事件处理

**任务**:
```
□ parseLine 中检测 error 对象
□ 返回 SseErrorEvent 包含 type/message/code
```

---

### 3.2 HybridProvider 统一 ApiError

**任务**:
```
□ DioException 处理 → ApiError
□ SseErrorEvent 处理 → ApiError
□ 取消处理 → ApiError (errorCode: 'cancelled')
□ 通用 catch → ApiError (errorCode: 'unknown')
□ 移除所有 Exception('流式请求失败') 模式
```

---

### 3.3 错误处理测试

**任务**:
```
□ 测试 401 错误正确解析
□ 测试 429 错误 isRetryable=true
□ 测试 SSE 内错误正确抛出
□ 测试网络错误处理
□ 测试取消错误
```

---

## Phase 4: 路由切换

### 4.1 修改 ProviderFactory

**文件**: `lib/adapters/ai_provider.dart`

**任务**:
```
□ 添加 import hybrid_langchain_provider.dart
□ 添加 useHybridLangChain 开关
□ 修改 createProvider 方法路由逻辑
```

**代码变更**:
```dart
// 在 ProviderFactory 类中添加
static bool useHybridLangChain = true;  // 新开关

static AIProvider createProvider(ProviderConfig config) {
  if (useHybridLangChain) {
    return HybridLangChainProvider(config);
  }
  if (useLangChain) {
    return LangChainProvider.fromConfig(config);
  }
  // 原有逻辑...
}
```

---

### 4.2 更新导出

**任务**:
```
□ 确保 hybrid_langchain_provider.dart 可被外部访问
□ 更新任何需要的 barrel export
```

---

## Phase 5: 测试验证

### 5.1 创建 SSE Fixture 文件

**目录**: `test/fixtures/sse/`

**任务**:
```
□ 创建 openai_normal.txt
□ 创建 deepseek_r1_reasoning.txt
□ 创建 claude_thinking.txt
□ 创建 gemini_candidates.txt
□ 创建 error_invalid_key.txt
□ 创建 error_rate_limit.txt
```

---

### 5.2 Golden Tests

**文件**: `test/golden/sse_parsing_test.dart`

**任务**:
```
□ 加载 fixture 文件
□ 验证解析结果与预期一致
□ 验证 thinking 标签正确注入
```

---

### 5.3 集成测试

**文件**: `test/integration/hybrid_provider_test.dart`

**任务**:
```
□ Mock Dio 返回 fixture
□ 测试完整流程
□ 测试取消逻辑
□ 测试错误传播
```

---

### 5.4 手动验证

**任务**:
```
□ OpenAI GPT-4 普通对话
□ DeepSeek R1 推理 (验证 thinking bubble)
□ Claude 3.7 extended thinking (验证 thinking bubble)
□ Gemini 2.0 thinking (验证 thinking bubble)
□ 无效 API Key (验证错误提示)
□ 请求取消 (验证立即停止)
```

---

## 回滚检查点

| 阶段 | 回滚方式 |
|------|---------|
| Phase 1 完成后 | 删除新文件即可，无影响 |
| Phase 2 完成后 | 删除新文件即可，无影响 |
| Phase 3 完成后 | 删除新文件即可，无影响 |
| Phase 4 完成后 | `useHybridLangChain = false` |
| Phase 5 完成后 | `useHybridLangChain = false` |

---

## 完成标志

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 手动验证 4 种 provider 类型
- [ ] 手动验证错误处理
- [ ] 代码已提交到 feature 分支
