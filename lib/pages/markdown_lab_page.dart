/// INPUT: 无（内置可编辑测试文本）
/// OUTPUT: MarkdownLabPage - flutter_smooth_markdown 渲染/流式试验场
/// POS: 临时试验页 / 评估 smooth_markdown 是否适合改造为 markstream 式策略
///
/// 仅用于工程评估，不接入生产链路。可从设置页进入。
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart'
    show ScrollDirection, RenderRepaintBoundary;
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter_smooth_markdown/flutter_smooth_markdown.dart';
// 以下三方包均为 smooth_markdown 的传递依赖；lab 直接复用其能力(API 取自包源码)。
// ignore: depend_on_referenced_packages
import 'package:flutter_math_fork/flutter_math.dart' show Math, MathStyle;
// ignore: depend_on_referenced_packages
import 'package:highlight/highlight.dart' show highlight, Node;
// ignore: depend_on_referenced_packages
import 'package:flutter_highlight/themes/github.dart' as hl_light;
// ignore: depend_on_referenced_packages
import 'package:flutter_highlight/themes/vs2015.dart' as hl_dark;

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

## 提示/警告块（admonition：框架有 plugin，builder 自建）

::: note 说明
这是 note 提示块，正文经框架 blockRenderer 渲染（样式与正文统一）。
:::

::: tip 小技巧
tip 提示块。
:::

::: warning 注意
warning 警告块。
:::

::: danger 危险
danger 错误块。
:::

::: important 重要
important 重要块。
:::

## 折叠块（details：框架内核能力，开箱可用）

<details>
<summary>点击展开详情</summary>
这里是被折叠的内容，框架原生支持 details 块。
</details>

## 更多 Mermaid 子图（原生 CustomPainter，验证类型推断）

```mermaid
sequenceDiagram
  participant A as 客户端
  participant B as 服务端
  A->>B: 请求
  B-->>A: 响应
```

```mermaid
pie title 渲染耗时占比
  "解析" : 25
  "布局" : 35
  "绘制" : 40
```

## d2 / infographic（框架不支持）

框架无 d2/infographic 的 parser 与 painter，Flutter 生态亦无现成渲染器；
以下 d2 块会回退为普通代码块显示（语言标 D2）：

```d2
a -> b -> c
```
''';

/// 图表/块全集样本：展示框架支持的全部 mermaid 子图 + 网络图片。
/// 各图语法逐字取自包官方 example/lib/mermaid_demo.dart（保证可渲染）。
const String _kGallerySample = r'''
# 框架支持的图表全集（原生 CustomPainter，无 WebView）

## 流程图 Flowchart

```mermaid
graph TD
    A[开始] --> B{判断}
    B -->|是| C[处理]
    B -->|否| D[结束]
    C --> D
```

## 时序图 Sequence

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as 服务器
    U->>S: 请求
    S-->>U: 响应
```

## 饼图 Pie

```mermaid
pie showData
    title 语言占比
    "Dart" : 55
    "Python" : 30
    "其他" : 15
```

## 甘特图 Gantt

```mermaid
gantt
    title 项目计划
    dateFormat YYYY-MM-DD
    section 开发
        设计 :done, des, 2024-01-01, 10d
        编码 :active, dev, after des, 20d
    section 测试
        联调 :test, after dev, 7d
```

## 时间线 Timeline

```mermaid
timeline
    title 发展历程
    2020 : 立项
    2022 : 上线
    2024 : 重构
```

## 看板 Kanban

```mermaid
kanban
  title 任务看板

  todo[待办]
    t1[需求分析]

  doing[进行中]
    t2[开发功能] @{ priority: "High" }

  done[完成]
    t3[环境搭建]
```

## 雷达图 Radar

```mermaid
radar-beta
    title 技能评估
    axis 编程, 设计, 沟通, 管理, 创新
    curve 张三{5, 3, 4, 2, 4}
    showLegend true
    max 5
    graticule polygon
    ticks 5
```

## XY 图 XY Chart

```mermaid
xychart-beta
    title "季度销售额"
    x-axis [Q1, Q2, Q3, Q4]
    y-axis "销售额(万)" 0 --> 100
    bar [23, 45, 67, 89]
    line [20, 40, 60, 85]
```

## 网络图片 Image（需联网，框架内核 builder：缓存 + 点击）

![随机图](https://picsum.photos/400/200)
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

  /// 解析插件：think / tool_call / artifact / mermaid / admonition
  /// admonition 由包提供 plugin(识别 `::: type` 块)，但包未配套 builder → 见 _builders。
  ParserPluginRegistry _plugins() => ParserPluginRegistry()
    ..register(const ThinkingPlugin())
    ..register(const ToolCallPlugin())
    ..register(const ArtifactPlugin())
    ..register(const MermaidPlugin())
    ..register(const AdmonitionPlugin());

  /// 自定义 builder 注册表（合并在 enhanced 内置之上、优先级最高）。
  /// 原则：框架有可用的直接用，仅对"缺失/不达标"的块自建：
  /// - inline_math/block_math：补回 enhanced 漏注册的 math builder + onErrorFallback
  ///   (解析失败回退空白，修复 enhanced LaTeX + 消除流式错误闪烁)
  /// - mermaid：默认两表均未注册；自建带头部栏(类型/切换/复位/复制/导出/全屏/缩放)
  /// - code_block：框架 EnhancedCodeBlock 把语言/复制浮在右上角且无折叠；自建独立头部栏
  /// - admonition：框架有 plugin 无 builder(否则显示 Unknown)；自建语义色块
  BuilderRegistry _builders() => BuilderRegistry()
    ..register('inline_math', const _SafeInlineMathBuilder())
    ..register('block_math', const _SafeBlockMathBuilder())
    ..register('mermaid', _LabMermaidBuilder(dark: _dark))
    ..register('code_block', const _LabCodeBlockBuilder())
    ..register('admonition', const _LabAdmonitionBuilder());

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

    // 关键(需求5)：enhanced 系 builder(blockquote/thinking/tool_call/artifact/header
    // 装饰、code 高亮主题)读的是 Theme.of(context) 而非传入的 styleSheet。只切 styleSheet
    // 不会改变它们 → 用与 _dark 同步的 Theme 包裹，令全部块级随深浅色切换。
    final brightness = _dark ? Brightness.dark : Brightness.light;
    return Theme(
      data: ThemeData(
        brightness: brightness,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4C6FFF),
          brightness: brightness,
        ),
      ),
      child: SmoothMarkdown(
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
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => setState(() {
                  _textController.text = _kGallerySample;
                  _session++;
                  _streamText = '';
                  _isFinal = false;
                }),
                icon: const Icon(Icons.dashboard_customize, size: 18),
                label: const Text('全图表'),
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

/// 自写 mermaid builder：覆盖包内置渲染（包默认两表均未注册 mermaid）。
/// 头部参照设计稿(Image#1)：左=图表类型，中=预览/源码切换，右=复位/复制/导出/全屏/收起；
/// 预览区右上角=缩放按钮+百分比。用包公开的 [MermaidDiagram]（CustomPainter，无 WebView）。
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

  /// 导出：RepaintBoundary 截图为 PNG。lab 验证捕获能力（提示尺寸）；
  /// 落盘/分享是宿主层细节，留待生产接入。
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
    final body = _collapsed
        ? null
        : (fill
            ? Expanded(child: _buildBody(cs))
            : SizedBox(height: widget.inlineHeight, child: _buildBody(cs)));
    return Container(
      decoration: BoxDecoration(
        color: cs.surfaceContainerLow,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: cs.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: fill ? MainAxisSize.max : MainAxisSize.min,
        children: [
          _buildHeader(cs),
          if (body != null) body,
        ],
      ),
    );
  }

  Widget _buildHeader(ColorScheme cs) {
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 4, 4, 4),
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
          const SizedBox(width: 10),
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
    Widget seg(String label, bool selected, VoidCallback onTap) => InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(6),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: selected
                  ? cs.primary.withValues(alpha: 0.16)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                color: selected ? cs.primary : cs.onSurfaceVariant,
              ),
            ),
          ),
        );
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: cs.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          seg('预览', !_showSource, () => setState(() => _showSource = false)),
          seg('源码', _showSource, () => setState(() => _showSource = true)),
        ],
      ),
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
                    boundaryMargin: const EdgeInsets.all(80),
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
        borderRadius: BorderRadius.circular(8),
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

/// 自建代码块：独立头部栏（左语言/右复制+收起），参照设计稿(Image#2)。
/// 复用框架同款高亮(highlight.parse + github/vs2015 主题表)，复制真实现，可折叠。
class _LabCodeBlockBuilder extends MarkdownWidgetBuilder {
  const _LabCodeBlockBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is CodeBlockNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as CodeBlockNode;
    return _LabCodeBlock(
        code: n.code, language: n.language, styleSheet: styleSheet);
  }
}

class _LabCodeBlock extends StatefulWidget {
  const _LabCodeBlock({
    required this.code,
    required this.styleSheet,
    this.language,
  });

  final String code;
  final String? language;
  final MarkdownStyleSheet styleSheet;

  @override
  State<_LabCodeBlock> createState() => _LabCodeBlockState();
}

class _LabCodeBlockState extends State<_LabCodeBlock> {
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
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: cs.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
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
          if (!_collapsed)
            Padding(
              padding: const EdgeInsets.all(12),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: _highlighted(context),
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
        return Text(widget.code, style: base); // 无高亮结果 → 纯文本兜底
      }
      return Text.rich(
          TextSpan(style: base, children: _convertHighlightNodes(nodes, theme)));
    } catch (_) {
      return Text(widget.code, style: base); // 未知语言/解析失败 → 纯文本
    }
  }
}

/// 自建 admonition：包有 plugin 无 builder（否则显示 Unknown node type）。
/// 正文用 context.blockRenderer 复用框架渲染器；视图层(_LabAdmonition)用 BuildContext
/// 读 Theme 深浅，配色经 alpha 适配。
class _LabAdmonitionBuilder extends MarkdownWidgetBuilder {
  const _LabAdmonitionBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is AdmonitionNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final n = node as AdmonitionNode;
    // blockRenderer 仅在此处(持 MarkdownRenderContext)可用，先算好正文交给视图层。
    return _LabAdmonition(
        node: n, body: context.blockRenderer?.call(n.children));
  }
}

class _LabAdmonition extends StatelessWidget {
  const _LabAdmonition({required this.node, this.body});

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
        borderRadius: BorderRadius.circular(8),
        border: Border(left: BorderSide(color: color, width: 4)),
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
