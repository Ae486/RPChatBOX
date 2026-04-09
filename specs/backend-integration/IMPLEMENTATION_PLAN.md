# Python 后端集成 - 零决策实施计划

> 创建时间：2026-02-03
> 状态：Ready for Execution
> 依赖文档：CONSTRAINT_SET.md, OPENSPEC_PROPOSAL.md

---

## 执行摘要

本计划将 Python 后端从「手动启动」改为「静默自启动」，分 5 个阶段执行。每个步骤均为原子操作，无需运行时决策。

**关键路径**：Phase A (PoC) → Phase B (桌面端) → Phase C (移动端) → Phase D (UI) → Phase E (测试)

---

## Phase A: PoC 验证

**目标**：验证技术可行性，降低后续阶段风险

### A.1 创建最小 FastAPI 后端 PoC

**输入**：现有 `backend/` 代码
**输出**：`backend/poc/minimal_app.py`

```python
# backend/poc/minimal_app.py
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/shutdown")
async def shutdown():
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)
    return {"status": "shutting_down"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, loop="asyncio")
```

**验收标准**：
- `python poc/minimal_app.py` 启动成功
- `curl localhost:8765/api/health` 返回 `{"status":"ok"}`
- `curl -X POST localhost:8765/api/shutdown` 触发优雅关闭

---

### A.2 桌面端 PyInstaller 打包测试

**输入**：A.1 产出的 `minimal_app.py`
**输出**：`backend/dist/chatbox-backend.exe` (Windows)

**步骤**：

```bash
# 1. 安装 PyInstaller
cd backend
pip install pyinstaller

# 2. 打包
pyinstaller --onefile --name chatbox-backend poc/minimal_app.py

# 3. 验证
./dist/chatbox-backend  # 或 dist\chatbox-backend.exe (Windows)
curl localhost:8765/api/health
```

**验收标准**：
- 可执行文件生成成功
- 双击运行后健康检查通过
- 关闭终端后进程正确退出

---

### A.3 桌面端 subprocess 启动测试

**输入**：A.2 产出的可执行文件
**输出**：`test/poc/subprocess_test.dart`

**步骤**：

```dart
// test/poc/subprocess_test.dart
import 'dart:io';

void main() async {
  // 1. 启动进程
  final process = await Process.start(
    'backend/dist/chatbox-backend',
    [],
    mode: ProcessStartMode.detached,
  );
  print('Started PID: ${process.pid}');

  // 2. 等待就绪
  await Future.delayed(Duration(seconds: 3));

  // 3. 健康检查
  final client = HttpClient();
  final request = await client.getUrl(Uri.parse('http://localhost:8765/api/health'));
  final response = await request.close();
  print('Health: ${response.statusCode}');

  // 4. 关闭
  if (Platform.isWindows) {
    await Process.run('taskkill', ['/F', '/PID', '${process.pid}']);
  } else {
    Process.killPid(process.pid);
  }
  print('Stopped');
}
```

**验收标准**：
- 进程成功启动
- 健康检查返回 200
- 进程正确终止

---

### A.4 移动端 serious_python 可行性测试

**输入**：A.1 产出的 `minimal_app.py`
**输出**：Android APK 或 iOS 真机测试

**步骤**：

```bash
# 1. 创建测试项目
flutter create poc_serious_python
cd poc_serious_python

# 2. 添加依赖 (pubspec.yaml)
# dependencies:
#   serious_python: ^0.9.0

# 3. 打包 Python 代码
dart run serious_python:main package ../backend/poc \
  -p Android \
  --asset assets/backend/app.zip \
  --requirements fastapi,uvicorn,pydantic

# 4. 编写测试代码 (lib/main.dart)
# 见下方代码块

# 5. 运行 Android 真机测试
flutter run -d <device_id>
```

**测试代码**：

```dart
// lib/main.dart
import 'package:flutter/material.dart';
import 'package:serious_python/serious_python.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const PocApp());

class PocApp extends StatefulWidget {
  const PocApp({super.key});
  @override
  State<PocApp> createState() => _PocAppState();
}

class _PocAppState extends State<PocApp> {
  String _status = 'Not started';

  Future<void> _startBackend() async {
    setState(() => _status = 'Starting...');

    await SeriousPython.run(
      'assets/backend/app.zip',
      appFileName: 'minimal_app.py',
      environmentVariables: {
        'CHATBOX_BACKEND_PORT': '8765',
      },
    );

    // 轮询健康检查
    for (int i = 0; i < 30; i++) {
      await Future.delayed(const Duration(seconds: 1));
      try {
        final resp = await http.get(Uri.parse('http://127.0.0.1:8765/api/health'));
        if (resp.statusCode == 200) {
          setState(() => _status = 'Ready: ${resp.body}');
          return;
        }
      } catch (_) {}
    }
    setState(() => _status = 'Timeout');
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(_status),
              ElevatedButton(
                onPressed: _startBackend,
                child: const Text('Start Backend'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

**验收标准**：
- serious_python 打包成功
- Android 真机上后端启动成功
- 健康检查返回 200

**Plan B**（若 uvicorn 失败）：
- 替换为 Hypercorn：`hypercorn minimal_app:app --bind 127.0.0.1:8765`
- 或替换为 Flask：使用 Werkzeug 开发服务器

---

## Phase B: 桌面端集成

**前置条件**：Phase A 全部通过

### B.1 创建接口定义

**输入**：OPENSPEC_PROPOSAL.md 中的接口设计
**输出**：`lib/services/backend_lifecycle.dart`

```dart
// lib/services/backend_lifecycle.dart

import 'dart:async';

/// 后端状态枚举
enum BackendStatus {
  stopped,     // 未启动
  starting,    // 启动中
  ready,       // 就绪
  error,       // 错误
  restarting,  // 重启中
}

/// 后端生命周期管理接口
abstract class BackendLifecycle {
  /// 启动后端
  Future<void> start();

  /// 停止后端
  Future<void> stop();

  /// 重启后端
  Future<void> restart();

  /// 健康检查
  Future<bool> isHealthy();

  /// 等待就绪
  Future<void> waitForReady({Duration timeout = const Duration(seconds: 15)});

  /// 状态流
  Stream<BackendStatus> get statusStream;

  /// 当前状态
  BackendStatus get status;

  /// 后端 URL
  String get baseUrl;

  /// 释放资源
  void dispose();
}
```

**验收标准**：
- 文件创建成功
- `flutter analyze` 无错误

---

### B.2 实现桌面端生命周期管理

**输入**：B.1 接口定义
**输出**：`lib/services/backend_lifecycle_desktop.dart`

```dart
// lib/services/backend_lifecycle_desktop.dart

import 'dart:async';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'backend_lifecycle.dart';

class DesktopBackendLifecycle implements BackendLifecycle {
  Process? _process;
  final int _port;
  int _restartCount = 0;
  static const _maxRestarts = 3;
  static const _healthCheckInterval = Duration(milliseconds: 500);

  BackendStatus _status = BackendStatus.stopped;
  final _statusController = StreamController<BackendStatus>.broadcast();

  DesktopBackendLifecycle({int port = 8765}) : _port = port;

  @override
  BackendStatus get status => _status;

  @override
  Stream<BackendStatus> get statusStream => _statusController.stream;

  @override
  String get baseUrl => 'http://127.0.0.1:$_port';

  @override
  Future<void> start() async {
    if (_status == BackendStatus.starting || _status == BackendStatus.ready) {
      return;
    }

    _setStatus(BackendStatus.starting);

    try {
      // 1. 获取可执行文件路径
      final execPath = await _getExecutablePath();

      // 2. 检查可执行文件是否存在
      if (!await File(execPath).exists()) {
        throw Exception('Backend executable not found: $execPath');
      }

      // 3. 设置可执行权限（macOS/Linux）
      if (!Platform.isWindows) {
        await Process.run('chmod', ['+x', execPath]);
      }

      // 4. 启动进程
      _process = await Process.start(
        execPath,
        ['--port', '$_port'],
        environment: {
          'CHATBOX_BACKEND_HOST': '127.0.0.1',
          'CHATBOX_BACKEND_PORT': '$_port',
        },
      );

      // 5. 监听退出
      _process!.exitCode.then(_onProcessExit);

      // 6. 等待就绪
      await waitForReady();
      _restartCount = 0;
      _setStatus(BackendStatus.ready);
    } catch (e) {
      _setStatus(BackendStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> stop() async {
    if (_status == BackendStatus.stopped) return;

    // 1. 尝试优雅关闭
    try {
      await http.post(Uri.parse('$baseUrl/api/shutdown'))
          .timeout(const Duration(seconds: 2));
    } catch (_) {}

    // 2. 等待进程退出
    await Future.delayed(const Duration(seconds: 1));

    // 3. 强制终止
    if (_process != null) {
      if (Platform.isWindows) {
        await Process.run('taskkill', ['/F', '/PID', '${_process!.pid}']);
      } else {
        _process!.kill(ProcessSignal.sigterm);
      }
    }

    _process = null;
    _setStatus(BackendStatus.stopped);
  }

  @override
  Future<void> restart() async {
    _setStatus(BackendStatus.restarting);
    await stop();
    await start();
  }

  @override
  Future<bool> isHealthy() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> waitForReady({Duration timeout = const Duration(seconds: 15)}) async {
    final deadline = DateTime.now().add(timeout);

    while (DateTime.now().isBefore(deadline)) {
      if (await isHealthy()) return;
      await Future.delayed(_healthCheckInterval);
    }

    throw TimeoutException('Backend failed to start within $timeout');
  }

  @override
  void dispose() {
    stop();
    _statusController.close();
  }

  // === Private Methods ===

  Future<String> _getExecutablePath() async {
    final appDir = await getApplicationSupportDirectory();
    final execName = Platform.isWindows ? 'chatbox-backend.exe' : 'chatbox-backend';
    return p.join(appDir.path, 'backend', execName);
  }

  void _setStatus(BackendStatus newStatus) {
    _status = newStatus;
    _statusController.add(newStatus);
  }

  void _onProcessExit(int exitCode) {
    if (_status == BackendStatus.stopped) return;

    // 非正常退出，尝试重启
    if (exitCode != 0 && _restartCount < _maxRestarts) {
      _restartCount++;
      restart();
    } else if (_restartCount >= _maxRestarts) {
      _setStatus(BackendStatus.error);
    }
  }
}
```

**验收标准**：
- 文件创建成功
- `flutter analyze` 无错误
- 单元测试通过（B.5）

---

### B.3 实现工厂类

**输入**：B.1, B.2 产出
**输出**：`lib/services/backend_lifecycle_service.dart`

```dart
// lib/services/backend_lifecycle_service.dart

import 'dart:io';
import 'backend_lifecycle.dart';
import 'backend_lifecycle_desktop.dart';
// import 'backend_lifecycle_mobile.dart';  // Phase C 添加

class BackendLifecycleService {
  static BackendLifecycle? _instance;

  /// 获取单例实例
  static BackendLifecycle get instance {
    _instance ??= create();
    return _instance!;
  }

  /// 创建平台特定实现
  static BackendLifecycle create({int port = 8765}) {
    if (Platform.isAndroid || Platform.isIOS) {
      // Phase C 实现
      throw UnimplementedError('Mobile backend not yet implemented');
    } else if (Platform.isWindows || Platform.isMacOS || Platform.isLinux) {
      return DesktopBackendLifecycle(port: port);
    } else {
      throw UnsupportedError('Unsupported platform');
    }
  }

  /// 重置单例（用于测试）
  static void reset() {
    _instance?.dispose();
    _instance = null;
  }
}
```

**验收标准**：
- 文件创建成功
- `flutter analyze` 无错误

---

### B.4 集成到 main.dart

**输入**：B.3 产出
**输出**：修改 `lib/main.dart`

**修改点**：

```dart
// lib/main.dart

import 'services/backend_lifecycle_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 初始化 Hive 等现有逻辑...

  // === 新增：启动后端 ===
  if (!kIsWeb) {  // Web 平台不启动本地后端
    try {
      final backend = BackendLifecycleService.instance;
      await backend.start();
    } catch (e) {
      debugPrint('Backend startup failed: $e');
      // 继续运行，使用 direct 模式 fallback
    }
  }

  runApp(const MyApp());
}

// === 新增：App 关闭时停止后端 ===
class MyApp extends StatefulWidget {
  // ...
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (!kIsWeb) {
      BackendLifecycleService.instance.dispose();
    }
    super.dispose();
  }

  @override
  Future<AppExitResponse> didRequestAppExit() async {
    if (!kIsWeb) {
      await BackendLifecycleService.instance.stop();
    }
    return AppExitResponse.exit;
  }

  // ...
}
```

**验收标准**：
- App 启动时后端自动启动
- App 关闭时后端正确退出
- 后端启动失败时 App 仍可正常使用（fallback 到 direct 模式）

---

### B.5 添加单元测试

**输入**：B.2 产出
**输出**：`test/unit/services/backend_lifecycle_desktop_test.dart`

```dart
// test/unit/services/backend_lifecycle_desktop_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/backend_lifecycle.dart';
import 'package:chatboxapp/services/backend_lifecycle_desktop.dart';

void main() {
  group('DesktopBackendLifecycle', () {
    late DesktopBackendLifecycle lifecycle;

    setUp(() {
      lifecycle = DesktopBackendLifecycle(port: 18765);  // 使用非默认端口避免冲突
    });

    tearDown(() {
      lifecycle.dispose();
    });

    test('initial status should be stopped', () {
      expect(lifecycle.status, BackendStatus.stopped);
    });

    test('baseUrl should be correct', () {
      expect(lifecycle.baseUrl, 'http://127.0.0.1:18765');
    });

    test('statusStream should emit status changes', () async {
      final statuses = <BackendStatus>[];
      lifecycle.statusStream.listen(statuses.add);

      // 模拟状态变化
      // ...

      expect(statuses, isNotEmpty);
    });

    // 集成测试需要实际可执行文件，标记为 skip
    test('start() should launch backend process', skip: 'Requires executable');
    test('stop() should terminate backend process', skip: 'Requires executable');
  });
}
```

**验收标准**：
- `flutter test test/unit/services/backend_lifecycle_desktop_test.dart` 通过

---

### B.6 创建桌面端打包脚本

**输入**：现有 `backend/` 代码
**输出**：`backend/scripts/build_desktop.sh`, `backend/scripts/build_desktop.ps1`

```bash
#!/bin/bash
# backend/scripts/build_desktop.sh

set -e

echo "Building ChatBox Backend for Desktop..."

cd "$(dirname "$0")/.."

# 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
pip install pyinstaller

# 打包
pyinstaller --onefile \
    --name chatbox-backend \
    --add-data "config.py:." \
    main.py

echo "Build complete: dist/chatbox-backend"
```

```powershell
# backend/scripts/build_desktop.ps1

$ErrorActionPreference = "Stop"

Write-Host "Building ChatBox Backend for Desktop..."

Push-Location "$PSScriptRoot\.."

# 创建虚拟环境
if (!(Test-Path "venv")) {
    python -m venv venv
}

# 激活
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
pip install pyinstaller

# 打包
pyinstaller --onefile `
    --name chatbox-backend `
    main.py

Write-Host "Build complete: dist\chatbox-backend.exe"

Pop-Location
```

**验收标准**：
- 脚本执行成功
- 生成 `backend/dist/chatbox-backend[.exe]`
- 可执行文件能独立运行

---

## Phase C: 移动端集成

**前置条件**：Phase A.4 通过

### C.1 添加 serious_python 依赖

**输入**：现有 `pubspec.yaml`
**输出**：修改 `pubspec.yaml`

```yaml
# pubspec.yaml

dependencies:
  # ... 现有依赖 ...
  serious_python: ^0.9.0

flutter:
  assets:
    # ... 现有资产 ...
    - assets/backend/app.zip
```

**验收标准**：
- `flutter pub get` 成功
- 无依赖冲突

---

### C.2 实现移动端生命周期管理

**输入**：B.1 接口定义
**输出**：`lib/services/backend_lifecycle_mobile.dart`

```dart
// lib/services/backend_lifecycle_mobile.dart

import 'dart:async';
import 'package:http/http.dart' as http;
import 'package:serious_python/serious_python.dart';
import 'backend_lifecycle.dart';

class MobileBackendLifecycle implements BackendLifecycle {
  static const _port = 8765;
  static const _healthCheckInterval = Duration(milliseconds: 500);

  BackendStatus _status = BackendStatus.stopped;
  final _statusController = StreamController<BackendStatus>.broadcast();

  @override
  BackendStatus get status => _status;

  @override
  Stream<BackendStatus> get statusStream => _statusController.stream;

  @override
  String get baseUrl => 'http://127.0.0.1:$_port';

  @override
  Future<void> start() async {
    if (_status == BackendStatus.starting || _status == BackendStatus.ready) {
      return;
    }

    _setStatus(BackendStatus.starting);

    try {
      // 使用 serious_python 启动
      await SeriousPython.run(
        'assets/backend/app.zip',
        appFileName: 'main.py',
        environmentVariables: {
          'CHATBOX_BACKEND_HOST': '127.0.0.1',
          'CHATBOX_BACKEND_PORT': '$_port',
        },
      );

      // 等待就绪
      await waitForReady();
      _setStatus(BackendStatus.ready);
    } catch (e) {
      _setStatus(BackendStatus.error);
      rethrow;
    }
  }

  @override
  Future<void> stop() async {
    if (_status == BackendStatus.stopped) return;

    try {
      await http.post(Uri.parse('$baseUrl/api/shutdown'))
          .timeout(const Duration(seconds: 2));
    } catch (_) {}

    _setStatus(BackendStatus.stopped);
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
      final response = await http.get(Uri.parse('$baseUrl/api/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> waitForReady({Duration timeout = const Duration(seconds: 15)}) async {
    final deadline = DateTime.now().add(timeout);

    while (DateTime.now().isBefore(deadline)) {
      if (await isHealthy()) return;
      await Future.delayed(_healthCheckInterval);
    }

    throw TimeoutException('Backend failed to start within $timeout');
  }

  @override
  void dispose() {
    stop();
    _statusController.close();
  }

  void _setStatus(BackendStatus newStatus) {
    _status = newStatus;
    _statusController.add(newStatus);
  }
}
```

**验收标准**：
- 文件创建成功
- `flutter analyze` 无错误

---

### C.3 更新工厂类

**输入**：C.2 产出
**输出**：修改 `lib/services/backend_lifecycle_service.dart`

```dart
// 取消注释 mobile 导入
import 'backend_lifecycle_mobile.dart';

// 修改 create 方法
static BackendLifecycle create({int port = 8765}) {
  if (Platform.isAndroid || Platform.isIOS) {
    return MobileBackendLifecycle();  // 移除 throw
  } else if (Platform.isWindows || Platform.isMacOS || Platform.isLinux) {
    return DesktopBackendLifecycle(port: port);
  } else {
    throw UnsupportedError('Unsupported platform');
  }
}
```

**验收标准**：
- `flutter analyze` 无错误

---

### C.4 配置 Android Gradle

**输入**：serious_python 文档
**输出**：修改 `android/app/build.gradle`

```groovy
// android/app/build.gradle

android {
    // ... 现有配置 ...

    defaultConfig {
        // ... 现有配置 ...

        // serious_python 需要的最低 SDK 版本
        minSdkVersion 26  // API 26 = Android 8.0

        // ABI 过滤（减少 APK 体积）
        ndk {
            abiFilters 'arm64-v8a', 'armeabi-v7a'
        }
    }
}
```

**验收标准**：
- `flutter build apk` 成功

---

### C.5 配置 iOS Podfile

**输入**：serious_python 文档
**输出**：修改 `ios/Podfile`

```ruby
# ios/Podfile

platform :ios, '12.0'  # serious_python 最低要求

# ... 现有配置 ...
```

**验收标准**：
- `cd ios && pod install` 成功

---

### C.6 创建移动端打包脚本

**输入**：现有 `backend/` 代码
**输出**：`backend/scripts/build_mobile.sh`

```bash
#!/bin/bash
# backend/scripts/build_mobile.sh

set -e

PLATFORM=${1:-Android}

echo "Building ChatBox Backend for $PLATFORM..."

cd "$(dirname "$0")/../.."

# 确保 Flutter 项目根目录
if [ ! -f "pubspec.yaml" ]; then
    echo "Error: Run from Flutter project root"
    exit 1
fi

# 创建资产目录
mkdir -p assets/backend

# 打包
dart run serious_python:main package backend \
    -p "$PLATFORM" \
    --asset assets/backend/app.zip \
    --requirements fastapi,uvicorn,pydantic,pydantic-settings,httpx,sse-starlette

echo "Build complete: assets/backend/app.zip"
echo "Run 'flutter build apk' or 'flutter build ios' to build app"
```

**验收标准**：
- `./backend/scripts/build_mobile.sh Android` 成功
- `assets/backend/app.zip` 生成

---

### C.7 Android 真机测试

**输入**：C.1-C.6 产出
**输出**：测试报告

**步骤**：

```bash
# 1. 打包后端
./backend/scripts/build_mobile.sh Android

# 2. 构建 APK
flutter build apk --debug

# 3. 安装到真机
adb install build/app/outputs/flutter-apk/app-debug.apk

# 4. 运行并观察日志
adb logcat | grep -E "(serious_python|chatbox)"
```

**验收标准**：
- App 启动成功
- 后端健康检查通过
- LLM 对话功能正常

---

### C.8 iOS 真机测试

**输入**：C.1-C.6 产出
**输出**：测试报告

**步骤**：

```bash
# 1. 打包后端
./backend/scripts/build_mobile.sh iOS

# 2. 构建
flutter build ios --debug

# 3. 通过 Xcode 安装到真机
open ios/Runner.xcworkspace
# Xcode: Product > Run
```

**验收标准**：
- App 启动成功
- 后端健康检查通过
- LLM 对话功能正常

---

## Phase D: UI 集成

**前置条件**：Phase B, C 通过

### D.1 添加后端状态指示器（可选）

**输入**：`BackendStatus` 枚举
**输出**：`lib/widgets/backend_status_indicator.dart`

```dart
// lib/widgets/backend_status_indicator.dart

import 'package:flutter/material.dart';
import '../services/backend_lifecycle.dart';
import '../services/backend_lifecycle_service.dart';

class BackendStatusIndicator extends StatelessWidget {
  const BackendStatusIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<BackendStatus>(
      stream: BackendLifecycleService.instance.statusStream,
      initialData: BackendLifecycleService.instance.status,
      builder: (context, snapshot) {
        final status = snapshot.data ?? BackendStatus.stopped;
        return _buildIndicator(status);
      },
    );
  }

  Widget _buildIndicator(BackendStatus status) {
    final (color, icon, tooltip) = switch (status) {
      BackendStatus.stopped => (Colors.grey, Icons.cloud_off, '后端未运行'),
      BackendStatus.starting => (Colors.orange, Icons.cloud_sync, '后端启动中...'),
      BackendStatus.ready => (Colors.green, Icons.cloud_done, '后端就绪'),
      BackendStatus.error => (Colors.red, Icons.cloud_off, '后端错误'),
      BackendStatus.restarting => (Colors.orange, Icons.refresh, '后端重启中...'),
    };

    return Tooltip(
      message: tooltip,
      child: Icon(icon, color: color, size: 16),
    );
  }
}
```

**验收标准**：
- 指示器正确显示后端状态
- 状态变化时自动更新

---

### D.2 集成到设置页面

**输入**：现有设置页面
**输出**：修改设置页面添加后端相关选项

**修改点**：
- 添加「本地后端」开关
- 添加「后端状态」显示
- 添加「重启后端」按钮

（具体实现取决于现有设置页面结构）

---

## Phase E: 测试与优化

### E.1 全平台集成测试

**测试矩阵**：

| 平台 | 测试项 | 预期结果 |
|------|--------|----------|
| Windows | App 启动 | 后端自动启动 |
| Windows | App 关闭 | 后端正确退出 |
| Windows | 后端崩溃 | 自动重启 |
| macOS | App 启动 | 后端自动启动 |
| macOS | App 关闭 | 后端正确退出 |
| macOS | 后端崩溃 | 自动重启 |
| Linux | App 启动 | 后端自动启动 |
| Android | App 启动 | 后端自动启动 |
| Android | App 关闭 | 后端正确退出 |
| iOS | App 启动 | 后端自动启动 |
| iOS | App 关闭 | 后端正确退出 |

---

### E.2 性能测试

**测试指标**：

| 指标 | 桌面端目标 | 移动端目标 | 测试方法 |
|------|------------|------------|----------|
| 冷启动时间 | < 5s | < 10s | 计时器 |
| 热启动时间 | < 2s | < 3s | 计时器 |
| 内存占用 | < 200MB | < 150MB | 系统监控 |

---

### E.3 文档更新

**更新文件**：

- `README.md` - 添加后端自动启动说明
- `CLAUDE.md` - 更新架构图和模块说明
- `specs/backend-integration/` - 归档实施文档

---

## 附录

### A. 文件清单

**新增文件**：

```
lib/services/
├── backend_lifecycle.dart
├── backend_lifecycle_desktop.dart
├── backend_lifecycle_mobile.dart
└── backend_lifecycle_service.dart

lib/widgets/
└── backend_status_indicator.dart

backend/scripts/
├── build_desktop.sh
├── build_desktop.ps1
└── build_mobile.sh

backend/poc/
└── minimal_app.py

test/unit/services/
└── backend_lifecycle_desktop_test.dart

assets/backend/
└── app.zip  (gitignore)
```

**修改文件**：

```
lib/main.dart
pubspec.yaml
android/app/build.gradle
ios/Podfile
backend/main.py  (添加 /api/shutdown)
.gitignore  (添加 assets/backend/)
```

### B. 回滚计划

若实施失败，回滚步骤：

1. `git revert` 相关提交
2. 删除新增文件
3. 恢复 `pubspec.yaml` 依赖
4. 继续使用手动启动后端模式

### C. 依赖版本

| 依赖 | 版本 | 用途 |
|------|------|------|
| serious_python | ^0.9.0 | 移动端 Python 嵌入 |
| path_provider | ^2.0.0 | 获取应用目录 |
| http | ^1.2.0 | 健康检查 HTTP 请求 |
