/// Gemini 响应解析器
/// 处理 Gemini/OpenRouter 的 candidates 格式响应
class GeminiParser {
  bool _reasoningOpen = false;
  bool _emittedBody = false;

  /// 从 Gemini candidates 格式提取内容
  /// [candidates] - 响应中的 candidates 数组
  /// [isGemini] - 是否为 Gemini 模型 (影响 thinking 处理逻辑)
  /// Returns: 文本片段流，包含自动注入的 <think> 标签
  Iterable<String> extractFromCandidates(
    List<dynamic> candidates, {
    bool isGemini = true,
  }) sync* {
    if (candidates.isEmpty) return;

    final cand0 = candidates[0] as Map<String, dynamic>;
    final content = cand0['content'] as Map<String, dynamic>?;

    if (content != null) {
      final parts = content['parts'] as List?;
      if (parts != null) {
        for (var i = 0; i < parts.length; i++) {
          final part = parts[i];
          if (part is! Map<String, dynamic>) continue;

          final pText = (part['text'] ?? part['content'] ?? '').toString();
          if (pText.isEmpty) continue;

          if (isGemini) {
            // Gemini 模式：第一个 part 视为 thinking，后续为正文
            if (!_emittedBody && i == 0) {
              if (!_reasoningOpen) {
                yield '<think>';
                _reasoningOpen = true;
              }
              yield pText;
            } else {
              if (_reasoningOpen) {
                yield '</think>';
                _reasoningOpen = false;
              }
              _emittedBody = true;
              yield pText;
            }
          } else {
            // OpenRouter 模式：根据 type/role 判断
            final pType = (part['type'] ?? part['role'] ?? '').toString();
            if (_isReasoningType(pType)) {
              if (!_reasoningOpen) {
                yield '<think>';
                _reasoningOpen = true;
              }
              yield pText;
            } else {
              if (_reasoningOpen) {
                yield '</think>';
                _reasoningOpen = false;
              }
              yield pText;
            }
          }
        }
      } else {
        // 无 parts，直接读取 text 字段
        final cText = (content['text'] ?? '').toString();
        if (cText.isNotEmpty) {
          if (_reasoningOpen) {
            yield '</think>';
            _reasoningOpen = false;
          }
          _emittedBody = true;
          yield cText;
        }
      }
    } else {
      // 无 content，直接读取 candidate 的 text 字段
      final cText = (cand0['text'] ?? '').toString();
      if (cText.isNotEmpty) {
        if (_reasoningOpen) {
          yield '</think>';
          _reasoningOpen = false;
        }
        _emittedBody = true;
        yield cText;
      }
    }
  }

  /// 获取关闭标签（流结束时调用）
  String? getClosingTag() => _reasoningOpen ? '</think>' : null;

  /// 重置状态
  void reset() {
    _reasoningOpen = false;
    _emittedBody = false;
  }

  /// 判断类型是否为思考/推理类型
  static bool _isReasoningType(String type) {
    final lower = type.toLowerCase();
    return lower.contains('reason') ||
        lower.contains('think') ||
        lower.contains('thought');
  }
}
