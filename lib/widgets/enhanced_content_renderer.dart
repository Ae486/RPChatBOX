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
    final mermaidBlocks = ContentDetector.extractMermaidBlocks(content);
    final remainingContent = ContentDetector.removeMermaidBlocks(content);
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 渲染普通 Markdown 内容（如果有）
        if (remainingContent.isNotEmpty)
          SmartContentRenderer(
            content: remainingContent,
            textStyle: textStyle,
            backgroundColor: backgroundColor,
            isUser: isUser,
          ),
        
        // 渲染所有 Mermaid 图表
        ...mermaidBlocks.map((mermaidCode) {
          return MermaidRenderer(
            mermaidCode: mermaidCode,
            isDark: isDark,
          );
        }),
      ],
    );
  }
}

