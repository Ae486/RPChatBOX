/// Worker Host (Main Isolate 侧)
///
/// 管理 Worker Isolate 的生命周期和通信
/// POS: Services / Roleplay / Worker
library;

import 'dart:async';
import 'dart:developer';
import 'dart:isolate';

import 'package:flutter/foundation.dart';

import 'rp_worker_entry.dart';
import 'rp_worker_protocol.dart';

/// Worker Isolate 管理器
///
/// 职责：
/// - 管理 Worker 生命周期（启动、停止、重启）
/// - 序列化/反序列化消息
/// - 处理错误和超时
/// - 实现懒重启策略
class RpWorkerHost {
  /// 单例实例
  static final RpWorkerHost instance = RpWorkerHost._();

  RpWorkerHost._();

  /// Worker Isolate 引用
  Isolate? _worker;

  /// Worker 的发送端口
  SendPort? _sendPort;

  /// 接收端口
  ReceivePort? _receivePort;

  /// 就绪 Completer
  Completer<void>? _readyCompleter;

  /// 待处理请求 (requestId → Completer)
  final Map<String, Completer<RpWorkerResponse>> _pending = {};

  /// 请求缓存 (requestId → 原始请求)
  final Map<String, RpWorkerRequest> _requestCache = {};

  /// Ping 等待 Completer
  Completer<void>? _pingCompleter;

  /// 启动 Future（防止并发启动）
  Future<void>? _startFuture;

  /// 状态通知器（供 UI 使用）
  final ValueNotifier<RpWorkerStatus> statusNotifier =
      ValueNotifier(RpWorkerStatus.idle);

  /// 进度事件流控制器
  final StreamController<RpWorkerProgress> _progressController =
      StreamController.broadcast();

  /// 进度事件流（供 UI 订阅）
  ///
  /// 订阅此流可获取任务执行的实时进度
  Stream<RpWorkerProgress> get onProgress => _progressController.stream;

  /// Worker 是否就绪
  bool get isReady => _sendPort != null;

  /// 是否有待处理请求
  bool get hasPending => _pending.isNotEmpty;

  /// 启动 Worker
  ///
  /// 如果已启动则直接返回
  /// 并发调用会等待同一个启动过程完成
  Future<void> start() async {
    // 已就绪（_sendPort 可用），直接返回
    if (isReady) return;

    // 如果启动正在进行中，等待它完成
    if (_startFuture != null) {
      return _startFuture;
    }

    // 启动并保存 Future
    _startFuture = _doStart();
    try {
      await _startFuture;
    } finally {
      _startFuture = null;
    }
  }

  /// 实际执行启动逻辑
  Future<void> _doStart() async {
    log('启动 Worker Isolate...', name: 'RpWorkerHost');
    statusNotifier.value = RpWorkerStatus.starting;

    _receivePort = ReceivePort();
    _readyCompleter = Completer<void>();

    try {
      // 启动 Worker Isolate
      _worker = await Isolate.spawn(
        rpWorkerEntryPoint,
        _receivePort!.sendPort,
        onError: _receivePort!.sendPort,
        onExit: _receivePort!.sendPort,
        errorsAreFatal: false,
        debugName: 'RpWorkerIsolate',
      );

      // 监听消息
      _receivePort!.listen(_handleMessage);

      // 等待 Worker 就绪（10秒超时）
      await _readyCompleter!.future.timeout(
        const Duration(seconds: 10),
        onTimeout: () {
          throw RpWorkerTimeoutException('worker_startup', const Duration(seconds: 10));
        },
      );

      log('Worker Isolate 启动完成', name: 'RpWorkerHost');
      statusNotifier.value = RpWorkerStatus.ready;
    } catch (e) {
      log('Worker Isolate 启动失败: $e', name: 'RpWorkerHost');
      _resetWorkerState();
      statusNotifier.value = RpWorkerStatus.error;
      rethrow;
    }
  }

  /// 停止 Worker
  Future<void> stop() async {
    if (_worker == null) return;

    log('停止 Worker Isolate...', name: 'RpWorkerHost');

    try {
      // 发送关闭消息
      if (_sendPort != null) {
        _sendControl(RpWorkerControl.shutdown());
      }

      // 等待一小段时间让 Worker 优雅退出
      await Future.delayed(const Duration(milliseconds: 100));
    } finally {
      // 强制清理
      _worker?.kill(priority: Isolate.immediate);
      _completePendingWithError('Worker 已停止');
      _resetWorkerState();
      statusNotifier.value = RpWorkerStatus.idle;

      log('Worker Isolate 已停止', name: 'RpWorkerHost');
    }
  }

  /// 发送请求
  ///
  /// 自动处理懒启动和超时
  Future<RpWorkerResponse> send(RpWorkerRequest request) async {
    // 如果已有待处理请求，报告排队阶段
    if (hasPending) {
      _progressController.add(RpWorkerProgress(
        requestId: request.requestId,
        stageCode: RpTaskStage.queued.code,
      ));
    }

    // 懒启动
    if (!isReady) {
      // 报告启动阶段
      _progressController.add(RpWorkerProgress(
        requestId: request.requestId,
        stageCode: RpTaskStage.booting.code,
      ));
      await start();
    }

    final completer = Completer<RpWorkerResponse>();
    _pending[request.requestId] = completer;
    _requestCache[request.requestId] = request;

    statusNotifier.value = RpWorkerStatus.working;

    // 发送请求
    _sendPort!.send(RpWorkerEnvelope.request(request).toJson());

    log(
      '发送请求: ${request.requestId}, tasks=${request.tasks}',
      name: 'RpWorkerHost',
    );

    // 超时处理
    try {
      return await completer.future.timeout(
        Duration(milliseconds: request.timeoutMs),
        onTimeout: () {
          // 从待处理中移除
          _pending.remove(request.requestId);
          _requestCache.remove(request.requestId);

          // 发送取消消息给 Worker（只发送，不处理 Completer）
          if (_sendPort != null) {
            _sendControl(RpWorkerControl.cancel(request.requestId));
          }

          throw RpWorkerTimeoutException(
            request.requestId,
            Duration(milliseconds: request.timeoutMs),
          );
        },
      );
    } finally {
      // 更新状态
      if (_pending.isEmpty) {
        statusNotifier.value = isReady ? RpWorkerStatus.ready : RpWorkerStatus.idle;
      }
    }
  }

  /// 取消请求
  void cancel(String requestId) {
    if (_sendPort != null) {
      _sendControl(RpWorkerControl.cancel(requestId));
      log('发送取消请求: $requestId', name: 'RpWorkerHost');
    }

    // 完成 Completer 并移除
    final completer = _pending.remove(requestId);
    if (completer != null && !completer.isCompleted) {
      completer.completeError(RpWorkerException('请求已取消: $requestId'));
    }
    _requestCache.remove(requestId);
  }

  /// 获取原始请求（用于版本闸门验证）
  RpWorkerRequest? getOriginalRequest(String requestId) {
    return _requestCache[requestId];
  }

  /// 处理接收到的消息
  void _handleMessage(dynamic message) {
    // 处理 Isolate 错误
    if (message is List && message.length == 2) {
      _handleWorkerError(message[0], message[1]);
      return;
    }

    // 处理 Isolate 退出
    if (message == null) {
      _handleWorkerExit();
      return;
    }

    // 处理正常消息
    if (message is Map<String, dynamic>) {
      try {
        final envelope = RpWorkerEnvelope.fromJson(message);

        // 校验协议版本
        if (envelope.schemaVersion > kRpWorkerProtocolVersion) {
          log(
            '协议版本不兼容: 收到 v${envelope.schemaVersion}, 当前 v$kRpWorkerProtocolVersion',
            name: 'RpWorkerHost',
          );
          return;
        }

        switch (envelope.type) {
          case RpMessageType.response:
            _handleResponse(envelope.payload);
          case RpMessageType.control:
            _handleControl(envelope.payload);
          case RpMessageType.progress:
            _handleProgress(envelope.payload);
          default:
            log('收到未知消息类型: ${envelope.type}', name: 'RpWorkerHost');
        }
      } catch (e) {
        log('消息处理错误: $e', name: 'RpWorkerHost');
      }
    }
  }

  /// 处理响应消息
  void _handleResponse(Map<String, dynamic> payload) {
    final response = RpWorkerResponse.fromJson(payload);
    final completer = _pending.remove(response.requestId);

    if (completer != null) {
      completer.complete(response);
      log(
        '收到响应: ${response.requestId}, ok=${response.ok}',
        name: 'RpWorkerHost',
      );
    } else {
      log(
        '收到未知请求的响应: ${response.requestId}（可能已超时或已取消）',
        name: 'RpWorkerHost',
      );
    }

    // 清理请求缓存（延迟清理，给版本闸门验证留时间）
    Future.delayed(const Duration(seconds: 5), () {
      _requestCache.remove(response.requestId);
    });
  }

  /// 处理控制消息
  void _handleControl(Map<String, dynamic> payload) {
    final control = RpWorkerControl.fromJson(payload);

    switch (control.controlType) {
      case RpWorkerControlType.ready:
        // Worker 就绪，获取其 SendPort
        final data = control.data;
        if (data != null && data['sendPort'] is SendPort) {
          _sendPort = data['sendPort'] as SendPort;
          _readyCompleter?.complete();
          log('Worker 就绪', name: 'RpWorkerHost');
        }

      case RpWorkerControlType.pong:
        log('收到心跳响应', name: 'RpWorkerHost');
        // 完成 ping 等待
        if (_pingCompleter != null && !_pingCompleter!.isCompleted) {
          _pingCompleter!.complete();
        }

      default:
        log('收到未知控制消息: ${control.controlType}', name: 'RpWorkerHost');
    }
  }

  /// 处理进度消息
  void _handleProgress(Map<String, dynamic> payload) {
    try {
      final progress = RpWorkerProgress.fromJson(payload);
      _progressController.add(progress);
      log(
        '收到进度: ${progress.requestId}, stage=${progress.stageCode}',
        name: 'RpWorkerHost',
      );
    } catch (e) {
      log('进度消息解析错误: $e', name: 'RpWorkerHost');
    }
  }

  /// 处理 Worker 错误
  void _handleWorkerError(dynamic error, dynamic stackTrace) {
    log('Worker 错误: $error', name: 'RpWorkerHost');
    log('StackTrace: $stackTrace', name: 'RpWorkerHost');

    _completePendingWithError('Worker 崩溃: $error');

    // 显式杀死 Worker 防止孤儿 isolate
    _worker?.kill(priority: Isolate.immediate);

    _resetWorkerState();
    statusNotifier.value = RpWorkerStatus.error;
  }

  /// 处理 Worker 退出
  void _handleWorkerExit() {
    log('Worker 退出', name: 'RpWorkerHost');

    _completePendingWithError('Worker 意外退出');
    _resetWorkerState();
    statusNotifier.value = RpWorkerStatus.idle;
  }

  /// 完成所有待处理请求（以错误结束）
  void _completePendingWithError(String errorMessage) {
    for (final entry in _pending.entries) {
      entry.value.completeError(RpWorkerException(errorMessage));
    }
    _pending.clear();
    _requestCache.clear();
  }

  /// 重置 Worker 状态（懒重启）
  void _resetWorkerState() {
    _worker = null;
    _sendPort = null;
    _receivePort?.close();
    _receivePort = null;
    _readyCompleter = null;
  }

  /// 发送控制消息
  void _sendControl(RpWorkerControl control) {
    _sendPort?.send(RpWorkerEnvelope.control(control).toJson());
  }

  /// 发送心跳检测
  ///
  /// 返回 true 表示 Worker 响应了 pong
  /// 返回 false 表示超时或 Worker 不可用
  Future<bool> ping() async {
    if (!isReady) return false;

    // 如果已有 ping 在进行中，等待它完成
    if (_pingCompleter != null && !_pingCompleter!.isCompleted) {
      try {
        await _pingCompleter!.future;
        return true;
      } catch (_) {
        return false;
      }
    }

    _pingCompleter = Completer<void>();

    // 发送 ping
    _sendControl(RpWorkerControl.ping());

    // 等待 pong（5秒超时）
    try {
      await _pingCompleter!.future.timeout(
        const Duration(seconds: 5),
        onTimeout: () {
          if (!_pingCompleter!.isCompleted) {
            _pingCompleter!.completeError('ping timeout');
          }
        },
      );
      return true;
    } catch (_) {
      return false;
    } finally {
      _pingCompleter = null;
    }
  }

  /// 预热 Worker
  ///
  /// 提前启动 Worker Isolate，减少首次请求的延迟
  /// 建议在进入 Roleplay 页面时调用
  ///
  /// 示例：
  /// ```dart
  /// @override
  /// void initState() {
  ///   super.initState();
  ///   RpWorkerHost.instance.warmup();
  /// }
  /// ```
  Future<void> warmup() async {
    if (isReady) return;
    await start();
    log('Worker 预热完成', name: 'RpWorkerHost');
  }
}

/// Worker 状态
enum RpWorkerStatus {
  /// 空闲（未启动或已停止）
  idle,

  /// 启动中
  starting,

  /// 就绪（等待任务）
  ready,

  /// 工作中（正在处理任务）
  working,

  /// 错误状态
  error,
}
