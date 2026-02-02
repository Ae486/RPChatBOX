/// 稳定前缀解析器
/// 
/// 用于流式 Markdown 渲染，将输入文本分割为"稳定部分"和"尾部"。
/// 稳定部分可以安全地渲染为 Markdown，尾部可能包含未闭合的结构。
/// 
/// 参考: markstream-vue 的流式渲染策略
library;

/// 解析结果
typedef StablePrefixResult = ({String stable, String tail});

/// 稳定前缀解析器
/// 
/// 核心算法:
/// 1. 逐行扫描，跟踪围栏代码块、数学块、HTML块、表格等状态
/// 2. 在安全边界（完整闭合的行）处记录 safeEnd
/// 3. 最终返回 [0, safeEnd) 作为稳定部分，[safeEnd, end) 作为尾部
class StablePrefixParser {
  /// 创建解析器实例
  const StablePrefixParser();

  /// 将 Markdown 源文本分割为稳定部分和尾部
  /// 
  /// - [source]: 完整的 Markdown 文本
  /// - 返回: (stable: 可安全渲染的部分, tail: 可能未闭合的尾部)
  StablePrefixResult split(String source) {
    if (source.isEmpty) return (stable: '', tail: '');

    var inFence = false;
    String? fenceMarker;
    var inMathBlock = false;
    var thinkDepth = 0;
    var errorDepth = 0;

    final htmlBlockStack = <String>[];
    var tableMode = 0; // 0 none, 1 maybeHeader, 2 inTable

    var safeEnd = 0;
    var cursor = 0;

    while (cursor < source.length) {
      final lineStart = cursor;
      final nl = source.indexOf('\n', cursor);
      final isLineTerminated = nl != -1;
      final end = nl == -1 ? source.length : nl + 1;
      final line = source.substring(lineStart, end);
      final trimmed = line.trimRight();

      // 检测围栏代码块
      final fenceMatch = RegExp(r'^\s*(```|~~~)').firstMatch(trimmed);
      if (fenceMatch != null) {
        final marker = fenceMatch.group(1)!;
        if (!inFence) {
          inFence = true;
          fenceMarker = marker;
        } else if (fenceMarker == marker) {
          inFence = false;
          fenceMarker = null;
        }
      }

      // 检测数学块
      if (!inFence && trimmed == r'$$') {
        inMathBlock = !inMathBlock;
      }

      // 检测 thinking 标签
      if (!inFence && !inMathBlock) {
        const thinkingTags = [
          (start: '<thinking>', end: '</thinking>'),
          (start: '<think>', end: '</think>'),
          (start: '<thought>', end: '</thought>'),
          (start: '<thoughts>', end: '</thoughts>'),
        ];
        for (final tag in thinkingTags) {
          thinkDepth += _countOccurrences(line, tag.start);
          thinkDepth -= _countOccurrences(line, tag.end);
        }
        if (thinkDepth < 0) thinkDepth = 0;

        // 检测 error 标签
        errorDepth += _countOccurrences(line, '<error');
        errorDepth -= _countOccurrences(line, '</error>');
        if (errorDepth < 0) errorDepth = 0;
      }

      final inThink = thinkDepth > 0;
      final inError = errorDepth > 0;

      // 检测 HTML 块
      var inHtmlBlock = false;
      var hasUnclosedHtml = false;
      if (!inFence && !inMathBlock) {
        hasUnclosedHtml = _hasUnclosedInlineHtmlTagBracket(line);

        final closeName = _leadingHtmlCloseTagName(line);
        if (closeName != null && !_isSpecialContentTag(closeName)) {
          for (var s = htmlBlockStack.length - 1; s >= 0; s--) {
            if (htmlBlockStack[s] == closeName) {
              htmlBlockStack.removeRange(s, htmlBlockStack.length);
              break;
            }
          }
        }

        final openName = _leadingHtmlTagName(line);
        if (openName != null &&
            !_isSpecialContentTag(openName) &&
            !_voidTags.contains(openName) &&
            !_isSelfClosingLeadingTag(line)) {
          htmlBlockStack.add(openName);
        }

        inHtmlBlock = htmlBlockStack.isNotEmpty;
      }

      // 检测表格状态
      if (!inFence && !inMathBlock && !inThink) {
        if (tableMode == 0) {
          if (_isPipeTableRowCandidate(trimmed)) {
            tableMode = 1;
          }
        } else if (tableMode == 1) {
          if (_tableSeparatorRow.hasMatch(trimmed)) {
            tableMode = 2;
            if (nl != -1) {
              safeEnd = end;
            }
          } else {
            tableMode = 0;
          }
        } else if (tableMode == 2) {
          if (trimmed.isEmpty || !_isPipeTableRowCandidate(trimmed)) {
            tableMode = 0;
          } else {
            if (nl != -1) {
              safeEnd = end;
            }
          }
        }
      }

      final isInUnstableBlock = inFence ||
          inMathBlock ||
          inThink ||
          inError ||
          inHtmlBlock ||
          hasUnclosedHtml ||
          tableMode == 1 ||
          (tableMode == 2 && !isLineTerminated);

      if (!isInUnstableBlock && !_isIncompleteListOrQuoteMarker(trimmed)) {
        safeEnd = end;
      }

      cursor = end;
    }

    if (safeEnd <= 0) return (stable: '', tail: source);
    if (safeEnd >= source.length) return (stable: source, tail: '');
    return (stable: source.substring(0, safeEnd), tail: source.substring(safeEnd));
  }

  /// 检测是否有未闭合的围栏代码块
  bool hasUnclosedFence(String source) {
    var inFence = false;
    String? fenceMarker;
    
    for (final line in source.split('\n')) {
      final trimmed = line.trimRight();
      final fenceMatch = RegExp(r'^\s*(```|~~~)').firstMatch(trimmed);
      if (fenceMatch != null) {
        final marker = fenceMatch.group(1)!;
        if (!inFence) {
          inFence = true;
          fenceMarker = marker;
        } else if (fenceMarker == marker) {
          inFence = false;
          fenceMarker = null;
        }
      }
    }
    return inFence;
  }

  /// 检测是否有未闭合的数学块
  bool hasUnclosedMathBlock(String source) {
    var count = 0;
    var index = 0;
    while (true) {
      final found = source.indexOf(r'$$', index);
      if (found == -1) break;
      count++;
      index = found + 2;
    }
    return count.isOdd;
  }

  // ===== 私有辅助方法 =====

  static int _countOccurrences(String haystack, String needle) {
    var count = 0;
    var index = 0;
    while (true) {
      final found = haystack.indexOf(needle, index);
      if (found == -1) return count;
      count++;
      index = found + needle.length;
    }
  }

  static bool _isIncompleteListOrQuoteMarker(String trimmedLine) {
    if (RegExp(r'^\s*[-*+]\s*$').hasMatch(trimmedLine)) return true;
    if (RegExp(r'^\s*\d+[.)]\s*$').hasMatch(trimmedLine)) return true;
    if (RegExp(r'^\s*-\s*\*\s*$').hasMatch(trimmedLine)) return true;
    if (RegExp(r'^\s*>\s*$').hasMatch(trimmedLine)) return true;
    if (RegExp(r'^\s*>\s*[-*+]\s*$').hasMatch(trimmedLine)) return true;
    if (RegExp(r'^\s*>\s*\d+[.)]\s*$').hasMatch(trimmedLine)) return true;
    return false;
  }

  static bool _isPipeTableRowCandidate(String trimmedLine) {
    final stripped = trimmedLine.trim();
    if (!stripped.contains('|')) return false;
    if (stripped == '|' || stripped == '||') return false;
    if (stripped.startsWith('|') || stripped.endsWith('|')) return true;
    final parts = stripped.split('|');
    final nonEmptyCells = parts.where((p) => p.trim().isNotEmpty).length;
    return nonEmptyCells >= 2;
  }

  static final _tableSeparatorRow = RegExp(
    r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$',
  );

  static bool _isAsciiLetter(int codeUnit) {
    return (codeUnit >= 65 && codeUnit <= 90) ||
        (codeUnit >= 97 && codeUnit <= 122);
  }

  static bool _hasUnclosedInlineHtmlTagBracket(String line) {
    var i = 0;
    while (i < line.length) {
      final idx = line.indexOf('<', i);
      if (idx == -1) return false;
      if (idx + 1 >= line.length) return true;

      var j = idx + 1;
      while (j < line.length && line.codeUnitAt(j) == 32) {
        j++;
      }

      if (j >= line.length) return true;
      final first = line.codeUnitAt(j);
      if (!(first == 47 || first == 33 || first == 63 || _isAsciiLetter(first))) {
        i = idx + 1;
        continue;
      }

      final closeIdx = line.indexOf('>', j + 1);
      if (closeIdx == -1) return true;
      i = closeIdx + 1;
    }
    return false;
  }

  static String? _leadingHtmlTagName(String line) {
    final match =
        RegExp(r'^\s*<\s*([A-Za-z][A-Za-z0-9-]*)\b[^>]*>').firstMatch(line);
    return match?.group(1)?.toLowerCase();
  }

  static String? _leadingHtmlCloseTagName(String line) {
    final match =
        RegExp(r'^\s*</\s*([A-Za-z][A-Za-z0-9-]*)\s*>').firstMatch(line);
    return match?.group(1)?.toLowerCase();
  }

  static bool _isSelfClosingLeadingTag(String line) {
    final match =
        RegExp(r'^\s*<\s*[A-Za-z][A-Za-z0-9-]*\b[^>]*>').firstMatch(line);
    if (match == null) return false;
    final text = match.group(0) ?? '';
    return text.contains('/>');
  }

  static const _voidTags = <String>{
    'area',
    'base',
    'br',
    'col',
    'embed',
    'hr',
    'img',
    'input',
    'link',
    'meta',
    'param',
    'source',
    'track',
    'wbr',
  };

  static bool _isSpecialContentTag(String name) {
    return name == 'think' ||
        name == 'thinking' ||
        name == 'thought' ||
        name == 'thoughts' ||
        name == 'error';
  }
}
