/// INPUT: 无（内置可编辑测试文本）
/// OUTPUT: MarkdownLabPage - flutter_smooth_markdown 渲染/流式试验场
/// POS: 临时试验页 / 评估 smooth_markdown 是否适合改造为 markstream 式策略
///
/// 仅用于工程评估，不接入生产链路。可从设置页进入。
library;

import 'dart:async';
import 'dart:convert' show base64Decode;
import 'dart:ffi' hide Size;
import 'dart:io' show File, Platform;
import 'dart:math' as math;
import 'dart:typed_data' show Uint8List;
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart'
    show ScrollDirection, RenderRepaintBoundary;
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter_smooth_markdown/flutter_smooth_markdown.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:win32/win32.dart'
    show
        GlobalAlloc,
        GlobalLock,
        GlobalUnlock,
        GlobalFree,
        OpenClipboard,
        EmptyClipboard,
        SetClipboardData,
        CloseClipboard,
        BITMAPV5HEADER,
        CF_DIBV5,
        BI_BITFIELDS,
        GMEM_MOVEABLE,
        GMEM_ZEROINIT;
// 以下三方包均为 smooth_markdown 的传递依赖；lab 直接复用其能力(API 取自包源码)。
// ignore: depend_on_referenced_packages
import 'package:flutter_math_fork/flutter_math.dart' show Math, MathStyle;
// ignore: depend_on_referenced_packages
import 'package:highlight/highlight.dart' show highlight, Node;
// ignore: depend_on_referenced_packages
import 'package:flutter_highlight/themes/github.dart' as hl_light;
// ignore: depend_on_referenced_packages
import 'package:flutter_highlight/themes/vs2015.dart' as hl_dark;

/// 展开/收起动画时长（毫秒）。想让动画更快就调小、更慢就调大；
/// 缓动曲线见各处 AnimatedSize 的 `curve:`（如 Curves.easeOutCubic）。
const int _kExpandMs = 220;

/// 主题切换「圆形揭示」动画时长（毫秒）。新主题从一角扩散铺满的快慢。
const int _kThemeRevealMs = 520;

/// 统一圆角半径：改这一个值，所有"有圆角"的卡片/控件一起变。
const double _kRadius = 10;

/// 表格最小宽度(逻辑像素)：可用宽度小于它时表格固定此宽+横向滚动，否则铺满。
const double _kTableMinWidth = 480;

/// 主题切换揭示方案：快照式 / 双层实时 / 颜色渐变。
enum _RevealMode { snapshot, dualTree, animatedTheme }

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

/// 图片来源测试样本：对照框架内核 ImageBuilder 对各来源的处理。
/// 预期：网络位图 / 网络 SVG 正常；本地文件 / data URI 碎图(走 Image.asset)。
const String _kImageSample = r'''
# 图片来源测试（框架默认 ImageBuilder）

> 观察框架内核 builder 对各来源的处理。预期：本地文件 / data URI 会碎图。

## 1. 网络位图 http/https —— 框架支持（CachedNetworkImage 带缓存）

![网络 PNG](https://picsum.photos/400/200)

## 2. 网络 SVG —— 框架支持（flutter_svg）

![网络 SVG](https://upload.wikimedia.org/wikipedia/commons/0/02/SVG_logo.svg)

## 3. 本地文件 —— 框架默认走 Image.asset，预期碎图

正斜杠绝对路径：

![本地-正斜杠](C:/Users/55473/Desktop/images/others/486.jpg)

反斜杠绝对路径：

![本地-反斜杠](C:\Users\55473\Desktop\images\others\486.jpg)

file URI：

![本地-fileURI](file:///C:/Users/55473/Desktop/images/others/486.jpg)

## 4. data URI base64 内联 —— 框架默认走 Image.asset，预期碎图

![内联1x1](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)

## 5. 不存在的网络图 —— 错误占位

![坏链](https://example.invalid/nope.png)
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
  // 主题切换揭示动画：通过此 key 在切换瞬间截屏 + 播放扩散
  final GlobalKey<_ThemeRevealState> _revealKey = GlobalKey<_ThemeRevealState>();
  _RevealMode _revealMode = _RevealMode.dualTree; // 默认双层实时(无快照副作用)
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
  BuilderRegistry _builders(bool dark) => BuilderRegistry()
    ..register('inline_math', const _SafeInlineMathBuilder())
    ..register('block_math', const _SafeBlockMathBuilder())
    ..register('mermaid', _LabMermaidBuilder(dark: dark))
    ..register('code_block', const _LabCodeBlockBuilder())
    ..register('admonition', const _LabAdmonitionBuilder())
    ..register('header', const _LabHeaderBuilder()) // 覆盖框架：去标题左侧竖线
    ..register('table', const _LabTableBuilder()) // 覆盖框架：最小宽+横向滚动
    ..register('link', const _LabLinkBuilder()); // 覆盖框架：链接 hover 不改变行高

  MarkdownConfig get _config =>
      const MarkdownConfig(enableLatex: true, enableEmoji: true);

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

  /// 渲染区：按当前选择的揭示方案构建。三方案共用 _canvas / _markdownBody。
  Widget _buildRevealArea() {
    final brightness = _dark ? Brightness.dark : Brightness.light;
    switch (_revealMode) {
      case _RevealMode.snapshot:
        // 快照式：截旧帧盖上，圆洞擦除露出新主题(见 _ThemeReveal)
        return _ThemeReveal(
          key: _revealKey,
          child: _canvas(brightness: brightness, controller: _scroll),
        );
      case _RevealMode.dualTree:
        // 双层实时：上下两层活树，上层新主题圆形揭示，滚动镜像同步(见 _DualTreeReveal)
        return _DualTreeReveal(
          dark: _dark,
          controller: _scroll,
          buildCanvas: (b, c) => _canvas(brightness: b, controller: c),
        );
      case _RevealMode.animatedTheme:
        // 颜色渐变：AnimatedTheme 插值环境主题；背景+增强块平滑，基础文字色离散(局限)
        return AnimatedTheme(
          data: ThemeData(
            brightness: brightness,
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFF4C6FFF),
              brightness: brightness,
            ),
            scaffoldBackgroundColor:
                _dark ? const Color(0xFF14161A) : Colors.white,
          ),
          duration: const Duration(milliseconds: _kThemeRevealMs),
          child: Builder(
            builder: (ctx) => _canvas(
              brightness: brightness,
              controller: _scroll,
              bgColor: Theme.of(ctx).scaffoldBackgroundColor,
              wrapBodyTheme: false, // 让 markdown 继承被插值的环境主题
            ),
          ),
        );
    }
  }

  /// 一层画布：背景 + 可滚动的 markdown 主体。
  Widget _canvas({
    required Brightness brightness,
    required ScrollController controller,
    Color? bgColor,
    bool wrapBodyTheme = true,
  }) {
    final bg = bgColor ??
        (brightness == Brightness.dark
            ? const Color(0xFF14161A)
            : Colors.white);
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: bg,
      padding: const EdgeInsets.all(16),
      child: SingleChildScrollView(
        controller: controller,
        child: _markdownBody(brightness, wrapTheme: wrapBodyTheme),
      ),
    );
  }

  /// 按指定亮度渲染 markdown 输出主体。
  /// wrapTheme=false 时不自带 Theme(供 AnimatedTheme 模式继承被插值的环境主题)。
  Widget _markdownBody(Brightness brightness, {bool wrapTheme = true}) {
    if (_mode == _LabMode.stream && _streamText.isEmpty && !_streaming) {
      return const Center(child: Text('点击「重放」开始模拟流式输出'));
    }
    // 流式与静态都喂同一个「静态」渲染器；流式数据由自建累积器提供(见 _replay)。
    final bool isFinal = _mode == _LabMode.staticRender ? true : _isFinal;
    final String source =
        _mode == _LabMode.staticRender ? _textController.text : _streamText;
    final bool dark = brightness == Brightness.dark;
    // enhanced 系 builder 读 Theme.of(context) 而非 styleSheet；wrapTheme 决定是否
    // 自带 Theme(快照/双层需自带固定主题，AnimatedTheme 模式则继承被插值的环境主题)。
    final rendered = _renderSource(source, isFinal);
    final imageOrder = _extractImageUrls(rendered);
    final md = SmoothMarkdown(
      key: ValueKey<int>(_session),
      data: rendered,
      styleSheet:
          dark ? MarkdownStyleSheet.dark() : MarkdownStyleSheet.light(),
      config: _config,
      useEnhancedComponents: _enhanced,
      selectable: true,
      enableCache: false,
      plugins: _plugins(),
      builderRegistry: _builders(dark),
      onTapLink: (url) => _toast('Link: $url'),
      imageBuilder: (url, alt, title) {
        final i = imageOrder.indexOf(url);
        return _LabImage(url: url, alt: alt, index: i >= 0 ? i + 1 : 0);
      },
    );
    if (!wrapTheme) return md;
    return Theme(
      data: ThemeData(
        brightness: brightness,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF4C6FFF),
          brightness: brightness,
        ),
      ),
      child: md,
    );
  }

  /// 主题切换：按所选方案触发对应动画。
  Future<void> _toggleTheme() async {
    if (_revealMode == _RevealMode.snapshot) {
      // 先停惯性滚动并锁定位置：消除 toImage 异步间隙内 offset 漂移造成的纵向偏移
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.offset);
      await _revealKey.currentState?.capture(); // 截下当前(旧)主题画面
      if (!mounted) return;
      setState(() => _dark = !_dark); // 切主题：内容在快照下方重建为新主题
      _revealKey.currentState?.play(); // 从一角擦除快照，露出新主题
    } else {
      // 双层实时 / 颜色渐变：直接切主题，由各自组件响应变化播放动画
      setState(() => _dark = !_dark);
    }
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('Smooth Markdown 试验场'),
        actions: [
          PopupMenuButton<_RevealMode>(
            tooltip: '切换动画方案',
            icon: const Icon(Icons.animation),
            initialValue: _revealMode,
            onSelected: (m) => setState(() => _revealMode = m),
            itemBuilder: (_) => const [
              PopupMenuItem(
                  value: _RevealMode.snapshot, child: Text('快照式扩散')),
              PopupMenuItem(
                  value: _RevealMode.dualTree, child: Text('双层实时扩散')),
              PopupMenuItem(
                  value: _RevealMode.animatedTheme,
                  child: Text('颜色渐变 (AnimatedTheme)')),
            ],
          ),
          IconButton(
            tooltip: _dark ? '切到浅色' : '切到深色',
            icon: Icon(_dark ? Icons.light_mode : Icons.dark_mode),
            onPressed: _toggleTheme,
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
                  _buildRevealArea(),
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
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => setState(() {
                  _textController.text = _kImageSample;
                  _session++;
                  _streamText = '';
                  _isFinal = false;
                }),
                icon: const Icon(Icons.image_outlined, size: 18),
                label: const Text('图片'),
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
            // 全屏：撑满剩余空间（折叠时留空）
            Expanded(
              child: _collapsed ? const SizedBox.shrink() : _buildBody(cs),
            )
          else
            // 内联：用 AnimatedSize 做展开/收起的高度过渡动画
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
      height: 48, // ← 图表头部高度。想更高/更矮就改这个数（单位：逻辑像素）
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
          const Spacer(), // 左弹簧：把 预览|源码 推向中间
          _toggle(cs),
          const Spacer(), // 右弹簧：与左对称 → toggle 居中
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
    // 一个分段：图标 + 文字。选中=主题色加粗，未选中=次要灰
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
    // 无背景：眼睛图标 预览 | 代码图标 源码
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
        borderRadius: BorderRadius.circular(_kRadius),
        border: Border.all(color: cs.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            height: 48, // ← 代码块头部高度。想更高/更矮就改这个数
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
          // 展开/收起平滑动画（与图表一致，时长见 _kExpandMs）
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
        // 无圆角、无四周边框，仅淡色填充 + 左侧较深色竖线(类似引用块)
        color: color.withValues(alpha: dark ? 0.16 : 0.08),
        border: Border(
          left: BorderSide(
            color: Color.lerp(color, Colors.black, 0.25)!, // 对应色的较深版
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

/// 主题切换「圆形揭示」动画容器。
/// 用法：用它包住会随主题变色的内容区；切换时先 capture() 截下旧画面，
/// 父级切主题(内容在下方重建为新主题)，再 play() 从一角把旧画面擦除。
class _ThemeReveal extends StatefulWidget {
  const _ThemeReveal({super.key, required this.child});

  final Widget child;

  @override
  State<_ThemeReveal> createState() => _ThemeRevealState();
}

class _ThemeRevealState extends State<_ThemeReveal>
    with SingleTickerProviderStateMixin {
  final GlobalKey _boundaryKey = GlobalKey();
  late final AnimationController _ac;
  ui.Image? _snapshot; // 旧主题快照，覆盖在新主题上方被逐渐挖空
  double _dpr = 1.0; // 截图时的设备像素比；回放按它 1:1 还原，避免重采样偏移

  // 扩散起点(改这里换角落)：topRight=右上、topLeft=左上、center=中心扩散…
  static const Alignment _origin = Alignment.topRight;

  @override
  void initState() {
    super.initState();
    _ac = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: _kThemeRevealMs),
    )..addStatusListener((s) {
        if (s == AnimationStatus.completed) {
          _snapshot?.dispose();
          if (mounted) setState(() => _snapshot = null);
        }
      });
  }

  @override
  void dispose() {
    _ac.dispose();
    _snapshot?.dispose();
    super.dispose();
  }

  /// 截下当前画面(应在父级切主题之前调用)。
  Future<void> capture() async {
    final obj = _boundaryKey.currentContext?.findRenderObject();
    if (obj is! RenderRepaintBoundary) return;
    final dpr = MediaQuery.of(context).devicePixelRatio;
    final img = await obj.toImage(pixelRatio: dpr);
    _snapshot?.dispose();
    if (!mounted) {
      img.dispose();
      return;
    }
    setState(() {
      _snapshot = img;
      _dpr = dpr;
      _ac.value = 0; // 半径0=快照全覆盖(此刻仍显示旧画面，无闪烁)
    });
  }

  /// 播放揭示：圆洞从一角扩大，擦除旧快照露出新主题。
  void play() {
    if (_snapshot == null) return;
    _ac.forward(from: 0);
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        RepaintBoundary(key: _boundaryKey, child: widget.child),
        if (_snapshot != null)
          Positioned(
            // 左上对齐 + 松约束，让快照按固有像素尺寸落位(不被 tight 拉伸)
            left: 0,
            top: 0,
            child: IgnorePointer(
              child: AnimatedBuilder(
                animation: _ac,
                builder: (_, __) => ClipPath(
                  clipper: _HoleClipper(_origin, _ac.value),
                  // scale:_dpr → 按截图物理像素 1:1 还原(禁止 BoxFit 重采样)，消除亚像素偏移
                  child: RawImage(
                    image: _snapshot,
                    scale: _dpr,
                    filterQuality: FilterQuality.none,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// 在矩形上从 [origin] 角挖一个半径随 [t](0..1)放大的圆洞；洞内透出下层(新主题)。
class _HoleClipper extends CustomClipper<Path> {
  _HoleClipper(this.origin, this.t);

  final Alignment origin;
  final double t; // 0=无洞(全覆盖) … 1=洞覆盖全图(全露出)

  @override
  Path getClip(Size size) {
    final rect = Path()..addRect(Offset.zero & size);
    if (t <= 0) return rect;
    final c = origin.alongSize(size);
    final maxR = <Offset>[
      Offset.zero,
      Offset(size.width, 0),
      Offset(0, size.height),
      Offset(size.width, size.height),
    ].map((p) => (p - c).distance).reduce(math.max);
    final hole = Path()
      ..addOval(Rect.fromCircle(center: c, radius: t * maxR));
    return Path.combine(PathOperation.difference, rect, hole);
  }

  @override
  bool shouldReclip(_HoleClipper old) => old.t != t || old.origin != origin;
}

/// 双层实时树主题揭示：上层(新主题)圆形揭示，下层(旧主题)实时同步滚动。
/// 无快照 → 无偏移、滚动不被静态图遮挡；代价：内容渲染两遍。
class _DualTreeReveal extends StatefulWidget {
  const _DualTreeReveal({
    required this.dark,
    required this.controller,
    required this.buildCanvas,
  });

  final bool dark; // 目标主题
  final ScrollController controller; // 新主题层(及稳态)使用的真实控制器
  final Widget Function(Brightness brightness, ScrollController controller)
      buildCanvas;

  @override
  State<_DualTreeReveal> createState() => _DualTreeRevealState();
}

class _DualTreeRevealState extends State<_DualTreeReveal>
    with SingleTickerProviderStateMixin {
  final ScrollController _mirror = ScrollController(); // 下层(旧主题)镜像滚动
  late final AnimationController _ac;
  bool _animating = false;
  Brightness? _oldBrightness; // 揭示期间下层显示的旧主题

  // 扩散起点(改这里换角落)：topRight=右上、topLeft=左上、center=中心…
  static const Alignment _origin = Alignment.topRight;

  @override
  void initState() {
    super.initState();
    _ac = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: _kThemeRevealMs),
    )..addStatusListener((s) {
        if (s == AnimationStatus.completed) {
          widget.controller.removeListener(_syncMirror);
          if (mounted) setState(() => _animating = false);
        }
      });
  }

  @override
  void didUpdateWidget(covariant _DualTreeReveal old) {
    super.didUpdateWidget(old);
    if (old.dark != widget.dark) {
      // 父级已在重建中，无需 setState：仅置状态并启动动画
      _oldBrightness = old.dark ? Brightness.dark : Brightness.light;
      _animating = true;
      widget.controller.removeListener(_syncMirror); // 防快速连切时重复累加
      widget.controller.addListener(_syncMirror);
      _ac.forward(from: 0);
    }
  }

  // 把真实滚动偏移镜像到下层，避免揭示期间两层错位
  void _syncMirror() {
    if (!_mirror.hasClients || !widget.controller.hasClients) return;
    final pos = _mirror.position;
    final target = widget.controller.offset
        .clamp(pos.minScrollExtent, pos.maxScrollExtent)
        .toDouble();
    _mirror.jumpTo(target);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_syncMirror);
    _ac.dispose();
    _mirror.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final newBrightness = widget.dark ? Brightness.dark : Brightness.light;
    final top = widget.buildCanvas(newBrightness, widget.controller);
    if (!_animating || _oldBrightness == null) return top; // 稳态：只渲染新主题
    return Stack(
      children: [
        // 下层：旧主题(实时)。吞掉其镜像滚动通知，避免干扰跟随逻辑
        NotificationListener<ScrollNotification>(
          onNotification: (_) => true,
          child: widget.buildCanvas(_oldBrightness!, _mirror),
        ),
        AnimatedBuilder(
          animation: _ac,
          builder: (_, __) => ClipPath(
            clipper: _RevealCircleClipper(_origin, _ac.value),
            child: top, // 上层：新主题，圆形从一角揭示
          ),
        ),
      ],
    );
  }
}

/// 从 [origin] 角揭示一个半径随 [t](0..1)放大的圆(圆内显示 child)。
class _RevealCircleClipper extends CustomClipper<Path> {
  _RevealCircleClipper(this.origin, this.t);

  final Alignment origin;
  final double t;

  @override
  Path getClip(Size size) {
    final c = origin.alongSize(size);
    final maxR = <Offset>[
      Offset.zero,
      Offset(size.width, 0),
      Offset(0, size.height),
      Offset(size.width, size.height),
    ].map((p) => (p - c).distance).reduce(math.max);
    return Path()..addOval(Rect.fromCircle(center: c, radius: t * maxR));
  }

  @override
  bool shouldReclip(_RevealCircleClipper old) =>
      old.t != t || old.origin != origin;
}

/// 自建 header builder：覆盖框架 EnhancedHeaderBuilder，去掉标题左侧渐变竖线
/// (保留 h1/h2 底部渐变细线)。注册 key 'header'，优先级高于框架。
class _LabHeaderBuilder extends MarkdownWidgetBuilder {
  const _LabHeaderBuilder();

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
    return _LabHeader(level: h.level, child: text);
  }
}

class _LabHeader extends StatelessWidget {
  const _LabHeader({required this.level, required this.child});

  final int level;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // 仅标题文本，无左侧竖线
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: child,
        ),
        // 保留 h1/h2 底部渐变细线(如也不想要，删掉这段即可)
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
/// 可用宽度 < _kTableMinWidth 时表格固定该宽并横向滚动，否则铺满(参考生产 owui 表格)。
class _LabTableBuilder extends MarkdownWidgetBuilder {
  const _LabTableBuilder();

  @override
  bool canBuild(MarkdownNode node) => node is TableNode;

  @override
  Widget build(
    MarkdownNode node,
    MarkdownStyleSheet styleSheet,
    MarkdownRenderContext context,
  ) {
    final t = node as TableNode;
    // 列数 = 表头/对齐/各行单元格数的最大值
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

    return _LabTableScroller(table: table);
  }
}

/// 表格横向滚动包装(参考生产 owui `_OwuiMarkdownTableWrapper`)：
/// 可用宽度 < _kTableMinWidth 时固定该宽并显示可拖动横向滚动条；否则铺满。
/// 显式 ScrollController + thumbVisibility 让桌面端能拖动滚动条横向滚动
/// (此前无 controller/滚动条，滚轮被外层纵向滚动截获，表现为"滚不动")。
class _LabTableScroller extends StatefulWidget {
  const _LabTableScroller({required this.table});

  final Widget table;

  @override
  State<_LabTableScroller> createState() => _LabTableScrollerState();
}

class _LabTableScrollerState extends State<_LabTableScroller> {
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
        // 窄屏：固定最小宽 + 始终可见且可拖动的横向滚动条
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

/// 覆盖框架增强链接：保留 hover 颜色反馈，但下划线宽度恒定，
/// 不再因 border 宽度 1→2px 动画而改变行高(框架 enhanced_link_builder 的副作用)。
class _LabLinkBuilder extends MarkdownWidgetBuilder {
  const _LabLinkBuilder();

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
    return _LabLink(
      url: n.url,
      color: styleSheet.linkStyle?.color ?? Colors.blue,
      external: external,
      onTap: () => context.onTapLink?.call(n.url),
      child: content,
    );
  }
}

class _LabLink extends StatefulWidget {
  const _LabLink({
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
  State<_LabLink> createState() => _LabLinkState();
}

class _LabLinkState extends State<_LabLink> {
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

/// lab 图片渲染：验证框架 imageBuilder 钩子可补齐"本地文件 / data URI"。
/// 来源判断顺序参考生产 _OwuiMarkdownImage：data URI → SVG → 本地文件 → 网络 → asset。
/// 轻量验证用：仅渲染 + 尺寸约束 + 圆角 + 占位/错误；不做缓存/复制/全屏预览
/// (持久化与 copy-on-import 留待后期附件存储模块改造)。
/// 解析 data URI(image)；非 base64 image 返回 null。
Uint8List? _imageDataUri(String raw) {
  if (!raw.startsWith('data:image')) return null;
  final comma = raw.indexOf(',');
  if (comma == -1) return null;
  if (!raw.substring(0, comma).contains(';base64')) return null;
  try {
    return base64Decode(raw.substring(comma + 1));
  } catch (_) {
    return null;
  }
}

/// 解析本地文件路径(file:// / Windows 盘符 / UNC / 无 scheme)；网络/其他 scheme 返回 null。
File? _imageLocalFile(String raw) {
  final uri = Uri.tryParse(raw);
  if (uri != null && uri.scheme == 'file') {
    try {
      return File.fromUri(uri);
    } catch (_) {
      return null;
    }
  }
  if (raw.startsWith('http://') || raw.startsWith('https://')) return null;
  if (RegExp(r'^[a-zA-Z]:[\\/]').hasMatch(raw)) return File(raw); // C:\ 或 C:/
  if (raw.startsWith(r'\\')) return File(raw); // UNC
  if (uri != null && uri.hasScheme) return null; // 其他 scheme 不当本地
  return File(raw); // 无 scheme 的相对/绝对路径
}

/// 读取图片字节(供复制/下载)：dataURI→decode；本地→readAsBytes；网络→http get。
Future<Uint8List?> _loadImageBytes(String url) async {
  final data = _imageDataUri(url);
  if (data != null) return data;
  final file = _imageLocalFile(url);
  if (file != null) {
    try {
      if (await file.exists()) return await file.readAsBytes();
    } catch (_) {}
    return null;
  }
  if (url.startsWith('http://') || url.startsWith('https://')) {
    try {
      final resp = await http.get(Uri.parse(url));
      if (resp.statusCode == 200) return resp.bodyBytes;
    } catch (_) {}
  }
  return null;
}

/// 解码图片字节为 RGBA 像素 + 宽高(dart:ui，无第三方解码器)。
Future<(Uint8List, int, int)?> _decodeRgba(Uint8List bytes) async {
  try {
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    final image = frame.image;
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    final w = image.width;
    final h = image.height;
    image.dispose();
    codec.dispose();
    if (data == null) return null;
    return (data.buffer.asUint8List(), w, h);
  } catch (_) {
    return null;
  }
}

/// 把 RGBA 像素写入 Windows 剪贴板(CF_DIBV5)。仅 Windows，直接调 Win32 API，无第三方框架。
/// 正确点(对比 image_clipboard 的缺陷)：用设备无关位图 DIBV5(非 DDB)、像素 BGRA、
/// bottom-up 行序、句柄交给系统后不释放。
/// 注：dart:ui rawRgba 为预乘 alpha，对不透明图无影响(半透明 png 颜色略偏，lab 验证可接受)。
bool _setClipboardImageDibv5(Uint8List rgba, int width, int height) {
  final headerSize = sizeOf<BITMAPV5HEADER>(); // 124
  final pixelSize = width * height * 4;
  final hGlobal =
      GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, headerSize + pixelSize);
  if (hGlobal == nullptr) return false;
  final ptr = GlobalLock(hGlobal);
  if (ptr == nullptr) {
    GlobalFree(hGlobal);
    return false;
  }
  try {
    final header = ptr.cast<BITMAPV5HEADER>().ref;
    header.bV5Size = headerSize;
    header.bV5Width = width;
    header.bV5Height = height; // 正值 = bottom-up(兼容性最好)
    header.bV5Planes = 1;
    header.bV5BitCount = 32;
    header.bV5Compression = BI_BITFIELDS;
    header.bV5SizeImage = pixelSize;
    header.bV5RedMask = 0x00FF0000;
    header.bV5GreenMask = 0x0000FF00;
    header.bV5BlueMask = 0x000000FF;
    header.bV5AlphaMask = 0xFF000000;
    header.bV5CSType = 0x73524742; // 'sRGB'，令系统忽略 Endpoints/Gamma
    // RGBA(top-down) → BGRA(bottom-up)
    final dst = (ptr.cast<Uint8>() + headerSize).asTypedList(pixelSize);
    for (var y = 0; y < height; y++) {
      final srcRow = (height - 1 - y) * width * 4;
      final dstRow = y * width * 4;
      for (var x = 0; x < width; x++) {
        final s = srcRow + x * 4;
        final d = dstRow + x * 4;
        dst[d] = rgba[s + 2]; // B
        dst[d + 1] = rgba[s + 1]; // G
        dst[d + 2] = rgba[s]; // R
        dst[d + 3] = rgba[s + 3]; // A
      }
    }
  } finally {
    GlobalUnlock(hGlobal);
  }
  if (OpenClipboard(0) == 0) {
    GlobalFree(hGlobal);
    return false;
  }
  EmptyClipboard();
  final ok = SetClipboardData(CF_DIBV5, hGlobal.address);
  CloseClipboard();
  if (ok == 0) {
    GlobalFree(hGlobal); // 系统未接管，释放
    return false;
  }
  return true; // 成功后所有权归系统，不释放
}

/// 按出现顺序提取 markdown 图片 url(供 [Image #N] 序号；含重复)。
List<String> _extractImageUrls(String md) {
  final re = RegExp(r'!\[[^\]]*\]\(\s*([^\s)]+)');
  return re.allMatches(md).map((m) => m.group(1) ?? '').toList();
}

/// lab 图片渲染：验证框架 imageBuilder 钩子可补齐"本地文件 / data URI"。
/// 来源顺序：data URI → SVG → 本地文件 → 网络 → asset。点击进入 _LabImageViewer 全屏。
class _LabImage extends StatelessWidget {
  const _LabImage({required this.url, this.alt, this.index = 0});

  final String url;
  final String? alt;
  final int index;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              fullscreenDialog: true,
              builder: (_) => _LabImageViewer(url: url, index: index),
            ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(_kRadius),
            child: ConstrainedBox(
              constraints:
                  const BoxConstraints(maxWidth: 480, maxHeight: 400),
              child: _content(context),
            ),
          ),
        ),
      ),
    );
  }

  Widget _content(BuildContext context) {
    // 1) data URI: data:image/...;base64,xxx → Image.memory(框架默认缺失)
    final bytes = _imageDataUri(url);
    if (bytes != null) {
      return Image.memory(bytes,
          fit: BoxFit.contain, errorBuilder: (_, __, ___) => _error(context));
    }
    // 2) SVG(网络/本地/asset) → flutter_svg(框架同款依赖)
    if (url.toLowerCase().endsWith('.svg')) return _svg(context);
    // 3) 本地文件(file:// / Windows 盘符 / UNC / 无 scheme) → Image.file(框架默认缺失)
    final file = _imageLocalFile(url);
    if (file != null) {
      return Image.file(file,
          fit: BoxFit.contain, errorBuilder: (_, __, ___) => _error(context));
    }
    // 4) 网络位图 → CachedNetworkImage(框架同款依赖，带缓存)
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return CachedNetworkImage(
        imageUrl: url,
        fit: BoxFit.contain,
        placeholder: (_, __) => _placeholder(),
        errorWidget: (_, __, ___) => _error(context),
      );
    }
    // 5) 兜底 asset
    return Image.asset(url,
        fit: BoxFit.contain, errorBuilder: (_, __, ___) => _error(context));
  }

  Widget _svg(BuildContext context) {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return SvgPicture.network(url, placeholderBuilder: (_) => _placeholder());
    }
    final file = _imageLocalFile(url);
    if (file != null) {
      return SvgPicture.file(file, placeholderBuilder: (_) => _placeholder());
    }
    return SvgPicture.asset(url, placeholderBuilder: (_) => _placeholder());
  }

  Widget _placeholder() => const SizedBox(
        width: 120,
        height: 90,
        child: Center(
          child: SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );

  Widget _error(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final bg = dark ? Colors.white10 : Colors.black12;
    final fg = dark ? Colors.white54 : Colors.black45;
    final label = (alt ?? '').trim();
    return Container(
      width: 160,
      padding: const EdgeInsets.all(12),
      color: bg,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.broken_image_outlined, size: 28, color: fg),
          if (label.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: fg)),
          ],
        ],
      ),
    );
  }
}

/// 图片全屏查看器：翻转/旋转/缩放/重置 + 复制(位图)/下载(file_picker)。
/// 对标生产 _OwuiMarkdownImage 全屏预览并增强工具栏(lab 验证)。
class _LabImageViewer extends StatefulWidget {
  const _LabImageViewer({required this.url, this.index = 0});

  final String url;
  final int index;

  @override
  State<_LabImageViewer> createState() => _LabImageViewerState();
}

class _LabImageViewerState extends State<_LabImageViewer> {
  final TransformationController _tc = TransformationController();
  int _quarter = 0; // 顺时针 90° 步进(可负)
  bool _flipH = false;
  bool _flipV = false;

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }

  void _reset() => setState(() {
        _quarter = 0;
        _flipH = false;
        _flipV = false;
        _tc.value = Matrix4.identity();
      });

  // 缩放改 _tc.value 即触发 InteractiveViewer 重建(无需 setState)。
  void _zoom(double factor) =>
      _tc.value = _tc.value.clone()..scaleByDouble(factor, factor, factor, 1.0);

  void _toast(String msg) {
    final m = ScaffoldMessenger.maybeOf(context);
    m?.hideCurrentSnackBar();
    m?.showSnackBar(SnackBar(content: Text(msg)));
  }

  String _fileName() {
    final url = widget.url;
    if (url.startsWith('data:image')) {
      final ext =
          RegExp(r'data:image/(\w+)').firstMatch(url)?.group(1) ?? 'png';
      return 'image_${widget.index > 0 ? widget.index : 1}.$ext';
    }
    final file = _imageLocalFile(url);
    if (file != null) return file.uri.pathSegments.last;
    final seg = Uri.tryParse(url)?.pathSegments;
    if (seg != null && seg.isNotEmpty && seg.last.isNotEmpty) return seg.last;
    return 'image.png';
  }

  // 复制：dart:ui 解码图片→RGBA，转 BGRA 写入 Windows 剪贴板(CF_DIBV5)。
  // 直接调系统 API(win32 FFI)，无第三方剪贴板框架；仅 Windows 验证。
  Future<void> _copy() async {
    try {
      final bytes = await _loadImageBytes(widget.url);
      if (bytes == null) {
        _toast('复制失败：无法读取图片');
        return;
      }
      if (!Platform.isWindows) {
        _toast('位图复制目前仅在 Windows 验证');
        return;
      }
      final decoded = await _decodeRgba(bytes);
      if (decoded == null) {
        _toast('复制失败：图片解码失败');
        return;
      }
      final ok = _setClipboardImageDibv5(decoded.$1, decoded.$2, decoded.$3);
      if (mounted) _toast(ok ? '已复制图片到剪贴板' : '复制失败：写入剪贴板失败');
    } catch (e) {
      if (mounted) _toast('复制失败：$e');
    }
  }

  Future<void> _download() async {
    try {
      final bytes = await _loadImageBytes(widget.url);
      if (bytes == null) {
        _toast('下载失败：无法读取图片');
        return;
      }
      final path = await FilePicker.platform.saveFile(
        dialogTitle: '保存图片',
        fileName: _fileName(),
        bytes: bytes,
      );
      if (path == null) return; // 用户取消
      await File(path).writeAsBytes(bytes); // 桌面端兜底写入
      if (mounted) _toast('已保存到 $path');
    } catch (e) {
      if (mounted) _toast('下载失败：$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: InteractiveViewer(
                transformationController: _tc,
                minScale: 0.5,
                maxScale: 5,
                child: Center(
                  child: Transform(
                    alignment: Alignment.center,
                    transform: Matrix4.identity()
                      ..rotateZ(_quarter * math.pi / 2)
                      ..scaleByDouble(
                          _flipH ? -1.0 : 1.0, _flipV ? -1.0 : 1.0, 1.0, 1.0),
                    child: _fullImage(),
                  ),
                ),
              ),
            ),
            Positioned(
              top: 8,
              left: 12,
              right: 12,
              child: Row(
                children: [
                  if (widget.index > 0)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(_kRadius),
                      ),
                      child: Text('[Image #${widget.index}]',
                          style: const TextStyle(
                              color: Colors.white, fontSize: 13)),
                    ),
                  const Spacer(),
                  _btn(Icons.close, '关闭', () => Navigator.of(context).pop()),
                ],
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 16,
              child: Center(child: _toolbar()),
            ),
          ],
        ),
      ),
    );
  }

  Widget _fullImage() {
    final url = widget.url;
    final bytes = _imageDataUri(url);
    if (bytes != null) return Image.memory(bytes, fit: BoxFit.contain);
    if (url.toLowerCase().endsWith('.svg')) {
      if (url.startsWith('http://') || url.startsWith('https://')) {
        return SvgPicture.network(url, fit: BoxFit.contain);
      }
      final f = _imageLocalFile(url);
      if (f != null) return SvgPicture.file(f, fit: BoxFit.contain);
      return SvgPicture.asset(url, fit: BoxFit.contain);
    }
    final file = _imageLocalFile(url);
    if (file != null) return Image.file(file, fit: BoxFit.contain);
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return CachedNetworkImage(imageUrl: url, fit: BoxFit.contain);
    }
    return Image.asset(url, fit: BoxFit.contain);
  }

  Widget _toolbar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(_kRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _btn(Icons.swap_vert, '垂直翻转',
              () => setState(() => _flipV = !_flipV)),
          _btn(Icons.swap_horiz, '水平翻转',
              () => setState(() => _flipH = !_flipH)),
          _btn(Icons.rotate_left, '逆时针 90°',
              () => setState(() => _quarter--)),
          _btn(Icons.rotate_right, '顺时针 90°',
              () => setState(() => _quarter++)),
          _btn(Icons.zoom_out, '缩小', () => _zoom(0.8)),
          _btn(Icons.zoom_in, '放大', () => _zoom(1.25)),
          _btn(Icons.restart_alt, '重置', _reset),
          _btn(Icons.content_copy, '复制', _copy),
          _btn(Icons.download, '下载', _download),
        ],
      ),
    );
  }

  Widget _btn(IconData icon, String tip, VoidCallback onTap) => IconButton(
        tooltip: tip,
        iconSize: 22,
        color: Colors.white,
        icon: Icon(icon),
        onPressed: onTap,
      );
}
