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
import 'palette.dart';
import 'stable_body.dart';

const String _latexTag = 'latex';

final SpanNodeGeneratorWithTag owuiLatexGenerator = SpanNodeGeneratorWithTag(
  tag: _latexTag,
  generator: (e, config, visitor) =>
      _OwuiLatexNode(e.attributes, e.textContent, config),
);

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
                leading: const Icon(Icons.copy_rounded),
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

  const OwuiMarkdown({
    super.key,
    required this.text,
    required this.isDark,
    required this.isStreaming,
    this.stableCacheKey,
  });

  static const StablePrefixParser _stablePrefixParser = StablePrefixParser();

  ({String stable, String tail}) _splitStableMarkdown(String source) =>
      _stablePrefixParser.split(source);

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
    final safeText = _preprocessMarkdownForMarkdownWidget(raw);
    final config = isDark
        ? MarkdownConfig.darkConfig
        : MarkdownConfig.defaultConfig;

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
      );
    }

    final blockquoteConfig = BlockquoteConfig(
      sideColor: isDark ? const Color(0xFF60A5FA) : const Color(0xFF1A73E8),
      textColor: isDark ? const Color(0xFFD1D5DB) : const Color(0xFF374151),
      sideWith: 4,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      margin: const EdgeInsets.fromLTRB(0, 10, 0, 10),
    );

    final tableConfig = TableConfig(
      headerRowDecoration: BoxDecoration(
        color: isDark ? const Color(0xFF141821) : const Color(0xFFF3F4F6),
      ),
      headerStyle: TextStyle(
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
      ),
      bodyStyle: TextStyle(
        color: isDark ? const Color(0xFFD1D5DB) : const Color(0xFF111827),
      ),
      headPadding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      bodyPadding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
      wrapper: (child) => _OwuiMarkdownTableWrapper(isDark: isDark, child: child),
    );

    return MarkdownWidget(
      data: safeText,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      config: config.copy(
        configs: [
          LinkConfig(
            style: TextStyle(
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
        ],
      ),
      markdownGenerator: MarkdownGenerator(
        generators: [owuiLatexGenerator],
        inlineSyntaxList: [OwuiLatexSyntax()],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final config = isDark
        ? MarkdownConfig.darkConfig
        : MarkdownConfig.defaultConfig;

    final parts = _splitStableMarkdown(text);
    final needsStableRenderer = isStreaming || parts.tail.isNotEmpty;
    if (!needsStableRenderer) {
      return _buildMarkdownWidget(context, text);
    }

    return OwuiStableBody(
      text: text,
      splitStableMarkdown: _splitStableMarkdown,
      stableCacheKey: stableCacheKey,
      markdown: (markdownText) => _buildMarkdownWidget(context, markdownText),
      plainTextStyle: config.p.textStyle,
      streamingCodeBlock:
          ({required language, required code, required isClosed}) {
            final inferred = inferCodeLanguage(
              declaredLanguage: language,
              code: code,
            );
            if (inferred == 'mermaid') {
              return OwuiMermaidBlock(
                mermaidCode: code,
                isDark: isDark,
                isStreaming: isStreaming && !isClosed,
              );
            }
            return OwuiCodeBlock(
              code: code,
              language: inferred.isEmpty ? 'plaintext' : inferred,
              isDark: isDark,
              isStreaming: isStreaming && !isClosed,
            );
          },
    );
  }
}
