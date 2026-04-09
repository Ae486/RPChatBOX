/// Thinking 内容提取器
/// 从 SSE delta 中提取 reasoning/thinking 内容，自动注入 <think> 标签
class ThinkingExtractor {
  bool _thinkingOpen = false;

  /// 从 SSE delta 提取内容
  /// [delta] - choices[0].delta 对象
  /// Returns: 文本片段流，包含自动注入的 <think> 标签
  Iterable<String> extract(Map<String, dynamic> delta) sync* {
    // 1) 识别 reasoning_content 等思考字段
    for (final key in const [
      'reasoning',
      'reasoning_content',
      'internal_thoughts',
      'thinking'
    ]) {
      final v = delta[key];
      if (v == null) continue;

      final reasoningText = _extractText(v);
      if (reasoningText != null && reasoningText.isNotEmpty) {
        if (!_thinkingOpen) {
          yield '<think>';
          _thinkingOpen = true;
        }
        yield reasoningText;
      }
    }

    // 2) 解析 content
    final contentField = delta['content'];
    if (contentField is String) {
      if (contentField.isNotEmpty) {
        if (_thinkingOpen) {
          yield '</think>';
          _thinkingOpen = false;
        }
        yield contentField;
      }
    } else if (contentField is List) {
      if (_thinkingOpen && contentField.isNotEmpty) {
        yield '</think>';
        _thinkingOpen = false;
      }
      for (final part in contentField) {
        if (part is Map<String, dynamic>) {
          final pText = (part['text'] ?? part['content'] ?? '').toString();
          if (pText.isEmpty) continue;
          if (_isReasoningType((part['type'] ?? part['role'] ?? '').toString())) {
            if (!_thinkingOpen) {
              yield '<think>';
              _thinkingOpen = true;
            }
            yield pText;
          } else {
            if (_thinkingOpen) {
              yield '</think>';
              _thinkingOpen = false;
            }
            yield pText;
          }
        } else if (part is String && part.isNotEmpty) {
          yield part;
        }
      }
    }
  }

  /// 获取关闭标签（流结束时调用）
  /// Returns: '</think>' 如果当前有未关闭的 thinking 块，否则 null
  String? getClosingTag() => _thinkingOpen ? '</think>' : null;

  /// 重置状态（开始新请求前调用）
  void reset() => _thinkingOpen = false;

  /// 判断类型是否为思考/推理类型
  static bool _isReasoningType(String type) {
    final lower = type.toLowerCase();
    return lower.contains('reason') ||
        lower.contains('think') ||
        lower.contains('thought');
  }

  /// 从不同格式中提取文本
  static String? _extractText(dynamic v) {
    if (v is String) return v;
    if (v is Map<String, dynamic>) {
      return (v['content'] ?? v['text']) as String?;
    }
    if (v is List) {
      return v
          .map((e) {
            if (e is String) return e;
            if (e is Map<String, dynamic>) {
              return (e['content'] ?? e['text'] ?? '').toString();
            }
            return '';
          })
          .where((s) => s.isNotEmpty)
          .join('');
    }
    return null;
  }
}
