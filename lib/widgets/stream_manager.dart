import 'dart:async';
import 'package:flutter/foundation.dart';

/// 流式消息状态
enum StreamStatus {
  idle,
  streaming,
  completed,
  error,
}

/// 单个流的状态数据
class StreamData {
  final String streamId;
  String content;
  StreamStatus status;
  String? errorMessage;
  DateTime? startTime;
  DateTime? endTime;

  // 思考相关
  String thinkingContent;
  bool isThinkingOpen;
  String? currentThinkingEndTag;
  DateTime? thinkingStartTime;
  DateTime? thinkingEndTime;

  StreamData({
    required this.streamId,
    this.content = '',
    this.status = StreamStatus.idle,
    this.errorMessage,
    this.startTime,
    this.endTime,
    this.thinkingContent = '',
    this.isThinkingOpen = false,
    this.currentThinkingEndTag,
    this.thinkingStartTime,
    this.thinkingEndTime,
  });

  /// 获取思考时长（秒）
  int get thinkingDurationSeconds {
    if (thinkingStartTime == null) return 0;
    final end = thinkingEndTime ?? DateTime.now();
    return end.difference(thinkingStartTime!).inSeconds;
  }

  /// 是否正在思考
  bool get isThinking => isThinkingOpen || (thinkingContent.isNotEmpty && thinkingEndTime == null);
}

/// 流式消息管理器
///
/// 管理多个流式消息的状态，支持思考内容解析
/// 与 flutter_chat_ui 的 TextStreamMessage 配合使用
class StreamManager extends ChangeNotifier {
  final Map<String, StreamData> _streams = {};
  final Map<String, StreamController<String>> _controllers = {};

  /// 思考标签列表
  static const _thinkingTags = [
    ('<thinking>', '</thinking>'),
    ('<think>', '</think>'),
    ('<thought>', '</thought>'),
    ('<thoughts>', '</thoughts>'),
  ];

  /// 创建新的流
  /// 如果流已存在，会先清理旧流再创建新流
  void createStream(String streamId) {
    // 防止重复创建时的内存泄漏：先清理已存在的流
    if (_streams.containsKey(streamId)) {
      _controllers[streamId]?.close();
      _controllers.remove(streamId);
      _streams.remove(streamId);
    }

    _streams[streamId] = StreamData(
      streamId: streamId,
      status: StreamStatus.streaming,
      startTime: DateTime.now(),
    );
    _controllers[streamId] = StreamController<String>.broadcast();
    notifyListeners();
  }

  /// 追加内容到流
  /// 如果流已关闭或不存在，忽略本次追加
  void append(String streamId, String chunk) {
    final data = _streams[streamId];
    if (data == null) return;

    // 防止向已关闭的流追加内容
    if (data.status != StreamStatus.streaming) {
      return;
    }

    // 解析思考内容
    _parseThinkingContent(data, chunk);

    // 只有控制器未关闭时才发送事件
    final controller = _controllers[streamId];
    if (controller != null && !controller.isClosed) {
      // 发送增量内容而非全部内容，减少内存分配
      controller.add(chunk);
    }
    notifyListeners();
  }

  /// 解析思考内容
  void _parseThinkingContent(StreamData data, String chunk) {
    var remaining = chunk;

    // 如果之前有未结束的思考段，优先补齐
    if (data.isThinkingOpen) {
      final endTag = data.currentThinkingEndTag ?? '</think>';
      final endIdx = remaining.indexOf(endTag);
      if (endIdx != -1) {
        data.thinkingContent += remaining.substring(0, endIdx);
        remaining = remaining.substring(endIdx + endTag.length);
        data.isThinkingOpen = false;
        data.currentThinkingEndTag = null;
        data.thinkingEndTime = DateTime.now();
      } else {
        data.thinkingContent += remaining;
        return;
      }
    }

    // 解析本段中的思考标签
    while (true) {
      int earliestIndex = -1;
      String? detectedStartTag;
      String? detectedEndTag;

      for (final (startTag, endTag) in _thinkingTags) {
        final idx = remaining.indexOf(startTag);
        if (idx != -1 && (earliestIndex == -1 || idx < earliestIndex)) {
          earliestIndex = idx;
          detectedStartTag = startTag;
          detectedEndTag = endTag;
        }
      }

      if (earliestIndex == -1) break;

      final before = remaining.substring(0, earliestIndex);
      final afterStart = earliestIndex + detectedStartTag!.length;

      if (before.isNotEmpty) {
        data.content += before;
      }

      final endIdx = remaining.indexOf(detectedEndTag!, afterStart);

      if (data.thinkingStartTime == null) {
        data.thinkingStartTime = DateTime.now();
      }

      if (endIdx != -1) {
        data.thinkingContent += remaining.substring(afterStart, endIdx);
        remaining = remaining.substring(endIdx + detectedEndTag.length);
        data.isThinkingOpen = false;
        data.currentThinkingEndTag = null;
        data.thinkingEndTime = DateTime.now();
      } else {
        data.thinkingContent += remaining.substring(afterStart);
        data.isThinkingOpen = true;
        data.currentThinkingEndTag = detectedEndTag;
        return;
      }
    }

    if (remaining.isNotEmpty) {
      data.content += remaining;
    }
  }

  /// 结束流
  void end(String streamId) {
    final data = _streams[streamId];
    if (data == null) return;

    data.status = StreamStatus.completed;
    data.endTime = DateTime.now();

    // 如果思考还未结束，强制结束
    if (data.isThinkingOpen) {
      data.isThinkingOpen = false;
      data.thinkingEndTime = DateTime.now();
    }

    _controllers[streamId]?.close();
    notifyListeners();
  }

  /// 标记流错误
  void error(String streamId, String message) {
    final data = _streams[streamId];
    if (data == null) return;

    data.status = StreamStatus.error;
    data.errorMessage = message;
    data.endTime = DateTime.now();

    _controllers[streamId]?.close();
    notifyListeners();
  }

  /// 获取流状态
  /// 返回一个包含文本和完成状态的记录
  ({String text, bool isComplete}) getState(String streamId) {
    final data = _streams[streamId];
    if (data == null) {
      return (text: '', isComplete: true);
    }

    return (
      text: data.content,
      isComplete: data.status == StreamStatus.completed || data.status == StreamStatus.error,
    );
  }

  /// 获取流数据
  StreamData? getData(String streamId) => _streams[streamId];

  /// 获取流的 Stream
  Stream<String>? getStream(String streamId) => _controllers[streamId]?.stream;

  /// 检查流是否存在
  bool hasStream(String streamId) => _streams.containsKey(streamId);

  /// 检查流是否正在进行
  bool isStreaming(String streamId) {
    final data = _streams[streamId];
    return data?.status == StreamStatus.streaming;
  }

  /// 获取所有活跃的流 ID
  List<String> get activeStreamIds {
    return _streams.entries
        .where((e) => e.value.status == StreamStatus.streaming)
        .map((e) => e.key)
        .toList();
  }

  /// 清理已完成的流
  void cleanupCompletedStreams() {
    final completedIds = _streams.entries
        .where((e) => e.value.status == StreamStatus.completed || e.value.status == StreamStatus.error)
        .map((e) => e.key)
        .toList();

    for (final id in completedIds) {
      _streams.remove(id);
      _controllers.remove(id);
    }

    if (completedIds.isNotEmpty) {
      notifyListeners();
    }
  }

  /// 清理指定的流
  void removeStream(String streamId) {
    _streams.remove(streamId);
    _controllers[streamId]?.close();
    _controllers.remove(streamId);
    notifyListeners();
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.close();
    }
    _controllers.clear();
    _streams.clear();
    super.dispose();
  }
}
