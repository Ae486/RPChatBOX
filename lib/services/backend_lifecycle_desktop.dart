/// Desktop backend lifecycle management using subprocess.
///
/// Manages the Python backend process on Windows, macOS, and Linux.
/// Uses PyInstaller-packaged executable for production, or direct Python
/// for development.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'backend_lifecycle.dart';

/// Desktop implementation of [BackendLifecycle].
///
/// Launches the backend as a subprocess and manages its lifecycle.
class DesktopBackendLifecycle implements BackendLifecycle {
  /// Creates a desktop backend lifecycle manager.
  DesktopBackendLifecycle({
    int port = 8765,
    this.maxRestarts = 3,
    this.healthCheckInterval = const Duration(milliseconds: 500),
  }) : _port = port;

  final int _port;

  /// Maximum number of automatic restarts after crashes.
  final int maxRestarts;

  /// Interval between health check polls during startup.
  final Duration healthCheckInterval;

  Process? _process;
  int _restartCount = 0;
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
      final launch = await _resolveLaunchCommand();

      // Start the process
      debugPrint('Starting backend: ${launch.display}');
      _process = await Process.start(
        launch.executable,
        launch.args,
        environment: {
          'CHATBOX_BACKEND_HOST': '127.0.0.1',
          'CHATBOX_BACKEND_PORT': '$_port',
        },
        workingDirectory: launch.workingDirectory,
      );

      // Forward stdout/stderr to debug console
      _process!.stdout
          .transform(const SystemEncoding().decoder)
          .listen((data) => debugPrint('[Backend] $data'));
      _process!.stderr
          .transform(const SystemEncoding().decoder)
          .listen((data) => debugPrint('[Backend:ERR] $data'));

      // Monitor process exit
      _process!.exitCode.then(_onProcessExit);

      // Wait for ready
      await waitForReady();
      _restartCount = 0;
      _setStatus(BackendStatus.ready);
      debugPrint('Backend ready at $baseUrl');
    } catch (e) {
      _setStatus(BackendStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> stop() async {
    if (_status == BackendStatus.stopped) return;

    debugPrint('Stopping backend...');

    // Try graceful shutdown first
    try {
      await http
          .post(Uri.parse('$baseUrl/api/shutdown'))
          .timeout(const Duration(seconds: 2));
    } catch (_) {
      // Ignore errors, will force kill
    }

    // Wait a moment for graceful shutdown
    await Future.delayed(const Duration(seconds: 1));

    // Force terminate if still running
    if (_process != null) {
      if (Platform.isWindows) {
        await Process.run('taskkill', ['/F', '/PID', '${_process!.pid}']);
      } else {
        _process!.kill(ProcessSignal.sigterm);
      }
    }

    _process = null;
    _setStatus(BackendStatus.stopped);
    debugPrint('Backend stopped');
  }

  @override
  Future<void> restart() async {
    _setStatus(BackendStatus.restarting);
    await stop();
    await Future.delayed(const Duration(milliseconds: 500));
    await start();
  }

  @override
  Future<bool> isHealthy() async {
    try {
      final healthResponse = await http
          .get(Uri.parse('$baseUrl/api/health'))
          .timeout(const Duration(seconds: 5));
      if (healthResponse.statusCode != 200) {
        return false;
      }

      // Guard against stale/incorrect services occupying the backend port.
      final modelsResponse = await http
          .get(Uri.parse('$baseUrl/models'))
          .timeout(const Duration(seconds: 5));
      return modelsResponse.statusCode == 200;
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

    throw TimeoutException('Backend failed to start within $timeout');
  }

  @override
  void dispose() {
    if (_isDisposed) return;
    _isDisposed = true;
    stop();
    _statusController.close();
  }

  // === Private Methods ===

  Future<String> _getExecutablePath() async {
    // In production, use app support directory
    final appDir = await getApplicationSupportDirectory();
    final execName = Platform.isWindows
        ? 'chatbox-backend.exe'
        : 'chatbox-backend';
    return p.join(appDir.path, 'backend', execName);
  }

  Future<_LaunchCommand> _resolveLaunchCommand() async {
    if (kDebugMode) {
      final projectRoot = Directory.current.path;
      final scriptPath = p.join(projectRoot, 'backend', 'main.py');
      if (await File(scriptPath).exists()) {
        final python = await _findPythonLauncher();
        if (python != null) {
          return _LaunchCommand(
            executable: python.executable,
            args: [...python.args, scriptPath],
            display: '${python.display} $scriptPath',
            workingDirectory: p.join(projectRoot, 'backend'),
          );
        }
        debugPrint(
          'No Python launcher found in debug mode, falling back to packaged backend executable',
        );
      }

      final execName = Platform.isWindows
          ? 'chatbox-backend.exe'
          : 'chatbox-backend';
      final devPath = p.join(projectRoot, 'backend', 'dist', execName);
      if (await File(devPath).exists()) {
        if (!Platform.isWindows) {
          await Process.run('chmod', ['+x', devPath]);
        }
        return _LaunchCommand(
          executable: devPath,
          args: const [],
          display: devPath,
        );
      }
    }

    final execPath = await _getExecutablePath();
    if (!await File(execPath).exists()) {
      throw Exception('Backend executable not found: $execPath');
    }

    if (!Platform.isWindows) {
      await Process.run('chmod', ['+x', execPath]);
    }

    return _LaunchCommand(
      executable: execPath,
      args: const [],
      display: execPath,
    );
  }

  Future<_PythonLauncher?> _findPythonLauncher() async {
    final candidates = Platform.isWindows
        ? const [
            _PythonLauncher(executable: 'python', args: [], display: 'python'),
          ]
        : const [
            _PythonLauncher(
              executable: 'python3',
              args: [],
              display: 'python3',
            ),
            _PythonLauncher(executable: 'python', args: [], display: 'python'),
          ];

    for (final candidate in candidates) {
      try {
        final result = await Process.run(candidate.executable, [
          ...candidate.args,
          '--version',
        ]);
        if (result.exitCode == 0) {
          return candidate;
        }
      } catch (_) {
        // Try the next launcher candidate.
      }
    }

    return null;
  }

  void _setStatus(BackendStatus newStatus) {
    if (_status == newStatus) return;
    _status = newStatus;
    if (!_statusController.isClosed) {
      _statusController.add(newStatus);
    }
  }

  void _onProcessExit(int exitCode) {
    if (_isDisposed || _status == BackendStatus.stopped) return;

    debugPrint('Backend exited with code: $exitCode');

    // Abnormal exit, try restart
    if (exitCode != 0 && _restartCount < maxRestarts) {
      _restartCount++;
      debugPrint('Attempting restart $_restartCount/$maxRestarts');
      restart();
    } else if (_restartCount >= maxRestarts) {
      debugPrint('Max restarts reached, giving up');
      _setStatus(BackendStatus.error);
    }
  }
}

class _LaunchCommand {
  const _LaunchCommand({
    required this.executable,
    required this.args,
    required this.display,
    this.workingDirectory,
  });

  final String executable;
  final List<String> args;
  final String display;
  final String? workingDirectory;
}

class _PythonLauncher {
  const _PythonLauncher({
    required this.executable,
    required this.args,
    required this.display,
  });

  final String executable;
  final List<String> args;
  final String display;
}
