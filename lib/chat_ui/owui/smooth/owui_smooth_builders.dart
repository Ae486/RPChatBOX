// owui_smooth_builders.dart —— 自建块渲染 builder 与配套 widget（part of owui_smooth_markdown）
part of 'owui_smooth_markdown.dart';

/// 安全行内公式：临时/最终语法错误均回退为空白，不显示红字报错。
/// 流式中相信数据流，临时不合法时不跳红字。
class _SafeInlineMathBuilder extends MarkdownWidgetBuilder {
  const _SafeInlineMathBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is InlineMathNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as InlineMathNode;
    return Math.tex(
      n.latex,
      mathStyle: MathStyle.text,
      textStyle: styleSheet.textStyle,
      // 临时语法错误 → 空白(不红字、不暴露 raw)；合法即渲染。
      onErrorFallback: (_) => const SizedBox.shrink(),
    );
  }
}

/// 安全块级公式：同上，解析失败回退为空白。
class _SafeBlockMathBuilder extends MarkdownWidgetBuilder {
  const _SafeBlockMathBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is BlockMathNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as BlockMathNode;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Center(
        child: Math.tex(
          n.latex,
          mathStyle: MathStyle.display,
          textStyle: styleSheet.textStyle,
          onErrorFallback: (_) => const SizedBox.shrink(),
        ),
      ),
    );
  }
}

/// 自写 mermaid builder：覆盖包内置渲染（包默认两表均未注册 mermaid）。
/// 头部：左=图表类型，中=预览/源码切换，右=复位/复制/导出/全屏/收起；
/// 预览区右上角=缩放按钮+百分比。用包公开的 [MermaidDiagram]（CustomPainter，无 WebView）。
class _MermaidBuilder extends MarkdownWidgetBuilder {
  const _MermaidBuilder({this.dark = false});

  final bool dark;

  @override
  bool canBuild(MarkdownNode node) => node is MermaidDiagramNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as MermaidDiagramNode;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: _MermaidChartView(code: n.code, themeName: n.theme, dark: dark),
    );
  }
}

/// 带头部栏的 mermaid 视图：类型/预览-源码/复位/复制/导出/全屏/收起 + 预览区缩放。
/// inlineHeight=null 时占满（全屏用）。
class _MermaidChartView extends StatefulWidget {
  const _MermaidChartView({
    required this.code,
    this.themeName,
    this.dark = false,
    this.inlineHeight = 320,
    this.showFullscreen = true,
  });

  final String code;
  final String? themeName;
  final bool dark;
  final double? inlineHeight;
  final bool showFullscreen;

  @override
  State<_MermaidChartView> createState() => _MermaidChartViewState();
}

class _MermaidChartViewState extends State<_MermaidChartView> {
  final TransformationController _tc = TransformationController();
  final GlobalKey _repaintKey = GlobalKey();
  Size _viewport = Size.zero;
  double _scale = 1.0;
  bool _showSource = false;
  bool _collapsed = false;
  bool _copied = false;
  static const double _min = 0.4;
  static const double _max = 4.0;

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }

  MermaidStyle get _style {
    switch (widget.themeName?.toLowerCase()) {
      case 'dark':
        return MermaidStyle.dark();
      case 'forest':
        return MermaidStyle.forest();
      case 'neutral':
        return MermaidStyle.neutral();
      case 'light':
        return const MermaidStyle();
    }
    return widget.dark ? MermaidStyle.dark() : const MermaidStyle();
  }

  /// 从源码首行关键字推断图表类型（依据包 mermaid_parser 支持的类型）。
  String get _typeLabel {
    final first =
        widget.code.trimLeft().split('\n').first.trim().toLowerCase();
    if (first.startsWith('flowchart') || first.startsWith('graph')) {
      return 'Flowchart';
    }
    if (first.startsWith('sequencediagram')) return 'Sequence';
    if (first.startsWith('pie')) return 'Pie';
    if (first.startsWith('gantt')) return 'Gantt';
    if (first.startsWith('timeline')) return 'Timeline';
    if (first.startsWith('kanban')) return 'Kanban';
    if (first.startsWith('radar')) return 'Radar';
    if (first.startsWith('xychart')) return 'XY Chart';
    return 'Diagram';
  }

  /// 围绕视口中心缩放到目标比例，保留当前平移。
  void _setScale(double target) {
    final next = target.clamp(_min, _max);
    final cur = _tc.value.getMaxScaleOnAxis();
    if ((next - cur).abs() < 0.0001) return;
    final factor = next / cur;
    final focal = _viewport == Size.zero
        ? Offset.zero
        : Offset(_viewport.width / 2, _viewport.height / 2);
    final scene = _tc.toScene(focal);
    final m = _tc.value.clone()
      ..translateByDouble(scene.dx, scene.dy, 0, 1)
      ..scaleByDouble(factor, factor, factor, 1)
      ..translateByDouble(-scene.dx, -scene.dy, 0, 1);
    setState(() {
      _tc.value = m;
      _scale = next;
    });
  }

  void _reset() => setState(() {
        _tc.value = Matrix4.identity();
        _scale = 1.0;
      });

  Future<void> _copySource() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    setState(() => _copied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
    _toast('已复制源码');
  }

  /// 导出：RepaintBoundary 截图为 PNG（提示尺寸）；落盘/分享留待宿主层接入。
  Future<void> _export() async {
    if (_collapsed || _showSource) {
      _toast('请在预览模式下导出');
      return;
    }
    try {
      final boundary = _repaintKey.currentContext?.findRenderObject()
          as RenderRepaintBoundary?;
      if (boundary == null) {
        _toast('导出失败：未就绪');
        return;
      }
      final image = await boundary.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      final kb = ((bytes?.lengthInBytes ?? 0) / 1024).round();
      _toast('已导出 PNG（${image.width}×${image.height}, ${kb}KB）');
    } catch (e) {
      _toast('导出失败: $e');
    }
  }

  void _toast(String m) {
    final s = ScaffoldMessenger.maybeOf(context);
    s?.hideCurrentSnackBar();
    s?.showSnackBar(SnackBar(
      content: Text(m),
      duration: const Duration(milliseconds: 1000),
    ));
  }

  void _openFullscreen() {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => Scaffold(
        backgroundColor:
            widget.dark ? const Color(0xFF14161A) : Colors.white,
        appBar: AppBar(title: Text('$_typeLabel · Mermaid')),
        body: _MermaidChartView(
          code: widget.code,
          themeName: widget.themeName,
          dark: widget.dark,
          inlineHeight: null,
          showFullscreen: false,
        ),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final fill = widget.inlineHeight == null;
    return Container(
      decoration: BoxDecoration(
        color: cs.surfaceContainerLow,
        borderRadius: BorderRadius.circular(_kRadius),
        border: Border.all(color: cs.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: fill ? MainAxisSize.max : MainAxisSize.min,
        children: [
          _buildHeader(cs),
          if (fill)
            Expanded(
              child: _collapsed ? const SizedBox.shrink() : _buildBody(cs),
            )
          else
            AnimatedSize(
              duration: const Duration(milliseconds: _kExpandMs),
              curve: Curves.easeOutCubic,
              alignment: Alignment.topCenter,
              child: _collapsed
                  ? const SizedBox(width: double.infinity)
                  : SizedBox(
                      height: widget.inlineHeight, child: _buildBody(cs)),
            ),
        ],
      ),
    );
  }

  Widget _buildHeader(ColorScheme cs) {
    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest,
        border: Border(bottom: BorderSide(color: cs.outlineVariant)),
      ),
      child: Row(
        children: [
          Icon(Icons.account_tree_outlined, size: 16, color: cs.primary),
          const SizedBox(width: 6),
          Text(
            _typeLabel,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: cs.onSurface,
            ),
          ),
          const Spacer(),
          _toggle(cs),
          const Spacer(),
          _hbtn(Icons.content_copy, _copied ? '已复制' : '复制源码', _copySource,
              active: _copied),
          _hbtn(Icons.download_outlined, '导出 PNG', _export),
          _hbtn(Icons.center_focus_strong, '复位', _reset),
          if (widget.showFullscreen)
            _hbtn(Icons.fullscreen, '全屏', _openFullscreen),
          _hbtn(
            _collapsed ? Icons.expand_more : Icons.expand_less,
            _collapsed ? '展开' : '收起',
            () => setState(() => _collapsed = !_collapsed),
          ),
        ],
      ),
    );
  }

  Widget _toggle(ColorScheme cs) {
    Widget seg(
            IconData icon, String label, bool selected, VoidCallback onTap) =>
        InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(_kRadius),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon,
                    size: 15,
                    color: selected ? cs.primary : cs.onSurfaceVariant),
                const SizedBox(width: 4),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    color: selected ? cs.primary : cs.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        seg(Icons.visibility_outlined, '预览', !_showSource,
            () => setState(() => _showSource = false)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Text('|',
              style: TextStyle(fontSize: 13, color: cs.outlineVariant)),
        ),
        seg(Icons.code, '源码', _showSource,
            () => setState(() => _showSource = true)),
      ],
    );
  }

  Widget _hbtn(IconData icon, String tip, VoidCallback onTap,
      {bool active = false}) {
    return IconButton(
      icon: Icon(icon, size: 17),
      tooltip: tip,
      color: active ? Colors.green : null,
      visualDensity: VisualDensity.compact,
      constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
      padding: EdgeInsets.zero,
      onPressed: onTap,
    );
  }

  Widget _buildBody(ColorScheme cs) =>
      _showSource ? _buildSource(cs) : _buildPreview(cs);

  Widget _buildPreview(ColorScheme cs) {
    return LayoutBuilder(
      builder: (ctx, c) {
        _viewport = Size(
          c.maxWidth.isFinite ? c.maxWidth : 0,
          c.maxHeight.isFinite ? c.maxHeight : 0,
        );
        return Stack(
          children: [
            Positioned.fill(
              child: Container(
                color: Color(_style.backgroundColor),
                child: RepaintBoundary(
                  key: _repaintKey,
                  child: InteractiveViewer(
                    transformationController: _tc,
                    scaleEnabled: false, // 滚轮归页面；缩放走按钮
                    panEnabled: true,
                    minScale: _min,
                    maxScale: _max,
                    boundaryMargin: const EdgeInsets.all(double.infinity),
                    child: Center(
                      child: MermaidDiagram(code: widget.code, style: _style),
                    ),
                  ),
                ),
              ),
            ),
            Positioned(top: 8, right: 8, child: _zoomBar(cs)),
          ],
        );
      },
    );
  }

  Widget _zoomBar(ColorScheme cs) {
    Widget zb(IconData i, String t, VoidCallback f) => IconButton(
          icon: Icon(i, size: 16),
          tooltip: t,
          visualDensity: VisualDensity.compact,
          constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
          padding: EdgeInsets.zero,
          onPressed: f,
        );
    return Container(
      decoration: BoxDecoration(
        color: cs.surface.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(_kRadius),
        border: Border.all(color: cs.outlineVariant),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          zb(Icons.remove, '缩小', () => _setScale(_scale * 0.8)),
          Text(
            '${(_scale * 100).round()}%',
            style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant),
          ),
          zb(Icons.add, '放大', () => _setScale(_scale * 1.25)),
        ],
      ),
    );
  }

  Widget _buildSource(ColorScheme cs) {
    return Container(
      width: double.infinity,
      color: cs.surfaceContainer,
      padding: const EdgeInsets.all(12),
      child: SingleChildScrollView(
        child: Text(
          widget.code,
          style: TextStyle(
            fontFamily: 'monospace',
            fontSize: 12.5,
            height: 1.5,
            color: cs.onSurface,
          ),
        ),
      ),
    );
  }
}

/// 自建代码块：独立头部栏（左语言/右复制+收起）。
/// 复用框架同款高亮(highlight.parse + github/vs2015 主题表)，复制真实现，可折叠。
class _CodeBlockBuilder extends MarkdownWidgetBuilder {
  const _CodeBlockBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is CodeBlockNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as CodeBlockNode;
    return _CodeBlock(
        code: n.code, language: n.language, styleSheet: styleSheet);
  }
}

class _CodeBlock extends StatefulWidget {
  const _CodeBlock({
    required this.code,
    required this.styleSheet,
    this.language,
  });

  final String code;
  final String? language;
  final MarkdownStyleSheet styleSheet;

  @override
  State<_CodeBlock> createState() => _CodeBlockState();
}

class _CodeBlockState extends State<_CodeBlock> {
  bool _collapsed = false;
  bool _copied = false;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;
    setState(() => _copied = true);
    _timer?.cancel();
    _timer = Timer(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final lang = (widget.language ?? '').trim();
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLow,
        borderRadius: BorderRadius.circular(_kRadius),
        border: Border.all(color: cs.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            height: 48,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: cs.surfaceContainerHighest,
              border: Border(bottom: BorderSide(color: cs.outlineVariant)),
            ),
            child: Row(
              children: [
                Icon(Icons.code, size: 15, color: cs.onSurfaceVariant),
                const SizedBox(width: 6),
                Text(
                  lang.isEmpty ? 'TEXT' : lang.toUpperCase(),
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.4,
                    color: cs.onSurfaceVariant,
                  ),
                ),
                const Spacer(),
                IconButton(
                  icon: Icon(_copied ? Icons.check : Icons.content_copy,
                      size: 16,
                      color: _copied ? Colors.green : cs.onSurfaceVariant),
                  tooltip: _copied ? '已复制' : '复制',
                  visualDensity: VisualDensity.compact,
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                  padding: EdgeInsets.zero,
                  onPressed: _copy,
                ),
                IconButton(
                  icon: Icon(
                      _collapsed ? Icons.expand_more : Icons.expand_less,
                      size: 18,
                      color: cs.onSurfaceVariant),
                  tooltip: _collapsed ? '展开' : '收起',
                  visualDensity: VisualDensity.compact,
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                  padding: EdgeInsets.zero,
                  onPressed: () => setState(() => _collapsed = !_collapsed),
                ),
              ],
            ),
          ),
          AnimatedSize(
            duration: const Duration(milliseconds: _kExpandMs),
            curve: Curves.easeOutCubic,
            alignment: Alignment.topCenter,
            child: _collapsed
                ? const SizedBox(width: double.infinity)
                : Padding(
                    padding: const EdgeInsets.all(12),
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: _highlighted(context),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _highlighted(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final base = widget.styleSheet.codeBlockStyle ??
        const TextStyle(fontFamily: 'monospace', fontSize: 13, height: 1.5);
    final lang = widget.language;
    if (lang == null || lang.trim().isEmpty) {
      return Text(widget.code, style: base);
    }
    try {
      final theme = dark ? hl_dark.vs2015Theme : hl_light.githubTheme;
      final nodes = highlight.parse(widget.code, language: lang).nodes;
      if (nodes == null || nodes.isEmpty) {
        return Text(widget.code, style: base);
      }
      return Text.rich(
          TextSpan(style: base, children: _convertHighlightNodes(nodes, theme)));
    } catch (_) {
      return Text(widget.code, style: base);
    }
  }
}

/// 复刻框架 EnhancedCodeBlock 的高亮转换(highlight Node → TextSpan)。
List<TextSpan> _convertHighlightNodes(
  List<Node> nodes,
  Map<String, TextStyle> theme,
) {
  final spans = <TextSpan>[];
  for (final node in nodes) {
    final cls = node.className;
    if (node.value != null) {
      spans.add(cls == null
          ? TextSpan(text: node.value)
          : TextSpan(text: node.value, style: theme[cls]));
    } else if (node.children != null) {
      spans.add(TextSpan(
        children: _convertHighlightNodes(node.children!, theme),
        style: cls == null ? null : theme[cls],
      ));
    }
  }
  return spans;
}

/// 自建 admonition：包有 plugin 无 builder。正文用 context.blockRenderer 复用框架渲染器；
/// 视图层(_Admonition)用 BuildContext 读 Theme 深浅，配色经 alpha 适配。
class _AdmonitionBuilder extends MarkdownWidgetBuilder {
  const _AdmonitionBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is AdmonitionNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as AdmonitionNode;
    return _Admonition(
        node: n, body: context.blockRenderer?.call(n.children));
  }
}

class _Admonition extends StatelessWidget {
  const _Admonition({required this.node, this.body});

  final AdmonitionNode node;
  final Widget? body;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final spec = switch (node.admonitionType) {
      AdmonitionType.note =>
        (const Color(0xFF3B82F6), Icons.info_outline, 'NOTE'),
      AdmonitionType.tip =>
        (const Color(0xFF10B981), Icons.lightbulb_outline, 'TIP'),
      AdmonitionType.warning =>
        (const Color(0xFFF59E0B), Icons.warning_amber_rounded, 'WARNING'),
      AdmonitionType.danger =>
        (const Color(0xFFEF4444), Icons.error_outline, 'DANGER'),
      AdmonitionType.important =>
        (const Color(0xFF8B5CF6), Icons.priority_high, 'IMPORTANT'),
      AdmonitionType.custom => (
          const Color(0xFF6B7280),
          Icons.label_outline,
          (node.customType ?? 'NOTE').toUpperCase()
        ),
    };
    final color = spec.$1;
    final icon = spec.$2;
    final title = node.title.isNotEmpty ? node.title : spec.$3;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: dark ? 0.16 : 0.08),
        border: Border(
          left: BorderSide(
            color: Color.lerp(color, Colors.black, 0.25)!,
            width: 3,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: color),
              const SizedBox(width: 8),
              Text(
                title,
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: color,
                  fontSize: 14,
                ),
              ),
            ],
          ),
          if (body != null) ...[
            const SizedBox(height: 6),
            body!,
          ],
        ],
      ),
    );
  }
}

/// 自建 header builder：覆盖框架 EnhancedHeaderBuilder，去掉标题左侧渐变竖线
/// (保留 h1/h2 底部渐变细线)。
class _HeaderBuilder extends MarkdownWidgetBuilder {
  const _HeaderBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is HeaderNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final h = node as HeaderNode;
    final style = switch (h.level) {
      1 => styleSheet.h1Style,
      2 => styleSheet.h2Style,
      3 => styleSheet.h3Style,
      4 => styleSheet.h4Style,
      5 => styleSheet.h5Style,
      6 => styleSheet.h6Style,
      _ => styleSheet.textStyle,
    };
    final inline = context.inlineRenderer;
    final text = (h.children?.isNotEmpty ?? false) && inline != null
        ? inline(h.children!, style)
        : Text(h.content, style: style);
    return _Header(level: h.level, child: text);
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.level, required this.child});

  final int level;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: child,
        ),
        if (level <= 2)
          Container(
            height: 2,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  primary.withValues(alpha: 0.3),
                  primary.withValues(alpha: 0),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

/// 自建 table builder：覆盖框架 TableBuilder(barrel 未导出，故复刻其渲染)。
/// 可用宽度 < _kTableMinWidth 时表格固定该宽并横向滚动，否则铺满。
class _TableBuilder extends MarkdownWidgetBuilder {
  const _TableBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is TableNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final t = node as TableNode;
    var cols = t.alignments.length;
    if (t.headers.length > cols) cols = t.headers.length;
    for (final r in t.rows) {
      if (r.cells.length > cols) cols = r.cells.length;
    }
    if (cols == 0) cols = 1;

    final inline = context.inlineRenderer;
    Widget cell(List<MarkdownNode> content, TableAlignment? al, bool header) {
      final ts = header
          ? (styleSheet.tableHeaderStyle ?? styleSheet.textStyle)
          : (styleSheet.tableCellStyle ?? styleSheet.textStyle);
      final w = inline != null
          ? inline(content, ts)
          : Text(content.whereType<TextNode>().map((n) => n.content).join(),
              style: ts);
      return Container(
        padding: styleSheet.tableCellPadding ?? const EdgeInsets.all(8),
        alignment: switch (al) {
          TableAlignment.center => Alignment.center,
          TableAlignment.right => Alignment.centerRight,
          _ => Alignment.centerLeft,
        },
        child: w,
      );
    }

    TableRow row(List<List<MarkdownNode>> cells, bool header) => TableRow(
          decoration: header ? styleSheet.tableHeaderDecoration : null,
          children: [
            for (var i = 0; i < cols; i++)
              cell(
                i < cells.length ? cells[i] : const <MarkdownNode>[],
                i < t.alignments.length ? t.alignments[i] : null,
                header,
              ),
          ],
        );

    final table = Table(
      border: styleSheet.tableBorder,
      defaultVerticalAlignment: TableCellVerticalAlignment.middle,
      children: [
        row(t.headers, true),
        for (final r in t.rows) row(r.cells, false),
      ],
    );

    return _TableScroller(table: table);
  }
}

/// 表格横向滚动包装：可用宽度 < _kTableMinWidth 时固定该宽并显示可拖动横向滚动条；否则铺满。
/// 显式 ScrollController + thumbVisibility 让桌面端能拖动滚动条横向滚动。
class _TableScroller extends StatefulWidget {
  const _TableScroller({required this.table});

  final Widget table;

  @override
  State<_TableScroller> createState() => _TableScrollerState();
}

class _TableScrollerState extends State<_TableScroller> {
  final ScrollController _h = ScrollController();

  @override
  void dispose() {
    _h.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (ctx, c) {
        if (c.maxWidth >= _kTableMinWidth) return widget.table; // 够宽：铺满
        return Scrollbar(
          controller: _h,
          thumbVisibility: true,
          child: SingleChildScrollView(
            controller: _h,
            scrollDirection: Axis.horizontal,
            physics: const ClampingScrollPhysics(),
            child: SizedBox(width: _kTableMinWidth, child: widget.table),
          ),
        );
      },
    );
  }
}

/// 覆盖框架增强链接：保留 hover 颜色反馈，但下划线宽度恒定，不因 border 1→2px 改变行高。
class _LinkBuilder extends MarkdownWidgetBuilder {
  const _LinkBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is LinkNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as LinkNode;
    final inline = context.inlineRenderer;
    final content = inline != null
        ? inline(n.children, styleSheet.linkStyle)
        : Text(n.children.whereType<TextNode>().map((e) => e.content).join(),
            style: styleSheet.linkStyle);
    final external =
        n.url.startsWith('http://') || n.url.startsWith('https://');
    return _Link(
      url: n.url,
      color: styleSheet.linkStyle?.color ?? Colors.blue,
      external: external,
      onTap: () => context.onTapLink?.call(n.url),
      child: content,
    );
  }
}

class _Link extends StatefulWidget {
  const _Link({
    required this.url,
    required this.color,
    required this.external,
    required this.onTap,
    required this.child,
  });

  final String url;
  final Color color;
  final bool external;
  final VoidCallback onTap;
  final Widget child;

  @override
  State<_Link> createState() => _LinkState();
}

class _LinkState extends State<_Link> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      link: true,
      label: widget.url,
      child: MouseRegion(
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: widget.onTap,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(
                  color: widget.color.withValues(alpha: _hover ? 1.0 : 0.4),
                  width: 1, // 恒定宽度 → hover 不改变行高
                ),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Flexible(child: widget.child),
                if (widget.external)
                  Padding(
                    padding: const EdgeInsets.only(left: 2),
                    child:
                        Icon(Icons.open_in_new, size: 12, color: widget.color),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
