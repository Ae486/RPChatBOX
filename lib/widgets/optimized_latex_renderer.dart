import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;
import 'package:flutter_math_fork/flutter_math.dart';
import '../utils/content_detector.dart';
import '../utils/markdown_preprocessor.dart';
import 'webview_math_widget.dart';
import '../rendering/widgets/enhanced_code_block.dart';
import '../rendering/core/render_cache.dart';
import '../rendering/utils/performance_monitor.dart';
import '../rendering/utils/markdown_style_helper.dart';
import '../rendering/widgets/latex_error_widget.dart';

/// 优化的LaTeX渲染器
/// 基于flutter_math_fork，通过预处理和语法转换提供更好的LaTeX支持
class OptimizedLaTeXRenderer extends StatelessWidget {
  final String content;
  final TextStyle? textStyle;
  final Color? backgroundColor;
  final bool isUser;
  final bool preferNative;

  const OptimizedLaTeXRenderer({
    super.key,
    required this.content,
    this.textStyle,
    this.backgroundColor,
    this.isUser = false,
    this.preferNative = true,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    // 🆕 开始性能监控
    final timer = RenderTimer(
      contentType: 'latex_renderer',
      contentLength: content.length,
    );
    timer.start();

    // 🆕 生成缓存键
    final cacheKey = RenderCache.generateKey(
      content,
      type: 'latex_renderer',
      options: {
        'isDark': isDark,
        'isUser': isUser,
        'preferNative': preferNative,
      },
    );

    // 🆕 尝试从缓存获取
    final cache = RenderCache();
    final cached = cache.get(cacheKey);
    if (cached != null) {
      timer.markCacheHit();
      timer.stop();
      return cached;
    }

    // 检测内容是否包含LaTeX公式
    Widget result;
    if (!content.contains('\$') && !ContentDetector.containsStandardLatex(content)) {
      // 没有LaTeX公式，使用标准Markdown渲染
      result = _buildMarkdown(content, isDark);
    } else {
      // 检测复杂度，选择渲染方式
      final hasComplexLatex = ContentDetector.containsComplexLatex(content);
      final hasStandardLatex = ContentDetector.containsStandardLatex(content);
      
      // 🔥 桌面平台不支持WebView，强制使用flutter_math_fork
      final isDesktop = Platform.isWindows || Platform.isLinux || Platform.isMacOS;

      if (preferNative && !hasComplexLatex && hasStandardLatex) {
        // 优先使用原生渲染，处理标准LaTeX
        result = _buildOptimizedNativeRenderer(content, isDark);
      } else if (hasComplexLatex && !isDesktop) {
        // 复杂公式，移动平台可以降级到WebView
        result = _buildWebViewRenderer(content, isDark);
      } else {
        // 基础公式或桌面平台，使用flutter_math_fork
        result = _buildFlutterMathRenderer(content, isDark);
      }
    }

    // 🆕 存入缓存
    cache.set(cacheKey, result);
    
    // 🆕 停止性能监控
    timer.stop();
    
    return result;
  }

  /// 使用优化的原生渲染器
  Widget _buildOptimizedNativeRenderer(String content, bool isDark) {
    try {
      // 预处理LaTeX内容，转换为flutter_math_fork兼容格式
      final processedContent = _preprocessLatex(content);
      return _buildFlutterMathRenderer(processedContent, isDark);
    } catch (e) {
      debugPrint('Optimized LaTeX rendering failed: $e');
      // 降级到WebView渲染
      return _buildWebViewRenderer(content, isDark);
    }
  }

  /// 预处理LaTeX内容，转换为flutter_math_fork兼容格式
  String _preprocessLatex(String content) {
    var processed = content;

    // 处理一些常见的LaTeX语法转换
    final conversions = {
      // 希腊字母大写
      r'\Alpha': 'A',
      r'\Beta': 'B',
      r'\Gamma': r'\Gamma',
      r'\Delta': r'\Delta',
      r'\Epsilon': 'E',
      r'\Zeta': 'Z',
      r'\Eta': 'H',
      r'\Theta': r'\Theta',
      r'\Iota': 'I',
      r'\Kappa': 'K',
      r'\Lambda': r'\Lambda',
      r'\Mu': 'M',
      r'\Nu': 'N',
      r'\Xi': r'\Xi',
      r'\Pi': r'\Pi',
      r'\Rho': 'P',
      r'\Sigma': r'\Sigma',
      r'\Tau': 'T',
      r'\Upsilon': r'\Upsilon',
      r'\Phi': r'\Phi',
      r'\Chi': 'X',
      r'\Psi': r'\Psi',
      r'\Omega': r'\Omega',

      // 常见数学符号
      r'\infty': r'\infty',
      r'\partial': r'\partial',
      r'\nabla': r'\nabla',
      r'\exists': r'\exists',
      r'\forall': r'\forall',
      r'\neg': r'\neg',
      r'\in': r'\in',
      r'\notin': r'\notin',
      r'\subset': r'\subset',
      r'\subseteq': r'\subseteq',
      r'\supset': r'\supset',
      r'\supseteq': r'\supseteq',
      r'\cup': r'\cup',
      r'\cap': r'\cap',
      r'\emptyset': r'\emptyset',
      r'\varnothing': r'\varnothing',

      // 二元运算符
      r'\pm': r'\pm',
      r'\mp': r'\mp',
      r'\times': r'\times',
      r'\div': r'\div',
      r'\cdot': r'\cdot',
      r'\circ': r'\circ',
      r'\oplus': r'\oplus',
      r'\ominus': r'\ominus',
      r'\otimes': r'\otimes',
      r'\oslash': r'\oslash',
      r'\odot': r'\odot',

      // 关系符号
      r'\leq': r'\leq',
      r'\geq': r'\geq',
      r'\neq': r'\neq',
      r'\equiv': r'\equiv',
      r'\approx': r'\approx',
      r'\sim': r'\sim',
      r'\simeq': r'\simeq',
      r'\cong': r'\cong',
      r'\propto': r'\propto',
      r'\parallel': r'\parallel',
      r'\perp': r'\perp',

      // 箭头
      r'\rightarrow': r'\rightarrow',
      r'\leftarrow': r'\leftarrow',
      r'\leftrightarrow': r'\leftrightarrow',
      r'\Rightarrow': r'\Rightarrow',
      r'\Leftarrow': r'\Leftarrow',
      r'\Leftrightarrow': r'\Leftrightarrow',
      r'\mapsto': r'\mapsto',
      r'\to': r'\to',

      // 其他符号
      r'\angle': r'\angle',
      r'\degree': r'^{\circ}',
      r'\prime': r'\prime',
      r'\backslash': r'\backslash',
      r'\ell': r'\ell',
      r'\wp': r'\wp',
      r'\Re': r'\Re',
      r'\Im': r'\Im',
      r'\aleph': r'\aleph',
      r'\hbar': r'\hbar',
      r'\clubsuit': r'\clubsuit',
      r'\diamondsuit': r'\diamondsuit',
      r'\heartsuit': r'\heartsuit',
      r'\spadesuit': r'\spadesuit',
    };

    // 应用转换
    conversions.forEach((pattern, replacement) {
      processed = processed.replaceAll(pattern, replacement);
    });

    // 处理一些复杂情况
    processed = _processComplexPatterns(processed);

    return processed;
  }

  /// 处理复杂的LaTeX模式
  String _processComplexPatterns(String content) {
    var processed = content;

    // 处理分数 \frac{a}{b}
    processed = processed.replaceAllMapped(
      RegExp(r'\\frac\{([^{}]+)\}\{([^{}]+)\}'),
      (match) => r'\frac{' + match.group(1)! + r'}{' + match.group(2)! + r'}',
    );

    // 处理根号 \sqrt[n]{a} 和 \sqrt{a}
    processed = processed.replaceAllMapped(
      RegExp(r'\\sqrt(?:\[([^\]]+)\])?\{([^{}]+)\}'),
      (match) {
        final index = match.group(1);
        final radicand = match.group(2)!;
        if (index != null) {
          return r'\sqrt[' + index + r']{' + radicand + r'}';
        } else {
          return r'\sqrt{' + radicand + r'}';
        }
      },
    );

    // 处理上下标，如 \sum_{i=1}^n
    processed = processed.replaceAllMapped(
      RegExp(r'(\\[a-zA-Z]+)(?:_\{([^{}]+)\})?(?:\^\{([^{}]+)\})?'),
      (match) {
        final command = match.group(1)!;
        final subscript = match.group(2);
        final superscript = match.group(3);

        var result = command;
        if (subscript != null) {
          result += '_{$subscript}';
        }
        if (superscript != null) {
          result += '^{$superscript}';
        }
        return result;
      },
    );

    // 处理自动大小的括号
    processed = processed.replaceAll(r'\left(', '(');
    processed = processed.replaceAll(r'\right)', ')');
    processed = processed.replaceAll(r'\left[', '[');
    processed = processed.replaceAll(r'\right]', ']');
    processed = processed.replaceAll(r'\left\{', '{');
    processed = processed.replaceAll(r'\right\}', '}');
    processed = processed.replaceAll(r'\left|', '|');
    processed = processed.replaceAll(r'\right|', '|');

    // 处理矩阵环境（简化为表格）
    processed = _processMatrixEnvironments(processed);

    return processed;
  }

  /// 处理矩阵环境，转换为简单格式
  String _processMatrixEnvironments(String content) {
    var processed = content;

    // 简单的矩阵处理：将 \begin{matrix} ... \end{matrix} 转换为分行
    processed = processed.replaceAllMapped(
      RegExp(r'\\begin\{(?:pmatrix|bmatrix|vmatrix|Vmatrix|matrix)\}([\s\S]*?)\\end\{(?:pmatrix|bmatrix|vmatrix|Vmatrix|matrix)\}'),
      (match) {
        final matrixContent = match.group(1)!;
        // 将矩阵内容按行分割，用换行符连接
        final rows = matrixContent
            .split(r'\\')
            .map((row) => row.trim())
            .where((row) => row.isNotEmpty)
            .join(r'\\');
        return r'\begin{aligned}' + rows + r'\end{aligned}';
      },
    );

    return processed;
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
            return _buildInlineMath(segment.content, isDark);
          case _LaTeXSegmentType.blockMath:
            return _buildBlockMath(segment.content, isDark);
        }
      }).toList(),
    );
  }

  /// 构建内联数学公式
  Widget _buildInlineMath(String latex, bool isDark) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
      child: Math.tex(
        latex,
        mathStyle: MathStyle.text,
        textStyle: textStyle ?? const TextStyle(fontSize: 15),
        onErrorFallback: (err) {
          debugPrint('LaTeX rendering error: ${err.messageWithType}');
          // 🆕 使用增强的错误组件
          return InlineLaTeXErrorWidget(
            latex: latex,
            isDark: isDark,
          );
        },
      ),
    );
  }

  /// 构建块级数学公式
  Widget _buildBlockMath(String latex, bool isDark) {
    return Math.tex(
      latex,
      mathStyle: MathStyle.display,
      textStyle: textStyle ?? const TextStyle(fontSize: 16),
      onErrorFallback: (err) {
        debugPrint('LaTeX rendering error: ${err.messageWithType}');
        // 🆕 使用增强的错误组件
        return LaTeXErrorWidget(
          latex: latex,
          errorMessage: err.messageWithType,
          isBlockMath: true,
          isDark: isDark,
        );
      },
    );
  }

  /// 标准Markdown渲染器
  Widget _buildMarkdown(String content, bool isDark) {
    // 🐛 修复：使用预处理器，只识别三反引号代码块
    final processedContent = MarkdownPreprocessor.preprocess(content);
    
    return MarkdownBody(
      data: processedContent,
      selectable: true,
      // 启用GitHub风格扩展（包含表格支持）
      extensionSet: md.ExtensionSet.gitHubWeb,
      // 🆕 使用增强的样式配置
      styleSheet: MarkdownStyleHelper.getCompactStyleSheet(
        isDark: isDark,
        baseTextStyle: textStyle,
      ),
      builders: {
        'code': CodeBlockBuilder(isDark: isDark),
        'codespan': CodespanBuilder(isDark: isDark),
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

/// 代码块构建器
class CodeBlockBuilder extends MarkdownElementBuilder {
  final bool isDark;

  CodeBlockBuilder({required this.isDark});

  @override
  Widget? visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final code = element.textContent;

    // 检查是否有language class属性，这是三反引号代码块的特征
    final className = element.attributes['class'];
    final hasLanguageClass = className != null && className.startsWith('language-');
    
    // 如果没有language class，这可能是单反引号行内代码
    // 但为了保险，我们也检查代码长度和换行符
    final isLikelyInlineCode = !hasLanguageClass && 
                                code.length < 100 && 
                                !code.contains('\n');
    
    if (isLikelyInlineCode) {
      // 这是单反引号行内代码，使用简单样式
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF2D2D2D) : const Color(0xFFF0F0F0),
          borderRadius: BorderRadius.circular(2),
        ),
        child: Text(
          code,
          style: TextStyle(
            fontFamily: 'monospace',
            fontSize: (preferredStyle?.fontSize ?? 15) * 0.88,
            color: isDark ? const Color.fromARGB(255, 255, 255, 255) : const Color.fromARGB(255, 52, 52, 52),
            fontWeight: FontWeight.w400,
          ),
        ),
      );
    }

    // 这是三反引号代码块
    String language = 'plaintext';
    if (hasLanguageClass) {
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
    // 使用简化的增强代码块（只有 Header + 代码内容）
    return EnhancedCodeBlock(
      code: widget.code,
      language: widget.language,
      isDark: widget.isDark,
    );
  }
}

/// 单反引号行内代码构建器
class CodespanBuilder extends MarkdownElementBuilder {
  final bool isDark;

  CodespanBuilder({required this.isDark});

  @override
  Widget? visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final code = element.textContent;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF2D2D2D) : const Color(0xFFF0F0F0),
        borderRadius: BorderRadius.circular(2),
      ),
      child: Text(
        code,
        style: TextStyle(
          fontFamily: 'monospace',
          fontSize: (preferredStyle?.fontSize ?? 15) * 0.88,
          color: isDark ? const Color(0xFFE06C75) : const Color(0xFFD73A49),
          fontWeight: FontWeight.w400,
        ),
      ),
    );
  }
}
