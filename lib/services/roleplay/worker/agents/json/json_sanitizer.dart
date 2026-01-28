/// JSON 清理器（S1 阶段）
///
/// 确定性清理 JSON 语法问题
/// POS: Services / Roleplay / Worker / Agents / JSON
library;

/// JSON 清理器
class JsonSanitizer {
  /// 清理 JSON 字符串
  ///
  /// 处理常见的 LLM 输出问题：
  /// - BOM 和零宽字符
  /// - 智能引号 → ASCII 引号
  /// - 尾随逗号
  /// - 单引号 → 双引号
  /// - Python 布尔值 (True/False/None)
  /// - 未引用的键
  String sanitize(String input) {
    var result = input;

    // 移除 BOM 和零宽字符
    result = _removeBomAndZeroWidth(result);

    // 智能引号 → ASCII 引号
    result = _fixSmartQuotes(result);

    // 移除尾随逗号
    result = _removeTrailingCommas(result);

    // 单引号 → 双引号（小心处理）
    result = _fixSingleQuotes(result);

    // Python 布尔值
    result = _fixPythonBooleans(result);

    // 未引用的键
    result = _fixUnquotedKeys(result);

    return result;
  }

  /// 移除 BOM 和零宽字符
  String _removeBomAndZeroWidth(String s) {
    return s.replaceAll(RegExp(r'[\uFEFF\u200B\u200C\u200D\u2060]'), '');
  }

  /// 修复智能引号
  String _fixSmartQuotes(String s) {
    return s
        .replaceAll('"', '"')
        .replaceAll('"', '"')
        .replaceAll(''', "'")
        .replaceAll(''', "'")
        .replaceAll('「', '"')
        .replaceAll('」', '"')
        .replaceAll('『', '"')
        .replaceAll('』', '"');
  }

  /// 移除尾随逗号
  String _removeTrailingCommas(String s) {
    // 匹配 ,] 或 ,}（允许中间有空白）
    return s.replaceAllMapped(
      RegExp(r',(\s*[}\]])'),
      (m) => m.group(1)!,
    );
  }

  /// 修复单引号（转换为双引号）
  String _fixSingleQuotes(String s) {
    // 只处理键和简单字符串值中的单引号
    // 避免破坏字符串内容中的撇号

    // 处理键: 'key': → "key":
    var result = s.replaceAllMapped(
      RegExp(r"(?<=[{\[,]\s*)'([^']+)'(?=\s*:)"),
      (m) => '"${m.group(1)}"',
    );

    // 处理值: : 'value' → : "value"
    result = result.replaceAllMapped(
      RegExp(r"(?<=:\s*)'([^']*)'(?=\s*[,}\]])"),
      (m) => '"${m.group(1)}"',
    );

    return result;
  }

  /// 修复 Python 风格布尔值
  String _fixPythonBooleans(String s) {
    // 使用 word boundary 避免误替换
    return s
        .replaceAllMapped(
          RegExp(r'\bTrue\b'),
          (_) => 'true',
        )
        .replaceAllMapped(
          RegExp(r'\bFalse\b'),
          (_) => 'false',
        )
        .replaceAllMapped(
          RegExp(r'\bNone\b'),
          (_) => 'null',
        );
  }

  /// 修复未引用的键
  String _fixUnquotedKeys(String s) {
    // 匹配 { key: 或 , key: 格式（key 未加引号）
    return s.replaceAllMapped(
      RegExp(r'([{\[,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)'),
      (m) => '${m.group(1)}"${m.group(2)}"${m.group(3)}',
    );
  }
}
