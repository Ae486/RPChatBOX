// owui_smooth_error.dart —— <error> 协议块：解析插件 + builder + UI（part of owui_smooth_markdown）
part of 'owui_smooth_markdown.dart';

/// `<error type="..." code="..." brief="...">details</error>` 的 AST 节点。
/// 由 error_formatter.toErrorTag() 产出、finalize 时追加到消息体，用于错误的持久化+渲染。
class _OwuiErrorNode extends MarkdownNode {
  const _OwuiErrorNode({
    required this.errorType,
    required this.errorCode,
    required this.brief,
    required this.details,
  });

  final String errorType;
  final int? errorCode;
  final String brief;
  final String details;

  @override
  String get type => 'owui_error';

  @override
  Map<String, dynamic> toJson() => {
        'type': type,
        'errorType': errorType,
        if (errorCode != null) 'errorCode': errorCode,
        'brief': brief,
        'details': details,
      };

  @override
  MarkdownNode copyWith() => this;
}

/// 块级解析插件：识别独立成块的 `<error ...>...</error>`（details 可跨行，已 XML 转义无裸 `<`）。
/// 累积自起始行直到出现 `</error>`，按 ErrorTagParser 同款正则提取属性。
class _OwuiErrorPlugin extends BlockParserPlugin {
  const _OwuiErrorPlugin();

  @override
  String get id => 'owui_error';

  @override
  String get name => 'Owui Error Plugin';

  @override
  int get priority => 20; // 高于其余块插件，确保 <error 行优先命中

  static final RegExp _start = RegExp(r'^\s*<error\s');
  static final RegExp _full = RegExp(
    r'<error\s+type="(\w+)"(?:\s+code="(\d+)")?(?:\s+brief="([^"]*)")?>([\s\S]*?)</error>',
  );

  @override
  bool canParse(String line, List<String> lines, int index) =>
      _start.hasMatch(line);

  @override
  BlockParseResult? parse(List<String> lines, int startIndex) {
    // 累积起始行起的内容直到出现 </error>
    final buf = StringBuffer();
    var end = startIndex;
    while (end < lines.length) {
      if (end > startIndex) buf.write('\n');
      buf.write(lines[end]);
      if (lines[end].contains('</error>')) break;
      end++;
    }
    final matched = _full.firstMatch(buf.toString());
    // 未闭合/不完整(理论上 error 在 finalize 整体追加，不会半截到来) → 回退普通段落
    if (matched == null) return null;

    final type = matched.group(1) ?? 'unknown';
    final codeStr = matched.group(2);
    final brief = _unescapeXml(matched.group(3) ?? '');
    final details = _unescapeXml(matched.group(4) ?? '');
    final lastLine = end < lines.length ? end : lines.length - 1;

    return BlockParseResult(
      node: _OwuiErrorNode(
        errorType: type,
        errorCode: codeStr != null ? int.tryParse(codeStr) : null,
        brief: brief.isNotEmpty ? brief : _briefFromDetails(details),
        details: details,
      ),
      linesConsumed: lastLine - startIndex + 1,
    );
  }

  static String _unescapeXml(String s) => s
      .replaceAll('&quot;', '"')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&amp;', '&');

  static String _briefFromDetails(String details) {
    if (details.length <= 50) return details;
    return '${details.substring(0, 47)}...';
  }
}

class _OwuiErrorBuilder extends MarkdownWidgetBuilder {
  const _OwuiErrorBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is _OwuiErrorNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as _OwuiErrorNode;
    return _OwuiErrorBlock(
      errorType: n.errorType,
      errorCode: n.errorCode,
      brief: n.brief,
      details: n.details,
    );
  }
}

/// 错误块渲染：图标 + 两行摘要(类型/状态码 + brief) + 可展开详情。复刻生产 _OwuiErrorBlock。
class _OwuiErrorBlock extends StatefulWidget {
  const _OwuiErrorBlock({
    required this.errorType,
    required this.errorCode,
    required this.brief,
    required this.details,
  });

  final String errorType;
  final int? errorCode;
  final String brief;
  final String details;

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
    final bgColor =
        isDark ? const Color(0xFF2A1A1A) : const Color(0xFFFEECEC);
    final borderColor = isDark
        ? Colors.red.withValues(alpha: 0.4)
        : Colors.red.withValues(alpha: 0.3);
    final iconColor = isDark ? Colors.red[300] : Colors.red[600];
    final textColor =
        isDark ? const Color(0xFFE5A0A0) : const Color(0xFF991B1B);
    final detailsColor =
        isDark ? const Color(0xFFD1D5DB) : const Color(0xFF4B5563);

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
