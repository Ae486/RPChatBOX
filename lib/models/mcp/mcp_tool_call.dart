/// MCP 工具调用数据模型
import 'dart:convert';

import 'package:hive/hive.dart';

part 'mcp_tool_call.g.dart';

/// 工具调用状态枚举
enum ToolCallStatus {
  /// 等待执行
  pending,

  /// 执行中
  running,

  /// 执行成功
  success,

  /// 执行失败
  error,
}

/// 工具调用数据（流式状态，不持久化）
class ToolCallData {
  /// 调用唯一标识
  final String callId;

  /// 工具名称
  final String toolName;

  /// 服务器名称
  final String? serverName;

  /// 当前状态
  ToolCallStatus status;

  /// 开始时间
  DateTime? startTime;

  /// 结束时间
  DateTime? endTime;

  /// 输入参数
  Map<String, dynamic>? arguments;

  /// 执行结果
  String? result;

  /// 错误信息
  String? errorMessage;

  ToolCallData({
    required this.callId,
    required this.toolName,
    this.serverName,
    this.status = ToolCallStatus.pending,
    this.startTime,
    this.endTime,
    this.arguments,
    this.result,
    this.errorMessage,
  });

  /// 获取执行耗时（毫秒）
  int? get durationMs {
    if (startTime == null) return null;
    final end = endTime ?? DateTime.now();
    return end.difference(startTime!).inMilliseconds;
  }

  /// 获取执行耗时（秒，保留1位小数）
  String get durationDisplay {
    final ms = durationMs;
    if (ms == null) return '0.0s';
    return '${(ms / 1000).toStringAsFixed(1)}s';
  }

  /// 获取参数摘要（用于折叠显示）
  String get argumentsSummary {
    if (arguments == null || arguments!.isEmpty) return '{}';
    final json = jsonEncode(arguments);
    if (json.length <= 50) return json;
    return '${json.substring(0, 47)}...';
  }

  /// 创建副本
  ToolCallData copyWith({
    String? callId,
    String? toolName,
    String? serverName,
    ToolCallStatus? status,
    DateTime? startTime,
    DateTime? endTime,
    Map<String, dynamic>? arguments,
    String? result,
    String? errorMessage,
  }) {
    return ToolCallData(
      callId: callId ?? this.callId,
      toolName: toolName ?? this.toolName,
      serverName: serverName ?? this.serverName,
      status: status ?? this.status,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      arguments: arguments ?? this.arguments,
      result: result ?? this.result,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }
}

/// 工具调用记录（持久化）
/// Hive TypeId: 61
@HiveType(typeId: 61)
class McpToolCallRecord {
  /// 调用唯一标识
  @HiveField(0)
  final String callId;

  /// 关联的消息 ID
  @HiveField(1)
  final String messageId;

  /// 工具名称
  @HiveField(2)
  final String toolName;

  /// 服务器名称
  @HiveField(3)
  final String? serverName;

  /// 状态（pending/running/success/error）
  @HiveField(4)
  final String status;

  /// 执行耗时（毫秒）
  @HiveField(5)
  final int? durationMs;

  /// 参数 JSON 字符串
  @HiveField(6)
  final String? argumentsJson;

  /// 执行结果
  @HiveField(7)
  final String? result;

  /// 错误信息
  @HiveField(8)
  final String? errorMessage;

  /// 记录时间戳
  @HiveField(9)
  final DateTime timestamp;

  McpToolCallRecord({
    required this.callId,
    required this.messageId,
    required this.toolName,
    this.serverName,
    required this.status,
    this.durationMs,
    this.argumentsJson,
    this.result,
    this.errorMessage,
    required this.timestamp,
  });

  /// 从 ToolCallData 创建记录
  factory McpToolCallRecord.fromToolCallData(
    ToolCallData data, {
    required String messageId,
  }) {
    return McpToolCallRecord(
      callId: data.callId,
      messageId: messageId,
      toolName: data.toolName,
      serverName: data.serverName,
      status: data.status.name,
      durationMs: data.durationMs,
      argumentsJson:
          data.arguments != null ? jsonEncode(data.arguments) : null,
      result: data.result,
      errorMessage: data.errorMessage,
      timestamp: DateTime.now(),
    );
  }

  /// 获取参数 Map
  Map<String, dynamic>? get arguments {
    if (argumentsJson == null) return null;
    return jsonDecode(argumentsJson!) as Map<String, dynamic>;
  }

  /// 获取状态枚举
  ToolCallStatus get statusEnum {
    switch (status) {
      case 'pending':
        return ToolCallStatus.pending;
      case 'running':
        return ToolCallStatus.running;
      case 'success':
        return ToolCallStatus.success;
      case 'error':
        return ToolCallStatus.error;
      default:
        return ToolCallStatus.pending;
    }
  }

  Map<String, dynamic> toJson() {
    return {
      'callId': callId,
      'messageId': messageId,
      'toolName': toolName,
      'serverName': serverName,
      'status': status,
      'durationMs': durationMs,
      'argumentsJson': argumentsJson,
      'result': result,
      'errorMessage': errorMessage,
      'timestamp': timestamp.toIso8601String(),
    };
  }

  factory McpToolCallRecord.fromJson(Map<String, dynamic> json) {
    return McpToolCallRecord(
      callId: json['callId'] as String,
      messageId: json['messageId'] as String,
      toolName: json['toolName'] as String,
      serverName: json['serverName'] as String?,
      status: json['status'] as String,
      durationMs: json['durationMs'] as int?,
      argumentsJson: json['argumentsJson'] as String?,
      result: json['result'] as String?,
      errorMessage: json['errorMessage'] as String?,
      timestamp: DateTime.parse(json['timestamp'] as String),
    );
  }
}

/// MCP 工具定义
class McpToolDefinition {
  /// 工具名称
  final String name;

  /// 工具描述
  final String? description;

  /// 输入参数 Schema
  final Map<String, dynamic>? inputSchema;

  /// 所属服务器 ID
  final String serverId;

  /// 所属服务器名称
  final String? serverName;

  McpToolDefinition({
    required this.name,
    this.description,
    this.inputSchema,
    required this.serverId,
    this.serverName,
  });

  /// 获取编码后的工具名称（server__tool 格式）
  String get encodedName => '${serverId}__$name';

  /// 转换为 OpenAI function calling 格式
  Map<String, dynamic> toOpenAIFormat() {
    return {
      'type': 'function',
      'function': {
        'name': encodedName,
        'description': description ?? 'Tool: $name from $serverName',
        'parameters': inputSchema ?? {'type': 'object', 'properties': {}},
      },
    };
  }
}
