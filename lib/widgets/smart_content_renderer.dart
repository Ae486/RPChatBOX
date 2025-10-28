import 'package:flutter/material.dart';
import '../utils/content_detector.dart';
import 'optimized_latex_renderer.dart';

/// 智能内容渲染器（支持 Markdown + LaTeX + 代码高亮）
/// 现在使用优化的LaTeX渲染器提供更好的兼容性和性能
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
    // 使用优化的LaTeX渲染器，提供更好的LaTeX支持和智能降级
    return OptimizedLaTeXRenderer(
      content: content,
      textStyle: textStyle,
      backgroundColor: backgroundColor,
      isUser: isUser,
      preferNative: true, // 优先使用原生渲染获得更好性能
    );
  }
}

