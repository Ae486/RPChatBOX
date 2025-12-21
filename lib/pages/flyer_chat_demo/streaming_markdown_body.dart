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

  const _StreamingMarkdownBody({
    required this.text,
    required this.splitStableMarkdown,
    required this.markdown,
    required this.plainTextStyle,
    this.streamingCodeBlock,
    this.stableCacheKey,
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

class _StreamingMarkdownBodyState extends State<_StreamingMarkdownBody> {
  late ({String stable, String tail}) _parts;

  String _cachedStable = '';
  Widget? _cachedStableWidget;
  Object? _cachedStableKey;

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
    _recomputeParts();
    _ensureStableCache();
  }

  @override
  void didUpdateWidget(covariant _StreamingMarkdownBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.text != oldWidget.text || widget.splitStableMarkdown != oldWidget.splitStableMarkdown) {
      _recomputeParts();
    }
    _ensureStableCache();
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
            if (fence.rest.isNotEmpty)
              Text(
                fence.rest,
                style: widget.plainTextStyle,
              ),
          ],
        );
      }

      return Text(
        parts.tail,
        style: widget.plainTextStyle,
      );
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
          if (fence.rest.isNotEmpty)
            Text(
              fence.rest,
              style: widget.plainTextStyle,
            ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        _cachedStableWidget ?? widget.markdown(parts.stable),
        Text(
          parts.tail,
          style: widget.plainTextStyle,
        ),
      ],
    );
  }
}
