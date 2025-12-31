part of '../flyer_chat_demo_page.dart';

// 注意: _inferCodeLanguage 和 _looksLikeUnifiedDiff 已迁移到
// lib/rendering/markdown_stream/language_utils.dart
// 使用: inferCodeLanguage() 和 looksLikeUnifiedDiff() 替代

class _MarkdownCodeWrapper extends StatelessWidget {
  final Widget child;
  final String code;
  final String language;
  final bool isDark;

  const _MarkdownCodeWrapper({
    required this.child,
    required this.code,
    required this.language,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final inferred = inferCodeLanguage(declaredLanguage: language, code: code);
    if (inferred == 'mermaid') {
      return _EnhancedMermaidBlock(
        mermaidCode: code,
        isDark: isDark,
        isStreaming: false,
      );
    }
    return _EnhancedCodeBlock(
      code: code,
      language: inferred,
      isDark: isDark,
    );
  }
}

class _StreamingMarkdownBody extends StatefulWidget {
  final String text;
  final ({String stable, String tail}) Function(String source) splitStableMarkdown;
  final Widget Function(String markdownText) markdown;
  final TextStyle plainTextStyle;
  final Widget Function({required String language, required String code, required bool isClosed})? streamingCodeBlock;
  final Object? stableCacheKey;

  /// 是否启用增量淡入动画（实验性功能）
  final bool enableFadeIn;

  const _StreamingMarkdownBody({
    required this.text,
    required this.splitStableMarkdown,
    required this.markdown,
    required this.plainTextStyle,
    this.streamingCodeBlock,
    this.stableCacheKey,
    this.enableFadeIn = false,
  });

  @override
  State<_StreamingMarkdownBody> createState() => _StreamingMarkdownBodyState();

  static ({String language, String code, String rest, bool isClosed})? _extractLeadingFence(String input) {
    final match = RegExp(r'^\s*(```|~~~)([^\n\r]*)\r?\n?').firstMatch(input);
    if (match == null) return null;

    final marker = match.group(1)!;
    final lang = (match.group(2) ?? '').trim();
    final after = input.substring(match.end);

    final close = RegExp('(^|\\r?\\n)${RegExp.escape(marker)}', multiLine: true).firstMatch(after);
    if (close == null) {
      return (language: lang, code: after, rest: '', isClosed: false);
    }

    final code = after.substring(0, close.start);
    final rest = after.substring(close.end);
    return (language: lang, code: code, rest: rest, isClosed: true);
  }

}

class _StreamingMarkdownBodyState extends State<_StreamingMarkdownBody>
    with SingleTickerProviderStateMixin {
  late ({String stable, String tail}) _parts;

  String _cachedStable = '';
  Widget? _cachedStableWidget;
  Object? _cachedStableKey;

  // 增量淡入动画状态
  int _lastTailLength = 0;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  void _recomputeParts() {
    _parts = widget.splitStableMarkdown(widget.text);
  }

  void _ensureStableCache() {
    final stableKey = widget.stableCacheKey;
    if (_cachedStableKey != stableKey) {
      _cachedStableKey = stableKey;
      _cachedStable = '';
      _cachedStableWidget = null;
    }

    if (_parts.stable != _cachedStable) {
      _cachedStable = _parts.stable;
      _cachedStableWidget = _cachedStable.isEmpty ? null : RepaintBoundary(child: widget.markdown(_cachedStable));
    }
  }

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 150),
    );
    _fadeAnimation = Tween<double>(begin: 0.3, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOut),
    );
    _fadeController.value = 1.0; // 初始完全可见
    _recomputeParts();
    _ensureStableCache();
    _lastTailLength = _parts.tail.length;
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant _StreamingMarkdownBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.text != oldWidget.text || widget.splitStableMarkdown != oldWidget.splitStableMarkdown) {
      _recomputeParts();

      // 增量淡入：检测 tail 是否有新增内容
      if (widget.enableFadeIn) {
        final newTailLen = _parts.tail.length;
        if (newTailLen > _lastTailLength && _parts.tail.isNotEmpty) {
          // 触发淡入动画：从 0.3 淡入到 1.0
          _fadeController.forward(from: 0.0);
        }
        _lastTailLength = newTailLen;
      }
    }
    _ensureStableCache();
  }

  /// 包装 tail 文本，支持淡入动画
  Widget _buildTailText(String text) {
    final textWidget = Text(text, style: widget.plainTextStyle);

    if (!widget.enableFadeIn) {
      return textWidget;
    }

    return FadeTransition(
      opacity: _fadeAnimation,
      child: textWidget,
    );
  }

  @override
  Widget build(BuildContext context) {
    final parts = _parts;

    final fence = widget.streamingCodeBlock == null ? null : _StreamingMarkdownBody._extractLeadingFence(parts.tail);

    if (parts.stable.isEmpty) {
      if (fence != null) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            widget.streamingCodeBlock!(
              language: inferCodeLanguage(declaredLanguage: fence.language, code: fence.code),
              code: fence.code,
              isClosed: fence.isClosed,
            ),
            if (fence.rest.isNotEmpty) _buildTailText(fence.rest),
          ],
        );
      }

      return _buildTailText(parts.tail);
    }

    if (parts.tail.isEmpty) {
      return _cachedStableWidget ?? widget.markdown(parts.stable);
    }

    if (fence != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _cachedStableWidget ?? widget.markdown(parts.stable),
          widget.streamingCodeBlock!(
            language: inferCodeLanguage(declaredLanguage: fence.language, code: fence.code),
            code: fence.code,
            isClosed: fence.isClosed,
          ),
          if (fence.rest.isNotEmpty) _buildTailText(fence.rest),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        _cachedStableWidget ?? widget.markdown(parts.stable),
        _buildTailText(parts.tail),
      ],
    );
  }
}
