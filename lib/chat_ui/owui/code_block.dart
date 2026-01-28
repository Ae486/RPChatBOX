/// INPUT: 代码文本 + 语言 + 主题/缩放 +（可选）流式状态
/// OUTPUT: OwuiCodeBlock - 高亮/复制/折叠/自动滚动的代码块 Widget
/// POS: UI 层 / Markdown / Owui - 代码块渲染（供 OwuiMarkdown 使用）

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/vs2015.dart';
import 'package:highlight/highlight.dart' show highlight, Node, Result;

import 'owui_icons.dart';
import 'owui_tokens_ext.dart';

/// OpenWebUI-inspired enhanced code block.
///
/// Ported from Demo: `lib/pages/flyer_chat_demo/enhanced_code_block.dart`.
class OwuiCodeBlock extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;
  final bool isStreaming;
  final bool showHeader;

  /// When enabled, applies smooth streaming behaviors.
  ///
  /// MUST default to false so existing behavior is unaffected.
  final bool enableSmoothStreaming;

  const OwuiCodeBlock({
    super.key,
    required this.code,
    required this.language,
    required this.isDark,
    this.isStreaming = false,
    this.showHeader = true,
    this.enableSmoothStreaming = false,
  });

  @override
  State<OwuiCodeBlock> createState() => _OwuiCodeBlockState();
}

class _OwuiCodeBlockState extends State<OwuiCodeBlock> {
  bool _isCollapsed = false;
  final ScrollController _scrollController = ScrollController();

  bool _autoScrollEnabled = true;
  double _lastScrollOffset = 0;

  List<String> _cachedLines = const [];
  String _cachedCode = '';
  String _cachedLanguage = '';
  bool _cachedIsDark = false;

  // P0-3 Phase C: 视觉行号缓存
  List<String> _cachedVisualLineNumbers = const [];
  double _cachedLayoutWidth = 0;
  int _cachedCodeHash = 0;

  // P0-3 Phase D: 高亮节流
  static const int _highlightThrottleMs = 400;
  static const int _highlightMaxCodeLength = 8000;
  DateTime _lastHighlightTime = DateTime.fromMillisecondsSinceEpoch(0);
  TextSpan? _cachedHighlightedSpan;
  String _cachedHighlightCode = '';
  bool _cachedHighlightIsDark = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleInternalScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_handleInternalScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _handleInternalScroll() {
    if (!_scrollController.hasClients) return;
    final offset = _scrollController.offset;
    final scrolledUp = offset < _lastScrollOffset;
    _lastScrollOffset = offset;

    const threshold = 60.0;
    final extentAfter = _scrollController.position.maxScrollExtent - offset;
    final isNearBottom = extentAfter <= threshold;

    if (scrolledUp && _autoScrollEnabled) {
      setState(() => _autoScrollEnabled = false);
    } else if (isNearBottom && !_autoScrollEnabled) {
      setState(() => _autoScrollEnabled = true);
    }
  }

  @override
  void didUpdateWidget(covariant OwuiCodeBlock oldWidget) {
    super.didUpdateWidget(oldWidget);


    if (!_isCollapsed && widget.isStreaming && _autoScrollEnabled) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (!_scrollController.hasClients) return;
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 100),
          curve: Curves.easeOut,
        );
      });
    }
  }

  List<String> _splitCodeLines(String code) {
    if (code.isEmpty) return const [''];
    return code.split('\n');
  }

  /// P0-3 Phase C: 使用 TextPainter 计算每个原始行在给定宽度下的视觉行数，
  /// 生成对应的行号列表（第一视觉行显示数字，其余显示空占位）。
  List<String> _computeVisualLineNumbers({
    required List<String> originalLines,
    required double availableWidth,
    required TextStyle textStyle,
  }) {
    final codeHash = widget.code.hashCode;

    // 缓存命中检查
    if (_cachedCodeHash == codeHash &&
        (_cachedLayoutWidth - availableWidth).abs() < 1.0 &&
        _cachedVisualLineNumbers.isNotEmpty) {
      return _cachedVisualLineNumbers;
    }

    final visualLineNumbers = <String>[];
    // 预留 horizontal padding (12 * 2 = 24)
    final layoutWidth = availableWidth - 24;
    if (layoutWidth <= 0) {
      // 宽度不足时回退到原始行号
      for (var i = 0; i < originalLines.length; i++) {
        visualLineNumbers.add('${i + 1}');
      }
      return visualLineNumbers;
    }

    for (var i = 0; i < originalLines.length; i++) {
      final line = originalLines[i];
      final lineNumber = '${i + 1}';

      if (line.isEmpty) {
        // 空行只占一个视觉行
        visualLineNumbers.add(lineNumber);
        continue;
      }

      final painter = TextPainter(
        text: TextSpan(text: line, style: textStyle),
        textDirection: TextDirection.ltr,
        maxLines: null,
      )..layout(maxWidth: layoutWidth);

      final lineMetrics = painter.computeLineMetrics();
      final visualLineCount = lineMetrics.isEmpty ? 1 : lineMetrics.length;

      // 第一视觉行显示行号，其余显示空占位
      visualLineNumbers.add(lineNumber);
      for (var j = 1; j < visualLineCount; j++) {
        visualLineNumbers.add('');
      }

      painter.dispose();
    }

    // 更新缓存
    _cachedCodeHash = codeHash;
    _cachedLayoutWidth = availableWidth;
    _cachedVisualLineNumbers = visualLineNumbers;

    return visualLineNumbers;
  }

  /// P0-3 Phase D: 高亮节流 - 判断是否应该执行高亮
  bool _shouldHighlight() {
    // 流式阶段：节流 + 长度限制
    if (widget.isStreaming) {
      if (widget.code.length > _highlightMaxCodeLength) {
        return false;
      }
      final now = DateTime.now();
      final elapsed = now.difference(_lastHighlightTime).inMilliseconds;
      return elapsed >= _highlightThrottleMs;
    }
    // 非流式阶段：总是高亮
    return true;
  }

  /// P0-3 Phase D: 获取节流后的高亮结果
  TextSpan _getThrottledHighlightedSpan(
    String code,
    TextStyle baseStyle,
    Map<String, TextStyle> theme,
  ) {
    // 缓存命中：代码和主题未变化
    if (_cachedHighlightedSpan != null &&
        _cachedHighlightCode == code &&
        _cachedHighlightIsDark == widget.isDark) {
      return _cachedHighlightedSpan!;
    }

    // 判断是否应该执行高亮
    if (!_shouldHighlight()) {
      // 返回缓存或纯文本
      if (_cachedHighlightedSpan != null) {
        return _cachedHighlightedSpan!;
      }
      return TextSpan(text: code, style: baseStyle);
    }

    // 执行高亮
    _lastHighlightTime = DateTime.now();
    final span = _buildHighlightedSpan(code, baseStyle, theme);

    // 更新缓存
    _cachedHighlightedSpan = span;
    _cachedHighlightCode = code;
    _cachedHighlightIsDark = widget.isDark;

    return span;
  }

  Future<void> _copyCode() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(
      const SnackBar(content: Text('已复制'), duration: Duration(milliseconds: 900)),
    );
  }

  Widget _buildIconBtn({
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
    required Color iconColor,
  }) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Icon(icon, size: 16, color: iconColor),
        ),
      ),
    );
  }

  Color _getLanguageColor(String lang) {
    final l = lang.toLowerCase();
    if (l == 'javascript' || l == 'js') return const Color(0xFFF7DF1E);
    if (l == 'typescript' || l == 'ts') return const Color(0xFF3178C6);
    if (l == 'python' || l == 'py') return const Color(0xFF3776AB);
    if (l == 'dart') return const Color(0xFF0175C2);
    if (l == 'java') return const Color(0xFFB07219);
    if (l == 'kotlin') return const Color(0xFFA97BFF);
    if (l == 'swift') return const Color(0xFFFA7343);
    if (l == 'rust') return const Color(0xFFDEA584);
    if (l == 'go') return const Color(0xFF00ADD8);
    if (l == 'cpp' || l == 'c++') return const Color(0xFF00599C);
    if (l == 'c') return const Color(0xFF555555);
    if (l == 'html') return const Color(0xFFE34F26);
    if (l == 'css') return const Color(0xFF1572B6);
    if (l == 'json') return const Color(0xFF292929);
    if (l == 'yaml' || l == 'yml') return const Color(0xFFCB171E);
    if (l == 'markdown' || l == 'md') return const Color(0xFF083FA1);
    if (l == 'shell' || l == 'bash' || l == 'sh') return const Color(0xFF4EAA25);
    if (l == 'sql') return const Color(0xFFCC2927);
    if (l == 'mermaid') return const Color(0xFF9B59B6);
    return const Color(0xFF6B7280);
  }

  String _getLanguageIcon(String lang) {
    final l = lang.toLowerCase();
    if (l == 'javascript' || l == 'js') return 'JS';
    if (l == 'typescript' || l == 'ts') return 'TS';
    if (l == 'python' || l == 'py') return 'PY';
    if (l == 'dart') return 'D';
    if (l == 'java') return 'J';
    if (l == 'kotlin') return 'K';
    if (l == 'swift') return 'S';
    if (l == 'rust') return 'R';
    if (l == 'go') return 'Go';
    if (l == 'cpp' || l == 'c++') return '++';
    if (l == 'c') return 'C';
    if (l == 'html') return '<>';
    if (l == 'css') return '#';
    if (l == 'json') return '{}';
    if (l == 'yaml' || l == 'yml') return 'Y';
    if (l == 'markdown' || l == 'md') return 'M';
    if (l == 'shell' || l == 'bash' || l == 'sh') return r'$';
    if (l == 'sql') return 'Q';
    if (l == 'mermaid') return '◇';
    return '?';
  }

  Map<String, TextStyle> _getNormalizedTheme(TextStyle baseStyle) {
    final baseTheme = widget.isDark ? vs2015Theme : githubTheme;
    final normalized = <String, TextStyle>{};
    baseTheme.forEach((k, v) {
      normalized[k] = TextStyle(
        color: v.color,
        backgroundColor: v.backgroundColor,
        decoration: v.decoration,
        decorationColor: v.decorationColor,
      );
    });
    return normalized;
  }

  TextSpan _buildHighlightedSpan(
    String code,
    TextStyle baseStyle,
    Map<String, TextStyle> theme,
  ) {
    Result result;
    final lang = widget.language.isNotEmpty ? widget.language : 'plaintext';
    try {
      if (lang.isNotEmpty && lang != 'plaintext') {
        result = highlight.parse(code, language: lang);
      } else {
        result = highlight.parse(code, autoDetection: true);
      }
    } catch (_) {
      return TextSpan(text: code, style: baseStyle);
    }

    final spans = <TextSpan>[];
    final nodes = result.nodes;
    if (nodes != null) {
      for (final node in nodes) {
        _processNode(node, spans, theme, baseStyle);
      }
    }

    if (spans.isEmpty) {
      return TextSpan(text: code, style: baseStyle);
    }

    return TextSpan(children: spans, style: baseStyle);
  }

  void _processNode(
    Node node,
    List<TextSpan> spans,
    Map<String, TextStyle> theme,
    TextStyle baseStyle,
  ) {
    if (node.value != null) {
      final className = node.className;
      TextStyle style = baseStyle;
      if (className != null && theme.containsKey(className)) {
        style = baseStyle.merge(theme[className]);
      }
      spans.add(TextSpan(text: node.value, style: style));
    } else if (node.children != null) {
      final className = node.className;
      TextStyle childBaseStyle = baseStyle;
      if (className != null && theme.containsKey(className)) {
        childBaseStyle = baseStyle.merge(theme[className]);
      }
      for (final child in node.children!) {
        _processNode(child, spans, theme, childBaseStyle);
      }
    }
  }

  Widget _buildHeader() {
    final iconColor = widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600;
    final uiScale = context.owui.uiScale;

    return Container(
      padding: EdgeInsets.symmetric(horizontal: 12 * uiScale, vertical: 8 * uiScale),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1A1D23) : const Color(0xFFEEF1F5),
        borderRadius: _isCollapsed
            ? BorderRadius.circular(12 * uiScale)
            : BorderRadius.only(
                topLeft: Radius.circular(12 * uiScale),
                topRight: Radius.circular(12 * uiScale),
              ),
      ),
      child: Row(
        children: [
          Container(
            width: 20 * uiScale,
            height: 20 * uiScale,
            decoration: BoxDecoration(
              color: _getLanguageColor(widget.language),
              borderRadius: BorderRadius.circular(4 * uiScale),
            ),
            child: Center(
              child: Text(
                _getLanguageIcon(widget.language),
                style: TextStyle(
                  fontSize: 10 * uiScale,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          SizedBox(width: 8 * uiScale),
          Text(
            widget.language.isNotEmpty ? widget.language : 'plaintext',
            style: TextStyle(
              fontSize: 13 * uiScale,
              fontWeight: FontWeight.w500,
              color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
            ),
          ),
          if (widget.isStreaming) ...[
            SizedBox(width: 8 * uiScale),
            Text(
              'Streaming…',
              style: TextStyle(
                fontSize: 12 * uiScale,
                color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
              ),
            ),
          ],
          const Spacer(),
          _buildIconBtn(
            icon: _isCollapsed ? OwuiIcons.unfoldMore : OwuiIcons.unfoldLess,
            tooltip: _isCollapsed ? '展开' : '收起',
            onPressed: () => setState(() => _isCollapsed = !_isCollapsed),
            iconColor: iconColor,
          ),
          _buildIconBtn(
            icon: OwuiIcons.copy,
            tooltip: '复制',
            onPressed: _copyCode,
            iconColor: iconColor,
          ),
        ],
      ),
    );
  }

  Widget _buildCodeContentInternal() {
    final uiScale = context.owui.uiScale;

    final textStyle = TextStyle(
      fontFamily: 'monospace',
      fontFamilyFallback: const ['Consolas', 'Menlo', 'Monaco', 'monospace'],
      fontSize: 13 * uiScale,
      height: 1.5,
      color: widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF1F2937),
    );

    final lineNumberStyle = textStyle.copyWith(
      color: widget.isDark ? const Color(0xFF6B7280) : const Color(0xFF9CA3AF),
    );

    final resolvedLanguage = widget.language.isNotEmpty ? widget.language : 'plaintext';
    if (_cachedCode != widget.code ||
        _cachedLanguage != resolvedLanguage ||
        _cachedIsDark != widget.isDark) {
      _cachedCode = widget.code;
      _cachedLanguage = resolvedLanguage;
      _cachedIsDark = widget.isDark;
      _cachedLines = _splitCodeLines(widget.code);
    }

    final lineCount = _cachedLines.length;
    final lineNumberDigits = lineCount.toString().length;
    // 行号宽度：基础 padding + 每位数字宽度（增加系数以确保缩小时不换行）
    // 使用 10.0 而非 8.0，确保即使在 0.85 缩放时也有足够空间
    final lineNumberWidth = (16.0 + lineNumberDigits * 10.0) * uiScale;

    final maxHeight = MediaQuery.sizeOf(context).height * 0.7;
    final constrainedMaxHeight = maxHeight > 500 ? 500.0 : maxHeight;

    final gutterBgColor = widget.isDark ? const Color(0xFF0D0F12) : const Color(0xFFE5E8EC);
    final gutterBorderColor = widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000);
    final codeBgColor = widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA);

    // P0-3: 使用 LayoutBuilder 获取代码区域可用宽度，用于计算视觉行号
    return LayoutBuilder(
      builder: (context, constraints) {
        // 计算代码区域可用宽度（去掉 gutter 宽度）
        final codeAreaWidth = constraints.maxWidth - lineNumberWidth;

        // P0-3 Phase C: 始终使用视觉行号（窗口变窄时行号随换行动态增加）
        final lineNumbers = _computeVisualLineNumbers(
          originalLines: _cachedLines,
          availableWidth: codeAreaWidth,
          textStyle: textStyle,
        );

        // P0-3 Phase D: 根据 enableSmoothStreaming 决定是否使用高亮节流
        Widget codeContent;
        if (widget.isStreaming) {
          if (widget.enableSmoothStreaming) {
            // 流式 + 启用平滑：使用节流高亮
            codeContent = Text.rich(
              _getThrottledHighlightedSpan(
                widget.code,
                textStyle,
                _getNormalizedTheme(textStyle),
              ),
              softWrap: true,
            );
          } else {
            // 流式 + 未启用平滑：纯文本（原有行为）
            codeContent = Text(widget.code, style: textStyle, softWrap: true);
          }
        } else {
          // 非流式：总是高亮
          codeContent = Text.rich(
            _buildHighlightedSpan(
              widget.code,
              textStyle,
              _getNormalizedTheme(textStyle),
            ),
            softWrap: true,
          );
        }

        return Container(
          constraints: BoxConstraints(maxHeight: constrainedMaxHeight),
          decoration: const BoxDecoration(
            borderRadius: BorderRadius.only(
              bottomLeft: Radius.circular(12),
              bottomRight: Radius.circular(12),
            ),
          ),
          child: ScrollConfiguration(
            behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
            child: SingleChildScrollView(
              controller: _scrollController,
              physics: const ClampingScrollPhysics(),
              child: SelectionArea(
                child: Container(
                  color: codeBgColor,
                  padding: EdgeInsets.symmetric(vertical: 8 * uiScale),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SelectionContainer.disabled(
                        child: Container(
                          width: lineNumberWidth,
                          padding: EdgeInsets.symmetric(horizontal: 8 * uiScale),
                          decoration: BoxDecoration(
                            color: gutterBgColor,
                            border: Border(
                              right: BorderSide(color: gutterBorderColor, width: 1),
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: lineNumbers
                                .map(
                                  (lineNum) => Text(
                                    lineNum,
                                    style: lineNumberStyle,
                                    textAlign: TextAlign.right,
                                  ),
                                )
                                .toList(),
                          ),
                        ),
                      ),
                      Expanded(
                        child: Padding(
                          padding: EdgeInsets.symmetric(horizontal: 12 * uiScale),
                          child: codeContent,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final borderRadius = BorderRadius.circular(12);
    final borderColor = widget.isDark ? const Color(0xFF2E3138) : const Color(0xFFD8DCE2);
    final bgColor = widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Material(
        color: bgColor,
        shape: RoundedRectangleBorder(
          borderRadius: borderRadius,
          side: BorderSide(color: borderColor),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
          if (widget.showHeader) _buildHeader(),
          AnimatedCrossFade(
            duration: const Duration(milliseconds: 200),
            sizeCurve: Curves.easeInOut,
            crossFadeState: _isCollapsed ? CrossFadeState.showFirst : CrossFadeState.showSecond,
            firstChild: const SizedBox.shrink(),
            secondChild: _buildCodeContentInternal(),
          ),
        ],
      ),
      ),
    );
  }
}
