/// INPUT: 无（内置可编辑测试文本）
/// OUTPUT: MarkdownLabPage - flutter_smooth_markdown 渲染/流式试验场
/// POS: 临时试验页 / 评估 smooth_markdown 是否适合改造为 markstream 式策略
///
/// 仅用于工程评估，不接入生产链路。可从设置页进入。
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter_smooth_markdown/flutter_smooth_markdown.dart';

/// 默认测试样本：覆盖文章 + 表格 + 代码 + 行内/块级 LaTeX + think + mermaid
const String _kSample = r'''
# Smooth Markdown 试验场

普通段落，含 **加粗**、*斜体*、`行内代码`、删除线 ~~删除~~ 与链接 [Flutter](https://flutter.dev)。

## 表格（观察流式时是否泄漏 raw）

| 维度 | 现状 owui | smooth_markdown |
| --- | --- | --- |
| 表格流式 | 泄漏 `\|x\|x\|` | 待观察 |
| 代码行号 | 预测错位 | 待观察 |
| Mermaid | WebView | 原生 CustomPainter |

## 任务列表

- [x] 已完成项
- [ ] 未完成项

## 代码块（观察长行换行与行号对齐）

```dart
void main() {
  final List<String> items = <String>['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta'];
  for (final item in items) {
    debugPrint('streaming code line that is intentionally long to force a soft wrap and test gutter alignment: $item');
  }
}
```

## LaTeX（行内与块级）

行内公式 $E = mc^2$ 与 $\alpha + \beta = \gamma$。

块级公式（观察是否过扁 / 是否横向溢出）：

$$
\int_{a}^{b} f(x)\,dx = F(b) - F(a) \qquad \sum_{i=1}^{n} i = \frac{n(n+1)}{2}
$$

## Think 块（注意：smooth_markdown 要求标签独占一行）

<think>
这是模型的推理过程。
上游 thinking_extractor 会把 reasoning 字段归一化为 <think> 标签。
</think>

## Mermaid（原生渲染，无 WebView）

```mermaid
graph TD
  A[开始] --> B{判断}
  B -->|是| C[执行]
  B -->|否| D[结束]
  C --> D
```

> 引用块：用于对照整体视觉风格是否统一。
''';

class MarkdownLabPage extends StatefulWidget {
  const MarkdownLabPage({super.key});

  @override
  State<MarkdownLabPage> createState() => _MarkdownLabPageState();
}

enum _LabMode { staticRender, stream }

class _MarkdownLabPageState extends State<MarkdownLabPage> {
  late final TextEditingController _textController =
      TextEditingController(text: _kSample);
  final ScrollController _scroll = ScrollController();

  _LabMode _mode = _LabMode.staticRender;
  bool _dark = false;
  bool _enhanced = true;
  bool _follow = true;
  double _gapMs = 18;
  int _chunkChars = 2;

  // 自建流式累积：我们自己的 subscription 驱动包的「静态」渲染器 + 健壮底部跟随。
  // 这正是推荐的「薄包装层」雏形（已闭合块沉淀 / 活动尾部暂挂 / 收敛留待后续）。
  StreamSubscription<String>? _sub;
  String _streamText = '';
  bool _streaming = false;
  bool _isFinal = false; // 流是否已结束(onDone)；门控 loading↔硬解析(第2/3项消费)
  int _session = 0;

  // 跟随状态机：_stick=当前是否粘底；_autoScrolling=屏蔽自身动画产生的滚动事件；
  // _showToBottom=「回到底部」浮钮可见。脱离只认用户手势，不认布局位移（见 _onScroll）。
  bool _stick = true;
  bool _autoScrolling = false;
  bool _pendingFollow = false;
  bool _showToBottom = false;
  static const double _nearBottomPx = 48;

  @override
  void dispose() {
    _sub?.cancel();
    _scroll.dispose();
    _textController.dispose();
    super.dispose();
  }

  /// 解析插件：think / tool_call / artifact / mermaid
  ParserPluginRegistry _plugins() => ParserPluginRegistry()
    ..register(const ThinkingPlugin())
    ..register(const ToolCallPlugin())
    ..register(const ArtifactPlugin())
    ..register(const MermaidPlugin());

  /// 自定义 builder 注册表（合并在 enhanced 内置之上、优先级最高）：
  /// - inline_math/block_math：enhanced 内置表漏注册，这里补回 → 修复 enhanced LaTeX
  /// - mermaid：默认表本就不含；用自写 builder 覆盖 → 居中、且不抢页面滚轮
  BuilderRegistry _builders() => BuilderRegistry()
    ..register('inline_math', const InlineMathBuilder())
    ..register('block_math', const BlockMathBuilder())
    ..register('mermaid', _LabMermaidBuilder(dark: _dark));

  MarkdownConfig get _config =>
      const MarkdownConfig(enableLatex: true, enableEmoji: true);

  MarkdownStyleSheet get _styleSheet =>
      _dark ? MarkdownStyleSheet.dark() : MarkdownStyleSheet.light();

  Stream<String> _simulate(String text) async* {
    final gap = Duration(milliseconds: _gapMs.round());
    for (var i = 0; i < text.length; i += _chunkChars) {
      yield text.substring(i, math.min(i + _chunkChars, text.length));
      await Future<void>.delayed(gap);
    }
  }

  void _replay() {
    _sub?.cancel();
    setState(() {
      _session++;
      _streamText = '';
      _streaming = true;
      _isFinal = false;
      _stick = true;
      _showToBottom = false;
    });
    _sub = _simulate(_textController.text).listen(
      (chunk) {
        if (!mounted) return;
        setState(() => _streamText += chunk);
        if (_follow && _stick) _runFollow();
      },
      onDone: () {
        if (mounted) {
          setState(() {
            _streaming = false;
            _isFinal = true; // 流结束 → 收敛：tail 并入解析、math 落定
          });
        }
      },
    );
  }

  /// 平滑跟随到底部。用 animateTo（非 jumpTo）以获得项目现有的顺滑手感；
  /// 自身动画期间置 _autoScrolling 屏蔽滚动事件；动画中到来的新块用 _pendingFollow 续接。
  void _runFollow() {
    if (!_scroll.hasClients) return;
    if (_autoScrolling) {
      _pendingFollow = true;
      return;
    }
    _autoScrolling = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted || !_scroll.hasClients) {
        _autoScrolling = false;
        return;
      }
      try {
        await _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 140),
          curve: Curves.easeOutCubic,
        );
      } catch (_) {
        // 列表可能尚未附着，下一帧重试
      }
      _autoScrolling = false;
      if (_pendingFollow && mounted) {
        _pendingFollow = false;
        _runFollow();
      }
    });
  }

  void _backToBottom() {
    setState(() {
      _stick = true;
      _showToBottom = false;
    });
    _runFollow();
  }

  /// 跟随状态机。要点：脱离只认 [UserScrollNotification]（真实用户手势），
  /// 绝不在 [ScrollUpdateNotification] 里按像素差判脱离——块级结构撑高引起的
  /// 布局位移会被误判为「用户上滑」，正是项目现有跟随在块级结构处丢失的根因。
  bool _onScroll(ScrollNotification n) {
    if (n.metrics.axis != Axis.vertical) return false;
    final nearBottom = n.metrics.extentAfter <= _nearBottomPx;

    if (n is UserScrollNotification) {
      if (n.direction == ScrollDirection.forward && _stick) {
        // 用户上滑 → 脱离
        setState(() {
          _stick = false;
          _showToBottom = true;
        });
      } else if (n.direction == ScrollDirection.reverse &&
          nearBottom &&
          !_stick) {
        // 用户下滑回到底部 → 恢复
        setState(() {
          _stick = true;
          _showToBottom = false;
        });
      }
      return false;
    }

    if (n is ScrollUpdateNotification) {
      if (_autoScrolling) return false; // 屏蔽自身动画
      // 仅做「到底则恢复 / 浮钮可见性」，不在此脱离
      if (nearBottom && !_stick) {
        setState(() {
          _stick = true;
          _showToBottom = false;
        });
      } else if (!nearBottom && !_stick && !_showToBottom) {
        setState(() => _showToBottom = true);
      }
    }
    return false;
  }

  /// 收敛切分：流式(!isFinal)时把末尾"未闭合块级构造"从送入解析器的文本剥离为 tail，
  /// 避免半截语法被当完整块错误渲染（表格首行泄漏 / $$ 闪烁的根因）。
  /// final 时不剥离——让尾部落定、该报错就报错（对应 markstream 的 final 门控）。
  ({String stable, String tail}) _splitForRender(String src, bool isFinal) {
    if (isFinal || src.isEmpty) return (stable: src, tail: '');
    final lines = src.split('\n');
    int cut = lines.length;

    // 1) 未闭合围栏 ```(含 ```mermaid)：fence 行奇数 → 从最后一个起挂起
    final fence = <int>[];
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trimLeft().startsWith('```')) fence.add(i);
    }
    if (fence.length.isOdd) cut = math.min(cut, fence.last);

    // 2) 未闭合块级公式 $$：仅统计 cut 之前的独占行 $$；奇数 → 从最后一个起挂起
    int dLast = -1, dCount = 0;
    for (var i = 0; i < cut; i++) {
      if (lines[i].trim() == r'$$') {
        dCount++;
        dLast = i;
      }
    }
    if (dCount.isOdd) cut = math.min(cut, dLast);

    // 3) 未完成表格：末尾连续表格行但尚无分隔行(|---|) → 整段挂起(只治首行泄漏)
    int t = cut;
    bool sawSep = false;
    while (t > 0) {
      final ln = lines[t - 1];
      if (ln.trim().isEmpty || !ln.contains('|')) break;
      if (_isTableSeparator(ln)) {
        sawSep = true;
        break;
      }
      t--;
    }
    if (!sawSep) cut = math.min(cut, t);

    if (cut >= lines.length) return (stable: src, tail: '');
    return (
      stable: lines.sublist(0, cut).join('\n'),
      tail: lines.sublist(cut).join('\n'),
    );
  }

  /// 表格分隔行判定：形如 `| --- | :--: |`，仅由 | : - 空格组成且含 - 与 |
  static bool _isTableSeparator(String line) {
    final s = line.trim();
    return s.contains('|') &&
        s.contains('-') &&
        RegExp(r'^\|?[\s:|-]+\|?$').hasMatch(s);
  }

  Widget _buildOutput() {
    if (_mode == _LabMode.stream && _streamText.isEmpty && !_streaming) {
      return const Center(child: Text('点击「重放」开始模拟流式输出'));
    }

    // 流式与静态都喂同一个「静态」渲染器；流式数据由自建累积器提供(见 _replay)。
    final bool isFinal = _mode == _LabMode.staticRender ? true : _isFinal;
    final String source =
        _mode == _LabMode.staticRender ? _textController.text : _streamText;
    final split = _splitForRender(source, isFinal);

    final markdown = SmoothMarkdown(
      key: ValueKey<int>(_session),
      data: split.stable,
      styleSheet: _styleSheet,
      config: _config,
      useEnhancedComponents: _enhanced,
      selectable: true,
      enableCache: false,
      plugins: _plugins(),
      builderRegistry: _builders(),
      onTapLink: (url) => _toast('Link: $url'),
    );

    if (split.tail.isEmpty) return markdown;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [markdown, _buildTail(split.tail)],
    );
  }

  /// 未闭合尾部的"活动"呈现：低调等宽原文，既不被错误渲染又保留流式实时可见。
  Widget _buildTail(String tail) {
    final fg = (_dark ? Colors.white : Colors.black).withValues(alpha: 0.45);
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text(
        tail,
        style: TextStyle(
            fontFamily: 'monospace', fontSize: 13, height: 1.4, color: fg),
      ),
    );
  }

  void _toast(String msg) {
    final m = ScaffoldMessenger.maybeOf(context);
    m?.hideCurrentSnackBar();
    m?.showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(milliseconds: 900)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bg = _dark ? const Color(0xFF14161A) : Colors.white;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Smooth Markdown 试验场'),
        actions: [
          IconButton(
            tooltip: _dark ? '切到浅色' : '切到深色',
            icon: Icon(_dark ? Icons.light_mode : Icons.dark_mode),
            onPressed: () => setState(() => _dark = !_dark),
          ),
        ],
      ),
      body: Column(
        children: [
          _buildControls(),
          const Divider(height: 1),
          Expanded(
            child: NotificationListener<ScrollNotification>(
              onNotification: _onScroll,
              child: Stack(
                children: [
                  Container(
                    width: double.infinity,
                    height: double.infinity,
                    color: bg,
                    padding: const EdgeInsets.all(16),
                    child: SingleChildScrollView(
                      controller: _scroll,
                      child: _buildOutput(),
                    ),
                  ),
                  if (_mode == _LabMode.stream && _follow && _showToBottom)
                    Positioned(
                      right: 16,
                      bottom: 16,
                      child: FloatingActionButton.small(
                        onPressed: _backToBottom,
                        tooltip: '回到底部并恢复跟随',
                        child: const Icon(Icons.arrow_downward),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildControls() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SegmentedButton<_LabMode>(
                segments: const [
                  ButtonSegment(
                    value: _LabMode.staticRender,
                    label: Text('静态'),
                    icon: Icon(Icons.article_outlined),
                  ),
                  ButtonSegment(
                    value: _LabMode.stream,
                    label: Text('流式'),
                    icon: Icon(Icons.stream),
                  ),
                ],
                selected: {_mode},
                onSelectionChanged: (s) => setState(() => _mode = s.first),
              ),
              const SizedBox(width: 12),
              FilterChip(
                label: const Text('Enhanced'),
                selected: _enhanced,
                onSelected: (v) => setState(() => _enhanced = v),
              ),
              if (_mode == _LabMode.stream) const SizedBox(width: 8),
              if (_mode == _LabMode.stream)
                FilterChip(
                  label: const Text('底部跟随'),
                  selected: _follow,
                  onSelected: (v) => setState(() => _follow = v),
                ),
              const Spacer(),
              if (_mode == _LabMode.stream)
                FilledButton.icon(
                  onPressed: _replay,
                  icon: Icon(_streaming ? Icons.refresh : Icons.play_arrow),
                  label: Text(_streaming ? '流式中…' : '重放'),
                ),
            ],
          ),
          if (_mode == _LabMode.stream)
            Row(
              children: [
                const Text('间隔'),
                Expanded(
                  child: Slider(
                    min: 5,
                    max: 60,
                    divisions: 11,
                    label: '${_gapMs.round()}ms',
                    value: _gapMs,
                    onChanged: (v) => setState(() => _gapMs = v),
                  ),
                ),
                const Text('块大小'),
                Expanded(
                  child: Slider(
                    min: 1,
                    max: 8,
                    divisions: 7,
                    label: '$_chunkChars 字',
                    value: _chunkChars.toDouble(),
                    onChanged: (v) => setState(() => _chunkChars = v.round()),
                  ),
                ),
              ],
            ),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('编辑测试文本'),
            children: [
              TextField(
                controller: _textController,
                maxLines: 8,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                onChanged: (_) => setState(() {}),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 自写 mermaid builder：覆盖包内置渲染，抄 markstream 的交互模型。
/// 用包公开的 [MermaidDiagram]（CustomPainter，无 WebView）；拖动平移、
/// 按钮放大/缩小（不抢页面滚轮）、可全屏。
class _LabMermaidBuilder extends MarkdownWidgetBuilder {
  const _LabMermaidBuilder({this.dark = false});

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
      child: _MermaidInteractive(code: n.code, dark: dark, inlineHeight: 300),
    );
  }
}

/// 可拖动 / 按钮缩放 / 全屏的 mermaid 视图。inlineHeight 为 null 时占满（全屏用）。
class _MermaidInteractive extends StatefulWidget {
  const _MermaidInteractive({
    required this.code,
    this.dark = false,
    this.inlineHeight,
    this.showFullscreen = true,
  });

  final String code;
  final bool dark;
  final double? inlineHeight;
  final bool showFullscreen;

  @override
  State<_MermaidInteractive> createState() => _MermaidInteractiveState();
}

class _MermaidInteractiveState extends State<_MermaidInteractive> {
  final TransformationController _tc = TransformationController();
  Size _viewport = Size.zero;
  static const double _min = 0.4;
  static const double _max = 4.0;

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }

  MermaidStyle get _style =>
      widget.dark ? MermaidStyle.dark() : const MermaidStyle();

  /// 围绕视口中心缩放，保留当前平移
  void _zoomBy(double f) {
    final m = _tc.value.clone();
    final cur = m.getMaxScaleOnAxis();
    final next = (cur * f).clamp(_min, _max);
    if ((next - cur).abs() < 0.0001) return;
    final factor = next / cur;
    final focal = _viewport == Size.zero
        ? Offset.zero
        : Offset(_viewport.width / 2, _viewport.height / 2);
    final scene = _tc.toScene(focal);
    final zoom = Matrix4.identity()
      ..translateByDouble(scene.dx, scene.dy, 0, 1)
      ..scaleByDouble(factor, factor, factor, 1)
      ..translateByDouble(-scene.dx, -scene.dy, 0, 1);
    setState(() => _tc.value = m.multiplied(zoom));
  }

  void _reset() => setState(() => _tc.value = Matrix4.identity());

  void _openFullscreen() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => Scaffold(
          backgroundColor:
              widget.dark ? const Color(0xFF14161A) : Colors.white,
          appBar: AppBar(title: const Text('Mermaid')),
          body: _MermaidInteractive(
            code: widget.code,
            dark: widget.dark,
            showFullscreen: false,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final viewer = LayoutBuilder(
      builder: (ctx, c) {
        _viewport = Size(
          c.maxWidth.isFinite ? c.maxWidth : 0,
          c.maxHeight.isFinite ? c.maxHeight : 0,
        );
        return InteractiveViewer(
          transformationController: _tc,
          scaleEnabled: false, // 滚轮/双指不缩放；缩放走按钮，滚轮归页面
          panEnabled: true, // 拖动平移
          minScale: _min,
          maxScale: _max,
          boundaryMargin: const EdgeInsets.all(80),
          child: Center(
            child: MermaidDiagram(code: widget.code, style: _style),
          ),
        );
      },
    );

    final decorated = Container(
      decoration: BoxDecoration(
        color: Color(_style.backgroundColor),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.grey.withValues(alpha: 0.3)),
      ),
      clipBehavior: Clip.antiAlias,
      child: viewer,
    );

    final content = Stack(
      children: [
        Positioned.fill(child: decorated),
        Positioned(top: 8, right: 8, child: _toolbar()),
      ],
    );

    if (widget.inlineHeight != null) {
      return SizedBox(height: widget.inlineHeight, child: content);
    }
    return content; // 全屏：由 Scaffold body 约束尺寸
  }

  Widget _toolbar() {
    Widget btn(IconData icon, String tip, VoidCallback onTap) => Material(
          color: Colors.black.withValues(alpha: 0.04),
          shape: const CircleBorder(),
          child: IconButton(
            icon: Icon(icon, size: 18),
            tooltip: tip,
            visualDensity: VisualDensity.compact,
            onPressed: onTap,
          ),
        );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        btn(Icons.remove, '缩小', () => _zoomBy(0.8)),
        const SizedBox(width: 4),
        btn(Icons.add, '放大', () => _zoomBy(1.25)),
        const SizedBox(width: 4),
        btn(Icons.center_focus_strong, '复位', _reset),
        if (widget.showFullscreen) const SizedBox(width: 4),
        if (widget.showFullscreen)
          btn(Icons.fullscreen, '全屏', _openFullscreen),
      ],
    );
  }
}
