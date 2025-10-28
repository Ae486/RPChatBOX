import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
// import 'package:latext/latext.dart';  // 暂时注释，避免依赖问题
import '../utils/content_detector.dart';
import 'webview_math_widget.dart';

/// 增强版LaTeX渲染器
/// 使用latext提供更完整的LaTeX支持，保持向后兼容
class EnhancedLaTeXRenderer extends StatelessWidget {
  final String content;
  final TextStyle? textStyle;
  final Color? backgroundColor;
  final bool isUser;
  final bool preferNative;

  const EnhancedLaTeXRenderer({
    super.key,
    required this.content,
    this.textStyle,
    this.backgroundColor,
    this.isUser = false,
    this.preferNative = true, // 优先使用原生渲染
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    // 检测内容是否包含LaTeX公式
    if (!ContentDetector.containsComplexLatex(content) && !content.contains('\$')) {
      // 没有LaTeX公式，使用标准Markdown渲染
      return _buildMarkdown(content, isDark);
    }

    // 检测复杂度，选择渲染方式
    final hasComplexLatex = ContentDetector.containsComplexLatex(content);
    final hasBasicLatex = content.contains('\$');

    if (preferNative && (!hasComplexLatex || _shouldUseNative(content))) {
      // 优先使用原生渲染，支持复杂公式
      return _buildLatextRenderer(content, isDark);
    } else if (hasComplexLatex) {
      // 复杂公式，降级到WebView
      return _buildWebViewRenderer(content, isDark);
    } else {
      // 基础公式，使用flutter_math_fork
      return _buildFlutterMathRenderer(content, isDark);
    }
  }

  /// 判断是否应该使用原生渲染
  bool _shouldUseNative(String content) {
    // 检测是否为latext支持的高级功能
    final supportedPatterns = [
      r'\begin{align}',      // 对齐环境
      r'\begin{cases}',      // 分段函数
      r'\begin{matrix}',     // 矩阵
      r'\begin{pmatrix}',    // 括号矩阵
      r'\begin{bmatrix}',    // 方括号矩阵
      r'\begin{vmatrix}',    // 竖线矩阵
      r'\begin{Vmatrix}',    // 双竖线矩阵
      r'\frac{',             // 分数
      r'\sqrt{',             // 根号
      r'\sum_{',             // 求和
      r'\int_{',             // 积分
      r'\lim_{',             // 极限
      r'\prod_{',            // 乘积
      r'\bigcup_{',          // 大并集
      r'\bigcap_{',          // 大交集
      r'\subset',            // 子集
      r'\subseteq',          // 子集或等于
      r'\supset',            // 超集
      r'\supseteq',          // 超集或等于
      r'\in',                // 属于
      r'\notin',             // 不属于
      r'\forall',            // 对所有
      r'\exists',            // 存在
      r'\nabla',             // 哈密顿算子
      r'\partial',           // 偏导数
      r'\infty',             // 无穷
    ];

    return supportedPatterns.any((pattern) => content.contains(pattern));
  }

  /// 使用latext渲染器（推荐方案）
  Widget _buildLatextRenderer(String content, bool isDark) {
    try {
      return LaTeXT(
        content: content,
        delimiter: LatexDelimiter.all,
        style: textStyle ?? const TextStyle(fontSize: 15),
        mathStyle: MathStyle.text,
        textDirection: TextDirection.ltr,
        renderOptions: LaTeXTOptions(
          throwOnError: false,
          macrons: true,
          strict: false,
          enableFancyUnicode: true,
        ),
      );
    } catch (e) {
      debugPrint('LaTeX rendering failed with latext: $e');
      // 降级到WebView渲染
      return _buildWebViewRenderer(content, isDark);
    }
  }

  /// 使用WebView渲染器（备用方案）
  Widget _buildWebViewRenderer(String content, bool isDark) {
    if (content.contains('\$\$')) {
      // 包含块级公式，需要复杂处理
      return WebViewMathWidget(
        latex: content.replaceAll(r'$$', '').replaceAll(r'$', ''),
        isBlockMath: true,
        textStyle: textStyle,
        isDark: isDark,
      );
    } else {
      // 内联公式
      return WebViewMathWidget(
        latex: content.replaceAll(r'$', ''),
        isBlockMath: false,
        textStyle: textStyle,
        isDark: isDark,
      );
    }
  }

  /// 使用flutter_math_fork渲染器（基础方案）
  Widget _buildFlutterMathRenderer(String content, bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _parseLaTeXSegments(content).map((segment) {
        switch (segment.type) {
          case _LaTeXSegmentType.text:
            return _buildMarkdown(segment.content, isDark);
          case _LaTeXSegmentType.inlineMath:
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
              child: Math.tex(
                segment.content,
                mathStyle: MathStyle.text,
                textStyle: textStyle ?? const TextStyle(fontSize: 15),
              ),
            );
          case _LaTeXSegmentType.blockMath:
            return Container(
              padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
              margin: const EdgeInsets.symmetric(vertical: 8),
              child: Center(
                child: Math.tex(
                  segment.content,
                  mathStyle: MathStyle.display,
                  textStyle: textStyle ?? const TextStyle(fontSize: 16),
                ),
              ),
            );
        }
      }).toList(),
    );
  }

  /// 标准Markdown渲染器
  Widget _buildMarkdown(String content, bool isDark) {
    return MarkdownBody(
      data: content,
      selectable: true,
      styleSheet: MarkdownStyleSheet(
        p: textStyle,
        code: TextStyle(
          backgroundColor: backgroundColor,
          fontFamily: 'monospace',
          fontSize: 13,
        ),
        codeblockPadding: const EdgeInsets.all(12),
        codeblockDecoration: BoxDecoration(
          color: isDark ? Colors.grey.shade900 : Colors.grey.shade100,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isDark ? Colors.grey.shade700 : Colors.grey.shade300,
          ),
        ),
      ),
      builders: {
        'code': CodeBlockBuilder(isDark: isDark),
      },
    );
  }

  /// 解析LaTeX内容片段
  List<_LaTeXSegment> _parseLaTeXSegments(String text) {
    final segments = <_LaTeXSegment>[];
    final buffer = StringBuffer();
    int i = 0;

    while (i < text.length) {
      // 检查块级公式 $$...$$
      if (i < text.length - 1 && text[i] == '\$' && text[i + 1] == '\$') {
        if (buffer.isNotEmpty) {
          segments.add(_LaTeXSegment(_LaTeXSegmentType.text, buffer.toString()));
          buffer.clear();
        }

        i += 2;
        final start = i;
        while (i < text.length - 1) {
          if (text[i] == '\$' && text[i + 1] == '\$') {
            segments.add(_LaTeXSegment(
              _LaTeXSegmentType.blockMath,
              text.substring(start, i),
            ));
            i += 2;
            break;
          }
          i++;
        }
        continue;
      }

      // 检查内联公式 $...$
      if (text[i] == '\$') {
        if (buffer.isNotEmpty) {
          segments.add(_LaTeXSegment(_LaTeXSegmentType.text, buffer.toString()));
          buffer.clear();
        }

        i++;
        final start = i;
        while (i < text.length && text[i] != '\$') {
          i++;
        }

        if (i < text.length) {
          segments.add(_LaTeXSegment(
            _LaTeXSegmentType.inlineMath,
            text.substring(start, i),
          ));
          i++;
        }
        continue;
      }

      buffer.write(text[i]);
      i++;
    }

    if (buffer.isNotEmpty) {
      segments.add(_LaTeXSegment(_LaTeXSegmentType.text, buffer.toString()));
    }

    return segments.isEmpty
        ? [_LaTeXSegment(_LaTeXSegmentType.text, text)]
        : segments;
  }
}

enum _LaTeXSegmentType {
  text,
  inlineMath,
  blockMath,
}

class _LaTeXSegment {
  final _LaTeXSegmentType type;
  final String content;

  _LaTeXSegment(this.type, this.content);
}

/// 代码块构建器（复制自smart_content_renderer.dart）
class CodeBlockBuilder extends MarkdownElementBuilder {
  final bool isDark;

  CodeBlockBuilder({required this.isDark});

  @override
  Widget? visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final code = element.textContent;

    String language = 'plaintext';
    final className = element.attributes['class'];
    if (className != null && className.startsWith('language-')) {
      language = className.substring(9);
    }

    return _CodeBlockWithCopy(
      code: code,
      language: language,
      isDark: isDark,
    );
  }
}

/// 带复制按钮的代码块组件
class _CodeBlockWithCopy extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;

  const _CodeBlockWithCopy({
    required this.code,
    required this.language,
    required this.isDark,
  });

  @override
  State<_CodeBlockWithCopy> createState() => _CodeBlockWithCopyState();
}

class _CodeBlockWithCopyState extends State<_CodeBlockWithCopy> {
  bool _copied = false;

  void _copyToClipboard(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    setState(() {
      _copied = true;
    });

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('代码已复制到剪贴板'),
          duration: Duration(seconds: 2),
        ),
      );
    }

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _copied = false;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF1E1E1E) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: widget.isDark ? const Color(0xFF353535) : const Color(0xFFD0D7DE),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0xFF2D2D2D) : const Color(0xFFEEF1F4),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(7),
                topRight: Radius.circular(7),
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                if (widget.language != 'plaintext')
                  Text(
                    widget.language.toUpperCase(),
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      color: widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600,
                      letterSpacing: 0.5,
                    ),
                  )
                else
                  const SizedBox.shrink(),

                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () => _copyToClipboard(context),
                    borderRadius: BorderRadius.circular(4),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            _copied ? Icons.check : Icons.content_copy,
                            size: 14,
                            color: _copied
                                ? Colors.green
                                : (widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            _copied ? '已复制' : '复制',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: _copied
                                  ? Colors.green
                                  : (widget.isDark ? Colors.grey.shade400 : Colors.grey.shade600),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          Divider(
            height: 1,
            thickness: 1,
            color: widget.isDark ? const Color(0xFF353535) : const Color(0xFFD0D7DE),
          ),

          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: HighlightView(
                widget.code,
                language: widget.language,
                theme: widget.isDark ? monokaiSublimeTheme : githubTheme,
                padding: EdgeInsets.zero,
                textStyle: const TextStyle(
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: 13.5,
                  height: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}