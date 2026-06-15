/// INPUT: 无（内置可编辑测试文本）
/// OUTPUT: MarkdownLabPage - flutter_smooth_markdown 渲染/流式试验场
/// POS: 临时试验页 / 评估 smooth_markdown 是否适合改造为 markstream 式策略
///
/// 仅用于工程评估，不接入生产链路。可从设置页进入。
/// 拆分：本库为瘦壳(页面/控制/对照台)；样本/揭示动画分置于 part 文件。
/// 渲染统一委托共享模块 OwuiSmoothMarkdown（与生产同源）。
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart'
    show ScrollDirection, RenderRepaintBoundary;
import '../chat_ui/owui/markdown.dart' show OwuiMarkdown;
import '../chat_ui/owui/smooth/owui_smooth_markdown.dart';

part 'markdown_lab_samples.dart';
part 'markdown_lab_reveal.dart';

/// 主题切换「圆形揭示」动画时长（毫秒）。新主题从一角扩散铺满的快慢。
const int _kThemeRevealMs = 520;

class MarkdownLabPage extends StatefulWidget {
  const MarkdownLabPage({super.key});

  @override
  State<MarkdownLabPage> createState() => _MarkdownLabPageState();
}

enum _LabMode { staticRender, stream }

/// 渲染引擎对照（换框架后二者同引擎，仅包装层差异；保留作回归对照）：
/// - smooth：直喂共享 OwuiSmoothMarkdown，每次 build 全量重解析 data（O(n)/帧）。
/// - production：经生产 OwuiMarkdown（同样委托 OwuiSmoothMarkdown），多 think 剥离/缩进码块归一预处理。
enum _RenderEngine { smooth, production }

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
  _RenderEngine _engine = _RenderEngine.smooth; // 渲染引擎对照（GATE）
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

  /// 纯解析压测样本：无 mermaid（避免生产引擎 WebView 干扰对照），重复文本/表格/代码/
  /// 列表/行内数学 N 次。隔离「每 chunk 重解析整段」的代价，用于换框架 GATE 公平对照。
  String _buildParseStressSample([int times = 30]) {
    const block = r'''
## 第 N 节标题

这是一段用于制造解析体量的正文，含 **加粗**、*斜体*、`行内代码` 与行内数学 $E=mc^2$。
连续多行文本放大整段重排代价，观察流式增长时帧时间是否随长度上升。

| 列 A | 列 B | 列 C |
|------|------|------|
| 1 | 2 | 3 |
| 4 | 5 | 6 |

- 列表项一
- 列表项二
  - 嵌套项

```dart
void main() {
  for (var i = 0; i < 10; i++) {
    print('line $i');
  }
}
```

> 引用块：观察流式增长时是否整段重排。
''';
    final b = StringBuffer();
    for (var i = 1; i <= times; i++) {
      b.write(block.replaceAll('第 N 节', '第 $i 节'));
      b.writeln('\n---\n');
    }
    return b.toString();
  }

  /// 载入样本文本并复位流式状态（供工具栏各样本按钮复用）。
  void _loadSample(String text) {
    setState(() {
      _textController.text = text;
      _session++;
      _streamText = '';
      _isFinal = false;
    });
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
    final Widget md = _engine == _RenderEngine.production
        ? _buildProductionBody(source, dark, isFinal)
        : _buildSmoothBody(source, dark, isFinal);
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

  /// flutter_smooth_markdown 渲染：直接复用生产同源的共享渲染模块 OwuiSmoothMarkdown
  /// （插件/builder/图片/表头守卫均封装其中），lab 与生产渲染规格完全一致。
  Widget _buildSmoothBody(String source, bool dark, bool isFinal) {
    return OwuiSmoothMarkdown(
      contentKey: ValueKey<int>(_session),
      text: source,
      isDark: dark,
      isStreaming: _mode == _LabMode.stream && !isFinal,
      useEnhancedComponents: _enhanced,
      onTapLink: (url) => _toast('Link: $url'),
    );
  }

  /// 生产渲染器对照：OwuiMarkdown 内部委托共享 OwuiSmoothMarkdown（与 smooth 同引擎，全量重解析）。
  /// 差异仅在生产包装层：think 剥离 + 缩进码块归一预处理。
  Widget _buildProductionBody(String source, bool dark, bool isFinal) {
    return OwuiMarkdown(
      text: source,
      isDark: dark,
      isStreaming: _mode == _LabMode.stream && !isFinal,
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
              SegmentedButton<_RenderEngine>(
                segments: const [
                  ButtonSegment(
                    value: _RenderEngine.smooth,
                    label: Text('Smooth'),
                    icon: Icon(Icons.auto_awesome_outlined),
                  ),
                  ButtonSegment(
                    value: _RenderEngine.production,
                    label: Text('生产'),
                    icon: Icon(Icons.verified_outlined),
                  ),
                ],
                selected: {_engine},
                onSelectionChanged: (s) => setState(() => _engine = s.first),
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
                onPressed: () => _loadSample(_buildLongSample()),
                icon: const Icon(Icons.article, size: 18),
                label: const Text('长文档'),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _loadSample(_buildParseStressSample()),
                icon: const Icon(Icons.speed, size: 18),
                label: const Text('压测'),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _loadSample(_kGallerySample),
                icon: const Icon(Icons.dashboard_customize, size: 18),
                label: const Text('全图表'),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _loadSample(_kImageSample),
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
