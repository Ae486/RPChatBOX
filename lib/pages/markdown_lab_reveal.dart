// markdown_lab_reveal.dart —— lab 主题切换揭示动画实验（part of markdown_lab_page）
part of 'markdown_lab_page.dart';

/// 主题切换揭示方案：快照式 / 双层实时 / 颜色渐变。
enum _RevealMode { snapshot, dualTree, animatedTheme }

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
