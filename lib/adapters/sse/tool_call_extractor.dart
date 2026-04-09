/// Tool Call Extractor
/// 从 SSE delta 中提取工具调用
import 'dart:convert';

/// 工具调用事件基类
sealed class ToolCallEvent {}

/// 工具调用开始事件
class ToolCallStarted extends ToolCallEvent {
  final String callId;
  final String name;
  final int index;

  ToolCallStarted({
    required this.callId,
    required this.name,
    required this.index,
  });
}

/// 工具调用参数更新事件
class ToolCallArgumentsUpdated extends ToolCallEvent {
  final String callId;
  final int index;
  final String argumentsChunk;

  ToolCallArgumentsUpdated({
    required this.callId,
    required this.index,
    required this.argumentsChunk,
  });
}

/// 工具调用完成事件
class ToolCallCompleted extends ToolCallEvent {
  final String callId;
  final String name;
  final int index;
  final Map<String, dynamic> arguments;

  ToolCallCompleted({
    required this.callId,
    required this.name,
    required this.index,
    required this.arguments,
  });
}

/// 工具调用累积器
class _ToolCallAccumulator {
  String id;
  String name;
  final StringBuffer argumentsBuffer;
  final int index;
  bool isComplete;

  _ToolCallAccumulator({
    required this.id,
    required this.name,
    required this.index,
  })  : argumentsBuffer = StringBuffer(),
        isComplete = false;

  void appendArguments(String chunk) {
    argumentsBuffer.write(chunk);
  }

  Map<String, dynamic>? tryParseArguments() {
    final str = argumentsBuffer.toString().trim();
    if (str.isEmpty) return {};

    try {
      return jsonDecode(str) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }
}

/// 工具调用提取器
/// 处理 OpenAI 流式响应中的 tool_calls 字段
class ToolCallExtractor {
  final Map<int, _ToolCallAccumulator> _accumulators = {};
  bool _hasToolCalls = false;

  /// 是否有工具调用
  bool get hasToolCalls => _hasToolCalls;

  /// 获取当前累积的工具调用数量
  int get pendingCount => _accumulators.length;

  /// 从 delta 中提取工具调用事件
  List<ToolCallEvent> extract(Map<String, dynamic> delta) {
    final toolCalls = delta['tool_calls'] as List?;
    if (toolCalls == null || toolCalls.isEmpty) return [];

    _hasToolCalls = true;
    final events = <ToolCallEvent>[];

    for (final tc in toolCalls) {
      final index = tc['index'] as int? ?? 0;
      final id = tc['id'] as String?;
      final type = tc['type'] as String?;
      final function = tc['function'] as Map<String, dynamic>?;

      // 新工具调用开始
      if (id != null && !_accumulators.containsKey(index)) {
        final name = function?['name'] as String? ?? '';
        _accumulators[index] = _ToolCallAccumulator(
          id: id,
          name: name,
          index: index,
        );

        events.add(ToolCallStarted(
          callId: id,
          name: name,
          index: index,
        ));
      }

      // 更新已有累积器
      final accumulator = _accumulators[index];
      if (accumulator != null) {
        // 更新 ID（某些 API 可能分开发送）
        if (id != null && accumulator.id.isEmpty) {
          accumulator.id = id;
        }

        // 更新名称
        final name = function?['name'] as String?;
        if (name != null && name.isNotEmpty && accumulator.name.isEmpty) {
          accumulator.name = name;
        }

        // 累积参数
        final argsChunk = function?['arguments'] as String?;
        if (argsChunk != null && argsChunk.isNotEmpty) {
          accumulator.appendArguments(argsChunk);

          events.add(ToolCallArgumentsUpdated(
            callId: accumulator.id,
            index: index,
            argumentsChunk: argsChunk,
          ));
        }
      }
    }

    return events;
  }

  /// 当 finish_reason == 'tool_calls' 时，完成所有累积的工具调用
  List<ToolCallCompleted> finalize() {
    final completed = <ToolCallCompleted>[];

    for (final accumulator in _accumulators.values) {
      if (!accumulator.isComplete) {
        final args = accumulator.tryParseArguments();
        if (args != null) {
          completed.add(ToolCallCompleted(
            callId: accumulator.id,
            name: accumulator.name,
            index: accumulator.index,
            arguments: args,
          ));
          accumulator.isComplete = true;
        }
      }
    }

    return completed;
  }

  /// 获取所有完成的工具调用（不清除状态）
  List<ToolCallCompleted> getCompletedCalls() {
    final completed = <ToolCallCompleted>[];

    for (final accumulator in _accumulators.values) {
      final args = accumulator.tryParseArguments();
      if (args != null) {
        completed.add(ToolCallCompleted(
          callId: accumulator.id,
          name: accumulator.name,
          index: accumulator.index,
          arguments: args,
        ));
      }
    }

    return completed;
  }

  /// 重置状态
  void reset() {
    _accumulators.clear();
    _hasToolCalls = false;
  }

  /// 检查 finish_reason 是否表示工具调用完成
  static bool isToolCallFinish(String? finishReason) {
    return finishReason == 'tool_calls' || finishReason == 'function_call';
  }

  /// 从 choice 中提取 finish_reason
  static String? extractFinishReason(Map<String, dynamic> choice) {
    return choice['finish_reason'] as String?;
  }
}
