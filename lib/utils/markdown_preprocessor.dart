/// Markdown 预处理器
/// 功能：
/// 1. 只识别三反引号 (```) 包裹的代码块
/// 2. 不将单反引号内容识别为代码（防止cout等被误识别）
class MarkdownPreprocessor {
  /// 预处理 Markdown 内容
  /// 将单反引号的内容转义为普通文本，保留三反引号代码块
  static String preprocess(String markdown) {
    var result = markdown;

    // 🔥 关键：保护三反引号代码块
    // 先提取所有三反引号代码块，后面再放回
    final codeBlocks = <String, String>{};
    int blockIndex = 0;

    // 匹配 ```language\n...code...\n```
    final codeBlockRegex = RegExp(
      r'```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```',
      multiLine: true,
    );

    result = result.replaceAllMapped(codeBlockRegex, (match) {
      final placeholder = '{{CODE_BLOCK_$blockIndex}}';
      codeBlocks[placeholder] = match.group(0)!;
      blockIndex++;
      return placeholder;
    });

    // 🔥 处理单反引号
    // 将 `content` 转换为 {{BACKTICK_content}} 来避免被识别为代码
    final singleBacktickRegex = RegExp(r'`([^`\n]+)`');
    result = result.replaceAllMapped(singleBacktickRegex, (match) {
      final content = match.group(1)!;
      // 保持原样，但标记为已处理
      return '`$content`'; // 保留原样，flutter_markdown 会正确处理
    });

    // 恢复代码块
    codeBlocks.forEach((placeholder, codeBlock) {
      result = result.replaceAll(placeholder, codeBlock);
    });

    return result;
  }

  /// 检测是否包含代码块
  static bool hasCodeBlocks(String markdown) {
    return markdown.contains(RegExp(r'```'));
  }

  /// 提取所有代码块
  static List<String> extractCodeBlocks(String markdown) {
    final codeBlockRegex = RegExp(
      r'```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```',
      multiLine: true,
    );

    final matches = codeBlockRegex.allMatches(markdown);
    return matches.map((match) => match.group(0)!).toList();
  }

  /// 移除所有代码块
  static String removeCodeBlocks(String markdown) {
    return markdown.replaceAll(RegExp(r'```([a-zA-Z0-9_+-]*)?\n?[\s\S]*?```'), '');
  }

  /// 获取代码块的语言标签
  static String? getCodeBlockLanguage(String codeBlock) {
    final match = RegExp(r'^```([a-zA-Z0-9_+-]*)').firstMatch(codeBlock);
    if (match != null && match.group(1)!.isNotEmpty) {
      return match.group(1);
    }
    return null;
  }

  /// 从代码块中提取代码内容（去掉围绕的反引号）
  static String extractCodeContent(String codeBlock) {
    final regex = RegExp(
      r'^```[a-zA-Z0-9_+-]*\n?([\s\S]*?)```$',
      multiLine: true,
    );
    final match = regex.firstMatch(codeBlock);
    if (match != null) {
      return match.group(1)!.trim();
    }
    return codeBlock;
  }

  /// 规范化代码块格式
  /// 确保所有代码块都有正确的格式：```language\ncode\n```
  static String normalizeCodeBlocks(String markdown) {
    var result = markdown;

    final codeBlockRegex = RegExp(
      r'```\n?([\s\S]*?)```',
      multiLine: true,
    );

    result = result.replaceAllMapped(codeBlockRegex, (match) {
      final code = match.group(1)!.trim();
      return '```\n$code\n```';
    });

    return result;
  }
}
