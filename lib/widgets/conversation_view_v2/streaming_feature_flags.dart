part of '../conversation_view_v2.dart';

/// Phase 4 (P0) feature flags for ConversationViewV2 smooth streaming.
///
/// Design goals:
/// - Each P0 item has an independent toggle.
/// - A per-conversation master switch controls rollout: `enableExperimentalStreamingMarkdown`.
/// - Sub-flags can be overridden via `--dart-define` at build/run time.
/// - Runtime tuning available via [StreamingTuningParams] for debugging.
class MarkstreamV2StreamingFlags {
  static bool _masterEnabled(ConversationSettings settings) {
    return settings.enableExperimentalStreamingMarkdown;
  }

  static const bool _p0CodeBlockPreviewDuringStreaming = bool.fromEnvironment(
    'MS_P0_CODE_PREVIEW',
    defaultValue: true,
  );

  static const bool _p0MermaidStablePlaceholderDuringStreaming = bool.fromEnvironment(
    'MS_P0_MERMAID_PLACEHOLDER',
    defaultValue: true,
  );

  static const bool _p0AnchorAutoFollow = bool.fromEnvironment(
    'MS_P0_ANCHOR_AUTO_FOLLOW',
    defaultValue: true,
  );

  static const bool _p0StableFlowReveal = bool.fromEnvironment(
    'MS_P0_STABLE_FLOW_REVEAL',
    defaultValue: true,
  );

  static bool codeBlockPreviewDuringStreaming(ConversationSettings settings) {
    return _masterEnabled(settings) && _p0CodeBlockPreviewDuringStreaming;
  }

  static bool mermaidStablePlaceholderDuringStreaming(ConversationSettings settings) {
    return _masterEnabled(settings) && _p0MermaidStablePlaceholderDuringStreaming;
  }

  static bool anchorAutoFollow(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return true;
    // 调试面板参数优先
    return StreamingTuningParams.instance.anchorAutoFollow && _p0AnchorAutoFollow;
  }

  static bool stableFlowReveal(ConversationSettings settings) {
    return _masterEnabled(settings) && _p0StableFlowReveal;
  }

  static double nearBottomPx(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 80.0;
    return StreamingTuningParams.instance.nearBottomPx;
  }

  static int revealTickMs(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 32;
    return StreamingTuningParams.instance.revealTickMs;
  }

  static int revealMinBufferChars(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 64;
    return StreamingTuningParams.instance.revealMinBufferChars;
  }

  static int revealMaxCharsPerTick(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 180;
    return StreamingTuningParams.instance.revealMaxCharsPerTick;
  }

  static int revealMaxLagChars(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 1200;
    return StreamingTuningParams.instance.revealMaxLagChars;
  }

  static int scrollDurationMs(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 160;
    return StreamingTuningParams.instance.scrollDurationMs;
  }

  static int scrollThrottleMs(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 800;
    return StreamingTuningParams.instance.scrollThrottleMs;
  }

  static int fadeInDurationMs(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 150;
    return StreamingTuningParams.instance.fadeInDurationMs;
  }

  static double fadeInStartOpacity(ConversationSettings settings) {
    if (!_masterEnabled(settings)) return 0.3;
    return StreamingTuningParams.instance.fadeInStartOpacity;
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
        'scrollThrottleMs': _scrollThrottleMs,
        'anchorAutoFollow': _anchorAutoFollow,
        'fadeInDurationMs': _fadeInDurationMs,
        'fadeInStartOpacity': _fadeInStartOpacity,
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

      bool? readBool(String key) {
        final v = map[key];
        if (v is bool) return v;
        if (v is String) {
          if (v == 'true') return true;
          if (v == 'false') return false;
        }
        return null;
      }

      final tickMs = readInt('revealTickMs');
      if (tickMs != null) {
        final clamped = tickMs.clamp(8, 100);
        if (clamped != _revealTickMs) {
          _revealTickMs = clamped;
          changed = true;
        }
      }

      final maxChars = readInt('revealMaxCharsPerTick');
      if (maxChars != null) {
        final clamped = maxChars.clamp(20, 500);
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
        final clamped = maxLag.clamp(200, 3000);
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

      final scrollThrottleMs = readInt('scrollThrottleMs');
      if (scrollThrottleMs != null) {
        final clamped = scrollThrottleMs.clamp(0, 1000);
        if (clamped != _scrollThrottleMs) {
          _scrollThrottleMs = clamped;
          changed = true;
        }
      }

      final anchorAutoFollow = readBool('anchorAutoFollow');
      if (anchorAutoFollow != null && anchorAutoFollow != _anchorAutoFollow) {
        _anchorAutoFollow = anchorAutoFollow;
        changed = true;
      }

      final fadeInDurationMs = readInt('fadeInDurationMs');
      if (fadeInDurationMs != null) {
        final clamped = fadeInDurationMs.clamp(50, 500);
        if (clamped != _fadeInDurationMs) {
          _fadeInDurationMs = clamped;
          changed = true;
        }
      }

      final fadeInStartOpacity = readDouble('fadeInStartOpacity');
      if (fadeInStartOpacity != null) {
        final clamped = fadeInStartOpacity.clamp(0.0, 1.0);
        if (clamped != _fadeInStartOpacity) {
          _fadeInStartOpacity = clamped;
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

  int _scrollThrottleMs = 800;
  int get scrollThrottleMs => _scrollThrottleMs;
  set scrollThrottleMs(int v) {
    if (_scrollThrottleMs == v) return;
    _scrollThrottleMs = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  // 智能跟随模式：true=检查是否在底部，false=始终跟随
  bool _anchorAutoFollow = true;
  bool get anchorAutoFollow => _anchorAutoFollow;
  set anchorAutoFollow(bool v) {
    if (_anchorAutoFollow == v) return;
    _anchorAutoFollow = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  // 淡入动画参数
  int _fadeInDurationMs = 150;
  int get fadeInDurationMs => _fadeInDurationMs;
  set fadeInDurationMs(int v) {
    if (_fadeInDurationMs == v) return;
    _fadeInDurationMs = v;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }

  double _fadeInStartOpacity = 0.3;
  double get fadeInStartOpacity => _fadeInStartOpacity;
  set fadeInStartOpacity(double v) {
    if (_fadeInStartOpacity == v) return;
    _fadeInStartOpacity = v;
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
    _scrollThrottleMs = 800;
    _anchorAutoFollow = true;
    _fadeInDurationMs = 150;
    _fadeInStartOpacity = 0.3;
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
scrollThrottleMs: $_scrollThrottleMs
anchorAutoFollow: $_anchorAutoFollow
fadeInDurationMs: $_fadeInDurationMs
fadeInStartOpacity: $_fadeInStartOpacity
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
              Icon(Icons.tune, size: 18, color: textColor),
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
                  icon: const Icon(Icons.close, size: 18),
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
              min: 8, max: 100,
              unit: 'ms',
              onChanged: (v) => _params.revealTickMs = v.round(),
            ),
            _buildSlider(
              label: '每 Tick 字符',
              value: _params.revealMaxCharsPerTick.toDouble(),
              min: 20, max: 500,
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
              min: 200, max: 3000,
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
            _buildSlider(
              label: '滚动节流',
              value: _params.scrollThrottleMs.toDouble(),
              min: 0, max: 1000,
              unit: 'ms',
              onChanged: (v) => _params.scrollThrottleMs = v.round(),
            ),
            _buildSwitch(
              label: '智能跟随',
              value: _params.anchorAutoFollow,
              description: '开：用户上滑时停止跟随\n关：始终跟随到底部',
              onChanged: (v) => _params.anchorAutoFollow = v,
            ),
          ]),

          const SizedBox(height: 12),

          // 淡入动画
          _buildSection('淡入动画', [
            _buildSlider(
              label: '动画时长',
              value: _params.fadeInDurationMs.toDouble(),
              min: 50, max: 500,
              unit: 'ms',
              onChanged: (v) => _params.fadeInDurationMs = v.round(),
            ),
            _buildSlider(
              label: '起始透明度',
              value: _params.fadeInStartOpacity,
              min: 0, max: 1,
              unit: '',
              decimals: 2,
              onChanged: (v) => _params.fadeInStartOpacity = v,
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

  Widget _buildSwitch({
    required String label,
    required bool value,
    required String description,
    required ValueChanged<bool> onChanged,
  }) {
    return Row(
      children: [
        SizedBox(width: 90, child: Text(label, style: const TextStyle(fontSize: 12))),
        Expanded(
          child: Tooltip(
            message: description,
            child: Text(
              value ? '开' : '关',
              style: TextStyle(
                fontSize: 11,
                color: value ? Colors.green : Colors.grey,
              ),
            ),
          ),
        ),
        Switch(
          value: value,
          onChanged: onChanged,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      ],
    );
  }
}

/// Debug-only lightweight counters for streaming-related hot paths.

/// Enable by passing `--dart-define=MS_STREAM_METRICS=true`.
class MarkstreamV2StreamingMetrics {
  static const bool _enabled = bool.fromEnvironment(
    'MS_STREAM_METRICS',
    defaultValue: false,
  );

  static final _Counter _updateMessage = _Counter('updateMessage');
  static final _Counter _scrollToIndex = _Counter('scrollToIndex');

  static void onUpdateMessage() {
    if (!kDebugMode || !_enabled) return;
    _updateMessage.tick();
  }

  static void onScrollToIndex() {
    if (!kDebugMode || !_enabled) return;
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
