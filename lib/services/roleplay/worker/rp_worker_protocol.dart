/// Worker Isolate 通信协议
///
/// 定义 Main Isolate 与 Worker Isolate 之间的消息格式
/// POS: Services / Roleplay / Worker
library;

import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

/// 当前协议版本
const int kRpWorkerProtocolVersion = 1;

// ============================================================================
// Envelope (统一消息格式)
// ============================================================================

/// 消息类型
abstract class RpMessageType {
  static const String request = 'request';
  static const String response = 'response';
  static const String control = 'control';
  static const String progress = 'progress';
}

/// 任务执行阶段
enum RpTaskStage {
  /// 排队中（Worker 忙碌）
  queued,

  /// 冷启动/初始化
  booting,

  /// LLM 推理中
  analyzing,

  /// JSON 管道处理
  processing,

  /// JSON 修复中
  repairing,

  /// 结果生成中
  finalizing,
}

/// RpTaskStage 扩展方法
extension RpTaskStageX on RpTaskStage {
  /// 获取阶段代码（用于序列化）
  String get code => name;

  /// 获取用户可见的显示名称
  String get displayName => switch (this) {
        RpTaskStage.queued => '排队中',
        RpTaskStage.booting => '启动中',
        RpTaskStage.analyzing => '思考中',
        RpTaskStage.processing => '整理中',
        RpTaskStage.repairing => '修正中',
        RpTaskStage.finalizing => '完成中',
      };

  /// 从代码解析阶段
  static RpTaskStage? fromCode(String code) {
    return switch (code) {
      'queued' => RpTaskStage.queued,
      'booting' => RpTaskStage.booting,
      'analyzing' => RpTaskStage.analyzing,
      'processing' => RpTaskStage.processing,
      'repairing' => RpTaskStage.repairing,
      'finalizing' => RpTaskStage.finalizing,
      _ => null,
    };
  }
}

/// 进度消息载荷
class RpWorkerProgress {
  /// 请求 ID
  final String requestId;

  /// 阶段代码
  final String stageCode;

  /// 当前尝试次数（用于重试场景）
  final int? attempt;

  /// 附加消息（调试用）
  final String? message;

  const RpWorkerProgress({
    required this.requestId,
    required this.stageCode,
    this.attempt,
    this.message,
  });

  factory RpWorkerProgress.fromJson(Map<String, dynamic> json) =>
      RpWorkerProgress(
        requestId: json['requestId'] as String,
        stageCode: json['stageCode'] as String,
        attempt: json['attempt'] as int?,
        message: json['message'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'requestId': requestId,
        'stageCode': stageCode,
        if (attempt != null) 'attempt': attempt,
        if (message != null) 'message': message,
      };

  /// 获取解析后的阶段枚举
  RpTaskStage? get stage => RpTaskStageX.fromCode(stageCode);
}

/// 协议 Envelope
///
/// 所有消息使用统一的 envelope 格式，便于路由和版本兼容
class RpWorkerEnvelope {
  /// 消息类型: request | response | control
  final String type;

  /// 协议版本号
  final int schemaVersion;

  /// 消息载荷
  final Map<String, dynamic> payload;

  RpWorkerEnvelope({
    required this.type,
    required this.schemaVersion,
    required this.payload,
  });

  factory RpWorkerEnvelope.fromJson(Map<String, dynamic> json) {
    return RpWorkerEnvelope(
      type: json['type'] as String,
      schemaVersion: json['schemaVersion'] as int? ?? 1,
      payload: json['payload'] as Map<String, dynamic>? ?? {},
    );
  }

  Map<String, dynamic> toJson() => {
        'type': type,
        'schemaVersion': schemaVersion,
        'payload': payload,
      };

  /// 创建请求 envelope
  static RpWorkerEnvelope request(RpWorkerRequest req) => RpWorkerEnvelope(
        type: RpMessageType.request,
        schemaVersion: kRpWorkerProtocolVersion,
        payload: req.toJson(),
      );

  /// 创建响应 envelope
  static RpWorkerEnvelope response(RpWorkerResponse res) => RpWorkerEnvelope(
        type: RpMessageType.response,
        schemaVersion: kRpWorkerProtocolVersion,
        payload: res.toJson(),
      );

  /// 创建控制 envelope
  static RpWorkerEnvelope control(RpWorkerControl ctrl) => RpWorkerEnvelope(
        type: RpMessageType.control,
        schemaVersion: kRpWorkerProtocolVersion,
        payload: ctrl.toJson(),
      );
}

// ============================================================================
// Request (Main → Worker)
// ============================================================================

/// Worker 请求消息
class RpWorkerRequest {
  /// 请求唯一标识
  final String requestId;

  /// 故事 ID
  final String storyId;

  /// 分支 ID
  final String branchId;

  /// 对话源版本号
  final int sourceRev;

  /// Foundation 版本号
  final int foundationRev;

  /// Story 版本号
  final int storyRev;

  /// 要执行的任务列表
  final List<String> tasks;

  /// 任务输入数据
  final Map<String, dynamic> inputs;

  /// 内存快照数据 (序列化的 Entry 数据)
  final Map<String, dynamic> memorySnapshot;

  /// 创建时间戳
  final int createdAtMs;

  /// 超时时间 (毫秒)
  final int timeoutMs;

  RpWorkerRequest({
    required this.requestId,
    required this.storyId,
    required this.branchId,
    required this.sourceRev,
    required this.foundationRev,
    required this.storyRev,
    required this.tasks,
    this.inputs = const {},
    this.memorySnapshot = const {},
    int? createdAtMs,
    this.timeoutMs = 30000,
  }) : createdAtMs = createdAtMs ?? DateTime.now().millisecondsSinceEpoch;

  factory RpWorkerRequest.fromJson(Map<String, dynamic> json) {
    return RpWorkerRequest(
      requestId: json['requestId'] as String,
      storyId: json['storyId'] as String,
      branchId: json['branchId'] as String,
      sourceRev: json['sourceRev'] as int,
      foundationRev: json['foundationRev'] as int,
      storyRev: json['storyRev'] as int,
      tasks: (json['tasks'] as List).cast<String>(),
      inputs: json['inputs'] as Map<String, dynamic>? ?? {},
      memorySnapshot: json['memorySnapshot'] as Map<String, dynamic>? ?? {},
      createdAtMs: json['createdAtMs'] as int?,
      timeoutMs: json['timeoutMs'] as int? ?? 30000,
    );
  }

  Map<String, dynamic> toJson() => {
        'requestId': requestId,
        'storyId': storyId,
        'branchId': branchId,
        'sourceRev': sourceRev,
        'foundationRev': foundationRev,
        'storyRev': storyRev,
        'tasks': tasks,
        'inputs': inputs,
        'memorySnapshot': memorySnapshot,
        'createdAtMs': createdAtMs,
        'timeoutMs': timeoutMs,
      };
}

// ============================================================================
// Response (Worker → Main)
// ============================================================================

/// Worker 响应消息
class RpWorkerResponse {
  /// 对应的请求 ID
  final String requestId;

  /// 是否成功
  final bool ok;

  /// 错误信息 (ok=false 时)
  final String? error;

  /// 错误堆栈 (ok=false 时，可选)
  final String? stackTrace;

  /// 生成的提议列表
  final List<Map<String, dynamic>> proposals;

  /// 执行日志
  final List<Map<String, dynamic>> logs;

  /// 性能指标
  final RpWorkerMetrics metrics;

  RpWorkerResponse({
    required this.requestId,
    required this.ok,
    this.error,
    this.stackTrace,
    this.proposals = const [],
    this.logs = const [],
    RpWorkerMetrics? metrics,
  }) : metrics = metrics ?? RpWorkerMetrics();

  factory RpWorkerResponse.fromJson(Map<String, dynamic> json) {
    return RpWorkerResponse(
      requestId: json['requestId'] as String,
      ok: json['ok'] as bool,
      error: json['error'] as String?,
      stackTrace: json['stackTrace'] as String?,
      proposals: (json['proposals'] as List?)
              ?.map((e) => e as Map<String, dynamic>)
              .toList() ??
          [],
      logs: (json['logs'] as List?)
              ?.map((e) => e as Map<String, dynamic>)
              .toList() ??
          [],
      metrics: json['metrics'] != null
          ? RpWorkerMetrics.fromJson(json['metrics'] as Map<String, dynamic>)
          : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'requestId': requestId,
        'ok': ok,
        if (error != null) 'error': error,
        if (stackTrace != null) 'stackTrace': stackTrace,
        'proposals': proposals,
        'logs': logs,
        'metrics': metrics.toJson(),
      };

  /// 创建成功响应
  factory RpWorkerResponse.success({
    required String requestId,
    List<Map<String, dynamic>> proposals = const [],
    List<Map<String, dynamic>> logs = const [],
    RpWorkerMetrics? metrics,
  }) {
    return RpWorkerResponse(
      requestId: requestId,
      ok: true,
      proposals: proposals,
      logs: logs,
      metrics: metrics,
    );
  }

  /// 创建错误响应
  factory RpWorkerResponse.error({
    required String requestId,
    required String error,
    String? stackTrace,
    RpWorkerMetrics? metrics,
  }) {
    return RpWorkerResponse(
      requestId: requestId,
      ok: false,
      error: error,
      stackTrace: stackTrace,
      metrics: metrics,
    );
  }
}

/// 性能指标
class RpWorkerMetrics {
  final int durationMs;
  final int llmCallCount;
  final int inputTokens;
  final int outputTokens;

  RpWorkerMetrics({
    this.durationMs = 0,
    this.llmCallCount = 0,
    this.inputTokens = 0,
    this.outputTokens = 0,
  });

  factory RpWorkerMetrics.fromJson(Map<String, dynamic> json) {
    return RpWorkerMetrics(
      durationMs: json['durationMs'] as int? ?? 0,
      llmCallCount: json['llmCallCount'] as int? ?? 0,
      inputTokens: json['inputTokens'] as int? ?? 0,
      outputTokens: json['outputTokens'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'durationMs': durationMs,
        'llmCallCount': llmCallCount,
        'inputTokens': inputTokens,
        'outputTokens': outputTokens,
      };

  RpWorkerMetrics copyWith({
    int? durationMs,
    int? llmCallCount,
    int? inputTokens,
    int? outputTokens,
  }) {
    return RpWorkerMetrics(
      durationMs: durationMs ?? this.durationMs,
      llmCallCount: llmCallCount ?? this.llmCallCount,
      inputTokens: inputTokens ?? this.inputTokens,
      outputTokens: outputTokens ?? this.outputTokens,
    );
  }
}

// ============================================================================
// Control (双向)
// ============================================================================

/// 控制消息类型
abstract class RpWorkerControlType {
  /// 初始化完成，data 包含 sendPort
  static const String ready = 'ready';

  /// 取消指定任务，data.requestId 为目标
  static const String cancel = 'cancel';

  /// 关闭 Worker
  static const String shutdown = 'shutdown';

  /// 心跳请求
  static const String ping = 'ping';

  /// 心跳响应
  static const String pong = 'pong';

  /// LLM 调用请求 (Worker → Main)
  static const String llmRequest = 'llm_request';

  /// LLM 调用响应 (Main → Worker)
  static const String llmResponse = 'llm_response';
}

/// 控制消息
class RpWorkerControl {
  /// 控制类型
  final String controlType;

  /// 相关数据
  final Map<String, dynamic>? data;

  RpWorkerControl({
    required this.controlType,
    this.data,
  });

  factory RpWorkerControl.fromJson(Map<String, dynamic> json) {
    return RpWorkerControl(
      controlType: json['controlType'] as String,
      data: json['data'] as Map<String, dynamic>?,
    );
  }

  Map<String, dynamic> toJson() => {
        'controlType': controlType,
        if (data != null) 'data': data,
      };

  /// 创建 ready 消息
  factory RpWorkerControl.ready() =>
      RpWorkerControl(controlType: RpWorkerControlType.ready);

  /// 创建 cancel 消息
  factory RpWorkerControl.cancel(String requestId) => RpWorkerControl(
        controlType: RpWorkerControlType.cancel,
        data: {'requestId': requestId},
      );

  /// 创建 shutdown 消息
  factory RpWorkerControl.shutdown() =>
      RpWorkerControl(controlType: RpWorkerControlType.shutdown);

  /// 创建 ping 消息
  factory RpWorkerControl.ping() =>
      RpWorkerControl(controlType: RpWorkerControlType.ping);

  /// 创建 pong 消息
  factory RpWorkerControl.pong() =>
      RpWorkerControl(controlType: RpWorkerControlType.pong);

  /// 创建 LLM 请求消息 (Worker → Main)
  factory RpWorkerControl.llmRequest({
    required String callId,
    required String systemPrompt,
    required String userPrompt,
    required String modelId,
    int? maxTokens,
    double? temperature,
  }) =>
      RpWorkerControl(
        controlType: RpWorkerControlType.llmRequest,
        data: {
          'callId': callId,
          'systemPrompt': systemPrompt,
          'userPrompt': userPrompt,
          'modelId': modelId,
          if (maxTokens != null) 'maxTokens': maxTokens,
          if (temperature != null) 'temperature': temperature,
        },
      );

  /// 创建 LLM 响应消息 (Main → Worker)
  factory RpWorkerControl.llmResponse({
    required String callId,
    required bool ok,
    String? output,
    String? error,
  }) =>
      RpWorkerControl(
        controlType: RpWorkerControlType.llmResponse,
        data: {
          'callId': callId,
          'ok': ok,
          if (output != null) 'output': output,
          if (error != null) 'error': error,
        },
      );
}

// ============================================================================
// Exceptions
// ============================================================================

/// Worker 异常
class RpWorkerException implements Exception {
  final String message;
  final String? stackTrace;

  RpWorkerException(this.message, [this.stackTrace]);

  @override
  String toString() => 'RpWorkerException: $message';
}

/// Worker 超时异常
class RpWorkerTimeoutException extends RpWorkerException {
  final Duration timeout;

  RpWorkerTimeoutException(String requestId, this.timeout)
      : super('任务超时: $requestId (${timeout.inMilliseconds}ms)');
}

// ============================================================================
// Serialization Helpers
// ============================================================================

/// 序列化辅助工具
abstract class RpWorkerSerializer {
  /// 将 Map 编码为 TransferableTypedData (用于大对象优化传输)
  static TransferableTypedData encodeToTransferable(Map<String, dynamic> data) {
    final jsonStr = jsonEncode(data);
    final bytes = utf8.encode(jsonStr);
    return TransferableTypedData.fromList([Uint8List.fromList(bytes)]);
  }

  /// 从 TransferableTypedData 解码
  static Map<String, dynamic> decodeFromTransferable(
      TransferableTypedData data) {
    final bytes = data.materialize().asUint8List();
    final jsonStr = utf8.decode(bytes);
    return jsonDecode(jsonStr) as Map<String, dynamic>;
  }

  /// 估算 JSON 大小 (字节)
  static int estimateJsonSize(Map<String, dynamic> data) {
    return utf8.encode(jsonEncode(data)).length;
  }

  /// 内存快照体积上限 (512KB)
  static const int maxSnapshotSize = 512 * 1024;

  /// 检查快照是否超过体积上限
  static bool isSnapshotOversized(Map<String, dynamic> snapshot) {
    return estimateJsonSize(snapshot) > maxSnapshotSize;
  }
}
