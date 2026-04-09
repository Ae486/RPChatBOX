import 'dart:async';
import 'dart:convert';

/// SSE 事件基类
sealed class SseEvent {}

/// 数据事件 - 包含解析后的 JSON 数据
class SseDataEvent extends SseEvent {
  final Map<String, dynamic> data;
  SseDataEvent(this.data);
}

/// 完成事件 - 流结束标记 [DONE]
class SseDoneEvent extends SseEvent {}

/// 错误事件 - 上游返回的错误响应
class SseErrorEvent extends SseEvent {
  final String type;
  final String message;
  final String? code;
  SseErrorEvent({required this.type, required this.message, this.code});
}

/// SSE 流解析器
/// 将原始字节流转换为结构化的 SseEvent 流
class SseParser {
  const SseParser._();

  /// 解析 SSE 字节流
  /// [byteStream] - 原始 HTTP 响应流
  /// Returns: SseEvent 流 (SseDataEvent | SseDoneEvent | SseErrorEvent)
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

  /// 解析单行 SSE 数据
  /// [line] - 单行 SSE 文本 (e.g., "data: {...}")
  /// Returns: SseEvent 或 null (跳过无效行)
  static SseEvent? parseLine(String line) {
    // 提取 data: 前缀后的内容
    final data = line.startsWith('data: ') ? line.substring(6) : null;
    if (data == null) return null;

    // 检测结束标记
    if (data == '[DONE]') return SseDoneEvent();

    // 解析 JSON
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
      // JSON 解析失败，跳过该行
      return null;
    }
  }
}
