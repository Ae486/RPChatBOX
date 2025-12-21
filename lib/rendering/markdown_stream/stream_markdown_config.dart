import 'package:flutter/material.dart';

/// 流式 Markdown 渲染配置
/// 
/// 统一管理所有节点组件的样式和行为配置
class StreamMarkdownConfig {
  /// 是否为暗色模式
  final bool isDark;

  /// 流式更新节流时间
  final Duration streamThrottle;

  /// 代码块配置
  final CodeBlockNodeConfig codeBlock;

  /// 表格配置
  final TableNodeConfig table;

  /// 链接配置
  final LinkNodeConfig link;

  /// 引用块配置
  final BlockquoteNodeConfig blockquote;

  /// LaTeX 配置
  final LatexNodeConfig latex;

  /// Mermaid 配置
  final MermaidNodeConfig mermaid;

  /// Thinking 块配置
  final ThinkingNodeConfig thinking;

  /// 气泡背景色
  final Color? bubbleColor;

  /// 气泡圆角
  final BorderRadius? borderRadius;

  const StreamMarkdownConfig({
    this.isDark = false,
    this.streamThrottle = const Duration(milliseconds: 220),
    this.codeBlock = const CodeBlockNodeConfig(),
    this.table = const TableNodeConfig(),
    this.link = const LinkNodeConfig(),
    this.blockquote = const BlockquoteNodeConfig(),
    this.latex = const LatexNodeConfig(),
    this.mermaid = const MermaidNodeConfig(),
    this.thinking = const ThinkingNodeConfig(),
    this.bubbleColor,
    this.borderRadius,
  });

  /// 创建亮色模式配置
  factory StreamMarkdownConfig.light() {
    return const StreamMarkdownConfig(isDark: false);
  }

  /// 创建暗色模式配置
  factory StreamMarkdownConfig.dark() {
    return const StreamMarkdownConfig(isDark: true);
  }

  /// 从 ThemeData 创建配置
  factory StreamMarkdownConfig.fromTheme(ThemeData theme) {
    final isDark = theme.brightness == Brightness.dark;
    return StreamMarkdownConfig(
      isDark: isDark,
      bubbleColor: isDark
          ? const Color(0xFF1E1E1E)
          : const Color(0xFFF5F5F5),
    );
  }

  /// 复制并修改配置
  StreamMarkdownConfig copyWith({
    bool? isDark,
    Duration? streamThrottle,
    CodeBlockNodeConfig? codeBlock,
    TableNodeConfig? table,
    LinkNodeConfig? link,
    BlockquoteNodeConfig? blockquote,
    LatexNodeConfig? latex,
    MermaidNodeConfig? mermaid,
    ThinkingNodeConfig? thinking,
    Color? bubbleColor,
    BorderRadius? borderRadius,
  }) {
    return StreamMarkdownConfig(
      isDark: isDark ?? this.isDark,
      streamThrottle: streamThrottle ?? this.streamThrottle,
      codeBlock: codeBlock ?? this.codeBlock,
      table: table ?? this.table,
      link: link ?? this.link,
      blockquote: blockquote ?? this.blockquote,
      latex: latex ?? this.latex,
      mermaid: mermaid ?? this.mermaid,
      thinking: thinking ?? this.thinking,
      bubbleColor: bubbleColor ?? this.bubbleColor,
      borderRadius: borderRadius ?? this.borderRadius,
    );
  }
}

/// 代码块节点配置
class CodeBlockNodeConfig {
  /// 背景色 (亮色模式)
  final Color lightBackground;

  /// 背景色 (暗色模式)
  final Color darkBackground;

  /// 是否显示行号
  final bool showLineNumbers;

  /// 是否可折叠
  final bool collapsible;

  /// 最大可见行数 (超过则折叠)
  final int maxVisibleLines;

  /// 是否启用全屏
  final bool enableFullscreen;

  const CodeBlockNodeConfig({
    this.lightBackground = const Color(0xFFF6F8FA),
    this.darkBackground = const Color(0xFF14161A),
    this.showLineNumbers = true,
    this.collapsible = true,
    this.maxVisibleLines = 16,
    this.enableFullscreen = true,
  });

  /// 根据 isDark 获取背景色
  Color getBackground(bool isDark) {
    return isDark ? darkBackground : lightBackground;
  }
}

/// 表格节点配置
class TableNodeConfig {
  /// 表头背景色 (亮色)
  final Color lightHeaderBackground;

  /// 表头背景色 (暗色)
  final Color darkHeaderBackground;

  /// 是否启用斑马纹
  final bool zebraStripes;

  /// 是否启用横向滚动
  final bool horizontalScroll;

  const TableNodeConfig({
    this.lightHeaderBackground = const Color(0xFFF3F4F6),
    this.darkHeaderBackground = const Color(0xFF141821),
    this.zebraStripes = true,
    this.horizontalScroll = true,
  });
}

/// 链接节点配置
class LinkNodeConfig {
  /// 链接颜色 (亮色)
  final Color lightColor;

  /// 链接颜色 (暗色)
  final Color darkColor;

  /// 是否显示下划线
  final bool underline;

  /// 桌面端是否显示 Tooltip
  final bool showTooltip;

  const LinkNodeConfig({
    this.lightColor = const Color(0xFF1A73E8),
    this.darkColor = const Color(0xFF8AB4F8),
    this.underline = true,
    this.showTooltip = true,
  });

  /// 根据 isDark 获取颜色
  Color getColor(bool isDark) {
    return isDark ? darkColor : lightColor;
  }
}

/// 引用块节点配置
class BlockquoteNodeConfig {
  /// 边框颜色 (亮色)
  final Color lightSideColor;

  /// 边框颜色 (暗色)
  final Color darkSideColor;

  /// 边框宽度
  final double sideWidth;

  /// 内边距
  final EdgeInsets padding;

  /// 外边距
  final EdgeInsets margin;

  const BlockquoteNodeConfig({
    this.lightSideColor = const Color(0xFF1A73E8),
    this.darkSideColor = const Color(0xFF60A5FA),
    this.sideWidth = 4,
    this.padding = const EdgeInsets.fromLTRB(12, 10, 12, 10),
    this.margin = const EdgeInsets.fromLTRB(0, 10, 0, 10),
  });

  /// 根据 isDark 获取边框颜色
  Color getSideColor(bool isDark) {
    return isDark ? darkSideColor : lightSideColor;
  }
}

/// LaTeX 节点配置
class LatexNodeConfig {
  /// 错误时显示原始文本
  final bool showRawOnError;

  /// 错误文本颜色
  final Color errorColor;

  /// 块级公式垂直边距
  final double blockMargin;

  const LatexNodeConfig({
    this.showRawOnError = true,
    this.errorColor = Colors.red,
    this.blockMargin = 16,
  });
}

/// Mermaid 节点配置
class MermaidNodeConfig {
  /// 默认高度
  final double defaultHeight;

  /// 是否在桌面端启用外部预览
  final bool desktopExternalPreview;

  /// 加载超时
  final Duration loadTimeout;

  const MermaidNodeConfig({
    this.defaultHeight = 300,
    this.desktopExternalPreview = true,
    this.loadTimeout = const Duration(seconds: 10),
  });
}

/// Thinking 块节点配置
class ThinkingNodeConfig {
  /// 背景色 (亮色)
  final Color lightBackground;

  /// 背景色 (暗色)
  final Color darkBackground;

  /// 边框颜色
  final Color borderColor;

  /// 最大高度
  final double maxHeight;

  /// 标题文本
  final String headerText;

  const ThinkingNodeConfig({
    this.lightBackground = const Color(0x1A3B82F6),
    this.darkBackground = const Color(0x331D4ED8),
    this.borderColor = const Color(0x33493BFF),
    this.maxHeight = 160,
    this.headerText = 'Thinking',
  });

  /// 根据 isDark 获取背景色
  Color getBackground(bool isDark) {
    return isDark ? darkBackground : lightBackground;
  }
}
