/// Worker Isolate 入口点
///
/// Worker Isolate 的启动函数和消息处理逻辑
/// POS: Services / Roleplay / Worker
library;

import 'dart:async';
import 'dart:developer';
import 'dart:isolate';

import 'rp_memory_snapshot.dart';
import 'rp_worker_protocol.dart';
import 'cancellation_token.dart';
import 'agents/agent_registry.dart';
import 'agents/agent_types.dart';
import 'agents/agent_executor.dart';
import 'agents/proposal_transformer.dart';
import 'agents/model_adapter.dart';
import 'agents/json/json_pipeline.dart';
import 'agents/output/output_truncator.dart';
import 'agents/output/output_summarizer.dart';
import 'agents/telemetry/agent_metrics.dart';

/// 默认 LLM 调用超时（毫秒）
const int kDefaultLlmTimeoutMs = 30000;

/// LLM 修复调用超时（毫秒）
const int kLlmRepairTimeoutMs = 15000;

/// LLM 超时异常
class LlmTimeoutException implements Exception {
  final String callId;
  final Duration timeout;

  LlmTimeoutException(this.callId, this.timeout);

  @override
  String toString() => 'LlmTimeoutException: $callId timed out after $timeout';
}

/// Worker Isolate 入口点
///
/// 必须是顶层函数（不能是实例方法）
/// 通过 @pragma 确保 AOT 编译时不被裁剪
@pragma('vm:entry-point')
void rpWorkerEntryPoint(SendPort mainSendPort) {
  final worker = _RpWorkerIsolate(mainSendPort);
  worker.start();
}

/// Worker Isolate 内部实现
class _RpWorkerIsolate {
  final SendPort _mainSendPort;
  final ReceivePort _receivePort = ReceivePort();

  /// 当前处理中的请求 ID（用于取消检测）
  String? _currentRequestId;

  /// 是否已请求取消
  bool _cancelRequested = false;

  /// 性能统计
  int _llmCallCount = 0;
  int _inputTokens = 0;
  int _outputTokens = 0;

  /// Agent 注册表
  late final AgentRegistry _agentRegistry;

  /// Proposal 转换器注册表
  late final ProposalTransformerRegistry _transformerRegistry;

  /// Agent 执行器
  late final AgentExecutor _agentExecutor;

  /// Agent 指标收集器
  final AgentMetrics _agentMetrics = AgentMetrics();

  /// LLM 调用等待队列
  final Map<String, Completer<String>> _llmCallCompleters = {};

  /// LLM 调用计数器
  int _llmCallIdCounter = 0;

  _RpWorkerIsolate(this._mainSendPort) {
    _initAgentRegistry();
    _initTransformerRegistry();
    _initAgentExecutor();
  }

  /// 初始化 Agent 注册表
  void _initAgentRegistry() {
    _agentRegistry = AgentRegistry();
    initDefaultAgents(_agentRegistry);
  }

  /// 初始化 Transformer 注册表
  void _initTransformerRegistry() {
    _transformerRegistry = ProposalTransformerRegistry();
    initDefaultTransformers(_transformerRegistry);
  }

  /// 初始化 Agent 执行器
  void _initAgentExecutor() {
    // 创建 OutputSummarizer（复用 LLM 代理调用）
    final summarizer = OutputSummarizer(llmCall: _proxyLlmCall);

    // 创建 OutputTruncator（集成 Summarizer）
    final truncator = OutputTruncator(summarizer: summarizer);

    // 创建 JsonPipeline
    final jsonPipeline = JsonPipeline();

    // 创建 ModelAdapter
    final modelAdapter = ModelAdapter();

    _agentExecutor = AgentExecutor(
      registry: _agentRegistry,
      transformerRegistry: _transformerRegistry,
      modelAdapter: modelAdapter,
      jsonPipeline: jsonPipeline,
      truncator: truncator,
      metrics: _agentMetrics,
      llmCall: _proxyLlmCall,
    );
  }

  /// LLM 调用代理（通过 Main Isolate）
  ///
  /// 支持超时和取消机制
  Future<String> _proxyLlmCall({
    required String systemPrompt,
    required String userPrompt,
    required String modelId,
    int? maxTokens,
    double? temperature,
    int? timeoutMs,
    CancellationToken? cancellation,
  }) async {
    // 检查是否已取消
    cancellation?.throwIfCancelled();

    final callId = 'llm_${_llmCallIdCounter++}';
    final completer = Completer<String>();
    _llmCallCompleters[callId] = completer;

    // 发送 LLM 请求到 Main Isolate
    _sendControl(RpWorkerControl.llmRequest(
      callId: callId,
      systemPrompt: systemPrompt,
      userPrompt: userPrompt,
      modelId: modelId,
      maxTokens: maxTokens,
      temperature: temperature,
    ));

    _llmCallCount++;

    // 设置超时 Timer
    final timeout = timeoutMs ?? kDefaultLlmTimeoutMs;
    final timer = Timer(Duration(milliseconds: timeout), () {
      if (!completer.isCompleted) {
        _llmCallCompleters.remove(callId);
        completer.completeError(
          LlmTimeoutException(callId, Duration(milliseconds: timeout)),
        );
      }
    });

    // 监听取消信号
    StreamSubscription<void>? cancelSub;
    if (cancellation?.onCancel != null) {
      cancelSub = cancellation!.onCancel!.listen((_) {
        if (!completer.isCompleted) {
          _llmCallCompleters.remove(callId);
          completer.completeError(CancelledException('LLM call cancelled'));
        }
      });
    }

    try {
      return await completer.future;
    } finally {
      timer.cancel();
      cancelSub?.cancel();
      _llmCallCompleters.remove(callId);
    }
  }

  /// 启动 Worker
  void start() {
    // 发送 ready 消息，包含 Worker 的 SendPort
    _mainSendPort.send({
      'type': 'control',
      'schemaVersion': kRpWorkerProtocolVersion,
      'payload': {
        'controlType': RpWorkerControlType.ready,
        'data': {'sendPort': _receivePort.sendPort},
      },
    });

    // 监听消息
    _receivePort.listen(_handleMessage);

    log('Worker Isolate 启动', name: 'RpWorkerEntry');
  }

  /// 处理接收到的消息
  void _handleMessage(dynamic message) {
    if (message is! Map<String, dynamic>) {
      log('Worker 收到无效消息类型: ${message.runtimeType}', name: 'RpWorkerEntry');
      return;
    }

    try {
      final envelope = RpWorkerEnvelope.fromJson(message);

      // 校验协议版本
      if (envelope.schemaVersion > kRpWorkerProtocolVersion) {
        log(
          'Worker 协议版本不兼容: 收到 v${envelope.schemaVersion}, 当前 v$kRpWorkerProtocolVersion',
          name: 'RpWorkerEntry',
        );
        return;
      }

      switch (envelope.type) {
        case RpMessageType.request:
          _handleRequest(envelope.payload);
        case RpMessageType.control:
          _handleControl(envelope.payload);
        default:
          log('Worker 收到未知消息类型: ${envelope.type}', name: 'RpWorkerEntry');
      }
    } catch (e, stackTrace) {
      log('Worker 消息处理错误: $e', name: 'RpWorkerEntry');
      log('StackTrace: $stackTrace', name: 'RpWorkerEntry');
    }
  }

  /// 处理控制消息
  void _handleControl(Map<String, dynamic> payload) {
    final control = RpWorkerControl.fromJson(payload);

    switch (control.controlType) {
      case RpWorkerControlType.cancel:
        final requestId = control.data?['requestId'] as String?;
        if (requestId != null && requestId == _currentRequestId) {
          _cancelRequested = true;
          log('Worker 收到取消请求: $requestId', name: 'RpWorkerEntry');
        }

      case RpWorkerControlType.shutdown:
        log('Worker 收到关闭请求', name: 'RpWorkerEntry');
        _receivePort.close();
        Isolate.exit();

      case RpWorkerControlType.ping:
        _sendControl(RpWorkerControl.pong());

      case RpWorkerControlType.llmResponse:
        _handleLlmResponse(control.data);

      default:
        log('Worker 收到未知控制类型: ${control.controlType}', name: 'RpWorkerEntry');
    }
  }

  /// 处理 LLM 响应
  void _handleLlmResponse(Map<String, dynamic>? data) {
    if (data == null) return;

    final callId = data['callId'] as String?;
    if (callId == null) return;

    final completer = _llmCallCompleters[callId];
    if (completer == null) {
      log('Worker 收到未知 LLM 响应: $callId', name: 'RpWorkerEntry');
      return;
    }

    final ok = data['ok'] as bool? ?? false;
    if (ok) {
      final output = data['output'] as String? ?? '';
      completer.complete(output);
    } else {
      final error = data['error'] as String? ?? 'Unknown LLM error';
      completer.completeError(Exception(error));
    }
  }

  /// 处理请求消息
  Future<void> _handleRequest(Map<String, dynamic> payload) async {
    final startTime = DateTime.now().millisecondsSinceEpoch;
    String? requestId;

    try {
      final request = RpWorkerRequest.fromJson(payload);
      requestId = request.requestId;
      _currentRequestId = requestId;
      _cancelRequested = false;

      // 重置性能统计
      _llmCallCount = 0;
      _inputTokens = 0;
      _outputTokens = 0;

      log('Worker 开始处理请求: $requestId, tasks=${request.tasks}', name: 'RpWorkerEntry');

      // 报告开始处理
      _reportProgress(requestId, RpTaskStage.analyzing);

      // 创建内存读取器
      final memoryReader = RpWorkerMemoryReader(request.memorySnapshot);

      // 执行任务
      final proposals = <Map<String, dynamic>>[];
      final logs = <Map<String, dynamic>>[];

      for (final taskType in request.tasks) {
        // 检查取消
        if (_cancelRequested) {
          log('Worker 任务被取消: $requestId', name: 'RpWorkerEntry');
          // 已取消的请求不发送响应
          _currentRequestId = null;
          return;
        }

        final result = await _executeTask(taskType, request, memoryReader);
        proposals.addAll(result.proposals);
        logs.addAll(result.logs);
      }

      // 报告完成中
      _reportProgress(requestId, RpTaskStage.finalizing);

      // 发送成功响应
      final endTime = DateTime.now().millisecondsSinceEpoch;
      _sendResponse(RpWorkerResponse.success(
        requestId: requestId,
        proposals: proposals,
        logs: logs,
        metrics: RpWorkerMetrics(
          durationMs: endTime - startTime,
          llmCallCount: _llmCallCount,
          inputTokens: _inputTokens,
          outputTokens: _outputTokens,
        ),
      ));

      log(
        'Worker 完成请求: $requestId, proposals=${proposals.length}, duration=${endTime - startTime}ms',
        name: 'RpWorkerEntry',
      );
    } catch (e, stackTrace) {
      final endTime = DateTime.now().millisecondsSinceEpoch;

      if (requestId != null) {
        _sendResponse(RpWorkerResponse.error(
          requestId: requestId,
          error: e.toString(),
          stackTrace: stackTrace.toString(),
          metrics: RpWorkerMetrics(
            durationMs: endTime - startTime,
            llmCallCount: _llmCallCount,
            inputTokens: _inputTokens,
            outputTokens: _outputTokens,
          ),
        ));
      }

      log('Worker 请求失败: $requestId, error=$e', name: 'RpWorkerEntry');
    } finally {
      _currentRequestId = null;
    }
  }

  /// 执行单个任务
  Future<_TaskResult> _executeTask(
    String taskType,
    RpWorkerRequest request,
    RpWorkerMemoryReader memoryReader,
  ) async {
    final proposals = <Map<String, dynamic>>[];
    final logs = <Map<String, dynamic>>[];

    // 检查是否为 Agent 任务
    final agentId = _resolveAgentId(taskType);
    if (agentId != null && _agentRegistry.has(agentId)) {
      return _executeAgentTask(agentId, request, memoryReader);
    }

    // 非 Agent 任务的占位处理
    logs.add({
      'level': 'info',
      'message': '任务执行: $taskType',
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });

    switch (taskType) {
      case 'foreshadow_link':
        logs.add({
          'level': 'debug',
          'message': '伏笔链接完成（占位）',
          'timestamp': DateTime.now().millisecondsSinceEpoch,
        });

      case 'summarize':
        logs.add({
          'level': 'debug',
          'message': '摘要压缩完成（占位）',
          'timestamp': DateTime.now().millisecondsSinceEpoch,
        });

      default:
        logs.add({
          'level': 'warn',
          'message': '未知任务类型: $taskType',
          'timestamp': DateTime.now().millisecondsSinceEpoch,
        });
    }

    return _TaskResult(proposals: proposals, logs: logs);
  }

  /// 解析 Agent ID
  String? _resolveAgentId(String taskType) {
    // 直接匹配
    if (_agentRegistry.has(taskType)) return taskType;

    // agent: 前缀
    if (taskType.startsWith('agent:')) {
      return taskType.substring(6);
    }

    // 旧任务名映射
    return switch (taskType) {
      'scene_detect' => 'scene_detector',
      'state_update' => 'state_updater',
      'consistency_heavy' => 'consistency_heavy',
      _ => null,
    };
  }

  /// 执行 Agent 任务
  Future<_TaskResult> _executeAgentTask(
    String agentId,
    RpWorkerRequest request,
    RpWorkerMemoryReader memoryReader,
  ) async {
    final logs = <Map<String, dynamic>>[];

    logs.add({
      'level': 'info',
      'message': 'Agent 任务开始: $agentId',
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });

    // 创建 Agent 请求
    final agentRequest = AgentRequest(
      agentId: agentId,
      inputs: request.inputs,
      memoryReader: memoryReader,
      modelId: request.inputs['modelId'] as String? ?? 'unknown',
      requestId: request.requestId,
    );

    // 报告进入处理阶段（JSON 管道处理）
    _reportProgress(request.requestId, RpTaskStage.processing);

    // 使用 AgentExecutor 执行（包含 LLM 调用和 JSON 管道）
    final result = await _agentExecutor.execute(
      agentRequest,
      onProgress: (stage, {int? attempt}) {
        // 将 Agent 进度映射到 Worker 进度
        if (stage == 'repairing') {
          _reportProgress(request.requestId, RpTaskStage.repairing, attempt: attempt);
        }
      },
    );

    logs.add({
      'level': result.ok ? 'info' : 'error',
      'message': 'Agent 任务完成: $agentId, ok=${result.ok}',
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });

    // 添加 Agent 日志
    for (final logEntry in result.logs) {
      logs.add({
        'level': 'debug',
        'message': logEntry,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      });
    }

    return _TaskResult(proposals: result.proposals, logs: logs);
  }

  /// 发送响应消息
  void _sendResponse(RpWorkerResponse response) {
    _mainSendPort.send(RpWorkerEnvelope.response(response).toJson());
  }

  /// 发送控制消息
  void _sendControl(RpWorkerControl control) {
    _mainSendPort.send(RpWorkerEnvelope.control(control).toJson());
  }

  /// 发送进度消息
  ///
  /// 用于向 Main Isolate 报告任务执行阶段
  void _reportProgress(String requestId, RpTaskStage stage, {int? attempt}) {
    _mainSendPort.send({
      'type': RpMessageType.progress,
      'schemaVersion': kRpWorkerProtocolVersion,
      'payload': RpWorkerProgress(
        requestId: requestId,
        stageCode: stage.code,
        attempt: attempt,
      ).toJson(),
    });
  }
}

/// 任务执行结果
class _TaskResult {
  final List<Map<String, dynamic>> proposals;
  final List<Map<String, dynamic>> logs;

  _TaskResult({
    required this.proposals,
    required this.logs,
  });
}
