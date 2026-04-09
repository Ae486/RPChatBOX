/// No-op backend lifecycle implementation for mobile platforms.
///
/// Mobile platforms use direct LLM API calls via HybridLangChainProvider,
/// so no Python backend is needed.
library;

import 'dart:async';

import 'backend_lifecycle.dart';

/// No-op implementation of [BackendLifecycle] for mobile platforms.
///
/// All operations are no-ops. The backend is never started.
/// This ensures mobile platforms always use direct mode.
class NoOpBackendLifecycle implements BackendLifecycle {
  NoOpBackendLifecycle({int port = 8765}) : _port = port;

  final int _port;
  final _statusController = StreamController<BackendStatus>.broadcast();
  bool _isDisposed = false;

  @override
  BackendStatus get status => BackendStatus.stopped;

  @override
  Stream<BackendStatus> get statusStream => _statusController.stream;

  @override
  String get baseUrl => 'http://127.0.0.1:$_port';

  @override
  int get port => _port;

  @override
  Future<void> start() async {
    // No-op: mobile uses direct mode
  }

  @override
  Future<void> stop() async {
    // No-op
  }

  @override
  Future<void> restart() async {
    // No-op
  }

  @override
  Future<bool> isHealthy() async => false;

  @override
  Future<void> waitForReady({
    Duration timeout = const Duration(seconds: 15),
  }) async {
    // No-op: immediately return (never ready)
  }

  @override
  void dispose() {
    if (_isDisposed) return;
    _isDisposed = true;
    _statusController.close();
  }
}
