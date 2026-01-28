/// 输出截断器
///
/// 处理 LLM 输出过长的情况
/// 支持软限（摘要）和硬限（截断）
/// POS: Services / Roleplay / Worker / Agents / Output
library;

import 'output_summarizer.dart';

/// 输出截断常量
const int kSoftCharLimit = 30000;
const int kHardCharLimit = 50000;

/// 截断结果
class TruncationResult {
  /// 处理后的文本
  final String text;

  /// 是否被截断/摘要
  final bool wasTruncated;

  /// 处理方法
  final String? method;

  /// 原始长度
  final int? originalLength;

  /// 处理后长度
  final int? processedLength;

  TruncationResult({
    required this.text,
    required this.wasTruncated,
    this.method,
    this.originalLength,
    this.processedLength,
  });
}

/// 输出截断器
class OutputTruncator {
  final int softLimit;
  final int hardLimit;
  final OutputSummarizer? _summarizer;

  OutputTruncator({
    this.softLimit = kSoftCharLimit,
    this.hardLimit = kHardCharLimit,
    OutputSummarizer? summarizer,
  }) : _summarizer = summarizer;

  /// 处理输出
  ///
  /// 策略：
  /// 1. 小于软限 → 直接返回
  /// 2. 软限 < 长度 <= 硬限 → 尝试摘要
  /// 3. 超过硬限 → 强制截断
  Future<TruncationResult> process(String text, String modelId) async {
    final originalLength = text.length;

    // 小于软限 → 直接返回
    if (originalLength <= softLimit) {
      return TruncationResult(
        text: text,
        wasTruncated: false,
        originalLength: originalLength,
        processedLength: originalLength,
      );
    }

    // 软限 < 长度 <= 硬限 → 尝试摘要
    if (originalLength <= hardLimit && _summarizer != null) {
      final summaryResult = await _summarizer.summarize(text, modelId);
      if (summaryResult.success && summaryResult.wasSummarized) {
        return TruncationResult(
          text: summaryResult.content,
          wasTruncated: true,
          method: 'summarized',
          originalLength: originalLength,
          processedLength: summaryResult.content.length,
        );
      }
      // 摘要失败，检查是否需要强制截断
      if (originalLength <= hardLimit) {
        // 未超硬限，返回原文但标记
        return TruncationResult(
          text: text,
          wasTruncated: false,
          method: 'summarize_failed_within_hard_limit',
          originalLength: originalLength,
          processedLength: originalLength,
        );
      }
    }

    // 超过硬限 或 无摘要器且超过软限 → 强制截断
    if (originalLength > hardLimit) {
      final truncated = _smartTruncate(text, hardLimit);
      return TruncationResult(
        text: truncated,
        wasTruncated: true,
        method: 'hard_truncate',
        originalLength: originalLength,
        processedLength: truncated.length,
      );
    }

    // 软限 < 长度 <= 硬限 且无摘要器
    return TruncationResult(
      text: text,
      wasTruncated: false,
      method: 'within_limits_no_summarizer',
      originalLength: originalLength,
      processedLength: originalLength,
    );
  }

  /// 智能截断（尝试在 JSON 边界截断）
  String _smartTruncate(String text, int limit) {
    if (text.length <= limit) return text;

    // 尝试找到最后一个完整的 JSON 对象
    var cutPoint = limit;

    // 向前查找 } 或 ]（最多回退 1000 字符）
    for (var i = limit - 1; i > limit - 1000 && i > 0; i--) {
      final ch = text[i];
      if (ch == '}' || ch == ']') {
        cutPoint = i + 1;
        break;
      }
    }

    return '${text.substring(0, cutPoint)}\n...[TRUNCATED]';
  }
}
