import 'dart:async';
import '../adapters/ai_provider.dart';
import '../models/model_config.dart';
import '../models/conversation_settings.dart';

/// 流式输出控制器
/// 负责管理AI响应的流式输出、中断和状态控制
class StreamOutputController {
  StreamSubscription<String>? _currentSubscription;
  StreamController<String>? _outputController;
  bool _isStreaming = false;
  bool _isCancelled = false;
  String _accumulatedContent = '';

  /// 当前是否正在流式输出
  bool get isStreaming => _isStreaming;

  /// 当前是否已被取消
  bool get isCancelled => _isCancelled;

  /// 累积的内容
  String get accumulatedContent => _accumulatedContent;

  /// 开始流式输出
  ///
  /// 参数：
  /// - provider: AI服务提供商实例
  /// - model: 模型配置
  /// - messages: 对话消息列表
  /// - parameters: 模型参数
  /// - files: 附件文件（可选）
  /// - onChunk: 每个内容块的回调
  /// - onDone: 完成时的回调
  /// - onError: 错误时的回调
  Future<void> startStreaming({
    required AIProvider provider,
    required String modelName,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    required void Function(String chunk) onChunk,
    required void Function() onDone,
    required void Function(dynamic error) onError,
  }) async {
    // 如果已经在流式输出，先停止
    if (_isStreaming) {
      await stop();
    }

    // 重置状态
    _isStreaming = true;
    _isCancelled = false;
    _accumulatedContent = '';
    _outputController = StreamController<String>();

    try {
      // 获取AI响应流
      final responseStream = provider.sendMessageStream(
        model: modelName,
        messages: messages,
        parameters: parameters,
        files: files,
      );

      // 监听流
      _currentSubscription = responseStream.listen(
        (chunk) {
          if (_isCancelled) return;

          _accumulatedContent += chunk;
          _outputController?.add(chunk);
          onChunk(chunk);
        },
        onError: (error) {
          _isStreaming = false;
          onError(error);
          _cleanup();
        },
        onDone: () {
          _isStreaming = false;
          if (!_isCancelled) {
            onDone();
          }
          _cleanup();
        },
        cancelOnError: true,
      );
    } catch (e) {
      _isStreaming = false;
      onError(e);
      _cleanup();
    }
  }

  /// 停止流式输出
  ///
  /// 返回当前已累积的内容
  Future<String> stop() async {
    if (!_isStreaming) return _accumulatedContent;

    _isCancelled = true;
    _isStreaming = false;

    await _currentSubscription?.cancel();
    await _outputController?.close();

    final content = _accumulatedContent;
    _cleanup();

    return content;
  }

  /// 暂停流式输出
  void pause() {
    _currentSubscription?.pause();
  }

  /// 恢复流式输出
  void resume() {
    _currentSubscription?.resume();
  }

  /// 清理资源
  void _cleanup() {
    _currentSubscription = null;
    _outputController = null;
  }

  /// 释放资源
  void dispose() {
    stop();
  }
}

/// 流式输出状态
enum StreamState {
  idle,       // 空闲
  streaming,  // 流式输出中
  paused,     // 已暂停
  stopped,    // 已停止
  error,      // 错误
}

/// 增强版流式输出控制器
/// 提供更详细的状态管理和事件通知
class EnhancedStreamController extends StreamOutputController {
  StreamState _state = StreamState.idle;
  final _stateController = StreamController<StreamState>.broadcast();
  DateTime? _startTime;
  DateTime? _endTime;
  int _chunkCount = 0;
  dynamic _lastError;

  /// 当前状态
  StreamState get state => _state;

  /// 状态变化流
  Stream<StreamState> get stateStream => _stateController.stream;

  /// 开始时间
  DateTime? get startTime => _startTime;

  /// 结束时间
  DateTime? get endTime => _endTime;

  /// 持续时间（毫秒）
  int? get durationMs {
    if (_startTime == null) return null;
    final end = _endTime ?? DateTime.now();
    return end.difference(_startTime!).inMilliseconds;
  }

  /// 接收到的块数量
  int get chunkCount => _chunkCount;

  /// 最后的错误
  dynamic get lastError => _lastError;

  /// 平均每秒字符数
  double? get charactersPerSecond {
    final duration = durationMs;
    if (duration == null || duration == 0) return null;
    return accumulatedContent.length / (duration / 1000.0);
  }

  @override
  Future<void> startStreaming({
    required AIProvider provider,
    required String modelName,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    required void Function(String chunk) onChunk,
    required void Function() onDone,
    required void Function(dynamic error) onError,
  }) async {
    _startTime = DateTime.now();
    _endTime = null;
    _chunkCount = 0;
    _lastError = null;
    _setState(StreamState.streaming);

    await super.startStreaming(
      provider: provider,
      modelName: modelName,
      messages: messages,
      parameters: parameters,
      files: files,
      onChunk: (chunk) {
        _chunkCount++;
        onChunk(chunk);
      },
      onDone: () {
        _endTime = DateTime.now();
        _setState(StreamState.idle);
        onDone();
      },
      onError: (error) {
        _endTime = DateTime.now();
        _lastError = error;
        _setState(StreamState.error);
        onError(error);
      },
    );
  }

  @override
  Future<String> stop() async {
    _endTime = DateTime.now();
    _setState(StreamState.stopped);
    return await super.stop();
  }

  @override
  void pause() {
    super.pause();
    _setState(StreamState.paused);
  }

  @override
  void resume() {
    super.resume();
    _setState(StreamState.streaming);
  }

  /// 设置状态
  void _setState(StreamState newState) {
    if (_state != newState) {
      _state = newState;
      _stateController.add(newState);
    }
  }

  /// 重置统计信息
  void resetStats() {
    _startTime = null;
    _endTime = null;
    _chunkCount = 0;
    _lastError = null;
  }

  @override
  void dispose() {
    super.dispose();
    _stateController.close();
  }

  /// 获取性能统计
  Map<String, dynamic> getStats() {
    return {
      'state': _state.name,
      'startTime': _startTime?.toIso8601String(),
      'endTime': _endTime?.toIso8601String(),
      'durationMs': durationMs,
      'chunkCount': _chunkCount,
      'contentLength': accumulatedContent.length,
      'charactersPerSecond': charactersPerSecond,
      'isCancelled': isCancelled,
      'hasError': _lastError != null,
    };
  }
}
