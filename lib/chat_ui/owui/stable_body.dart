/// INPUT: 流式文本 + stable/tail 分割函数 + Markdown builder +（可选）块级占位渲染
/// OUTPUT: OwuiStableBody - 稳定前缀 Markdown + 尾巴增量渲染容器
/// POS: UI 层 / Markdown / Owui - 流式渲染稳定性（减少重排与抖动）

import 'package:flutter/material.dart';

/// Streaming Markdown body: renders stable prefix as Markdown and tail as plain
/// text (or a streaming block placeholder for code/latex/think blocks).
///
/// Ported from Demo: `lib/pages/flyer_chat_demo/streaming_markdown_body.dart`.
class OwuiStableBody extends StatefulWidget {
  final String text;
  final ({String stable, String tail}) Function(String source) splitStableMarkdown;
  final Widget Function(String markdownText) markdown;
  final TextStyle plainTextStyle;

  /// 是否启用增量淡入动画（实验性功能）。
  ///
  /// 仅对“尾巴纯文本”生效（不会影响稳定前缀 Markdown/代码块占位等）。
  final bool enableFadeIn;

  /// 增量淡入动画时长。
  final Duration fadeInDuration;

  /// 增量淡入动画起始透明度。
  final double fadeInStartOpacity;

  /// 流式代码块渲染回调
  final Widget Function({
    required String language,
    required String code,
    required bool isClosed,
  })? streamingCodeBlock;

  /// 流式 LaTeX 块渲染回调
  final Widget Function({
    required String content,
    required bool isClosed,
  })? streamingLatexBlock;

  /// 流式 Think 块渲染回调
  final Widget Function({
    required String content,
    required bool isClosed,
  })? streamingThinkBlock;

  final Object? stableCacheKey;

  const OwuiStableBody({
    super.key,
    required this.text,
    required this.splitStableMarkdown,
    required this.markdown,
    required this.plainTextStyle,
    this.enableFadeIn = false,
    this.fadeInDuration = const Duration(milliseconds: 150),
    this.fadeInStartOpacity = 0.3,
    this.streamingCodeBlock,
    this.streamingLatexBlock,
    this.streamingThinkBlock,
    this.stableCacheKey,
  });

  @override
  State<OwuiStableBody> createState() => _OwuiStableBodyState();

  /// 提取 tail 开头的代码块
  static ({String language, String code, String rest, bool isClosed})? extractLeadingFence(
    String input,
  ) {
    final match = RegExp(r'^\s*(```|~~~)([^\n\r]*)\r?\n?').firstMatch(input);
    if (match == null) return null;

    final marker = match.group(1)!;
    final lang = (match.group(2) ?? '').trim();
    final after = input.substring(match.end);

    final close = RegExp(
      '(^|\r?\n)${RegExp.escape(marker)}',
      multiLine: true,
    ).firstMatch(after);
    if (close == null) {
      return (language: lang, code: after, rest: '', isClosed: false);
    }

    final code = after.substring(0, close.start);
    final rest = after.substring(close.end);
    return (language: lang, code: code, rest: rest, isClosed: true);
  }

  /// 提取 tail 开头的 LaTeX 块 ($$...$$)
  static ({String content, String rest, bool isClosed})? extractLeadingLatex(
    String input,
  ) {
    final match = RegExp(r'^\s*\$\$').firstMatch(input);
    if (match == null) return null;

    final after = input.substring(match.end);
    final close = after.indexOf(r'$$');
    if (close == -1) {
      return (content: after.trimLeft(), rest: '', isClosed: false);
    }

    final content = after.substring(0, close);
    final rest = after.substring(close + 2);
    return (content: content, rest: rest, isClosed: true);
  }

  /// 提取 tail 开头的 Think 块 (`<think>...</think>` 等)
  static ({String content, String rest, bool isClosed})? extractLeadingThink(
    String input,
  ) {
    const thinkPairs = [
      ('<thinking>', '</thinking>'),
      ('<think>', '</think>'),
      ('<thought>', '</thought>'),
      ('<thoughts>', '</thoughts>'),
    ];

    final trimmed = input.trimLeft();
    for (final (open, close) in thinkPairs) {
      if (!trimmed.startsWith(open)) continue;

      final openEnd = input.indexOf(open) + open.length;
      final after = input.substring(openEnd);
      final closeIdx = after.indexOf(close);
      if (closeIdx == -1) {
        return (content: after, rest: '', isClosed: false);
      }
      return (
        content: after.substring(0, closeIdx),
        rest: after.substring(closeIdx + close.length),
        isClosed: true
      );
    }

    return null;
  }

  /// 统一块级信号检测
  /// 返回: (type, language?, content, rest, isClosed)
  static ({String type, String? language, String content, String rest, bool isClosed})?
  extractLeadingBlock(String input) {
    // 1. 代码块检测（优先级最高）
    final fence = extractLeadingFence(input);
    if (fence != null) {
      return (
        type: 'code',
        language: fence.language,
        content: fence.code,
        rest: fence.rest,
        isClosed: fence.isClosed,
      );
    }

    // 2. LaTeX 块检测
    final latex = extractLeadingLatex(input);
    if (latex != null) {
      return (
        type: 'latex',
        language: null,
        content: latex.content,
        rest: latex.rest,
        isClosed: latex.isClosed,
      );
    }

    // 3. Think 块检测
    final think = extractLeadingThink(input);
    if (think != null) {
      return (
        type: 'think',
        language: null,
        content: think.content,
        rest: think.rest,
        isClosed: think.isClosed,
      );
    }

    return null;
  }

  /// 检测文本中是否包含完整的 Markdown 图片语法
  /// 返回: 图片语法列表和剩余文本
  static ({List<String> images, String rest}) extractImages(String input) {
    final images = <String>[];
    var rest = input;

    // 匹配 Markdown 图片语法: ![alt](url)
    final imageRegex = RegExp(r'!\[[^\]]*\]\([^)]+\)');

    while (true) {
      final match = imageRegex.firstMatch(rest);
      if (match == null) break;

      images.add(match.group(0)!);
      rest = rest.substring(0, match.start) + rest.substring(match.end);
    }

    return (images: images, rest: rest.trim());
  }

  /// 检测 tail 是否需要 Markdown 渲染（包含完整的图片语法）
  static bool tailNeedsMarkdown(String tail) {
    // 检测完整的图片语法: ![alt](url)
    return RegExp(r'!\[[^\]]*\]\([^)]+\)').hasMatch(tail);
  }
}

class _OwuiStableBodyState extends State<OwuiStableBody>
    with SingleTickerProviderStateMixin {
  late ({String stable, String tail}) _parts;

  String _cachedStable = '';
  Widget? _cachedStableWidget;
  Object? _cachedStableKey;

  // 增量淡入动画状态
  int _lastTailTextLength = 0;
  AnimationController? _fadeController;
  Animation<double>? _fadeAnimation;
  double _fadeStartOpacity = 0.3;

  bool get _fadeEnabled {
    final start = widget.fadeInStartOpacity.clamp(0.0, 1.0).toDouble();
    return widget.enableFadeIn &&
        widget.fadeInDuration > Duration.zero &&
        start < 1.0;
  }

  void _recomputeParts() {
    _parts = widget.splitStableMarkdown(widget.text);
  }

  void _ensureFadeAnimation() {
    if (!_fadeEnabled) {
      _fadeController?.dispose();
      _fadeController = null;
      _fadeAnimation = null;
      return;
    }

    final duration = widget.fadeInDuration;
    final startOpacity = widget.fadeInStartOpacity.clamp(0.0, 1.0).toDouble();

    final controller = _fadeController;
    if (controller == null) {
      _fadeController = AnimationController(vsync: this, duration: duration)
        ..value = 1.0; // 初始完全可见
    } else if (controller.duration != duration) {
      controller.duration = duration;
    }

    if (_fadeAnimation == null || _fadeStartOpacity != startOpacity) {
      _fadeStartOpacity = startOpacity;
      _fadeAnimation = Tween<double>(begin: startOpacity, end: 1.0).animate(
        CurvedAnimation(parent: _fadeController!, curve: Curves.easeOut),
      );
    }
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
      _cachedStableWidget =
          _cachedStable.isEmpty ? null : RepaintBoundary(child: widget.markdown(_cachedStable));
    }
  }

  int _computeTailTextLength() {
    final parts = _parts;
    final block = OwuiStableBody.extractLeadingBlock(parts.tail);
    final tailText =
        (block != null && _canRenderBlock(block)) ? block.rest : parts.tail;
    return tailText.length;
  }

  bool _canRenderBlock(
    ({String type, String? language, String content, String rest, bool isClosed}) block,
  ) {
    switch (block.type) {
      case 'code':
        return widget.streamingCodeBlock != null;
      case 'latex':
        return widget.streamingLatexBlock != null;
      case 'think':
        return widget.streamingThinkBlock != null;
      default:
        return false;
    }
  }

  void _maybeTriggerFadeIn() {
    if (!_fadeEnabled) return;
    final controller = _fadeController;
    if (controller == null) return;

    final tailLen = _computeTailTextLength();
    if (tailLen > _lastTailTextLength && tailLen > 0) {
      controller.forward(from: 0.0);
    }
    _lastTailTextLength = tailLen;
  }

  @override
  void initState() {
    super.initState();
    _recomputeParts();
    _ensureFadeAnimation();
    _ensureStableCache();
    _lastTailTextLength = _computeTailTextLength();
  }

  @override
  void dispose() {
    _fadeController?.dispose();
    _fadeController = null;
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant OwuiStableBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.text != oldWidget.text || widget.splitStableMarkdown != oldWidget.splitStableMarkdown) {
      _recomputeParts();
    }

    if (widget.enableFadeIn != oldWidget.enableFadeIn ||
        widget.fadeInDuration != oldWidget.fadeInDuration ||
        widget.fadeInStartOpacity != oldWidget.fadeInStartOpacity) {
      _ensureFadeAnimation();
    }
    _ensureStableCache();

    if (widget.text != oldWidget.text || widget.splitStableMarkdown != oldWidget.splitStableMarkdown) {
      _maybeTriggerFadeIn();
    } else {
      _lastTailTextLength = _computeTailTextLength();
    }
  }

  /// 根据块类型渲染对应的流式容器
  Widget? _buildBlockWidget(
    ({String type, String? language, String content, String rest, bool isClosed}) block,
  ) {
    switch (block.type) {
      case 'code':
        return widget.streamingCodeBlock?.call(
          language: block.language ?? '',
          code: block.content,
          isClosed: block.isClosed,
        );
      case 'latex':
        return widget.streamingLatexBlock?.call(
          content: block.content,
          isClosed: block.isClosed,
        );
      case 'think':
        return widget.streamingThinkBlock?.call(
          content: block.content,
          isClosed: block.isClosed,
        );
      default:
        return null;
    }
  }

  Widget _buildTailText(String text) {
    // 检测是否包含完整的图片语法，如果有则用 Markdown 渲染
    if (OwuiStableBody.tailNeedsMarkdown(text)) {
      return widget.markdown(text);
    }

    final textWidget = Text(text, style: widget.plainTextStyle);
    final animation = _fadeAnimation;
    if (!_fadeEnabled || animation == null) {
      return textWidget;
    }

    return FadeTransition(
      opacity: animation,
      child: textWidget,
    );
  }

  @override
  Widget build(BuildContext context) {
    final parts = _parts;

    // 使用统一的块级信号检测
    final block = OwuiStableBody.extractLeadingBlock(parts.tail);
    final blockWidget = block != null ? _buildBlockWidget(block) : null;

    if (parts.stable.isEmpty) {
      if (blockWidget != null) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            blockWidget,
            if (block!.rest.isNotEmpty) _buildTailText(block.rest),
          ],
        );
      }

      return _buildTailText(parts.tail);
    }

    if (parts.tail.isEmpty) {
      return _cachedStableWidget ?? widget.markdown(parts.stable);
    }

    if (blockWidget != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _cachedStableWidget ?? widget.markdown(parts.stable),
          blockWidget,
          if (block!.rest.isNotEmpty) _buildTailText(block.rest),
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
