import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/vs2015.dart';
import 'package:highlight/highlight.dart' show highlight, Node, Result;

/// OpenWebUI-inspired enhanced code block.
///
/// Ported from Demo: `lib/pages/flyer_chat_demo/enhanced_code_block.dart`.
class OwuiCodeBlock extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;
  final bool isStreaming;
  final bool showHeader;

  const OwuiCodeBlock({
    super.key,
    required this.code,
    required this.language,
    required this.isDark,
    this.isStreaming = false,
    this.showHeader = true,
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
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      });
    }
  }

  List<String> _splitCodeLines(String code) {
    if (code.isEmpty) return const [''];
    return code.split('\n');
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

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1A1D23) : const Color(0xFFEEF1F5),
        borderRadius: _isCollapsed
            ? BorderRadius.circular(12)
            : const BorderRadius.only(
                topLeft: Radius.circular(12),
                topRight: Radius.circular(12),
              ),
      ),
      child: Row(
        children: [
          Container(
            width: 20,
            height: 20,
            decoration: BoxDecoration(
              color: _getLanguageColor(widget.language),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Center(
              child: Text(
                _getLanguageIcon(widget.language),
                style: const TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            widget.language.isNotEmpty ? widget.language : 'plaintext',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
            ),
          ),
          if (widget.isStreaming) ...[
            const SizedBox(width: 8),
            Text(
              'Streaming…',
              style: TextStyle(
                fontSize: 12,
                color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
              ),
            ),
          ],
          const Spacer(),
          _buildIconBtn(
            icon: _isCollapsed ? Icons.unfold_more_rounded : Icons.unfold_less_rounded,
            tooltip: _isCollapsed ? '展开' : '收起',
            onPressed: () => setState(() => _isCollapsed = !_isCollapsed),
            iconColor: iconColor,
          ),
          _buildIconBtn(
            icon: Icons.content_copy_rounded,
            tooltip: '复制',
            onPressed: _copyCode,
            iconColor: iconColor,
          ),
        ],
      ),
    );
  }

  Widget _buildCodeContentInternal() {
    final textStyle = TextStyle(
      fontFamily: 'monospace',
      fontFamilyFallback: const ['Consolas', 'Menlo', 'Monaco', 'monospace'],
      fontSize: 13,
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
    final lineNumberWidth = 16.0 + lineNumberDigits * 8.0;

    final maxHeight = MediaQuery.sizeOf(context).height * 0.7;
    final constrainedMaxHeight = maxHeight > 500 ? 500.0 : maxHeight;

    final gutterBgColor = widget.isDark ? const Color(0xFF0D0F12) : const Color(0xFFE5E8EC);
    final gutterBorderColor = widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000);
    final codeBgColor = widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA);

    final lineNumbers = List.generate(lineCount, (i) => '${i + 1}');

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
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SelectionContainer.disabled(
                    child: Container(
                      width: lineNumberWidth,
                      padding: const EdgeInsets.symmetric(horizontal: 8),
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
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: widget.isStreaming
                          ? Text(widget.code, style: textStyle, softWrap: true)
                          : Text.rich(
                              _buildHighlightedSpan(
                                widget.code,
                                textStyle,
                                _getNormalizedTheme(textStyle),
                              ),
                              softWrap: true,
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
        ),
      ),
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
    );
  }
}
