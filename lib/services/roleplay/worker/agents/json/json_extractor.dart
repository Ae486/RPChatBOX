/// JSON 提取器（S0 阶段）
///
/// 从 LLM 原始输出中提取 JSON 块
/// POS: Services / Roleplay / Worker / Agents / JSON
library;

/// JSON 提取器
class JsonExtractor {
  /// 从文本中提取 JSON 块
  ///
  /// 策略：
  /// 1. 优先查找 fenced code block (```json ... ```)
  /// 2. 回退到平衡括号扫描
  String? extract(String text) {
    // 策略 1: fenced code block
    final fenced = _extractFromFencedBlock(text);
    if (fenced != null) return fenced;

    // 策略 2: 平衡括号扫描
    return _extractByBraceBalance(text);
  }

  /// 从 markdown 代码块中提取
  String? _extractFromFencedBlock(String text) {
    // 匹配 ```json ... ``` 或 ``` ... ```
    final patterns = [
      RegExp(r'```json\s*([\s\S]*?)```', multiLine: true),
      RegExp(r'```\s*([\s\S]*?)```', multiLine: true),
    ];

    for (final pattern in patterns) {
      final match = pattern.firstMatch(text);
      if (match != null) {
        final content = match.group(1)?.trim();
        if (content != null && _looksLikeJson(content)) {
          return content;
        }
      }
    }

    return null;
  }

  /// 通过括号平衡提取
  String? _extractByBraceBalance(String text) {
    int depth = 0;
    int start = -1;

    for (int i = 0; i < text.length; i++) {
      final ch = text[i];

      if (ch == '{') {
        if (depth == 0) start = i;
        depth++;
      } else if (ch == '}') {
        depth--;
        if (depth == 0 && start != -1) {
          final extracted = text.substring(start, i + 1).trim();
          if (_looksLikeJson(extracted)) {
            return extracted;
          }
        }
      }
    }

    // 尝试数组
    depth = 0;
    start = -1;
    for (int i = 0; i < text.length; i++) {
      final ch = text[i];

      if (ch == '[') {
        if (depth == 0) start = i;
        depth++;
      } else if (ch == ']') {
        depth--;
        if (depth == 0 && start != -1) {
          final extracted = text.substring(start, i + 1).trim();
          if (_looksLikeJson(extracted)) {
            return extracted;
          }
        }
      }
    }

    return null;
  }

  /// 简单检查是否像 JSON
  bool _looksLikeJson(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return false;

    // 必须以 { 或 [ 开头
    final firstChar = trimmed[0];
    if (firstChar != '{' && firstChar != '[') return false;

    // 必须以 } 或 ] 结尾
    final lastChar = trimmed[trimmed.length - 1];
    if (lastChar != '}' && lastChar != ']') return false;

    return true;
  }
}
