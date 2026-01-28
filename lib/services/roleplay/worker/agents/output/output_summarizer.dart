/// 输出摘要器
///
/// 当输出超过软限但未达硬限时，使用 LLM 进行摘要
/// POS: Services / Roleplay / Worker / Agents / Output
library;

import 'dart:async';

/// LLM 调用回调类型
typedef SummarizerLlmCallback = Future<String> Function({
  required String systemPrompt,
  required String userPrompt,
  required String modelId,
  int? maxTokens,
  double? temperature,
});

/// 摘要器配置
class OutputSummarizerConfig {
  /// 目标长度（字符）
  final int targetLength;

  /// 最大输出 token
  final int maxOutputTokens;

  /// 温度
  final double temperature;

  /// 超时（毫秒）
  final int timeoutMs;

  const OutputSummarizerConfig({
    this.targetLength = 25000,
    this.maxOutputTokens = 4000,
    this.temperature = 0.3,
    this.timeoutMs = 45000,
  });
}

/// 输出摘要器
class OutputSummarizer {
  final SummarizerLlmCallback _llmCall;
  final OutputSummarizerConfig _config;

  OutputSummarizer({
    required SummarizerLlmCallback llmCall,
    OutputSummarizerConfig? config,
  })  : _llmCall = llmCall,
        _config = config ?? const OutputSummarizerConfig();

  /// 系统提示词
  static const _systemPrompt = '''
You are a JSON output summarizer for an AI agent system.

Your job:
1. Preserve the JSON structure exactly
2. Keep all key facts and decisions
3. Remove verbose details, repetitive content, and filler text
4. Maintain data integrity - don't change values, just condense descriptions
5. Output ONLY valid JSON, no explanation

Priority order for preservation:
1. Proposal kinds, domains, and targets
2. Key evidence and reasons
3. Numerical values and IDs
4. Detailed descriptions (can be shortened)
''';

  /// 构建用户提示词
  static String _buildUserPrompt(String content, int targetLength) => '''
## Raw Output (too long)
$content

## Task
Summarize this JSON output to approximately $targetLength characters while preserving:
- All proposal structures
- Key facts and decisions
- Evidence references

Output only the summarized JSON.
''';

  /// 摘要输出
  ///
  /// [content] 原始内容
  /// [modelId] 使用的模型 ID
  Future<SummarizerResult> summarize(String content, String modelId) async {
    if (content.length <= _config.targetLength) {
      return SummarizerResult.unchanged(content);
    }

    try {
      final result = await _llmCall(
        systemPrompt: _systemPrompt,
        userPrompt: _buildUserPrompt(content, _config.targetLength),
        modelId: modelId,
        maxTokens: _config.maxOutputTokens,
        temperature: _config.temperature,
      ).timeout(
        Duration(milliseconds: _config.timeoutMs),
        onTimeout: () => throw TimeoutException('Summarizer timeout'),
      );

      // 验证摘要长度
      if (result.length > _config.targetLength * 1.2) {
        // 允许 20% 超出
        return SummarizerResult.failed(
          message: 'Summarized output still too long: ${result.length}',
          originalContent: content,
        );
      }

      return SummarizerResult.success(
        summarizedContent: result,
        originalLength: content.length,
        summarizedLength: result.length,
      );
    } on TimeoutException catch (e) {
      return SummarizerResult.failed(
        message: e.message ?? 'Timeout',
        originalContent: content,
      );
    } catch (e) {
      return SummarizerResult.failed(
        message: e.toString(),
        originalContent: content,
      );
    }
  }
}

/// 摘要结果
class SummarizerResult {
  /// 是否成功
  final bool success;

  /// 摘要后的内容（成功时）或原始内容（失败时）
  final String content;

  /// 是否进行了摘要
  final bool wasSummarized;

  /// 原始长度
  final int? originalLength;

  /// 摘要后长度
  final int? summarizedLength;

  /// 错误消息
  final String? errorMessage;

  const SummarizerResult._({
    required this.success,
    required this.content,
    required this.wasSummarized,
    this.originalLength,
    this.summarizedLength,
    this.errorMessage,
  });

  factory SummarizerResult.success({
    required String summarizedContent,
    required int originalLength,
    required int summarizedLength,
  }) {
    return SummarizerResult._(
      success: true,
      content: summarizedContent,
      wasSummarized: true,
      originalLength: originalLength,
      summarizedLength: summarizedLength,
    );
  }

  factory SummarizerResult.unchanged(String content) {
    return SummarizerResult._(
      success: true,
      content: content,
      wasSummarized: false,
    );
  }

  factory SummarizerResult.failed({
    required String message,
    required String originalContent,
  }) {
    return SummarizerResult._(
      success: false,
      content: originalContent,
      wasSummarized: false,
      errorMessage: message,
    );
  }

  /// 压缩率（如果进行了摘要）
  double? get compressionRatio {
    if (!wasSummarized ||
        originalLength == null ||
        summarizedLength == null ||
        originalLength == 0) {
      return null;
    }
    return 1.0 - (summarizedLength! / originalLength!);
  }
}
