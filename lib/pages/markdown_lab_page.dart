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
// flutter_math_fork 经 smooth_markdown 传递引入；lab 直接用 Math.tex 的 onErrorFallback。
// ignore: depend_on_referenced_packages
import 'package:flutter_math_fork/flutter_math.dart' show Math, MathStyle;

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
  bool _perf = false; // 性能浮层(PerformanceOverlay)开关
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
  /// - inline_math/block_math：补回 enhanced 漏注册的 math builder，并加 onErrorFallback
  ///   解析失败回退源码原文(不红字) → 修复 enhanced LaTeX + 消除流式错误闪烁
  /// - mermaid：默认表本就不含；用自写 builder 覆盖 → 居中、且不抢页面滚轮
  BuilderRegistry _builders() => BuilderRegistry()
    ..register('inline_math', const _SafeInlineMathBuilder())
    ..register('block_math', const _SafeBlockMathBuilder())
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

  /// 长文档压测样本：重复基础样本 N 次，制造 ~千行级文档。
  /// 用于观察 smooth_markdown「每 chunk 重解析整段」在长文档下是否掉帧。
  String _buildLongSample([int times = 20]) {
    final b = StringBuffer();
    for (var i = 1; i <= times; i++) {
      b.writeln('# 第 $i 节\n');
      b.write(_kSample);
      b.writeln('\n---\n');
    }
    return b.toString();
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

  /// 边输出边渲染（相信数据流语法正确）。流式时唯一的预处理：隐藏"未成型表格头"
  /// ——分隔行 |---| 到达前的表格行会被引擎当普通段落显示出 raw `|x|x|`，故先裁掉
  /// 不显示（这是 raw 泄漏，onErrorFallback 救不了，因为它并未报错）。
  /// 其余一律照常喂引擎；latex/mermaid 流式中的临时语法错误由 builder 的
  /// onErrorFallback 兜成空白，避免红字<->正常的跳变。final 时不裁。
  String _renderSource(String src, bool isFinal) {
    if (isFinal || src.isEmpty) return src;
    final lines = src.split('\n');
    int t = lines.length;
    bool sawSep = false;
    while (t > 0) {
      final ln = lines[t - 1];
      if (ln.trim().isEmpty || !ln.contains('|')) break; // 段落边界 / 非表格行
      if (_isTableSeparator(ln)) {
        sawSep = true;
        break;
      }
      t--;
    }
    // 末尾存在「表格行但尚无分隔行」→ 裁掉这段未成型表格头(隐藏)
    if (sawSep || t == lines.length) return src;
    return lines.sublist(0, t).join('\n');
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

    return SmoothMarkdown(
      key: ValueKey<int>(_session),
      data: _renderSource(source, isFinal),
      styleSheet: _styleSheet,
      config: _config,
      useEnhancedComponents: _enhanced,
      selectable: true,
      enableCache: false,
      plugins: _plugins(),
      builderRegistry: _builders(),
      onTapLink: (url) => _toast('Link: $url'),
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
                  if (_perf)
                    Positioned(
                      top: 0,
                      left: 0,
                      right: 0,
                      child: IgnorePointer(
                        child: SizedBox(
                          height: 80,
                          child: PerformanceOverlay.allEnabled(),
                        ),
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
              const SizedBox(width: 8),
              FilterChip(
                label: const Text('性能浮层'),
                selected: _perf,
                onSelected: (v) => setState(() => _perf = v),
              ),
              if (_mode == _LabMode.stream) const SizedBox(width: 8),
              if (_mode == _LabMode.stream)
                FilterChip(
                  label: const Text('底部跟随'),
                  selected: _follow,
                  onSelected: (v) => setState(() => _follow = v),
                ),
              const Spacer(),
              OutlinedButton.icon(
                onPressed: () => setState(() {
                  _textController.text = _buildLongSample();
                  _session++;
                  _streamText = '';
                  _isFinal = false;
                }),
                icon: const Icon(Icons.article, size: 18),
                label: const Text('长文档'),
              ),
              if (_mode == _LabMode.stream) const SizedBox(width: 8),
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

/// 安全行内公式：临时/最终语法错误均回退为空白，不显示红字报错。
/// 落地用户诉求"把报错改为空白"——流式中相信数据流，临时不合法时不跳红字。
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
