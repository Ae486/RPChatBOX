/// INPUT: Markdown 文本 + 主题深浅 +（可选）流式标记/链接交互
/// OUTPUT: OwuiSmoothMarkdown - 基于 flutter_smooth_markdown 的统一渲染入口
/// POS: UI 层 / Markdown / Owui - 共享 smooth 渲染模块（lab 与生产同源）
///
/// 由 markdown 试验场(lab)验证后的渲染规格提升而来：块 builder(数学/mermaid/代码/
/// admonition/标题/表格/链接)、图片来源分支、`<error>` 协议块均集中于此，生产与 lab 共用。
/// 每次 build 全量重解析(见包 SmoothMarkdown.build)——已实测优于旧稳定前缀栈，故精简直喂。
library;

import 'dart:async';
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderRepaintBoundary;
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter_smooth_markdown/flutter_smooth_markdown.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';
// 以下三方包均为 smooth_markdown 的传递依赖；模块直接复用其能力(API 取自包源码)。
// ignore: depend_on_referenced_packages
import 'package:flutter_math_fork/flutter_math.dart' show Math, MathStyle;
// ignore: depend_on_referenced_packages
import 'package:highlight/highlight.dart' show highlight, Node;
// ignore: depend_on_referenced_packages
import 'package:flutter_highlight/themes/github.dart' as hl_light;
// ignore: depend_on_referenced_packages
import 'package:flutter_highlight/themes/vs2015.dart' as hl_dark;

import '../image_clipboard_win.dart';
import '../owui_icons.dart';
import '../owui_image_viewer.dart';

part 'owui_smooth_builders.dart';
part 'owui_smooth_image.dart';
part 'owui_smooth_error.dart';

/// 展开/收起动画时长（毫秒）。
const int _kExpandMs = 220;

/// 统一圆角半径。
const double _kRadius = 10;

/// 表格最小宽度(逻辑像素)：可用宽度小于它时表格固定此宽+横向滚动，否则铺满。
const double _kTableMinWidth = 480;

/// 解析配置：启用 LaTeX 与 emoji（与 lab 验证一致）。
const MarkdownConfig _owuiSmoothConfig =
    MarkdownConfig(enableLatex: true, enableEmoji: true);

/// 统一的 markdown 渲染组件：生产 OwuiMarkdown 与 lab 试验场共用的渲染规格。
///
/// 负责装配 plugins(think/tool_call/artifact/mermaid/admonition/error) + 自建 builder +
/// 图片来源分支 + 链接打开，屏蔽 flutter_smooth_markdown 的装配细节。
class OwuiSmoothMarkdown extends StatelessWidget {
  const OwuiSmoothMarkdown({
    super.key,
    required this.text,
    required this.isDark,
    this.selectable = true,
    this.isStreaming = false,
    this.useEnhancedComponents = true,
    this.enableCache = false,
    this.contentKey,
    this.onTapLink,
  });

  /// 待渲染的 markdown 文本（调用方已完成 think 剥离/围栏归一等预处理）。
  final String text;

  /// 主题深浅：决定 styleSheet 与各 builder 的取色。
  final bool isDark;

  /// 是否可选中：生产流式时传 false 规避 SelectionArea 布局 bug。
  final bool selectable;

  /// 是否流式：流式中裁掉「未成型表格头」避免 raw `|x|x|` 泄漏；final 不裁。
  final bool isStreaming;

  /// 是否启用增强组件（代码/引用/链接/标题的增强 builder）。
  final bool useEnhancedComponents;

  /// 是否启用包内 LRU 解析缓存。流式/频繁变更内容应关闭。
  final bool enableCache;

  /// 内容 key：lab 重放时用 ValueKey(session) 强制整树重建。
  final Key? contentKey;

  /// 链接点击回调；默认用系统浏览器打开外链。
  final void Function(String url)? onTapLink;

  @override
  Widget build(BuildContext context) {
    final src = _ensureErrorBlockBoundary(
      _stripIncompleteTableHead(text, isStreaming),
    );
    final imageOrder = _extractImageUrls(src);
    return SmoothMarkdown(
      key: contentKey,
      data: src,
      styleSheet:
          isDark ? MarkdownStyleSheet.dark() : MarkdownStyleSheet.light(),
      config: _owuiSmoothConfig,
      useEnhancedComponents: useEnhancedComponents,
      selectable: selectable,
      enableCache: enableCache,
      plugins: _buildOwuiSmoothPlugins(),
      builderRegistry: _buildOwuiSmoothBuilders(isDark),
      onTapLink: onTapLink ?? _defaultOnTapLink,
      imageBuilder: (url, alt, title) {
        final i = imageOrder.indexOf(url);
        return _SmoothImage(url: url, alt: alt, index: i >= 0 ? i + 1 : 0);
      },
    );
  }
}

/// 默认链接处理：系统浏览器打开（解析失败则忽略）。
void _defaultOnTapLink(String url) {
  final uri = Uri.tryParse(url);
  if (uri == null) return;
  unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
}

/// 解析插件：think / tool_call / artifact / mermaid / admonition / error。
/// admonition/mermaid 由包提供 plugin 但缺 builder(见 _buildOwuiSmoothBuilders)；
/// error 为生产自定义协议块(见 owui_smooth_error)。
ParserPluginRegistry _buildOwuiSmoothPlugins() => ParserPluginRegistry()
  ..register(const ThinkingPlugin())
  ..register(const ToolCallPlugin())
  ..register(const ArtifactPlugin())
  ..register(const MermaidPlugin())
  ..register(const AdmonitionPlugin())
  ..register(const _OwuiErrorPlugin());

/// 自建 builder 注册表（合并在 enhanced 内置之上、优先级最高）。
/// 仅对「缺失/不达标」的块自建：math(补 onErrorFallback)、mermaid(头部栏)、
/// code(独立头部栏+折叠)、admonition(语义色块)、header(去左竖线)、table(最小宽+横向滚动)、
/// link(hover 不改行高)、owui_error(生产错误块)。
BuilderRegistry _buildOwuiSmoothBuilders(bool dark) => BuilderRegistry()
  ..register('inline_math', const _SafeInlineMathBuilder())
  ..register('block_math', const _SafeBlockMathBuilder())
  ..register('mermaid', _MermaidBuilder(dark: dark))
  ..register('code_block', const _CodeBlockBuilder())
  ..register('admonition', const _AdmonitionBuilder())
  ..register('header', const _HeaderBuilder())
  ..register('table', const _TableBuilder())
  ..register('link', const _LinkBuilder())
  ..register('owui_error', const _OwuiErrorBuilder());

/// 确保 `<error ...>` 标签前有空行，使其作为独立块被 _OwuiErrorPlugin 解析。
/// 必要性：包段落解析器会贪婪吞并仅以单个 `\n` 相邻的 `<error>` 行(它只在
/// header/code/quote/list/hr/table 处断行)。生产以 `$body\n$errorTag` 追加，故需补空行。
String _ensureErrorBlockBoundary(String src) {
  if (!src.contains('<error')) return src;
  // 仅匹配真实错误标签起始(`<error ` 后接属性)，避免误伤代码块内的字面量。
  return src.replaceAllMapped(
    RegExp(r'([^\n])\n(<error\s)'),
    (m) => '${m.group(1)}\n\n${m.group(2)}',
  );
}

/// 流式专用：裁掉「分隔行 |---| 尚未到达」的末尾表格头，避免引擎当普通段落显示 raw `|x|x|`。
/// final/静态不裁。其余临时语法错误由各 builder 的 onErrorFallback 兜空白。
String _stripIncompleteTableHead(String src, bool isStreaming) {
  if (!isStreaming || src.isEmpty) return src;
  final lines = src.split('\n');
  var t = lines.length;
  var sawSep = false;
  while (t > 0) {
    final ln = lines[t - 1];
    if (ln.trim().isEmpty || !ln.contains('|')) break; // 段落边界 / 非表格行
    if (_isTableSeparator(ln)) {
      sawSep = true;
      break;
    }
    t--;
  }
  if (sawSep || t == lines.length) return src;
  return lines.sublist(0, t).join('\n');
}

/// 表格分隔行判定：形如 `| --- | :--: |`，仅由 | : - 空格组成且含 - 与 |。
bool _isTableSeparator(String line) {
  final s = line.trim();
  return s.contains('|') &&
      s.contains('-') &&
      RegExp(r'^\|?[\s:|-]+\|?$').hasMatch(s);
}
