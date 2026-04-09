/// Backend lifecycle service factory.
///
/// Creates the appropriate [BackendLifecycle] implementation based on
/// the current platform.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';

import 'backend_lifecycle.dart';
import 'backend_lifecycle_desktop.dart';
import 'backend_lifecycle_noop.dart';

/// Factory for creating platform-specific [BackendLifecycle] instances.
class BackendLifecycleService {
  BackendLifecycleService._();

  static BackendLifecycle? _instance;

  /// Get the singleton instance.
  ///
  /// Creates the instance on first access using [create].
  static BackendLifecycle get instance {
    _instance ??= create();
    return _instance!;
  }

  /// Check if a backend instance exists and is ready.
  static bool get isReady => _instance?.status == BackendStatus.ready;

  /// Create a platform-specific [BackendLifecycle].
  static BackendLifecycle create({int port = 8765}) {
    if (kIsWeb) {
      throw UnsupportedError('Local backend not supported on web platform');
    }

    if (Platform.isWindows || Platform.isMacOS || Platform.isLinux) {
      return DesktopBackendLifecycle(port: port);
    }

    if (Platform.isAndroid || Platform.isIOS) {
      // Mobile: use NoOp implementation (direct mode via HybridLangChainProvider)
      return NoOpBackendLifecycle(port: port);
    }

    throw UnsupportedError('Unsupported platform: ${Platform.operatingSystem}');
  }

  /// Reset the singleton instance.
  ///
  /// Used for testing or when reconfiguring the backend.
  static void reset() {
    _instance?.dispose();
    _instance = null;
  }
}
