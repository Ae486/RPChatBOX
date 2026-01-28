/// JSON LLM 修复回退（S4 阶段）
///
/// 当确定性修复失败时，使用 LLM 进行 JSON 修复
/// POS: Services / Roleplay / Worker / Agents / JSON
library;

import 'dart:async';

/// LLM 调用回调类型
typedef LlmRepairCallCallback = Future<String> Function({
  required String systemPrompt,
  required String userPrompt,
  required String modelId,
  int? maxTokens,
  double? temperature,
});

/// JSON LLM 修复配置
class JsonLlmFallbackConfig {
  /// 最大重试次数
  final int maxAttempts;

  /// 重试间隔（毫秒）
  final int retryDelayMs;

  /// 修复超时（毫秒）
  final int timeoutMs;

  /// 最大输出 token
  final int maxOutputTokens;

  /// 温度
  final double temperature;

  const JsonLlmFallbackConfig({
    this.maxAttempts = 2,
    this.retryDelayMs = 50,
    this.timeoutMs = 30000,
    this.maxOutputTokens = 2000,
    this.temperature = 0.0,
  });
}

/// JSON LLM 修复回退
class JsonLlmFallback {
  final LlmRepairCallCallback _llmCall;
  final JsonLlmFallbackConfig _config;

  JsonLlmFallback({
    required LlmRepairCallCallback llmCall,
    JsonLlmFallbackConfig? config,
  })  : _llmCall = llmCall,
        _config = config ?? const JsonLlmFallbackConfig();

  /// 系统提示词
  static const _systemPrompt = '''
You are a JSON repair tool. Your job is to fix broken JSON.

Rules:
1. Output ONLY valid JSON, no explanation or extra text
2. Preserve as much original content as possible
3. Match the expected schema structure
4. If data is completely unrecoverable, return: {"ok": false, "error": "unrecoverable_json"}
''';

  /// 构建用户提示词
  static String _buildUserPrompt(String brokenJson, String schema) => '''
## Expected Schema
$schema

## Broken JSON
$brokenJson

## Task
Fix the JSON to match the schema. Output only the fixed JSON.
''';

  /// 修复 JSON
  ///
  /// [brokenJson] 损坏的 JSON
  /// [schema] 期望的 Schema
  /// [modelId] 使用的模型 ID
  /// [attempt] 当前尝试次数（从 0 开始）
  Future<JsonLlmFallbackResult> repair({
    required String brokenJson,
    required String schema,
    required String modelId,
    int attempt = 0,
  }) async {
    if (attempt >= _config.maxAttempts) {
      return JsonLlmFallbackResult.exhausted(
        message: 'Max attempts ($attempt) reached',
      );
    }

    try {
      // 添加重试延迟
      if (attempt > 0 && _config.retryDelayMs > 0) {
        await Future.delayed(Duration(milliseconds: _config.retryDelayMs));
      }

      // 调用 LLM
      final result = await _llmCall(
        systemPrompt: _systemPrompt,
        userPrompt: _buildUserPrompt(brokenJson, schema),
        modelId: modelId,
        maxTokens: _config.maxOutputTokens,
        temperature: _config.temperature,
      ).timeout(
        Duration(milliseconds: _config.timeoutMs),
        onTimeout: () => throw TimeoutException('LLM repair timeout'),
      );

      return JsonLlmFallbackResult.success(
        repairedJson: result,
        attempt: attempt,
      );
    } on TimeoutException catch (e) {
      return JsonLlmFallbackResult.failed(
        message: e.message ?? 'Timeout',
        attempt: attempt,
        isRetryable: attempt + 1 < _config.maxAttempts,
      );
    } catch (e) {
      return JsonLlmFallbackResult.failed(
        message: e.toString(),
        attempt: attempt,
        isRetryable: attempt + 1 < _config.maxAttempts,
      );
    }
  }

  /// 带自动重试的修复
  Future<JsonLlmFallbackResult> repairWithRetry({
    required String brokenJson,
    required String schema,
    required String modelId,
  }) async {
    for (int attempt = 0; attempt < _config.maxAttempts; attempt++) {
      final result = await repair(
        brokenJson: brokenJson,
        schema: schema,
        modelId: modelId,
        attempt: attempt,
      );

      if (result.success) {
        return result;
      }

      if (!result.isRetryable) {
        return result;
      }
    }

    return JsonLlmFallbackResult.exhausted(
      message: 'All ${_config.maxAttempts} attempts failed',
    );
  }

  /// 创建适用于 JsonPipeline 的回调
  LlmRepairCallback createPipelineCallback(String modelId) {
    return (brokenJson, schema) async {
      final result = await repairWithRetry(
        brokenJson: brokenJson,
        schema: schema,
        modelId: modelId,
      );
      return result.repairedJson;
    };
  }
}

/// LLM 修复回调类型（用于 JsonPipeline）
typedef LlmRepairCallback = Future<String?> Function(
    String brokenJson, String schema);

/// JSON LLM 修复结果
class JsonLlmFallbackResult {
  /// 是否成功
  final bool success;

  /// 修复后的 JSON
  final String? repairedJson;

  /// 错误消息
  final String? message;

  /// 尝试次数
  final int attempt;

  /// 是否可重试
  final bool isRetryable;

  /// 是否已用尽重试
  final bool exhausted;

  const JsonLlmFallbackResult._({
    required this.success,
    this.repairedJson,
    this.message,
    this.attempt = 0,
    this.isRetryable = false,
    this.exhausted = false,
  });

  factory JsonLlmFallbackResult.success({
    required String repairedJson,
    int attempt = 0,
  }) {
    return JsonLlmFallbackResult._(
      success: true,
      repairedJson: repairedJson,
      attempt: attempt,
    );
  }

  factory JsonLlmFallbackResult.failed({
    required String message,
    int attempt = 0,
    bool isRetryable = false,
  }) {
    return JsonLlmFallbackResult._(
      success: false,
      message: message,
      attempt: attempt,
      isRetryable: isRetryable,
    );
  }

  factory JsonLlmFallbackResult.exhausted({
    required String message,
  }) {
    return JsonLlmFallbackResult._(
      success: false,
      message: message,
      exhausted: true,
    );
  }
}
