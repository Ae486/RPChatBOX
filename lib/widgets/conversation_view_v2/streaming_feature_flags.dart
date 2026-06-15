/// INPUT: ConversationSettings +（可选）dart-define 覆盖
/// OUTPUT: MarkstreamV2StreamingFlags - P0 实验开关集合（供 V2/OWUI 渲染读）
/// POS: UI 层 / Chat / V2 - 流式渲染功能开关（part of ConversationViewV2）

part of '../conversation_view_v2.dart';

/// Phase 4 (P0) feature flags for ConversationViewV2 smooth streaming.
///
/// Design goals:
/// - Each P0 item has an independent toggle.
/// - A per-conversation master switch controls rollout: `enableExperimentalStreamingMarkdown`.
/// - Sub-flags can be overridden via `--dart-define` at build/run time.
/// - Runtime tuning available via [StreamingTuningParams] for debugging.
class MarkstreamV2StreamingFlags {
  static const bool _p0StableFlowReveal = bool.fromEnvironment(
    'MS_P0_STABLE_FLOW_REVEAL',
    defaultValue: true,
  );

  static bool stableFlowReveal(ConversationSettings settings) {
    // 始终启用渐进式渲染，不受主开关限制
    return _p0StableFlowReveal;
  }

  static double nearBottomPx(ConversationSettings settings) {
    // 始终使用运行时参数
    return StreamingTuningParams.instance.nearBottomPx;
  }

  static int revealTickMs(ConversationSettings settings) {
    // 始终使用运行时参数
    return StreamingTuningParams.instance.revealTickMs;
  }

  static int revealMinBufferChars(ConversationSettings settings) {
    // 始终使用运行时参数
    return StreamingTuningParams.instance.revealMinBufferChars;
  }

  static int revealMaxCharsPerTick(ConversationSettings settings) {
    // 始终使用运行时参数
    return StreamingTuningParams.instance.revealMaxCharsPerTick;
  }

  static int revealMaxLagChars(ConversationSettings settings) {
    // 始终使用运行时参数
    return StreamingTuningParams.instance.revealMaxLagChars;
  }

  static int scrollDurationMs(ConversationSettings settings) {
    // 始终使用运行时参数
    return StreamingTuningParams.instance.scrollDurationMs;
  }
}

/// 运行时可调参数（用于调试）
class StreamingTuningParams extends ChangeNotifier {
  static final StreamingTuningParams instance = StreamingTuningParams._();
  StreamingTuningParams._() {
    unawaited(ensureLoaded());
  }

  static const String _prefsKey = 'markstream_v2_streaming_tuning_params_v1';
  static const Duration _saveDebounce = Duration(milliseconds: 300);

  Future<void>? _loadFuture;
  bool _dirty = false;
  int _persistNonce = 0;
  Timer? _saveTimer;

  Future<void> ensureLoaded() {
    final existing = _loadFuture;
    if (existing != null) return existing;
    final future = _loadFromPrefs();
    _loadFuture = future;
    return future;
  }

  void _markDirtyAndScheduleSave() {
    _dirty = true;
    _persistNonce++;

    _saveTimer?.cancel();
    final nonce = _persistNonce;
    _saveTimer = Timer(_saveDebounce, () {
      unawaited(_saveToPrefs(expectedNonce: nonce));
    });
  }

  Future<void> _saveToPrefs({required int expectedNonce}) async {
    if (!_dirty) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      final payload = <String, Object?>{
        'revealTickMs': _revealTickMs,
        'revealMaxCharsPerTick': _revealMaxCharsPerTick,
        'revealMinBufferChars': _revealMinBufferChars,
        'revealMaxLagChars': _revealMaxLagChars,
        'nearBottomPx': _nearBottomPx,
        'scrollDurationMs': _scrollDurationMs,
      };
      await prefs.setString(_prefsKey, jsonEncode(payload));
      if (_persistNonce == expectedNonce) {
        _dirty = false;
      }
    } catch (_) {
      // ignore
    }
  }

  Future<void> _loadFromPrefs() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_prefsKey);
      if (raw == null || raw.trim().isEmpty) return;

      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      if (_dirty) return;

      final map = decoded.cast<String, dynamic>();
      var changed = false;

      int? readInt(String key) {
        final v = map[key];
        if (v is int) return v;
        if (v is num) return v.round();
        if (v is String) return int.tryParse(v);
        return null;
      }

      double? readDouble(String key) {
        final v = map[key];
        if (v is double) return v;
        if (v is num) return v.toDouble();
        if (v is String) return double.tryParse(v);
        return null;
      }

      final tickMs = readInt('revealTickMs');
      if (tickMs != null) {
        final clamped = tickMs.clamp(8, 500);
        if (clamped != _revealTickMs) {
          _revealTickMs = clamped;
          changed = true;
        }
      }

      final maxChars = readInt('revealMaxCharsPerTick');
      if (maxChars != null) {
        final clamped = maxChars.clamp(1, 500);
        if (clamped != _revealMaxCharsPerTick) {
          _revealMaxCharsPerTick = clamped;
          changed = true;
        }
      }

      final minBuffer = readInt('revealMinBufferChars');
      if (minBuffer != null) {
        final clamped = minBuffer.clamp(0, 200);
        if (clamped != _revealMinBufferChars) {
          _revealMinBufferChars = clamped;
          changed = true;
        }
      }

      final maxLag = readInt('revealMaxLagChars');
      if (maxLag != null) {
        final clamped = maxLag.clamp(200, 10000);
        if (clamped != _revealMaxLagChars) {
          _revealMaxLagChars = clamped;
          changed = true;
        }
      }

      final nearBottomPx = readDouble('nearBottomPx');
      if (nearBottomPx != null) {
        final clamped = nearBottomPx.clamp(20.0, 200.0);
        if (clamped != _nearBottomPx) {
          _nearBottomPx = clamped;
          changed = true;
        }
      }

      final scrollDurationMs = readInt('scrollDurationMs');
      if (scrollDurationMs != null) {
        final clamped = scrollDurationMs.clamp(0, 500);
        if (clamped != _scrollDurationMs) {
          _scrollDurationMs = clamped;
          changed = true;
        }
      }

      if (changed) notifyListeners();
    } catch (_) {
      // ignore
    }
  }

  // 渲染节奏参数
  int _revealTickMs = 32;
  int get revealTickMs => _revealTickMs;
  set revealTickMs(int v) {
    if (_revealTickMs == v) return;
    _revealTickMs = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  int _revealMaxCharsPerTick = 180;
  int get revealMaxCharsPerTick => _revealMaxCharsPerTick;
  set revealMaxCharsPerTick(int v) {
    if (_revealMaxCharsPerTick == v) return;
    _revealMaxCharsPerTick = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  int _revealMinBufferChars = 64;
  int get revealMinBufferChars => _revealMinBufferChars;
  set revealMinBufferChars(int v) {
    if (_revealMinBufferChars == v) return;
    _revealMinBufferChars = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  int _revealMaxLagChars = 1200;
  int get revealMaxLagChars => _revealMaxLagChars;
  set revealMaxLagChars(int v) {
    if (_revealMaxLagChars == v) return;
    _revealMaxLagChars = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  // 滚动参数
  double _nearBottomPx = 80.0;
  double get nearBottomPx => _nearBottomPx;
  set nearBottomPx(double v) {
    if (_nearBottomPx == v) return;
    _nearBottomPx = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  int _scrollDurationMs = 160;
  int get scrollDurationMs => _scrollDurationMs;
  set scrollDurationMs(int v) {
    if (_scrollDurationMs == v) return;
    _scrollDurationMs = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  /// 重置为默认值
  void reset() {
    _revealTickMs = 32;
    _revealMaxCharsPerTick = 180;
    _revealMinBufferChars = 64;
    _revealMaxLagChars = 1200;
    _nearBottomPx = 80.0;
    _scrollDurationMs = 160;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  /// 导出当前参数为字符串
  String export() {
    return '''
revealTickMs: $_revealTickMs
revealMaxCharsPerTick: $_revealMaxCharsPerTick
revealMinBufferChars: $_revealMinBufferChars
revealMaxLagChars: $_revealMaxLagChars
nearBottomPx: $_nearBottomPx
scrollDurationMs: $_scrollDurationMs
''';
  }
}

/// 调试面板组件
class StreamingTuningPanel extends StatefulWidget {
  final VoidCallback? onClose;

  const StreamingTuningPanel({super.key, this.onClose});

  @override
  State<StreamingTuningPanel> createState() => _StreamingTuningPanelState();
}

class _StreamingTuningPanelState extends State<StreamingTuningPanel> {
  final _params = StreamingTuningParams.instance;

  @override
  void initState() {
    super.initState();
    _params.addListener(_onParamsChanged);
  }

  @override
  void dispose() {
    _params.removeListener(_onParamsChanged);
    super.dispose();
  }

  void _onParamsChanged() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor = isDark ? const Color(0xFF1E1E1E) : const Color(0xFFF5F5F5);
    final textColor = isDark ? Colors.white70 : Colors.black87;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: isDark ? Colors.white24 : Colors.black12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(OwuiIcons.tune, size: 18, color: textColor),
              const SizedBox(width: 8),
              Text('流式渲染参数调试', style: TextStyle(fontWeight: FontWeight.bold, color: textColor)),
              const Spacer(),
              TextButton(
                onPressed: () {
                  _params.reset();
                },
                child: const Text('重置'),
              ),
              TextButton(
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: _params.export()));
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('参数已复制'), duration: Duration(seconds: 1)),
                  );
                },
                child: const Text('导出'),
              ),
              if (widget.onClose != null)
                IconButton(
                  onPressed: widget.onClose,
                  icon: const Icon(OwuiIcons.close, size: 18),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  tooltip: '关闭',
                ),
            ],
          ),
          const Divider(height: 16),

          // 渲染节奏
          _buildSection('渲染节奏', [
            _buildSlider(
              label: 'Tick 间隔',
              value: _params.revealTickMs.toDouble(),
              min: 8, max: 500,
              unit: 'ms',
              onChanged: (v) => _params.revealTickMs = v.round(),
            ),
            _buildSlider(
              label: '每 Tick 字符',
              value: _params.revealMaxCharsPerTick.toDouble(),
              min: 1, max: 500,
              unit: '字符',
              onChanged: (v) => _params.revealMaxCharsPerTick = v.round(),
            ),
            _buildSlider(
              label: '最小缓冲',
              value: _params.revealMinBufferChars.toDouble(),
              min: 0, max: 200,
              unit: '字符',
              onChanged: (v) => _params.revealMinBufferChars = v.round(),
            ),
            _buildSlider(
              label: '最大滞后',
              value: _params.revealMaxLagChars.toDouble(),
              min: 200, max: 10000,
              unit: '字符',
              onChanged: (v) => _params.revealMaxLagChars = v.round(),
            ),
          ]),

          const SizedBox(height: 12),

          // 滚动参数
          _buildSection('滚动', [
            _buildSlider(
              label: '底部检测',
              value: _params.nearBottomPx,
              min: 20, max: 200,
              unit: 'px',
              onChanged: (v) => _params.nearBottomPx = v,
            ),
            _buildSlider(
              label: '滚动时长',
              value: _params.scrollDurationMs.toDouble(),
              min: 0, max: 500,
              unit: 'ms',
              onChanged: (v) => _params.scrollDurationMs = v.round(),
            ),
          ]),
        ],
      ),
    );
  }

  Widget _buildSection(String title, List<Widget> children) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        ...children,
      ],
    );
  }

  Widget _buildSlider({
    required String label,
    required double value,
    required double min,
    required double max,
    required String unit,
    required ValueChanged<double> onChanged,
    int decimals = 0,
  }) {
    final displayValue = decimals > 0 ? value.toStringAsFixed(decimals) : value.round().toString();
    return Row(
      children: [
        SizedBox(width: 90, child: Text(label, style: const TextStyle(fontSize: 12))),
        Expanded(
          child: Slider(
            value: value.clamp(min, max),
            min: min,
            max: max,
            onChanged: onChanged,
          ),
        ),
        SizedBox(width: 60, child: Text('$displayValue$unit', style: const TextStyle(fontSize: 11))),
      ],
    );
  }
}

/// 轻量计数器：用于监控流式渲染热路径（全版本可用）
class MarkstreamV2StreamingMetrics {
  static const bool _enabled = bool.fromEnvironment(
    'MS_STREAM_METRICS',
    defaultValue: false,
  );

  static final _Counter _updateMessage = _Counter('updateMessage');
  static final _Counter _scrollToIndex = _Counter('scrollToIndex');

  static void onUpdateMessage() {
    if (!_enabled) return;
    _updateMessage.tick();
  }

  static void onScrollToIndex() {
    if (!_enabled) return;
    _scrollToIndex.tick();
  }
}

class _Counter {
  final String name;
  DateTime _windowStart = DateTime.now();
  int _count = 0;

  _Counter(this.name);

  void tick() {
    _count++;

    final now = DateTime.now();
    final elapsedMs = now.difference(_windowStart).inMilliseconds;
    if (elapsedMs < 1000) return;

    final seconds = elapsedMs / 1000.0;
    final rate = _count / seconds;

    debugPrint('[markstream-v2] $name: ${rate.toStringAsFixed(1)}/s');

    _windowStart = now;
    _count = 0;
  }
}
