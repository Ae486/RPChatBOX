/// Agent 核心类型定义
///
/// 定义 Agent 请求和结果类型
/// POS: Services / Roleplay / Worker / Agents
library;

import '../rp_memory_snapshot.dart';
import 'telemetry/agent_metrics.dart';

/// Agent 请求
class AgentRequest {
  /// Agent ID
  final String agentId;

  /// 输入数据
  final Map<String, dynamic> inputs;

  /// 内存读取器
  final RpWorkerMemoryReader memoryReader;

  /// 模型 ID
  final String modelId;

  /// 请求 ID（用于追踪）
  final String? requestId;

  AgentRequest({
    required this.agentId,
    required this.inputs,
    required this.memoryReader,
    required this.modelId,
    this.requestId,
  });

  /// 从 inputs 获取字符串
  String? getString(String key) => inputs[key] as String?;

  /// 从 inputs 获取整数
  int? getInt(String key) => inputs[key] as int?;

  /// 从 inputs 获取布尔值
  bool? getBool(String key) => inputs[key] as bool?;

  /// 从 inputs 获取列表
  List<dynamic>? getList(String key) => inputs[key] as List<dynamic>?;

  /// 从 inputs 获取 Map
  Map<String, dynamic>? getMap(String key) =>
      inputs[key] as Map<String, dynamic>?;
}

/// Agent 执行结果
class AgentResult {
  /// 是否成功
  final bool ok;

  /// Agent ID
  final String agentId;

  /// 生成的 Proposals
  final List<Map<String, dynamic>> proposals;

  /// 错误码
  final String? errorCode;

  /// 错误信息
  final String? errorMessage;

  /// 执行日志
  final List<String> logs;

  /// 性能指标
  final AgentResultMetrics? metrics;

  AgentResult._({
    required this.ok,
    required this.agentId,
    required this.proposals,
    this.errorCode,
    this.errorMessage,
    required this.logs,
    this.metrics,
  });

  /// 创建成功结果
  factory AgentResult.success({
    required String agentId,
    required List<Map<String, dynamic>> proposals,
    List<String>? logs,
    AgentResultMetrics? metrics,
  }) {
    return AgentResult._(
      ok: true,
      agentId: agentId,
      proposals: proposals,
      logs: logs ?? const [],
      metrics: metrics,
    );
  }

  /// 创建失败结果
  factory AgentResult.failed({
    required String agentId,
    required String errorCode,
    String? errorMessage,
    List<String>? logs,
  }) {
    return AgentResult._(
      ok: false,
      agentId: agentId,
      proposals: const [],
      errorCode: errorCode,
      errorMessage: errorMessage,
      logs: logs ?? const [],
    );
  }

  /// 创建错误结果
  factory AgentResult.error({
    required String agentId,
    required String errorCode,
    required String message,
    String? stackTrace,
  }) {
    return AgentResult._(
      ok: false,
      agentId: agentId,
      proposals: const [],
      errorCode: errorCode,
      errorMessage: message,
      logs: [if (stackTrace != null) 'StackTrace: $stackTrace'],
    );
  }

  /// 转换为 JSON
  Map<String, dynamic> toJson() => {
        'ok': ok,
        'agentId': agentId,
        'proposals': proposals,
        if (errorCode != null) 'errorCode': errorCode,
        if (errorMessage != null) 'errorMessage': errorMessage,
        'logs': logs,
        if (metrics != null) 'metrics': metrics!.toJson(),
      };
}

/// Agent 异常
class AgentException implements Exception {
  final String message;
  final String errorCode;
  final String? stackTrace;

  AgentException(this.message, this.errorCode, [this.stackTrace]);

  @override
  String toString() => 'AgentException[$errorCode]: $message';
}
