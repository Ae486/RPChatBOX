part of '../flyer_chat_demo_page.dart';

class _InteractiveTableNode extends ElementNode {
  final m.Element source;
  final MarkdownConfig config;
  final WidgetVisitor visitor;
  final bool isDark;

  _InteractiveTableNode({
    required this.source,
    required this.config,
    required this.visitor,
    required this.isDark,
  });

  @override
  InlineSpan build() {
    final rows = <TableRow>[];

    var cellCount = 0;
    for (final child in children) {
      if (child is THeadNode) {
        cellCount = child.cellCount;
        rows.addAll(child.rows);
      } else if (child is TBodyNode) {
        rows.addAll(child.buildRows(cellCount));
      }
    }

    final tbConfig = config.table;

    final tableWidget = Table(
      columnWidths: tbConfig.columnWidths,
      defaultColumnWidth: tbConfig.defaultColumnWidth ?? const IntrinsicColumnWidth(),
      textBaseline: tbConfig.textBaseline,
      textDirection: tbConfig.textDirection,
      border: tbConfig.border ??
          TableBorder.all(
            color: (parentStyle?.color ?? config.p.textStyle.color ?? Colors.grey)
                .withAlpha(((isDark ? 0.25 : 0.18) * 255).round()),
          ),
      defaultVerticalAlignment: tbConfig.defaultVerticalAlignment ?? TableCellVerticalAlignment.middle,
      children: rows,
    );

    final wrapped = tbConfig.wrapper?.call(tableWidget) ?? tableWidget;

    return WidgetSpan(
      child: _MarkdownContextMenuWrapper(
        title: '表格',
        copyText: _tableToMarkdown(source),
        copyPlainText: _tableToPlainText(source),
        child: wrapped,
      ),
    );
  }
}

class _InteractiveLinkNode extends ElementNode {
  final m.Element source;
  final LinkConfig config;
  final WidgetVisitor visitor;

  _InteractiveLinkNode({
    required this.source,
    required this.config,
    required this.visitor,
  });

  @override
  InlineSpan build() {
    final href = source.attributes['href'] ?? '';

    return WidgetSpan(
      alignment: PlaceholderAlignment.baseline,
      baseline: TextBaseline.alphabetic,
      child: _MarkdownInlineLink(
        href: href,
        linkText: childrenSpan,
        richTextBuilder: visitor.richTextBuilder,
        title: source.textContent.trim().isEmpty ? href : source.textContent.trim(),
      ),
    );
  }

  @override
  TextStyle? get style => config.style.merge(parentStyle);
}

class _MarkdownInlineLink extends StatelessWidget {
  final String href;
  final InlineSpan linkText;
  final RichTextBuilder? richTextBuilder;
  final String title;

  const _MarkdownInlineLink({
    required this.href,
    required this.linkText,
    required this.richTextBuilder,
    required this.title,
  });

  Future<void> _openLink(BuildContext context) async {
    final uri = Uri.tryParse(href);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _copyLink(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: href));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('链接已复制')),
    );
  }

  Future<void> _showBottomSheet(BuildContext context) async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                title: Text(title),
                subtitle: Text(href),
              ),
              ListTile(
                leading: const Icon(Icons.open_in_new_rounded),
                title: const Text('打开链接'),
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await _openLink(context);
                },
              ),
              ListTile(
                leading: const Icon(Icons.copy_rounded),
                title: const Text('复制链接'),
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await _copyLink(context);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _showContextMenu(BuildContext context, Offset globalPosition) async {
    final parentContext = context;
    final overlay = Overlay.of(context).context.findRenderObject() as RenderBox;
    final position = RelativeRect.fromRect(
      Rect.fromPoints(globalPosition, globalPosition),
      Offset.zero & overlay.size,
    );

    final selected = await showMenu<int>(
      context: context,
      position: position,
      items: const [
        PopupMenuItem(value: 1, child: Text('打开链接')),
        PopupMenuItem(value: 2, child: Text('复制链接')),
      ],
    );

    if (!parentContext.mounted) return;

    switch (selected) {
      case 1:
        await _openLink(parentContext);
        break;
      case 2:
        await _copyLink(parentContext);
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (href.trim().isEmpty) {
      return ProxyRichText(linkText, richTextBuilder: richTextBuilder);
    }

    final isDesktop = Platform.isWindows || Platform.isLinux || Platform.isMacOS;

    final link = MouseRegion(
      cursor: SystemMouseCursors.click,
      child: ProxyRichText(linkText, richTextBuilder: richTextBuilder),
    );

    final wrapped = isDesktop
        ? Tooltip(
            message: href,
            waitDuration: const Duration(milliseconds: 450),
            child: link,
          )
        : link;

    return GestureDetector(
      behavior: HitTestBehavior.deferToChild,
      onTap: () => _openLink(context),
      onLongPress: () => _showBottomSheet(context),
      onSecondaryTapDown: (details) => _showContextMenu(context, details.globalPosition),
      child: wrapped,
    );
  }
}

class _MarkdownContextMenuWrapper extends StatelessWidget {
  final String title;
  final String copyText;
  final String? copyPlainText;
  final Widget child;

  const _MarkdownContextMenuWrapper({
    required this.title,
    required this.copyText,
    this.copyPlainText,
    required this.child,
  });

  Future<void> _copy(BuildContext context, String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$title 已复制')),
    );
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
              ListTile(
                title: Text(title),
                subtitle: const Text('长按/右键块级内容的快捷操作'),
              ),
              ListTile(
                leading: const Icon(Icons.copy_rounded),
                title: const Text('复制（Markdown）'),
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await _copy(context, copyText);
                },
              ),
              if (copyPlainText != null)
                ListTile(
                  leading: const Icon(Icons.copy_all_rounded),
                  title: const Text('复制（纯文本）'),
                  onTap: () async {
                    Navigator.of(ctx).pop();
                    await _copy(context, copyPlainText!);
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

String _blockquoteToMarkdown(m.Element blockquote) {
  final raw = blockquote.textContent.trim();
  if (raw.isEmpty) return '> ';
  final lines = raw.split(RegExp(r'\r?\n')).where((e) => e.trim().isNotEmpty);
  return lines.map((l) => '> ${l.trim()}').join('\n');
}

String _listItemToPlainText(m.Element li) {
  return li.textContent.replaceAll(RegExp(r'\s+'), ' ').trim();
}

String _listItemToMarkdown(m.Element li) {
  final raw = li.textContent.trim();
  final indexAttr = li.attributes['index'] ?? li.attributes['value'];
  final marker = (indexAttr != null && indexAttr.trim().isNotEmpty)
      ? '${indexAttr.trim()}.'
      : '-';
  if (raw.isEmpty) return '$marker ';
  final lines = raw.split(RegExp(r'\r?\n')).where((e) => e.trim().isNotEmpty).toList();
  if (lines.isEmpty) return '$marker ';
  final buf = StringBuffer();
  buf.writeln('$marker ${lines.first.trim()}');
  for (var i = 1; i < lines.length; i++) {
    buf.writeln('  ${lines[i].trim()}');
  }
  return buf.toString().trimRight();
}

String _tableToPlainText(m.Element table) {
  final tableChildren = table.children ?? const <m.Node>[];

  m.Element? thead;
  m.Element? tbody;
  for (final node in tableChildren) {
    if (node is! m.Element) continue;
    if (node.tag == MarkdownTag.thead.name) thead = node;
    if (node.tag == MarkdownTag.tbody.name) tbody = node;
  }

  final headerCells = <String>[];
  if (thead != null) {
    final headChildren = thead.children ?? const <m.Node>[];
    m.Element? tr;
    for (final node in headChildren) {
      if (node is m.Element && node.tag == MarkdownTag.tr.name) {
        tr = node;
        break;
      }
    }

    if (tr != null) {
      final trChildren = tr.children ?? const <m.Node>[];
      for (final node in trChildren) {
        if (node is! m.Element) continue;
        if (node.tag != MarkdownTag.th.name) continue;
        headerCells.add(node.textContent.trim());
      }
    }
  }

  final bodyRows = <List<String>>[];
  if (tbody != null) {
    final bodyChildren = tbody.children ?? const <m.Node>[];
    for (final node in bodyChildren) {
      if (node is! m.Element) continue;
      final tr = node;
      if (tr.tag != MarkdownTag.tr.name) continue;
      final row = <String>[];
      final trChildren = tr.children ?? const <m.Node>[];
      for (final cellNode in trChildren) {
        if (cellNode is! m.Element) continue;
        if (cellNode.tag != MarkdownTag.td.name) continue;
        row.add(cellNode.textContent.replaceAll(RegExp(r'\s+'), ' ').trim());
      }
      if (row.isNotEmpty) bodyRows.add(row);
    }
  }

  final columnCount = <int>[
    headerCells.length,
    if (bodyRows.isNotEmpty) bodyRows.map((r) => r.length).reduce((a, b) => a > b ? a : b),
  ].reduce((a, b) => a > b ? a : b);

  if (columnCount == 0) return '';

  List<String> padRow(List<String> row) {
    if (row.length >= columnCount) return row;
    return [...row, ...List.filled(columnCount - row.length, '')];
  }

  final buf = StringBuffer();
  if (headerCells.isNotEmpty) {
    buf.writeln(padRow(headerCells).join('\t'));
  }
  for (final row in bodyRows) {
    buf.writeln(padRow(row).join('\t'));
  }
  return buf.toString().trimRight();
}

String _tableToMarkdown(m.Element table) {
  final tableChildren = table.children ?? const <m.Node>[];

  m.Element? thead;
  m.Element? tbody;
  for (final node in tableChildren) {
    if (node is! m.Element) continue;
    if (node.tag == MarkdownTag.thead.name) thead = node;
    if (node.tag == MarkdownTag.tbody.name) tbody = node;
  }

  final headerCells = <String>[];
  if (thead != null) {
    final headChildren = thead.children ?? const <m.Node>[];
    m.Element? tr;
    for (final node in headChildren) {
      if (node is m.Element && node.tag == MarkdownTag.tr.name) {
        tr = node;
        break;
      }
    }

    if (tr != null) {
      final trChildren = tr.children ?? const <m.Node>[];
      for (final node in trChildren) {
        if (node is! m.Element) continue;
        if (node.tag != MarkdownTag.th.name) continue;
        headerCells.add(_escapeTableCell(node.textContent));
      }
    }
  }

  final bodyRows = <List<String>>[];
  if (tbody != null) {
    final bodyChildren = tbody.children ?? const <m.Node>[];
    for (final node in bodyChildren) {
      if (node is! m.Element) continue;
      final tr = node;
      if (tr.tag != MarkdownTag.tr.name) continue;
      final row = <String>[];
      final trChildren = tr.children ?? const <m.Node>[];
      for (final cellNode in trChildren) {
        if (cellNode is! m.Element) continue;
        if (cellNode.tag != MarkdownTag.td.name) continue;
        row.add(_escapeTableCell(cellNode.textContent));
      }
      if (row.isNotEmpty) bodyRows.add(row);
    }
  }

  final columnCount = <int>[
    headerCells.length,
    if (bodyRows.isNotEmpty) bodyRows.map((r) => r.length).reduce((a, b) => a > b ? a : b),
  ].reduce((a, b) => a > b ? a : b);

  if (columnCount == 0) return '';

  List<String> padRow(List<String> row) {
    if (row.length >= columnCount) return row;
    return [...row, ...List.filled(columnCount - row.length, '')];
  }

  final header = headerCells.isNotEmpty ? padRow(headerCells) : List.generate(columnCount, (i) => 'Col${i + 1}');
  final sep = List.generate(columnCount, (_) => '---');

  final buf = StringBuffer();
  buf.writeln('| ${header.join(' | ')} |');
  buf.writeln('| ${sep.join(' | ')} |');
  for (final row in bodyRows) {
    final r = padRow(row);
    buf.writeln('| ${r.join(' | ')} |');
  }
  return buf.toString().trimRight();
}

String _escapeTableCell(String input) {
  return input.replaceAll('|', r'\|').replaceAll(RegExp(r'\s+'), ' ').trim();
}

SpanNodeGeneratorWithTag _zebraTbodyGenerator({required bool isDark}) {
  return SpanNodeGeneratorWithTag(
    tag: MarkdownTag.tbody.name,
    generator: (e, config, visitor) => _ZebraTBodyNode(
      config,
      visitor,
      isDark: isDark,
    ),
  );
}

SpanNodeGeneratorWithTag _styledBlockquoteGenerator({required bool isDark}) {
  return SpanNodeGeneratorWithTag(
    tag: MarkdownTag.blockquote.name,
    generator: (e, config, visitor) => _StyledBlockquoteNode(
      source: e,
      config: config.blockquote,
      visitor: visitor,
      isDark: isDark,
    ),
  );
}

SpanNodeGeneratorWithTag _interactiveLinkGenerator() {
  return SpanNodeGeneratorWithTag(
    tag: MarkdownTag.a.name,
    generator: (e, config, visitor) => _InteractiveLinkNode(
      source: e,
      config: config.a,
      visitor: visitor,
    ),
  );
}

SpanNodeGeneratorWithTag _interactiveTableGenerator({required bool isDark}) {
  return SpanNodeGeneratorWithTag(
    tag: MarkdownTag.table.name,
    generator: (e, config, visitor) => _InteractiveTableNode(
      source: e,
      config: config,
      visitor: visitor,
      isDark: isDark,
    ),
  );
}

SpanNodeGeneratorWithTag _styledListItemGenerator({required bool isDark}) {
  return SpanNodeGeneratorWithTag(
    tag: MarkdownTag.li.name,
    generator: (e, config, visitor) => _StyledListItemNode(
      source: e,
      config: config,
      visitor: visitor,
      isDark: isDark,
    ),
  );
}

class _ZebraTBodyNode extends TBodyNode {
  final bool isDark;

  _ZebraTBodyNode(super.config, super.visitor, {required this.isDark});

  @override
  List<TableRow> buildRows(int cellCount) {
    return List.generate(children.length, (index) {
      final child = children[index] as TrNode;
      final List<Widget> widgets = List.generate(cellCount, (index) => Container());

      for (var i = 0; i < child.children.length; ++i) {
        final c = child.children[i];
        widgets[i] = Padding(
          padding: config.table.bodyPadding,
          child: ProxyRichText(
            c.build(),
            richTextBuilder: visitor.richTextBuilder,
          ),
        );
      }

      final zebra = index.isEven
          ? (isDark ? const Color(0xFF111318) : const Color(0xFFFFFFFF))
          : (isDark ? const Color(0xFF0D0F14) : const Color(0xFFF7F8FA));

      return TableRow(
        decoration: BoxDecoration(color: zebra),
        children: widgets,
      );
    });
  }

  @override
  TextStyle? get style =>
      config.table.bodyStyle?.merge(parentStyle) ?? parentStyle ?? config.p.textStyle;
}

class _StyledBlockquoteNode extends ElementNode {
  final m.Element source;
  final BlockquoteConfig config;
  final WidgetVisitor visitor;
  final bool isDark;

  _StyledBlockquoteNode({
    required this.source,
    required this.config,
    required this.visitor,
    required this.isDark,
  });

  @override
  InlineSpan build() {
    final bg = isDark ? const Color(0x141A73E8) : const Color(0x0D1A73E8);

    final copyText = _blockquoteToMarkdown(source);
    final copyPlainText = source.textContent.replaceAll(RegExp(r'\s+'), ' ').trim();

    return WidgetSpan(
      child: _MarkdownContextMenuWrapper(
        title: '引用块',
        copyText: copyText,
        copyPlainText: copyPlainText,
        child: Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(10),
            border: Border(
              left: BorderSide(color: config.sideColor, width: config.sideWith),
            ),
          ),
          padding: config.padding,
          margin: config.margin,
          child: ProxyRichText(childrenSpan, richTextBuilder: visitor.richTextBuilder),
        ),
      ),
    );
  }

  @override
  TextStyle? get style => TextStyle(color: config.textColor).merge(parentStyle);
}

class _StyledListItemNode extends ElementNode {
  final m.Element source;
  final MarkdownConfig config;
  final WidgetVisitor visitor;
  final bool isDark;

  _StyledListItemNode({
    required this.source,
    required this.config,
    required this.visitor,
    required this.isDark,
  });

  @override
  InlineSpan build() {
    final baseStyle = parentStyle ?? config.p.textStyle;
    final bulletColor = isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280);

    final indexAttr = source.attributes['index'] ?? source.attributes['value'];
    final marker = (indexAttr != null && indexAttr.trim().isNotEmpty) ? '${indexAttr.trim()}.' : '•';

    return WidgetSpan(
      child: _MarkdownContextMenuWrapper(
        title: '列表项',
        copyText: _listItemToMarkdown(source),
        copyPlainText: _listItemToPlainText(source),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 26,
                child: Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    marker,
                    textAlign: TextAlign.right,
                    style: baseStyle.copyWith(color: bulletColor),
                  ),
                ),
              ),
              Expanded(
                child: ProxyRichText(
                  childrenSpan,
                  richTextBuilder: visitor.richTextBuilder,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MarkdownTableWrapper extends StatefulWidget {
  final Widget child;
  final bool isDark;

  const _MarkdownTableWrapper({
    required this.child,
    required this.isDark,
  });

  @override
  State<_MarkdownTableWrapper> createState() => _MarkdownTableWrapperState();
}

class _MarkdownTableWrapperState extends State<_MarkdownTableWrapper> {
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

  @override
  Widget build(BuildContext context) {
    final isDesktop = Platform.isWindows || Platform.isLinux || Platform.isMacOS;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: widget.isDark ? const Color(0xFF0D0F14) : const Color(0xFFFFFFFF),
            border: Border.all(
              color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
            ),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final scroller = ScrollConfiguration(
                behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
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

              if (!isDesktop) return scroller;

              return Scrollbar(
                controller: _horizontalController,
                thumbVisibility: true,
                interactive: true,
                child: scroller,
              );
            },
          ),
        ),
      ),
    );
  }
}
