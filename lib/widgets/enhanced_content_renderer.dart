import 'package:flutter/material.dart';
import '../utils/content_detector.dart';
import 'smart_content_renderer.dart';
import 'mermaid_renderer.dart';

/// 增强内容渲染器
/// 支持 Markdown + LaTeX + Mermaid 混合渲染
class EnhancedContentRenderer extends StatelessWidget {
  final String content;
  final TextStyle? textStyle;
  final Color? backgroundColor;
  final bool isUser;

  const EnhancedContentRenderer({
    super.key,
    required this.content,
    this.textStyle,
    this.backgroundColor,
    this.isUser = false,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    // 检测是否包含 Mermaid
    if (ContentDetector.containsMermaid(content)) {
      return _buildMixedContent(context, isDark);
    }
    
    // 否则使用原有渲染器（保持现有功能）
    return SmartContentRenderer(
      content: content,
      textStyle: textStyle,
      backgroundColor: backgroundColor,
      isUser: isUser,
    );
  }

  /// 构建混合内容（Markdown + Mermaid）
  Widget _buildMixedContent(BuildContext context, bool isDark) {
    final segments = ContentDetector.splitByMermaidBlocks(content);

    final children = <Widget>[];
    for (final segment in segments) {
      final segContent = segment.content;
      if (segment.isMermaid) {
        if (segContent.trim().isEmpty) continue;
        children.add(
          MermaidRenderer(
            mermaidCode: segContent,
            isDark: isDark,
          ),
        );
      } else {
        if (segContent.trim().isEmpty) continue;
        children.add(
          SmartContentRenderer(
            content: segContent,
            textStyle: textStyle,
            backgroundColor: backgroundColor,
            isUser: isUser,
          ),
        );
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: children,
    );
  }
}

