# Python 后端集成 - OpenSpec 提案

> 创建时间：2026-02-03
> 状态：Proposal
> 范围：桌面端后端静默自启动 + 移动端 Python 嵌入

---

## 1. 提案概述

### 1.1 问题陈述

当前 ChatBoxApp 的 Python 后端需要用户手动运行 `python main.py` 启动，这对普通用户不友好，也无法在移动端使用。

### 1.2 目标

1. **桌面端**：App 启动时自动启动 Python 后端，用户无感知
2. **移动端**：将 Python 运行时嵌入 App，实现离线运行
3. **统一接口**：所有平台使用相同的 HTTP API 通信

### 1.3 非目标

- iOS App Store 审核问题（后续处理）
- Python 后端功能扩展（MCP、RAG）
- Web 平台支持

---

## 2. 技术方案

### 2.1 方案选型

| 平台 | 方案 | 理由 |
|------|------|------|
| Windows | PyInstaller + subprocess | 成熟稳定，体积可控 |
| macOS | PyInstaller + subprocess | 同上 |
| Linux | PyInstaller + subprocess | 同上 |
| Android | serious_python | 官方 Flutter 支持，全功能 |
| iOS | serious_python | 同上，App Store 允许 |

### 2.2 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        Flutter App                           │
├─────────────────────────────────────────────────────────────┤
│                   BackendLifecycleService                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ interface BackendLifecycle {                          │  │
│  │   Future<void> start();                               │  │
│  │   Future<void> stop();                                │  │
│  │   Future<bool> isHealthy();                           │  │
│  │   Stream<BackendStatus> get statusStream;             │  │
│  │ }                                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                 │
│         ┌──────────────────┼──────────────────┐             │
│         ▼                  ▼                  ▼             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐       │
│  │ Desktop     │   │ Android     │   │ iOS         │       │
│  │ Lifecycle   │   │ Lifecycle   │   │ Lifecycle   │       │
│  │ (subprocess)│   │ (serious_py)│   │ (serious_py)│       │
│  └─────────────┘   └─────────────┘   └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 核心接口

```dart
/// 后端状态
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
}

/// 后端生命周期服务（工厂模式）
class BackendLifecycleService {
  static BackendLifecycle create() {
    if (Platform.isAndroid || Platform.isIOS) {
      return MobileBackendLifecycle();
    } else {
      return DesktopBackendLifecycle();
    }
  }
}
```

### 2.4 桌面端实现细节

#### 2.4.1 文件结构

```
ChatBoxApp.app/  (macOS)
├── Contents/
│   ├── MacOS/
│   │   ├── ChatBoxApp           # Flutter 可执行文件
│   │   └── chatbox-backend      # Python 后端可执行文件
│   └── Resources/
│       └── ...

ChatBoxApp/  (Windows)
├── ChatBoxApp.exe               # Flutter 可执行文件
├── chatbox-backend.exe          # Python 后端可执行文件
└── data/
    └── ...
```

#### 2.4.2 启动流程

```
App 启动
    │
    ▼
BackendLifecycleService.start()
    │
    ├─► 检查可执行文件是否存在
    │       │
    │       ├─► 不存在：解压到缓存目录
    │       │
    │       └─► 存在：检查版本
    │               │
    │               ├─► 版本不匹配：重新解压
    │               │
    │               └─► 版本匹配：继续
    │
    ├─► 分配端口（默认 8765，冲突时自动分配）
    │
    ├─► 设置可执行权限（macOS/Linux）
    │
    ├─► Process.start() 启动子进程
    │
    ├─► 注册退出回调（崩溃检测）
    │
    └─► 轮询健康检查直到就绪
            │
            ├─► 成功：状态 → ready
            │
            └─► 超时：状态 → error，触发 fallback
```

#### 2.4.3 关闭流程

```
App 关闭 / didRequestAppExit()
    │
    ▼
BackendLifecycleService.stop()
    │
    ├─► 发送 POST /api/shutdown（优雅关闭）
    │
    ├─► 等待 3 秒
    │
    └─► 强制终止（taskkill / pkill）
```

### 2.5 移动端实现细节

#### 2.5.1 打包结构

```
flutter:
  assets:
    - assets/backend/app.zip    # 打包的 Python 后端
```

#### 2.5.2 启动流程

```
App 启动
    │
    ▼
BackendLifecycleService.start()
    │
    ├─► SeriousPython.run('assets/backend/app.zip')
    │       │
    │       ├─► 解压到临时目录
    │       │
    │       ├─► 启动 Python 解释器
    │       │
    │       └─► 执行 main.py
    │
    └─► 轮询健康检查直到就绪
```

#### 2.5.3 ASGI 服务器选择

由于 uvloop 无法在移动端使用，需要选择替代方案：

| 方案 | 纯 Python | 性能 | 兼容性 |
|------|-----------|------|--------|
| uvicorn (asyncio) | ✅ | 中 | ⚠️ 需验证 |
| Hypercorn | ✅ | 中 | ✅ |
| Starlette.TestClient | ✅ | 低 | ✅ |

**推荐**：先尝试 uvicorn 的 asyncio 后端，若失败则回退到 Hypercorn

```python
# main.py
import uvicorn
from app import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        loop="asyncio",  # 不使用 uvloop
    )
```

---

## 3. 详细设计

### 3.1 新增文件

```
lib/
├── services/
│   ├── backend_lifecycle.dart           # 接口定义
│   ├── backend_lifecycle_desktop.dart   # 桌面端实现
│   ├── backend_lifecycle_mobile.dart    # 移动端实现
│   └── backend_lifecycle_service.dart   # 工厂类
│
├── models/
│   └── backend_status.dart              # 状态枚举
│
└── widgets/
    └── backend_status_indicator.dart    # 状态指示器（可选）

backend/
├── scripts/
│   ├── build_desktop.sh                 # 桌面端打包脚本
│   └── build_mobile.sh                  # 移动端打包脚本
│
└── main.py                              # 添加 shutdown 端点

assets/
└── backend/
    └── app.zip                          # 移动端打包资产（gitignore）
```

### 3.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `lib/main.dart` | App 启动时调用 `BackendLifecycleService.start()` |
| `lib/adapters/ai_provider.dart` | 集成后端状态检查 |
| `pubspec.yaml` | 添加 `serious_python` 依赖 |
| `android/app/build.gradle` | 配置 serious_python |
| `ios/Podfile` | 配置 platform 版本 |
| `backend/main.py` | 添加 `/api/shutdown` 端点 |
| `backend/requirements.txt` | 确保依赖兼容移动端 |

### 3.3 配置扩展

```dart
// lib/models/provider_config.dart 扩展

class ProviderConfig {
  // ... 现有字段 ...

  /// 后端自动启动（默认 true）
  final bool backendAutoStart;

  /// 后端启动超时（秒）
  final int backendStartupTimeoutSec;

  /// 后端崩溃最大重启次数
  final int backendMaxRestarts;
}
```

---

## 4. 测试计划

### 4.1 单元测试

```dart
// test/unit/services/backend_lifecycle_test.dart

void main() {
  group('BackendLifecycle', () {
    test('start() should transition to ready state', () async {
      final lifecycle = MockBackendLifecycle();
      await lifecycle.start();
      expect(lifecycle.status, BackendStatus.ready);
    });

    test('stop() should terminate process', () async {
      // ...
    });

    test('restart() should recover from crash', () async {
      // ...
    });
  });
}
```

### 4.2 集成测试

| 测试场景 | 平台 | 预期结果 |
|----------|------|----------|
| App 启动时后端自动启动 | 全平台 | 健康检查成功 |
| App 关闭时后端优雅退出 | 全平台 | 无僵尸进程 |
| 后端崩溃后自动重启 | 全平台 | 最多重启 3 次 |
| 端口冲突时自动分配新端口 | 桌面端 | 使用新端口 |
| 首次启动解压资产 | 全平台 | 解压成功 |

### 4.3 性能测试

| 指标 | 桌面端目标 | 移动端目标 |
|------|------------|------------|
| 冷启动时间 | < 5s | < 10s |
| 热启动时间 | < 2s | < 3s |
| 内存占用 | < 200MB | < 150MB |
| 首次解压时间 | < 10s | < 15s |

---

## 5. 实施计划

### Phase A: PoC 验证（3 天）

- [ ] A.1 创建最小 FastAPI 后端
- [ ] A.2 桌面端：PyInstaller 打包 + subprocess 启动测试
- [ ] A.3 移动端：serious_python 打包 + 真机测试
- [ ] A.4 验证 uvicorn asyncio 模式在移动端可行性

### Phase B: 桌面端集成（5 天）

- [ ] B.1 实现 `DesktopBackendLifecycle` 类
- [ ] B.2 实现可执行文件解压和版本管理
- [ ] B.3 实现进程生命周期管理
- [ ] B.4 集成到 `main.dart` 启动流程
- [ ] B.5 添加单元测试

### Phase C: 移动端集成（5 天）

- [ ] C.1 配置 `serious_python` 依赖
- [ ] C.2 实现 `MobileBackendLifecycle` 类
- [ ] C.3 配置 Android Gradle
- [ ] C.4 配置 iOS Podfile
- [ ] C.5 Android 真机测试
- [ ] C.6 iOS 真机测试

### Phase D: UI 集成（2 天）

- [ ] D.1 添加后端状态指示器（可选）
- [ ] D.2 添加设置页面配置项
- [ ] D.3 添加启动失败错误提示

### Phase E: 测试与优化（3 天）

- [ ] E.1 全平台集成测试
- [ ] E.2 性能优化
- [ ] E.3 文档更新

---

## 6. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| uvicorn 移动端不兼容 | 中 | 高 | 准备 Hypercorn 作为 Plan B |
| iOS App Store 审核拒绝 | 低 | 高 | serious_python 已有成功案例 |
| 移动端内存不足 | 低 | 中 | 限制并发，监控内存 |
| 首次启动过慢 | 中 | 低 | 显示加载动画，后台解压 |

---

## 7. 开放问题

1. **Q: 是否需要支持用户自定义后端端口？**
   - 建议：暂不支持，使用固定端口 8765，冲突时自动分配

2. **Q: 后端崩溃时是否需要通知用户？**
   - 建议：静默重启，连续失败 3 次后显示错误

3. **Q: 是否需要支持后端日志查看？**
   - 建议：Phase 1 不支持，后续迭代

4. **Q: Web 平台如何处理？**
   - 建议：Web 平台使用远程后端或直接调用 LLM API

---

## 8. 参考资料

- [serious_python GitHub](https://github.com/flet-dev/serious-python)
- [flutter_python_starter](https://github.com/maxim-saplin/flutter_python_starter)
- [PyInstaller 文档](https://pyinstaller.org/)
- [uvicorn 文档](https://www.uvicorn.org/)
