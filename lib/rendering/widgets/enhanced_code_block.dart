import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../../design_system/apple_icons.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
import '/utils/global_toast.dart';

/// 增强代码块组件
/// 功能：简洁的 Header (语言标签 + 复制按钮) + 代码内容
class EnhancedCodeBlock extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;

  final bool showLineNumbers;
  final bool collapsible;
  final int maxVisibleLines;
  final bool enableFullscreen;

  final bool streaming;

  const EnhancedCodeBlock({
    super.key,
    required this.code,
    required this.language,
    required this.isDark,
    this.showLineNumbers = true,
    this.collapsible = true,
    this.maxVisibleLines = 16,
    this.enableFullscreen = true,
    this.streaming = false,
  });

  @override
  State<EnhancedCodeBlock> createState() => _EnhancedCodeBlockState();
}

class _EnhancedCodeBlockState extends State<EnhancedCodeBlock>
    with SingleTickerProviderStateMixin {
  bool _copied = false;
  bool _expanded = false;
  bool _wrap = false;
  final ScrollController _scrollController = ScrollController();
  late final AnimationController _shimmerController;

  bool get _isDesktopPlatform {
    if (kIsWeb) return true;
    return defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.macOS ||
        defaultTargetPlatform == TargetPlatform.linux;
  }

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    if (widget.streaming && widget.code.trim().isEmpty) {
      if (!_isDesktopPlatform) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          if (widget.streaming && widget.code.trim().isEmpty) {
            _shimmerController.repeat();
          }
        });
      }
    }
  }

  @override
  void didUpdateWidget(covariant EnhancedCodeBlock oldWidget) {
    super.didUpdateWidget(oldWidget);
    final oldShowSkeleton = oldWidget.streaming && oldWidget.code.trim().isEmpty;
    final newShowSkeleton = widget.streaming && widget.code.trim().isEmpty;
    if (oldShowSkeleton != newShowSkeleton) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        if (newShowSkeleton) {
          if (_isDesktopPlatform) {
            _shimmerController.stop();
            _shimmerController.value = 0;
          } else {
            _shimmerController.repeat();
          }
        } else {
          _shimmerController.stop();
        }
      });
    }
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    _scrollController.dispose();
    super.dispose();
  }



  void _copyToClipboard() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    
    setState(() => _copied = true);
    
    GlobalToast.showSuccess(
      context,
      '代码已复制到剪贴板',
    );
    

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  Future<void> _openFullscreen() async {
    await showDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierColor: Colors.black54,
      builder: (context) {
        return _CodeBlockFullscreenDialog(
          code: widget.code,
          language: widget.language,
          isDark: widget.isDark,
          initialWrap: _wrap,
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final lineCount = _countLines(widget.code);
    final canCollapse = widget.collapsible && lineCount > widget.maxVisibleLines;

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
          _buildHeader(canCollapse: canCollapse),
          _buildCodeContent(
            canCollapse: canCollapse,
            isExpanded: _expanded,
          ),
        ],
      ),
    );
  }

  Widget _buildHeader({required bool canCollapse}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1B1E24) : const Color(0xFFEEF2F6),
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(11),
          topRight: Radius.circular(11),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.max,
        children: [
          // 语言标签
          if (widget.language != 'plaintext')
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: widget.isDark ? const Color(0x263B82F6) : const Color(0x1A1A73E8),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                widget.language.toUpperCase(),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: widget.isDark ? const Color(0xFF93C5FD) : const Color(0xFF1A73E8),
                  letterSpacing: 0.5,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),

          const SizedBox(width: 8),
          Opacity(
            opacity: canCollapse ? 1 : 0,
            child: IgnorePointer(
              ignoring: !canCollapse,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  setState(() {
                    _expanded = !_expanded;
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  child: Icon(
                    _expanded ? AppleIcons.arrowUp : AppleIcons.arrowDown,
                    size: 16,
                    color: widget.isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                  ),
                ),
              ),
            ),
          ),

          const Spacer(),

          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              setState(() {
                _wrap = !_wrap;
              });
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              child: SizedBox(
                width: 16,
                height: 16,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Opacity(
                      opacity: _wrap ? 1 : 0,
                      child: Icon(
                        Icons.wrap_text_rounded,
                        size: 16,
                        color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                    Opacity(
                      opacity: _wrap ? 0 : 1,
                      child: Icon(
                        Icons.code_rounded,
                        size: 16,
                        color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

          if (widget.enableFullscreen)
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _openFullscreen,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                child: Icon(
                  Icons.open_in_full_rounded,
                  size: 16,
                  color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                ),
              ),
            ),

          // 复制按钮
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: _copyToClipboard,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              child: SizedBox(
                width: 16,
                height: 16,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Opacity(
                      opacity: _copied ? 1 : 0,
                      child: Icon(
                        AppleIcons.check,
                        size: 16,
                        color: Colors.green,
                      ),
                    ),
                    Opacity(
                      opacity: _copied ? 0 : 1,
                      child: Icon(
                        AppleIcons.copy,
                        size: 16,
                        color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCodeContent({required bool canCollapse, required bool isExpanded}) {
    final textStyle = TextStyle(
      fontFamily: 'monospace',
      fontFamilyFallback: const [
        'Consolas',
        'Menlo',
        'Monaco',
        'RobotoMono',
        'Courier New',
        'monospace',
      ],
      fontSize: 13,
      height: 1.55,
      letterSpacing: 0.2,
      color: widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
    );

    final lineHeight = (textStyle.fontSize ?? 13) * (textStyle.height ?? 1.55);
    final collapsedMaxHeight = widget.maxVisibleLines * lineHeight + 32;

    final showSkeleton = widget.streaming && widget.code.trim().isEmpty;

    final Widget codeView = showSkeleton
        ? _CodeSkeleton(
            controller: _shimmerController,
            isDark: widget.isDark,
          )
        : (widget.streaming
            ? Text(
                widget.code,
                style: textStyle,
                softWrap: false,
              )
            : HighlightView(
                widget.code,
                language: widget.language,
                theme: widget.isDark ? monokaiSublimeTheme : githubTheme,
                padding: EdgeInsets.zero,
                textStyle: textStyle,
              ));

    final Widget content = _wrap
        ? Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            child: codeView,
          )
        : ScrollConfiguration(
            behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
            child: SingleChildScrollView(
              controller: _scrollController,
              scrollDirection: Axis.horizontal,
              physics: const ClampingScrollPhysics(),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              child: codeView,
            ),
          );

    Widget body = content;
    if (canCollapse) {
      body = AnimatedSize(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeInOut,
        alignment: Alignment.topCenter,
        child: ClipRect(
          child: ConstrainedBox(
            constraints: isExpanded ? const BoxConstraints() : BoxConstraints(maxHeight: collapsedMaxHeight),
            child: body,
          ),
        ),
      );
    }

    if (!widget.showLineNumbers) return body;

    final lineCount = _countLines(widget.code);
    final visibleLineCount = (canCollapse && !isExpanded) ? widget.maxVisibleLines : lineCount;
    final showEllipsis = (canCollapse && !isExpanded) && lineCount > widget.maxVisibleLines;
    final lineLabels = <String>[
      ...List.generate(visibleLineCount, (i) => '${i + 1}'),
      if (showEllipsis) '…',
    ];

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 40,
          child: Container(
            padding: const EdgeInsets.fromLTRB(12, 12, 8, 12),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0xFF171A20) : const Color(0xFFF1F3F5),
              borderRadius: const BorderRadius.only(
                bottomLeft: Radius.circular(11),
              ),
              border: Border(
                right: BorderSide(
                  color: widget.isDark ? const Color(0x1AFFFFFF) : const Color(0x14000000),
                ),
              ),
            ),
            child: Text(
              lineLabels.join('\n'),
              textAlign: TextAlign.right,
              style: textStyle.copyWith(
                color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
              ),
            ),
          ),
        ),
        Expanded(child: body),
      ],
    );
  }

  int _countLines(String code) {
    if (code.isEmpty) return 1;
    var count = 1;
    for (var i = 0; i < code.length; i++) {
      if (code.codeUnitAt(i) == 10) count++;
    }
    return count;
  }
}

class _CodeSkeleton extends StatelessWidget {
  final Animation<double> controller;
  final bool isDark;

  const _CodeSkeleton({
    required this.controller,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final base = isDark ? Colors.white.withAlpha((0.06 * 255).round()) : Colors.black.withAlpha((0.06 * 255).round());
    final glow = isDark ? Colors.white.withAlpha((0.14 * 255).round()) : Colors.black.withAlpha((0.12 * 255).round());

    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final t = controller.value;
        final begin = Alignment(-1.0 - t * 2, 0);
        final end = Alignment(1.0 - t * 2, 0);

        BoxDecoration deco(double wFactor) {
          return BoxDecoration(
            borderRadius: BorderRadius.circular(6),
            gradient: LinearGradient(
              begin: begin,
              end: end,
              colors: [base, glow, base],
              stops: const [0.25, 0.5, 0.75],
            ),
          );
        }

        Widget line(double widthFactor) {
          return FractionallySizedBox(
            widthFactor: widthFactor,
            child: Container(
              height: 14,
              decoration: deco(widthFactor),
            ),
          );
        }

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              line(0.95),
              const SizedBox(height: 10),
              line(0.86),
              const SizedBox(height: 10),
              line(0.62),
            ],
          ),
        );
      },
    );
  }
}

class _CodeBlockFullscreenDialog extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;
  final bool initialWrap;

  const _CodeBlockFullscreenDialog({
    required this.code,
    required this.language,
    required this.isDark,
    required this.initialWrap,
  });

  @override
  State<_CodeBlockFullscreenDialog> createState() => _CodeBlockFullscreenDialogState();
}

class _CodeBlockFullscreenDialogState extends State<_CodeBlockFullscreenDialog> {
  late bool _wrap;

  @override
  void initState() {
    super.initState();
    _wrap = widget.initialWrap;
  }

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    GlobalToast.showSuccess(context, '代码已复制到剪贴板');
  }

  @override
  Widget build(BuildContext context) {
    final bg = widget.isDark ? const Color(0xFF0F1115) : const Color(0xFFFFFFFF);
    final barBg = widget.isDark ? const Color(0xFF161A20) : const Color(0xFFF3F4F6);
    final fg = widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827);

    final codeView = HighlightView(
      widget.code,
      language: widget.language,
      theme: widget.isDark ? monokaiSublimeTheme : githubTheme,
      padding: EdgeInsets.zero,
      textStyle: TextStyle(
        fontFamily: 'monospace',
        fontSize: 13,
        height: 1.55,
        letterSpacing: 0.2,
        color: fg,
      ),
    );

    final content = _wrap
        ? Padding(
            padding: const EdgeInsets.all(16),
            child: codeView,
          )
        : ScrollConfiguration(
            behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              physics: const ClampingScrollPhysics(),
              padding: const EdgeInsets.all(16),
              child: codeView,
            ),
          );

    return Dialog(
      insetPadding: EdgeInsets.zero,
      backgroundColor: bg,
      child: SafeArea(
        child: Column(
          children: [
            Container(
              color: barBg,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.language.isEmpty ? 'code' : widget.language.toUpperCase(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: fg,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: _wrap ? '不换行' : '自动换行',
                    onPressed: () {
                      setState(() {
                        _wrap = !_wrap;
                      });
                    },
                    icon: Icon(
                      _wrap ? Icons.wrap_text_rounded : Icons.code_rounded,
                      color: fg,
                      size: 20,
                    ),
                  ),
                  IconButton(
                    tooltip: '复制',
                    onPressed: _copy,
                    icon: Icon(
                      AppleIcons.copy,
                      color: fg,
                      size: 20,
                    ),
                  ),
                  IconButton(
                    tooltip: '关闭',
                    onPressed: () => Navigator.of(context).maybePop(),
                    icon: Icon(
                      AppleIcons.close,
                      color: fg,
                      size: 20,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ScrollConfiguration(
                behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
                child: SingleChildScrollView(
                  physics: const ClampingScrollPhysics(),
                  child: content,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
