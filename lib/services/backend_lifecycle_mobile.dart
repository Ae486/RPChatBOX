/// Mobile backend lifecycle management using serious_python.
///
/// Embeds the Python runtime into the Flutter app on Android and iOS.
/// Runs the FastAPI backend as a background process within the app.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:serious_python/serious_python.dart';

import 'backend_lifecycle.dart';

/// Mobile implementation of [BackendLifecycle].
///
/// Uses [SeriousPython] to embed and run the Python backend.
class MobileBackendLifecycle implements BackendLifecycle {
  /// Creates a mobile backend lifecycle manager.
  MobileBackendLifecycle({
    int port = 8765,
    this.healthCheckInterval = const Duration(milliseconds: 500),
  }) : _port = port;

  final int _port;

  /// Interval between health check polls during startup.
  final Duration healthCheckInterval;

  BackendStatus _status = BackendStatus.stopped;
  final _statusController = StreamController<BackendStatus>.broadcast();
  bool _isDisposed = false;

  @override
  BackendStatus get status => _status;

  @override
  Stream<BackendStatus> get statusStream => _statusController.stream;

  @override
  String get baseUrl => 'http://127.0.0.1:$_port';

  @override
  int get port => _port;

  @override
  Future<void> start() async {
    if (_isDisposed) {
      throw StateError('BackendLifecycle has been disposed');
    }

    if (_status == BackendStatus.starting || _status == BackendStatus.ready) {
      return;
    }

    _setStatus(BackendStatus.starting);

    try {
      debugPrint('Starting mobile backend via serious_python...');

      final result = await SeriousPython.run(
        'assets/backend/app.zip',
        appFileName: 'main.py',
        environmentVariables: {
          'CHATBOX_BACKEND_HOST': '127.0.0.1',
          'CHATBOX_BACKEND_PORT': '$_port',
        },
      );

      // Log Python output for debugging
      if (result != null && result.isNotEmpty) {
        debugPrint('[serious_python] Python output: $result');
      }

      await waitForReady();
      _setStatus(BackendStatus.ready);
      debugPrint('Mobile backend ready at $baseUrl');
    } catch (e) {
      _setStatus(BackendStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> stop() async {
    if (_status == BackendStatus.stopped) return;

    debugPrint('Stopping mobile backend...');

    try {
      await http
          .post(Uri.parse('$baseUrl/api/shutdown'))
          .timeout(const Duration(seconds: 2));
    } catch (_) {
      // Ignore; serious_python will clean up on app exit
    }

    _setStatus(BackendStatus.stopped);
    debugPrint('Mobile backend stopped');
  }

  @override
  Future<void> restart() async {
    _setStatus(BackendStatus.restarting);
    await stop();
    await Future.delayed(const Duration(seconds: 1));
    await start();
  }

  @override
  Future<bool> isHealthy() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/api/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> waitForReady({
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final deadline = DateTime.now().add(timeout);

    while (DateTime.now().isBefore(deadline)) {
      if (await isHealthy()) return;
      await Future.delayed(healthCheckInterval);
    }

    throw TimeoutException('Mobile backend failed to start within $timeout');
  }

  @override
  void dispose() {
    if (_isDisposed) return;
    _isDisposed = true;
    stop();
    _statusController.close();
  }

  void _setStatus(BackendStatus newStatus) {
    if (_status == newStatus) return;
    _status = newStatus;
    if (!_statusController.isClosed) {
      _statusController.add(newStatus);
    }
  }
}
