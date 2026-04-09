/// INPUT: Markdown 文本 + UI Tokens/主题 +（可选）图片/链接交互
/// OUTPUT: OwuiMarkdown - Markdown 渲染（表格/代码块/LaTeX/图片/Mermaid 扩展）
/// POS: UI 层 / Markdown / Owui - 主 Markdown 渲染入口

import 'dart:convert';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
import 'package:markdown/markdown.dart' as m;
import 'package:markdown_widget/markdown_widget.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../rendering/markdown_stream/language_utils.dart';
import '../../rendering/markdown_stream/stable_prefix_parser.dart';
import 'code_block.dart';
import 'mermaid_block.dart';
import 'owui_icons.dart';
import 'owui_tokens_ext.dart';
import 'palette.dart';
import 'stable_body.dart';

const String _latexTag = 'latex';
const String _errorTag = 'owui_error';

final SpanNodeGeneratorWithTag owuiLatexGenerator = SpanNodeGeneratorWithTag(
  tag: _latexTag,
  generator: (e, config, visitor) =>
      _OwuiLatexNode(e.attributes, e.textContent, config),
);

final SpanNodeGeneratorWithTag owuiErrorGenerator = SpanNodeGeneratorWithTag(
  tag: _errorTag,
  generator: (e, config, visitor) =>
      _OwuiErrorNode(e.attributes, e.textContent, config),
);

/// 匹配 <error type="..." ...>...</error> 标签
class OwuiErrorSyntax extends m.InlineSyntax {
  OwuiErrorSyntax() : super(r'<error\s+[^>]*>[\s\S]*?</error>');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final matchValue = match.group(0)!;

    // 解析属性
    final typeMatch = RegExp(r'type="(\w+)"').firstMatch(matchValue);
    final codeMatch = RegExp(r'code="(\d+)"').firstMatch(matchValue);
    final briefMatch = RegExp(r'brief="([^"]*)"').firstMatch(matchValue);

    // 提取内容
    final contentMatch = RegExp(r'>([^<]*)</error>').firstMatch(matchValue);
    final content = contentMatch?.group(1) ?? '';

    final el = m.Element.text(_errorTag, matchValue);
    el.attributes['errorType'] = typeMatch?.group(1) ?? 'unknown';
    el.attributes['errorCode'] = codeMatch?.group(1) ?? '';
    el.attributes['brief'] = _unescapeXml(briefMatch?.group(1) ?? '');
    el.attributes['details'] = _unescapeXml(content);
    parser.addNode(el);
    return true;
  }

  static String _unescapeXml(String input) {
    return input
        .replaceAll('&quot;', '"')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&amp;', '&');
  }
}

class OwuiLatexSyntax extends m.InlineSyntax {
  OwuiLatexSyntax() : super(r'(\$\$[\s\S]+?\$\$)|(\$[^\$\n]+?\$)');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final input = match.input;
    final matchValue = input.substring(match.start, match.end);

    String content = '';
    bool isInline = true;
    const blockSyntax = r'$$';
    const inlineSyntax = r'$';

    if (matchValue.startsWith(blockSyntax) &&
        matchValue.endsWith(blockSyntax) &&
        matchValue != blockSyntax) {
      content = matchValue.substring(2, matchValue.length - 2);
      isInline = false;
    } else if (matchValue.startsWith(inlineSyntax) &&
        matchValue.endsWith(inlineSyntax) &&
        matchValue != inlineSyntax) {
      content = matchValue.substring(1, matchValue.length - 1);
    }

    final el = m.Element.text(_latexTag, matchValue);
    el.attributes['content'] = content;
    el.attributes['isInline'] = '$isInline';
    parser.addNode(el);
    return true;
  }
}

class _OwuiContextMenuWrapper extends StatelessWidget {
  final String title;
  final String copyText;
  final Widget child;

  const _OwuiContextMenuWrapper({
    required this.title,
    required this.copyText,
    required this.child,
  });

  Future<void> _copy(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: copyText));
    if (!context.mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(SnackBar(content: Text('$title 已复制')));
  }

  void _showMenu(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(title: Text(title), subtitle: const Text('长按块级内容的快捷操作')),
              ListTile(
                leading: const Icon(OwuiIcons.copy),
                title: const Text('复制'),
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await _copy(context);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.deferToChild,
      onLongPress: () => _showMenu(context),
      onSecondaryTap: () => _showMenu(context),
      child: child,
    );
  }
}

class _OwuiLatexNode extends SpanNode {
  final Map<String, String> attributes;
  final String textContent;
  final MarkdownConfig config;

  _OwuiLatexNode(this.attributes, this.textContent, this.config);

  @override
  InlineSpan build() {
    final content = attributes['content'] ?? '';
    final isInline = attributes['isInline'] == 'true';
    final style = parentStyle ?? config.p.textStyle;
    if (content.isEmpty) return TextSpan(style: style, text: textContent);

    final latex = Math.tex(
      content,
      mathStyle: MathStyle.text,
      textStyle: style,
      textScaleFactor: 1,
      onErrorFallback: (_) {
        return Text(textContent, style: style.copyWith(color: Colors.red));
      },
    );

    final child = !isInline
        ? _OwuiContextMenuWrapper(
            title: 'LaTeX',
            copyText: content,
            child: Container(
              width: double.infinity,
              margin: const EdgeInsets.symmetric(vertical: 16),
              child: Center(child: latex),
            ),
          )
        : latex;

    return WidgetSpan(alignment: PlaceholderAlignment.middle, child: child);
  }
}

/// Error 标签渲染节点
class _OwuiErrorNode extends SpanNode {
  final Map<String, String> attributes;
  final String textContent;
  final MarkdownConfig config;

  _OwuiErrorNode(this.attributes, this.textContent, this.config);

  @override
  InlineSpan build() {
    final errorType = attributes['errorType'] ?? 'unknown';
    final errorCodeStr = attributes['errorCode'] ?? '';
    final errorCode = errorCodeStr.isNotEmpty ? int.tryParse(errorCodeStr) : null;
    final brief = attributes['brief'] ?? '';
    final details = attributes['details'] ?? '';

    final child = _OwuiErrorBlock(
      errorType: errorType,
      errorCode: errorCode,
      brief: brief,
      details: details,
    );

    return WidgetSpan(
      alignment: PlaceholderAlignment.middle,
      child: child,
    );
  }
}

/// Error 块渲染组件（用于 Markdown 中的静态渲染）
class _OwuiErrorBlock extends StatefulWidget {
  final String errorType;
  final int? errorCode;
  final String brief;
  final String details;

  const _OwuiErrorBlock({
    required this.errorType,
    required this.errorCode,
    required this.brief,
    required this.details,
  });

  @override
  State<_OwuiErrorBlock> createState() => _OwuiErrorBlockState();
}

class _OwuiErrorBlockState extends State<_OwuiErrorBlock> {
  bool _expanded = false;

  String get _firstLine {
    if (widget.errorCode != null) {
      return 'ERROR ${widget.errorCode}';
    }
    return switch (widget.errorType) {
      'upstream' => 'API 错误',
      'connection' => '连接错误',
      'timeout' => '超时',
      'parse' => '解析错误',
      'backend' => '后端错误',
      _ => '错误',
    };
  }

  String get _secondLine {
    final brief = widget.brief.trim();
    if (brief.isEmpty) {
      final details = widget.details.trim();
      if (details.length <= 40) return details;
      return '${details.substring(0, 37)}...';
    }
    if (brief.length <= 40) return brief;
    return '${brief.substring(0, 37)}...';
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor = isDark
        ? const Color(0xFF2A1A1A)
        : const Color(0xFFFEECEC);
    final borderColor = isDark
        ? Colors.red.withValues(alpha: 0.4)
        : Colors.red.withValues(alpha: 0.3);
    final iconColor = isDark ? Colors.red[300] : Colors.red[600];
    final textColor = isDark
        ? const Color(0xFFE5A0A0)
        : const Color(0xFF991B1B);
    final detailsColor = isDark
        ? const Color(0xFFD1D5DB)
        : const Color(0xFF4B5563);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Icon(OwuiIcons.error, size: 28, color: iconColor),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _firstLine,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: textColor,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          _secondLine,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: textColor.withValues(alpha: 0.85),
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Icon(
                    _expanded ? OwuiIcons.expandLess : OwuiIcons.expandMore,
                    size: 20,
                    color: textColor.withValues(alpha: 0.7),
                  ),
                ],
              ),
            ),
          ),
          if (_expanded && widget.details.trim().isNotEmpty) ...[
            Divider(height: 1, thickness: 1, color: borderColor),
            Padding(
              padding: const EdgeInsets.all(12),
              child: SelectableText(
                widget.details,
                style: TextStyle(
                  fontSize: 12,
                  color: detailsColor,
                  height: 1.5,
                  fontFamily: 'monospace',
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _OwuiMarkdownTableWrapper extends StatefulWidget {
  final Widget child;
  final bool isDark;

  const _OwuiMarkdownTableWrapper({required this.child, required this.isDark});

  @override
  State<_OwuiMarkdownTableWrapper> createState() =>
      _OwuiMarkdownTableWrapperState();
}

class _OwuiMarkdownTableWrapperState extends State<_OwuiMarkdownTableWrapper> {
  late final ScrollController _horizontalController;

  @override
  void initState() {
    super.initState();
    _horizontalController = ScrollController();
  }

  @override
  void dispose() {
    _horizontalController.dispose();
    super.dispose();
  }

  bool get _isDesktop {
    if (kIsWeb) return false;
    return defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.linux ||
        defaultTargetPlatform == TargetPlatform.macOS;
  }

  @override
  Widget build(BuildContext context) {
    final borderColor = OwuiPalette.borderSubtle(context);
    final bg = widget.isDark ? const Color(0xFF0D0F14) : Colors.white;
    final radius = BorderRadius.circular(10);
    final shape = RoundedRectangleBorder(
      borderRadius: radius,
      side: BorderSide(color: borderColor),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Material(
        color: bg,
        shape: shape,
        clipBehavior: Clip.hardEdge,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final scroller = ScrollConfiguration(
              behavior: ScrollConfiguration.of(
                context,
              ).copyWith(scrollbars: false),
              child: SingleChildScrollView(
                controller: _horizontalController,
                scrollDirection: Axis.horizontal,
                physics: const ClampingScrollPhysics(),
                child: ConstrainedBox(
                  constraints: BoxConstraints(minWidth: constraints.maxWidth),
                  child: widget.child,
                ),
              ),
            );

            if (!_isDesktop) return scroller;

            return Scrollbar(
              controller: _horizontalController,
              thumbVisibility: true,
              interactive: true,
              child: scroller,
            );
          },
        ),
      ),
    );
  }
}

class OwuiMarkdown extends StatelessWidget {
  final String text;
  final bool isDark;
  final bool isStreaming;
  final Object? stableCacheKey;

  /// P0-3: 启用平滑流式代码块（高亮节流 + 行号对齐等）。
  final bool enableSmoothCodeBlock;

  /// P0-4: 启用 Mermaid 稳定占位（固定高度，避免 WebView 跳变）。
  final bool enableSmoothMermaid;

  /// 启用增量淡入（仅对“尾巴纯文本”生效）。
  final bool enableFadeIn;

  /// 增量淡入动画时长。
  final Duration fadeInDuration;

  /// 增量淡入动画起始透明度。
  final double fadeInStartOpacity;

  const OwuiMarkdown({
    super.key,
    required this.text,
    required this.isDark,
    required this.isStreaming,
    this.stableCacheKey,
    this.enableSmoothCodeBlock = false,
    this.enableSmoothMermaid = false,
    this.enableFadeIn = false,
    this.fadeInDuration = const Duration(milliseconds: 150),
    this.fadeInStartOpacity = 0.3,
  });

  static const StablePrefixParser _stablePrefixParser = StablePrefixParser();

  @visibleForTesting
  static String debugStripInternalThinkBlocks(String source) {
    var sanitized = source;

    for (final tagName in const ['thinking', 'think', 'thought', 'thoughts']) {
      sanitized = sanitized.replaceAll(
        RegExp('<$tagName>[\\s\\S]*?</$tagName>', dotAll: true),
        '',
      );
      sanitized = sanitized.replaceAll('<$tagName>', '');
      sanitized = sanitized.replaceAll('</$tagName>', '');
    }

    return sanitized;
  }

  String _stripInternalThinkBlocks(String source) =>
      debugStripInternalThinkBlocks(source);

  ({String stable, String tail}) _splitStableMarkdown(String source) =>
      _stablePrefixParser.split(_stripInternalThinkBlocks(source));

  /// `markdown_widget`'s code block node expects a `<code class="language-...">`
  /// attribute for some code blocks. Indented code blocks (4-space blocks)
  /// typically don't have this attribute, causing noisy logs and, in some cases,
  /// downstream rendering issues. Convert such blocks into fenced blocks with a
  /// default language.
  String _normalizeIndentedCodeBlocks(String markdown) {
    final lines = markdown.split('\n');
    final out = <String>[];

    var inFence = false;
    var fenceChar = '';
    var fenceLen = 0;
    var prevBlank = true;

    bool isIndented(String line) => line.startsWith('\t') || line.startsWith('    ');
    String leadingIndent(String line) =>
        RegExp(r'^[ \t]+').firstMatch(line)?.group(0) ?? '';

    final fenceRe = RegExp(r'^(\s*)(```+|~~~+)(.*)$');

    var i = 0;
    while (i < lines.length) {
      final line = lines[i];
      final trimmed = line.trimRight();

      final m = fenceRe.firstMatch(line);
      if (m != null) {
        final fence = m.group(2)!;
        final rest = (m.group(3) ?? '').trim();
        if (!inFence) {
          inFence = true;
          fenceChar = fence[0];
          fenceLen = fence.length;
        } else {
          final isClosing =
              fence[0] == fenceChar && fence.length >= fenceLen && rest.isEmpty;
          if (isClosing) {
            inFence = false;
            fenceChar = '';
            fenceLen = 0;
          }
        }
        out.add(line);
        prevBlank = trimmed.isEmpty;
        i++;
        continue;
      }

      if (!inFence && prevBlank && isIndented(line)) {
        final indent = leadingIndent(line);
        out.add('$indent```plain');
        while (i < lines.length) {
          final l = lines[i];
          if (l.trim().isEmpty) {
            out.add('');
            i++;
            continue;
          }
          if (!l.startsWith(indent)) break;
          out.add(l.substring(indent.length));
          i++;
        }
        out.add('$indent```');
        prevBlank = true;
        continue;
      }

      out.add(line);
      prevBlank = trimmed.isEmpty;
      i++;
    }

    return out.join('\n');
  }

  String _preprocessMarkdownForMarkdownWidget(String markdown) {
    var safe = markdown;
    safe = _normalizeIndentedCodeBlocks(safe);
    safe = _ensureFenceLanguage(safe);
    if (safe.endsWith('- *')) {
      safe = safe.replaceFirst(RegExp(r'- \*$'), r'- \\*');
    }

    safe = safe.replaceFirst(RegExp(r'\n\s*[-*+]\s*$'), '\n');
    safe = safe.replaceFirst(RegExp(r'\n\s*-\s*$'), '\n');
    safe = safe.replaceFirst(RegExp(r'\n\s*>\s*$'), '\n');

    return safe;
  }

  /// Workaround for `markdown_widget`'s fenced code parsing:
  /// When a fence has no language (```\\n), it may log "get language error" and
  /// the built-in highlighter can crash on some platforms. We normalize such
  /// fences to `plain` so the `<code class=\"language-plain\">` attribute is
  /// always present.
  String _ensureFenceLanguage(String markdown) {
    final lines = markdown.split('\n');
    final out = <String>[];

    var inFence = false;
    var fenceChar = '';
    var fenceLen = 0;

    final fenceRe = RegExp(r'^(\s*)(```+|~~~+)(.*)$');

    for (final line in lines) {
      final m = fenceRe.firstMatch(line);
      if (m == null) {
        out.add(line);
        continue;
      }

      final indent = m.group(1) ?? '';
      final fence = m.group(2)!;
      final rest = (m.group(3) ?? '').trim();

      if (!inFence) {
        // Opening fence.
        inFence = true;
        fenceChar = fence[0];
        fenceLen = fence.length;
        if (rest.isEmpty) {
          out.add('$indent${fence}plain');
        } else {
          out.add(line);
        }
        continue;
      }

      // Closing fence (must match marker type and be at least as long).
      final isClosing =
          fence[0] == fenceChar && fence.length >= fenceLen && rest.isEmpty;
      if (isClosing) {
        inFence = false;
        fenceChar = '';
        fenceLen = 0;
      }
      out.add(line);
    }

    return out.join('\n');
  }

  Widget _buildMarkdownWidget(BuildContext context, String raw) {
    final safeText = _preprocessMarkdownForMarkdownWidget(
      _stripInternalThinkBlocks(raw),
    );
    final config = isDark
        ? MarkdownConfig.darkConfig
        : MarkdownConfig.defaultConfig;

    // 获取 UI 缩放系数
    final uiScale = context.owui.uiScale;

    // 基础文本颜色
    final textColor = isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827);
    final secondaryColor = isDark ? const Color(0xFFD1D5DB) : const Color(0xFF374151);

    Widget codeBuilder(String code, String language) {
      final inferred = inferCodeLanguage(
        declaredLanguage: language.trim().toLowerCase(),
        code: code,
      );
      if (inferred == 'mermaid') {
        return OwuiMermaidBlock(
          mermaidCode: code,
          isDark: isDark,
          isStreaming: false,
        );
      }
      return OwuiCodeBlock(
        code: code,
        language: inferred,
        isDark: isDark,
        isStreaming: false,
        // 非流式代码块也启用视觉行号（窗口变窄时行号随换行动态增加）
        enableSmoothStreaming: enableSmoothCodeBlock,
      );
    }

    // 段落配置（基础文本样式）
    final pConfig = PConfig(
      textStyle: TextStyle(
        fontSize: 15 * uiScale,
        height: 1.6,
        color: textColor,
      ),
    );

    // 标题配置
    final h1Config = H1Config(
      style: TextStyle(
        fontSize: 28 * uiScale,
        fontWeight: FontWeight.bold,
        height: 1.4,
        color: textColor,
      ),
    );
    final h2Config = H2Config(
      style: TextStyle(
        fontSize: 24 * uiScale,
        fontWeight: FontWeight.bold,
        height: 1.4,
        color: textColor,
      ),
    );
    final h3Config = H3Config(
      style: TextStyle(
        fontSize: 20 * uiScale,
        fontWeight: FontWeight.w600,
        height: 1.4,
        color: textColor,
      ),
    );
    final h4Config = H4Config(
      style: TextStyle(
        fontSize: 18 * uiScale,
        fontWeight: FontWeight.w600,
        height: 1.4,
        color: textColor,
      ),
    );
    final h5Config = H5Config(
      style: TextStyle(
        fontSize: 16 * uiScale,
        fontWeight: FontWeight.w600,
        height: 1.4,
        color: textColor,
      ),
    );
    final h6Config = H6Config(
      style: TextStyle(
        fontSize: 15 * uiScale,
        fontWeight: FontWeight.w600,
        height: 1.4,
        color: textColor,
      ),
    );

    final blockquoteConfig = BlockquoteConfig(
      sideColor: isDark ? const Color(0xFF60A5FA) : const Color(0xFF1A73E8),
      textColor: secondaryColor,
      sideWith: 4,
      padding: EdgeInsets.fromLTRB(12 * uiScale, 10 * uiScale, 12 * uiScale, 10 * uiScale),
      margin: EdgeInsets.fromLTRB(0, 10 * uiScale, 0, 10 * uiScale),
    );

    final tableConfig = TableConfig(
      // 去除内部网格线，仅保留外层圆角边框
      border: const TableBorder(),
      headerRowDecoration: BoxDecoration(
        color: isDark ? const Color(0xFF141821) : const Color(0xFFF3F4F6),
      ),
      headerStyle: TextStyle(
        fontSize: 15 * uiScale,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
      ),
      bodyStyle: TextStyle(
        fontSize: 15 * uiScale,
        color: isDark ? const Color(0xFFD1D5DB) : const Color(0xFF111827),
      ),
      headPadding: EdgeInsets.fromLTRB(10 * uiScale, 8 * uiScale, 10 * uiScale, 8 * uiScale),
      bodyPadding: EdgeInsets.fromLTRB(10 * uiScale, 8 * uiScale, 10 * uiScale, 8 * uiScale),
      wrapper: (child) => _OwuiMarkdownTableWrapper(isDark: isDark, child: child),
    );

    // 图片配置
    final imgConfig = ImgConfig(
      builder: (url, attributes) {
        return _OwuiMarkdownImage(
          url: url,
          attributes: attributes,
          isDark: isDark,
        );
      },
    );

    // 流式输出时禁用选择功能，避免 SelectionArea 布局 bug
    // 参见: https://github.com/nickvdyck/MarkdownWidget/issues/xxx
    return MarkdownWidget(
      data: safeText,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      selectable: !isStreaming, // 流式时禁用选择，避免 RenderBox 布局错误
      config: config.copy(
        configs: [
          pConfig,
          h1Config,
          h2Config,
          h3Config,
          h4Config,
          h5Config,
          h6Config,
          LinkConfig(
            style: TextStyle(
              fontSize: 15 * uiScale,
              color: isDark ? const Color(0xFF8AB4F8) : const Color(0xFF1A73E8),
              decoration: TextDecoration.underline,
            ),
            onTap: (url) async {
              final uri = Uri.tryParse(url);
              if (uri == null) return;
              await launchUrl(uri, mode: LaunchMode.externalApplication);
            },
          ),
          PreConfig(
            theme: isDark ? monokaiSublimeTheme : githubTheme,
            builder: codeBuilder,
          ),
          blockquoteConfig,
          tableConfig,
          imgConfig,
        ],
      ),
      markdownGenerator: MarkdownGenerator(
        generators: [owuiLatexGenerator, owuiErrorGenerator],
        inlineSyntaxList: [OwuiLatexSyntax(), OwuiErrorSyntax()],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final sanitizedText = _stripInternalThinkBlocks(text);

    // 获取 UI 缩放系数
    final uiScale = context.owui.uiScale;
    final textColor = isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827);

    // 用于流式渲染的尾部文本样式
    final plainTextStyle = TextStyle(
      fontSize: 15 * uiScale,
      height: 1.6,
      color: textColor,
    );

    final parts = _splitStableMarkdown(sanitizedText);
    final needsStableRenderer = isStreaming || parts.tail.isNotEmpty;
    if (!needsStableRenderer) {
      return _buildMarkdownWidget(context, sanitizedText);
    }

    return OwuiStableBody(
      text: sanitizedText,
      splitStableMarkdown: _splitStableMarkdown,
      stableCacheKey: stableCacheKey,
      markdown: (markdownText) => _buildMarkdownWidget(context, markdownText),
      plainTextStyle: plainTextStyle,
      enableFadeIn: enableFadeIn && isStreaming,
      fadeInDuration: fadeInDuration,
      fadeInStartOpacity: fadeInStartOpacity,
      streamingCodeBlock:
          ({required language, required code, required isClosed}) {
            final inferred = inferCodeLanguage(
              declaredLanguage: language,
              code: code,
            );
            final isStreamingCode = isStreaming && !isClosed;
            if (inferred == 'mermaid') {
              return OwuiMermaidBlock(
                mermaidCode: code,
                isDark: isDark,
                isStreaming: isStreamingCode,
                enableStablePlaceholder: isStreamingCode && enableSmoothMermaid,
              );
            }
            return OwuiCodeBlock(
              code: code,
              language: inferred.isEmpty ? 'plaintext' : inferred,
              isDark: isDark,
              isStreaming: isStreamingCode,
              // 视觉行号不依赖流式状态，只要 enableSmoothCodeBlock 启用就生效
              enableSmoothStreaming: enableSmoothCodeBlock,
            );
          },
      // LaTeX 块流式容器
      streamingLatexBlock: ({required content, required isClosed}) {
        return _StreamingLatexContainer(
          content: content,
          isClosed: isClosed,
          isDark: isDark,
        );
      },
      // Think 块流式容器
      streamingThinkBlock: ({required content, required isClosed}) {
        return _StreamingThinkContainer(
          content: content,
          isClosed: isClosed,
          isDark: isDark,
        );
      },
      // Error 块流式容器
      streamingErrorBlock: ({
        required errorType,
        required errorCode,
        required brief,
        required details,
        required isClosed,
      }) {
        return _StreamingErrorContainer(
          errorType: errorType,
          errorCode: errorCode,
          brief: brief,
          details: details,
          isClosed: isClosed,
          isDark: isDark,
        );
      },
    );
  }
}

/// 流式 LaTeX 块容器
class _StreamingLatexContainer extends StatelessWidget {
  final String content;
  final bool isClosed;
  final bool isDark;

  const _StreamingLatexContainer({
    required this.content,
    required this.isClosed,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final bgColor = isDark ? const Color(0xFF1A1C20) : const Color(0xFFF5F5F5);
    final borderColor = isDark ? Colors.white24 : Colors.black12;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (!isClosed)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        isDark ? Colors.white54 : Colors.black45,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'LaTeX...',
                    style: TextStyle(
                      fontSize: 12,
                      color: isDark ? Colors.white54 : Colors.black45,
                    ),
                  ),
                ],
              ),
            ),
          if (content.trim().isNotEmpty)
            Math.tex(
              content.trim(),
              mathStyle: MathStyle.display,
              textStyle: TextStyle(
                fontSize: 16,
                color: isDark ? Colors.white : Colors.black87,
              ),
              onErrorFallback: (err) => Text(
                content,
                style: TextStyle(
                  fontSize: 14,
                  color: isDark ? Colors.red[300] : Colors.red[700],
                  fontFamily: 'monospace',
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// 流式 Think 块容器
class _StreamingThinkContainer extends StatelessWidget {
  final String content;
  final bool isClosed;
  final bool isDark;

  const _StreamingThinkContainer({
    required this.content,
    required this.isClosed,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final bgColor = isDark ? const Color(0xFF1A1C20) : const Color(0xFFFFF8E1);
    final textColor = isDark ? const Color(0xFFD1D5DB) : const Color(0xFF5D4037);
    final headerColor = isDark ? Colors.amber[300] : Colors.amber[700];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isDark ? Colors.amber.withValues(alpha: 0.3) : Colors.amber.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(OwuiIcons.lightbulb, size: 16, color: headerColor),
              const SizedBox(width: 6),
              Text(
                '思考中',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: headerColor,
                ),
              ),
              if (!isClosed) ...[
                const SizedBox(width: 8),
                SizedBox(
                  width: 12,
                  height: 12,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(headerColor!),
                  ),
                ),
              ],
            ],
          ),
          if (content.trim().isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              content,
              style: TextStyle(
                fontSize: 14,
                color: textColor,
                height: 1.5,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 流式 Error 块容器 - 可折叠错误显示
class _StreamingErrorContainer extends StatefulWidget {
  final String errorType;
  final int? errorCode;
  final String brief;
  final String details;
  final bool isClosed;
  final bool isDark;

  const _StreamingErrorContainer({
    required this.errorType,
    required this.errorCode,
    required this.brief,
    required this.details,
    required this.isClosed,
    required this.isDark,
  });

  @override
  State<_StreamingErrorContainer> createState() => _StreamingErrorContainerState();
}

class _StreamingErrorContainerState extends State<_StreamingErrorContainer> {
  bool _expanded = false;

  String get _firstLine {
    if (widget.errorCode != null) {
      return 'ERROR ${widget.errorCode}';
    }
    return switch (widget.errorType) {
      'upstream' => 'API 错误',
      'connection' => '连接错误',
      'timeout' => '超时',
      'parse' => '解析错误',
      'backend' => '后端错误',
      _ => '错误',
    };
  }

  String get _secondLine {
    final brief = widget.brief.trim();
    if (brief.isEmpty) {
      // 从 details 提取简略信息
      final details = widget.details.trim();
      if (details.length <= 40) return details;
      return '${details.substring(0, 37)}...';
    }
    if (brief.length <= 40) return brief;
    return '${brief.substring(0, 37)}...';
  }

  @override
  Widget build(BuildContext context) {
    final bgColor = widget.isDark
        ? const Color(0xFF2A1A1A)
        : const Color(0xFFFEECEC);
    final borderColor = widget.isDark
        ? Colors.red.withValues(alpha: 0.4)
        : Colors.red.withValues(alpha: 0.3);
    final iconColor = widget.isDark
        ? Colors.red[300]
        : Colors.red[600];
    final textColor = widget.isDark
        ? const Color(0xFFE5A0A0)
        : const Color(0xFF991B1B);
    final detailsColor = widget.isDark
        ? const Color(0xFFD1D5DB)
        : const Color(0xFF4B5563);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // 头部：图标 + 两行信息 + 展开箭头
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  // 左侧图标
                  Icon(
                    OwuiIcons.error,
                    size: 28,
                    color: iconColor,
                  ),
                  const SizedBox(width: 10),
                  // 中间两行文本
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _firstLine,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: textColor,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          _secondLine,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: textColor.withValues(alpha: 0.85),
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  // 右侧展开箭头
                  Icon(
                    _expanded ? OwuiIcons.expandLess : OwuiIcons.expandMore,
                    size: 20,
                    color: textColor.withValues(alpha: 0.7),
                  ),
                ],
              ),
            ),
          ),
          // 展开后的详情
          if (_expanded && widget.details.trim().isNotEmpty) ...[
            Divider(
              height: 1,
              thickness: 1,
              color: borderColor,
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: SelectableText(
                widget.details,
                style: TextStyle(
                  fontSize: 12,
                  color: detailsColor,
                  height: 1.5,
                  fontFamily: 'monospace',
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Markdown 图片组件
class _OwuiMarkdownImage extends StatelessWidget {
  final String url;
  final Map<String, String> attributes;
  final bool isDark;

  const _OwuiMarkdownImage({
    required this.url,
    required this.attributes,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final alt = attributes['alt'] ?? '';

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: GestureDetector(
        onTap: () => _showImagePreview(context),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480, maxHeight: 400),
            child: _buildInlineImage(alt),
          ),
        ),
      ),
    );
  }

  Widget _buildInlineImage(String alt) {
    final dataBytes = _tryDecodeDataImage(url);
    if (dataBytes != null) {
      return Image.memory(
        dataBytes,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => _buildError(_errorText(alt)),
      );
    }

    final file = _tryResolveLocalFile(url);
    if (file != null) {
      return Image.file(
        file,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => _buildError(_errorText(alt)),
      );
    }

    return CachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.contain,
      placeholder: (_, __) => _buildPlaceholder(),
      errorWidget: (_, __, ___) => _buildError(_errorText(alt)),
    );
  }

  Widget _buildPlaceholder() {
    return Container(
      width: 200,
      height: 150,
      color: isDark
          ? Colors.white.withValues(alpha: 0.05)
          : Colors.black.withValues(alpha: 0.03),
      child: Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: isDark ? Colors.white54 : Colors.black45,
          ),
        ),
      ),
    );
  }

  Widget _buildError(String message) {
    final text = message.trim().isNotEmpty ? message : 'Failed to load image';
    return Container(
      width: 200,
      height: 100,
      decoration: BoxDecoration(
        color: isDark
            ? Colors.white.withValues(alpha: 0.1)
            : Colors.black.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            OwuiIcons.brokenImage,
            size: 32,
            color: isDark ? Colors.white54 : Colors.black45,
          ),
          const SizedBox(height: 4),
          Text(
            text,
            style: TextStyle(
              fontSize: 12,
              color: isDark ? Colors.white54 : Colors.black45,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  void _showImagePreview(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: const EdgeInsets.all(16),
        child: Stack(
          alignment: Alignment.center,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: InteractiveViewer(
                minScale: 0.5,
                maxScale: 4.0,
                child: _buildFullImage(ctx),
              ),
            ),
            // 关闭按钮
            Positioned(
              top: 0,
              right: 0,
              child: IconButton(
                onPressed: () => Navigator.of(ctx).pop(),
                icon: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(OwuiIcons.close, color: Colors.white, size: 20),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFullImage(BuildContext context) {
    final dataBytes = _tryDecodeDataImage(url);
    if (dataBytes != null) {
      return Image.memory(
        dataBytes,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => _fullError(context),
      );
    }

    final file = _tryResolveLocalFile(url);
    if (file != null) {
      return Image.file(
        file,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => _fullError(context),
      );
    }

    return CachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.contain,
      errorWidget: (_, __, ___) => _fullError(context),
    );
  }

  Widget _fullError(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            OwuiIcons.brokenImage,
            size: 48,
            color: isDark ? Colors.white54 : Colors.black45,
          ),
          const SizedBox(height: 8),
          Text(
            'Failed to load image',
            style: TextStyle(
              color: isDark ? Colors.white54 : Colors.black45,
            ),
          ),
        ],
      ),
    );
  }

  Uint8List? _tryDecodeDataImage(String raw) {
    if (!raw.startsWith('data:image')) return null;
    final comma = raw.indexOf(',');
    if (comma == -1) return null;
    final meta = raw.substring(0, comma);
    final data = raw.substring(comma + 1);
    if (!meta.contains(';base64')) return null;
    try {
      return base64Decode(data);
    } catch (_) {
      return null;
    }
  }

  File? _tryResolveLocalFile(String raw) {
    final uri = Uri.tryParse(raw);
    if (uri != null && uri.scheme == 'file') {
      try {
        return File.fromUri(uri);
      } catch (_) {
        return null;
      }
    }

    final isNetwork = raw.startsWith('http://') || raw.startsWith('https://');
    if (isNetwork) return null;

    // Windows 驱动器路径 (C:\path)
    final isWindowsDrivePath = RegExp(r'^[a-zA-Z]:[\\/]').hasMatch(raw);
    // UNC 路径 (\\server\share)
    final isUncPath = raw.startsWith(r'\\');
    if (isWindowsDrivePath || isUncPath) return File(raw);

    // 其他非网络字符串视为本地路径
    if (uri != null && uri.hasScheme) return null;
    return File(raw);
  }

  String _errorText(String alt) {
    if (alt.trim().isNotEmpty) return alt.trim();

    final uri = Uri.tryParse(url);
    if (uri != null) {
      // 检测 URL 过期
      final expires = uri.queryParameters['x-expires'];
      final exp = int.tryParse(expires ?? '');
      if (exp != null) {
        final ms = exp > 100000000000 ? exp : exp * 1000;
        final at = DateTime.fromMillisecondsSinceEpoch(ms, isUtc: true);
        if (DateTime.now().toUtc().isAfter(at)) {
          return 'Image URL expired';
        }
      }
      if (uri.scheme == 'file') {
        return 'Local image not found';
      }
    }

    if (url.startsWith('data:image')) {
      return 'Invalid image data';
    }

    return 'Failed to load image';
  }
}
