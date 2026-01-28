/// INPUT: SVG 数据（字符串 + 尺寸）+ 主题/样式配置
/// OUTPUT: MermaidSvgWidget - 基于 flutter_svg 的原生 Mermaid 渲染
/// POS: UI 层 / Widgets - Mermaid SVG 原生渲染（替代 WebView）

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../design_system/design_tokens.dart';
import '../services/mermaid_svg_cache.dart';

/// 基于 flutter_svg 的 Mermaid 渲染 Widget
///
/// 用于 ListView 内联展示，替代 WebView。
/// 从 MermaidSvgCache 获取缓存的 SVG 数据进行原生渲染。
///
/// 优势：
/// - 零高度跳变：SVG 是原生 Flutter Widget，高度在 build 时已确定
/// - 高性能：滚动时完全是原生图形渲染，无浏览器内核开销
/// - 矢量清晰：无论缩放比例如何，文字线条保持清晰
class MermaidSvgWidget extends StatelessWidget {
  final MermaidSvgData svgData;
  final bool isDark;
  final VoidCallback? onTap;
  final bool includeOuterContainer;
  final EdgeInsets? margin;

  const MermaidSvgWidget({
    super.key,
    required this.svgData,
    this.isDark = false,
    this.onTap,
    this.includeOuterContainer = true,
    this.margin,
  });

  @override
  Widget build(BuildContext context) {
    // 使用 flutter_svg 渲染 SVG 字符串
    final svgWidget = SvgPicture.string(
      svgData.svgString,
      width: svgData.width,
      height: svgData.height,
      fit: BoxFit.contain,
      placeholderBuilder: (context) => SizedBox(
        width: svgData.width,
        height: svgData.height,
        child: const Center(child: CircularProgressIndicator()),
      ),
    );

    final content = GestureDetector(
      onTap: onTap,
      child: MouseRegion(
        cursor: onTap != null ? SystemMouseCursors.click : SystemMouseCursors.basic,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: svgWidget,
        ),
      ),
    );

    if (!includeOuterContainer) {
      return content;
    }

    return Container(
      margin: margin ?? EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
      decoration: BoxDecoration(
        color: isDark ? Colors.grey.shade900 : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
        border: Border.all(
          color: isDark ? Colors.grey.shade700 : Colors.grey.shade300,
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
        child: content,
      ),
    );
  }
}
