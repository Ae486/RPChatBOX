/// 取消令牌
///
/// 支持跨 Isolate 的任务取消机制
/// POS: Services / Roleplay / Worker
library;

import 'dart:async';
import 'dart:isolate';

/// 取消令牌
///
/// 用于检查任务是否被取消
class CancellationToken {
  bool _cancelled = false;

  /// 取消事件流（由 CancellationTokenSource 注入）
  Stream<void>? _onCancel;

  /// 是否已取消
  bool get isCancelled => _cancelled;

  /// 取消事件流
  ///
  /// 订阅此流可在取消时立即收到通知
  Stream<void>? get onCancel => _onCancel;

  /// 内部取消方法（由 CancellationTokenSource 调用）
  void _cancel() => _cancelled = true;

  /// 内部设置取消流（由 CancellationTokenSource 调用）
  void _setOnCancel(Stream<void> stream) => _onCancel = stream;

  /// 检查取消状态，如果已取消则抛出异常
  void throwIfCancelled() {
    if (_cancelled) {
      throw CancelledException();
    }
  }
}

/// 取消令牌源
///
/// 用于发出取消信号
class CancellationTokenSource {
  /// 关联的令牌
  final CancellationToken token = CancellationToken();

  /// 取消事件流控制器
  final StreamController<void> _controller = StreamController.broadcast();

  /// 是否已取消
  bool get isCancelled => token.isCancelled;

  /// 取消事件流
  Stream<void> get onCancel => _controller.stream;

  CancellationTokenSource() {
    // 注入取消流到 token
    token._setOnCancel(_controller.stream);
  }

  /// 发出取消信号
  void cancel() {
    if (token.isCancelled) return;
    token._cancel();
    _controller.add(null);
  }

  /// 释放资源
  void dispose() {
    _controller.close();
  }
}

/// 可取消的异常
class CancelledException implements Exception {
  final String message;

  CancelledException([this.message = 'Operation was cancelled']);

  @override
  String toString() => 'CancelledException: $message';
}

/// Isolate 取消令牌
///
/// 用于跨 Isolate 传递取消信号
class IsolateCancellationToken {
  final ReceivePort _receivePort;
  final CancellationToken _token = CancellationToken();
  StreamSubscription? _subscription;

  IsolateCancellationToken._(this._receivePort) {
    _subscription = _receivePort.listen((_) {
      _token._cancel();
    });
  }

  /// 创建一个新的 Isolate 取消令牌
  ///
  /// 返回 (token, sendPort)，其中：
  /// - token: 在 Worker Isolate 中使用
  /// - sendPort: 在主 Isolate 中用于发送取消信号
  static (IsolateCancellationToken, SendPort) create() {
    final receivePort = ReceivePort();
    final token = IsolateCancellationToken._(receivePort);
    return (token, receivePort.sendPort);
  }

  /// 获取内部令牌
  CancellationToken get token => _token;

  /// 是否已取消
  bool get isCancelled => _token.isCancelled;

  /// 检查取消状态
  void throwIfCancelled() => _token.throwIfCancelled();

  /// 释放资源
  void dispose() {
    _subscription?.cancel();
    _receivePort.close();
  }
}

/// Isolate 取消令牌源
///
/// 在主 Isolate 中使用，用于发送取消信号到 Worker
class IsolateCancellationTokenSource {
  final SendPort _sendPort;
  bool _cancelled = false;

  IsolateCancellationTokenSource(this._sendPort);

  /// 是否已取消
  bool get isCancelled => _cancelled;

  /// 发送取消信号
  void cancel() {
    if (_cancelled) return;
    _cancelled = true;
    _sendPort.send(null);
  }
}

/// 取消令牌扩展
extension CancellationTokenExtension on CancellationToken {
  /// 包装 Future，使其支持取消
  Future<T> wrapFuture<T>(Future<T> future) async {
    if (isCancelled) {
      throw CancelledException();
    }

    // 创建一个 Completer 用于取消
    final completer = Completer<T>();

    // 监听原 Future
    future.then((value) {
      if (!completer.isCompleted) {
        completer.complete(value);
      }
    }).catchError((error, stackTrace) {
      if (!completer.isCompleted) {
        completer.completeError(error, stackTrace);
      }
    });

    // 定期检查取消状态
    Timer.periodic(const Duration(milliseconds: 100), (timer) {
      if (isCancelled) {
        timer.cancel();
        if (!completer.isCompleted) {
          completer.completeError(CancelledException());
        }
      }
      if (completer.isCompleted) {
        timer.cancel();
      }
    });

    return completer.future;
  }
}

/// 可取消的操作
mixin Cancellable {
  CancellationToken? _cancellationToken;

  /// 设置取消令牌
  void setCancellationToken(CancellationToken token) {
    _cancellationToken = token;
  }

  /// 检查是否已取消
  bool get isCancelled => _cancellationToken?.isCancelled ?? false;

  /// 如果已取消则抛出异常
  void throwIfCancelled() {
    _cancellationToken?.throwIfCancelled();
  }
}
