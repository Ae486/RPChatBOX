/// Backend lifecycle management interface.
///
/// Provides a common interface for managing the Python backend process
/// across different platforms (desktop subprocess, mobile embedded).
library;

import 'dart:async';

/// Backend status enum.
enum BackendStatus {
  /// Backend is not running.
  stopped,

  /// Backend is starting up.
  starting,

  /// Backend is ready and accepting requests.
  ready,

  /// Backend encountered an error.
  error,

  /// Backend is restarting after a crash.
  restarting,
}

/// Backend lifecycle management interface.
///
/// Implementations should handle platform-specific backend startup,
/// shutdown, and health monitoring.
abstract class BackendLifecycle {
  /// Start the backend process.
  ///
  /// Throws [TimeoutException] if the backend fails to start within the timeout.
  /// Throws [Exception] if the backend executable is not found or cannot be started.
  Future<void> start();

  /// Stop the backend process.
  ///
  /// Attempts graceful shutdown first, then forces termination if necessary.
  Future<void> stop();

  /// Restart the backend process.
  ///
  /// Equivalent to calling [stop] followed by [start].
  Future<void> restart();

  /// Check if the backend is healthy.
  ///
  /// Returns true if the backend responds to health check within 5 seconds.
  Future<bool> isHealthy();

  /// Wait for the backend to become ready.
  ///
  /// Polls the health endpoint until it responds successfully.
  /// Throws [TimeoutException] if the backend doesn't become ready within [timeout].
  Future<void> waitForReady({Duration timeout = const Duration(seconds: 15)});

  /// Stream of backend status changes.
  Stream<BackendStatus> get statusStream;

  /// Current backend status.
  BackendStatus get status;

  /// Backend base URL for API requests.
  String get baseUrl;

  /// Backend port number.
  int get port;

  /// Release resources.
  void dispose();
}
