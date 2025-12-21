part of '../flyer_chat_demo_page.dart';

enum _StreamingRenderMode {
  strategyA,
  markdownStablePrefix,
}

/// 渲染速度配置
/// 
/// 参考 markstream-vue NodeRendererProps 默认值:
/// - renderBatchDelay: 16ms
/// - renderBatchBudgetMs: 6ms  
/// - streamThrottle: 见下方
class _RenderSpeedConfig {
  /// 流式更新节流时间 (ms)
  /// markstream-vue 无直接对应，但批次延迟约 16ms
  /// 范围: 20-500ms
  final int streamThrottleMs;
  
  /// 块延迟时间 (ms) - 模拟 token 到达间隔
  /// 用于测试不同网络/API 速度
  /// 范围: 10-300ms
  final int chunkDelayMs;
  
  /// 初始批次大小
  /// markstream-vue 默认: 40
  final int initialBatchSize;
  
  /// 每批节点数
  /// markstream-vue 默认: 80
  final int batchSize;

  const _RenderSpeedConfig({
    this.streamThrottleMs = 220,
    this.chunkDelayMs = 140,
    this.initialBatchSize = 40,
    this.batchSize = 80,
  });

  Duration get streamThrottle => Duration(milliseconds: streamThrottleMs);
  Duration get chunkDelay => Duration(milliseconds: chunkDelayMs);
  
  /// 预设: 慢速 (用于观察渲染过程)
  static const slow = _RenderSpeedConfig(
    streamThrottleMs: 420,
    chunkDelayMs: 240,
  );
  
  /// 预设: 正常 (平衡体验)
  static const normal = _RenderSpeedConfig(
    streamThrottleMs: 220,
    chunkDelayMs: 140,
  );
  
  /// 预设: 快速 (接近真实 API)
  static const fast = _RenderSpeedConfig(
    streamThrottleMs: 120,
    chunkDelayMs: 80,
  );
  
  /// 预设: 极快 (压力测试)
  static const ultra = _RenderSpeedConfig(
    streamThrottleMs: 60,
    chunkDelayMs: 30,
  );
  
  _RenderSpeedConfig copyWith({
    int? streamThrottleMs,
    int? chunkDelayMs,
    int? initialBatchSize,
    int? batchSize,
  }) {
    return _RenderSpeedConfig(
      streamThrottleMs: streamThrottleMs ?? this.streamThrottleMs,
      chunkDelayMs: chunkDelayMs ?? this.chunkDelayMs,
      initialBatchSize: initialBatchSize ?? this.initialBatchSize,
      batchSize: batchSize ?? this.batchSize,
    );
  }
}

class _DemoStreamManager extends ChangeNotifier {
  final ChatController _chatController;
  final Duration _chunkAnimationDuration;

  final Map<String, StreamState> _streamStates = {};
  final Map<String, TextStreamMessage> _originalMessages = {};
  final Map<String, String> _accumulatedTexts = {};

  _DemoStreamManager({
    required ChatController chatController,
    required Duration chunkAnimationDuration,
  })  : _chatController = chatController,
        _chunkAnimationDuration = chunkAnimationDuration;

  StreamState getState(String streamId) {
    return _streamStates[streamId] ?? const StreamStateLoading();
  }

  void startStream(String streamId, TextStreamMessage originalMessage) {
    _originalMessages[streamId] = originalMessage;
    _streamStates[streamId] = const StreamStateLoading();
    _accumulatedTexts[streamId] = '';
    notifyListeners();
  }

  void addChunk(String streamId, String chunk) {
    if (!_streamStates.containsKey(streamId)) return;

    var processedChunk = chunk;
    if (processedChunk.endsWith('\n') && !processedChunk.endsWith('\n\n')) {
      processedChunk = processedChunk.substring(0, processedChunk.length - 1);
    }

    _accumulatedTexts[streamId] = (_accumulatedTexts[streamId] ?? '') + processedChunk;
    _streamStates[streamId] = StreamStateStreaming(_accumulatedTexts[streamId]!);
    notifyListeners();
  }

  Future<void> completeStream(String streamId) async {
    final finalText = _accumulatedTexts[streamId];
    if (finalText == null) {
      _cleanupStream(streamId);
      return;
    }

    await Future.delayed(_chunkAnimationDuration);

    final originalMessage = _originalMessages[streamId];
    if (originalMessage == null) return;

    final finalTextMessage = TextMessage(
      id: originalMessage.id,
      authorId: originalMessage.authorId,
      createdAt: originalMessage.createdAt,
      text: finalText,
    );

    try {
      await _chatController.updateMessage(originalMessage, finalTextMessage);
    } finally {
      _cleanupStream(streamId);
    }
  }

  void _cleanupStream(String streamId) {
    _streamStates.remove(streamId);
    _originalMessages.remove(streamId);
    _accumulatedTexts.remove(streamId);
    notifyListeners();
  }
}

/// 渲染速度配置对话框
class _SpeedConfigDialog extends StatefulWidget {
  final _RenderSpeedConfig config;
  final ValueChanged<_RenderSpeedConfig> onChanged;

  const _SpeedConfigDialog({
    required this.config,
    required this.onChanged,
  });

  @override
  State<_SpeedConfigDialog> createState() => _SpeedConfigDialogState();
}

class _SpeedConfigDialogState extends State<_SpeedConfigDialog> {
  late int _streamThrottleMs;
  late int _chunkDelayMs;

  @override
  void initState() {
    super.initState();
    _streamThrottleMs = widget.config.streamThrottleMs;
    _chunkDelayMs = widget.config.chunkDelayMs;
  }

  void _applyPreset(_RenderSpeedConfig preset) {
    setState(() {
      _streamThrottleMs = preset.streamThrottleMs;
      _chunkDelayMs = preset.chunkDelayMs;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('渲染速度配置'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('预设:', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                ActionChip(
                  label: const Text('慢速'),
                  onPressed: () => _applyPreset(_RenderSpeedConfig.slow),
                ),
                ActionChip(
                  label: const Text('正常'),
                  onPressed: () => _applyPreset(_RenderSpeedConfig.normal),
                ),
                ActionChip(
                  label: const Text('快速'),
                  onPressed: () => _applyPreset(_RenderSpeedConfig.fast),
                ),
                ActionChip(
                  label: const Text('极快'),
                  onPressed: () => _applyPreset(_RenderSpeedConfig.ultra),
                ),
              ],
            ),
            const SizedBox(height: 24),
            Text('流式节流: $_streamThrottleMs ms',
                style: const TextStyle(fontWeight: FontWeight.bold)),
            const Text('控制Markdown渲染更新频率', style: TextStyle(fontSize: 12, color: Colors.grey)),
            Slider(
              value: _streamThrottleMs.toDouble(),
              min: 20,
              max: 500,
              divisions: 48,
              label: '$_streamThrottleMs ms',
              onChanged: (v) => setState(() => _streamThrottleMs = v.round()),
            ),
            const SizedBox(height: 16),
            Text('块延迟: $_chunkDelayMs ms',
                style: const TextStyle(fontWeight: FontWeight.bold)),
            const Text('模拟token到达间隔', style: TextStyle(fontSize: 12, color: Colors.grey)),
            Slider(
              value: _chunkDelayMs.toDouble(),
              min: 10,
              max: 300,
              divisions: 29,
              label: '$_chunkDelayMs ms',
              onChanged: (v) => setState(() => _chunkDelayMs = v.round()),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('参考值 (markstream-vue):', 
                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                  const SizedBox(height: 4),
                  const Text('• renderBatchDelay: 16ms', style: TextStyle(fontSize: 11)),
                  const Text('• renderBatchBudgetMs: 6ms', style: TextStyle(fontSize: 11)),
                  const Text('• 真实API约: 30-80ms/token', style: TextStyle(fontSize: 11)),
                ],
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () {
            widget.onChanged(_RenderSpeedConfig(
              streamThrottleMs: _streamThrottleMs,
              chunkDelayMs: _chunkDelayMs,
            ));
            Navigator.pop(context);
          },
          child: const Text('应用'),
        ),
      ],
    );
  }
}
