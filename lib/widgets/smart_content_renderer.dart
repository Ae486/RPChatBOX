import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
import '../utils/content_detector.dart';
import 'webview_math_widget.dart';

/// 智能内容渲染器（支持 Markdown + LaTeX + 代码高亮）
class SmartContentRenderer extends StatelessWidget {
  final String content;
  final TextStyle? textStyle;
  final Color? backgroundColor;
  final bool isUser;

  const SmartContentRenderer({
    super.key,
    required this.content,
    this.textStyle,
    this.backgroundColor,
    this.isUser = false,
  });

  @override
  Widget build(BuildContext context) {
    // 解析内容，识别 LaTeX 公式
    final segments = _parseContent(content);
    
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    if (segments.length == 1 && segments.first.type == _SegmentType.text) {
      // 纯文本，使用标准 Markdown（带代码高亮）
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

    // 混合内容（包含 LaTeX），需要自定义渲染
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: segments.map((segment) {
        switch (segment.type) {
          case _SegmentType.text:
            return MarkdownBody(
              data: segment.content,
              selectable: true,
              styleSheet: MarkdownStyleSheet(p: textStyle),
            );
          
          case _SegmentType.inlineMath:
            return _buildInlineMath(segment.content);
          
          case _SegmentType.blockMath:
            return _buildBlockMath(segment.content);
        }
      }).toList(),
    );
  }

  /// 解析内容为文本和 LaTeX 片段
  List<_ContentSegment> _parseContent(String text) {
    final segments = <_ContentSegment>[];
    final buffer = StringBuffer();
    int i = 0;

    while (i < text.length) {
      // 检查块级公式 $$...$$
      if (i < text.length - 1 && text[i] == '\$' && text[i + 1] == '\$') {
        // 保存之前的文本
        if (buffer.isNotEmpty) {
          segments.add(_ContentSegment(_SegmentType.text, buffer.toString()));
          buffer.clear();
        }

        // 查找结束的 $$
        i += 2;
        final start = i;
        while (i < text.length - 1) {
          if (text[i] == '\$' && text[i + 1] == '\$') {
            segments.add(_ContentSegment(
              _SegmentType.blockMath,
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
        // 保存之前的文本
        if (buffer.isNotEmpty) {
          segments.add(_ContentSegment(_SegmentType.text, buffer.toString()));
          buffer.clear();
        }

        // 查找结束的 $
        i++;
        final start = i;
        while (i < text.length && text[i] != '\$') {
          i++;
        }
        
        if (i < text.length) {
          segments.add(_ContentSegment(
            _SegmentType.inlineMath,
            text.substring(start, i),
          ));
          i++;
        }
        continue;
      }

      buffer.write(text[i]);
      i++;
    }

    // 添加剩余文本
    if (buffer.isNotEmpty) {
      segments.add(_ContentSegment(_SegmentType.text, buffer.toString()));
    }

    return segments.isEmpty 
        ? [_ContentSegment(_SegmentType.text, text)]
        : segments;
  }

  /// 构建内联数学公式
  Widget _buildInlineMath(String latex) {
    // 检测是否为复杂公式，需要 WebView 渲染
    if (_isComplexLatex(latex)) {
      return WebViewMathWidget(
        latex: latex,
        isBlockMath: false,
        textStyle: textStyle,
        isDark: backgroundColor != null,
      );
    }
    
    // 简单公式，使用原生渲染（性能更好）
    try {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
        child: Math.tex(
          latex,
          mathStyle: MathStyle.text,
          textStyle: textStyle ?? const TextStyle(fontSize: 15),
        ),
      );
    } catch (e) {
      // 原生渲染失败，降级到 WebView
      return WebViewMathWidget(
        latex: latex,
        isBlockMath: false,
        textStyle: textStyle,
        isDark: backgroundColor != null,
      );
    }
  }

  /// 构建块级数学公式
  Widget _buildBlockMath(String latex) {
    // 检测是否为复杂公式，需要 WebView 渲染
    if (_isComplexLatex(latex)) {
      return WebViewMathWidget(
        latex: latex,
        isBlockMath: true,
        textStyle: textStyle,
        isDark: backgroundColor != null,
      );
    }
    
    // 简单公式，使用原生渲染（性能更好）
    try {
      return Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
        margin: const EdgeInsets.symmetric(vertical: 8),
        child: Center(
          child: Math.tex(
            latex,
            mathStyle: MathStyle.display,
            textStyle: textStyle ?? const TextStyle(fontSize: 16),
          ),
        ),
      );
    } catch (e) {
      // 原生渲染失败，降级到 WebView
      return WebViewMathWidget(
        latex: latex,
        isBlockMath: true,
        textStyle: textStyle,
        isDark: backgroundColor != null,
      );
    }
  }
  
  /// 判断是否为复杂 LaTeX（需要 WebView）
  bool _isComplexLatex(String latex) {
    return ContentDetector.containsComplexLatex('\$$latex\$');
  }
}

enum _SegmentType {
  text,
  inlineMath,
  blockMath,
}

class _ContentSegment {
  final _SegmentType type;
  final String content;

  _ContentSegment(this.type, this.content);
}

/// 代码块构建器（支持语法高亮 + 一键复制）
class CodeBlockBuilder extends MarkdownElementBuilder {
  final bool isDark;

  CodeBlockBuilder({required this.isDark});

  @override
  Widget? visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final code = element.textContent;
    
    // 获取语言标识
    String language = 'plaintext';
    final className = element.attributes['class'];
    if (className != null && className.startsWith('language-')) {
      language = className.substring(9); // 移除 'language-' 前缀
    }

    // 使用语法高亮渲染 + 复制按钮
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
    
    // 显示提示
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('代码已复制到剪贴板'),
          duration: Duration(seconds: 2),
        ),
      );
    }
    
    // 2秒后恢复按钮状态
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
          // 顶部：语言标签 + 复制按钮
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
                // 语言标签
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
                
                // 复制按钮
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
          
          // 分割线
          Divider(
            height: 1,
            thickness: 1,
            color: widget.isDark ? const Color(0xFF353535) : const Color(0xFFD0D7DE),
          ),
          
          // 代码内容（带语法高亮，完整展示）
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

