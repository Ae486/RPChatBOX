# Python 后端集成约束集

> 创建时间：2026-02-03
> 状态：Draft
> 范围：桌面端后端自启动 + 移动端 Python 嵌入

---

## 1. 术语定义

| 术语 | 定义 |
|------|------|
| **静默自启动** | App 启动时自动启动 Python 后端进程，用户无感知 |
| **进程生命周期管理** | 随 App 启动/关闭，包括健康检查、崩溃恢复 |
| **嵌入式 Python** | Python 运行时打包到 App 内部，无需用户安装 Python |
| **serious_python** | Flet 团队开发的 Flutter 嵌入 Python 运行时插件 |

---

## 2. 调研结论

### 2.1 Serious Python 可行性评估

| 维度 | 结论 |
|------|------|
| **平台支持** | ✅ iOS + Android + macOS + Linux + Windows（全平台） |
| **Python 版本** | Python 3.12.9（所有平台统一） |
| **架构模式** | 进程隔离 + API 通信（HTTP/Socket/File） |
| **FastAPI 兼容** | ⚠️ 需要验证，pydantic_core 已有预编译包 |
| **uvicorn 兼容** | ⚠️ 无预编译包，可能需要纯 Python 模式或替代方案 |
| **Flask 验证** | ✅ 官方示例已验证 Flask HTTP Server 可行 |
| **授权** | MIT License，无商业限制 |

**关键发现**：
1. serious_python 设计用于"后台服务 + API 通信"模式，与我们的架构完全匹配
2. pypi.flet.dev 有 80+ 预编译原生包，包括 pydantic_core、aiohttp、websockets
3. 官方 Flask 示例验证了在移动端运行 HTTP Server 的可行性
4. 不支持 uvloop（uvicorn 的高性能依赖），需要测试纯 Python 模式

### 2.2 桌面端方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **serious_python** | 全平台统一、官方维护 | 桌面端可能过重 | ⭐⭐⭐ |
| **PyInstaller + subprocess** | 成熟、体积可控 | 需要自己管理进程 | ⭐⭐⭐⭐ |
| **py_engine_desktop** | 专为桌面设计 | 新项目、仅桌面 | ⭐⭐ |

**推荐**：桌面端使用 PyInstaller 打包 + subprocess 管理，参考 `flutter_python_starter` 模式

### 2.3 移动端方案

| 方案 | iOS | Android | 推荐度 |
|------|-----|---------|--------|
| **serious_python** | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| **Chaquopy** | ❌ | ✅ | ⭐⭐ |
| **BeeWare (Briefcase)** | ✅ | ✅ | ⭐⭐ |

**推荐**：移动端使用 serious_python，唯一的全平台统一方案

---

## 3. 约束条件

### 3.1 功能约束

| ID | 约束 | 类型 | 优先级 |
|----|------|------|--------|
| F-01 | 后端进程必须随 App 启动自动启动 | 必须 | P0 |
| F-02 | 后端进程必须随 App 关闭优雅退出 | 必须 | P0 |
| F-03 | 后端启动失败时必须有 fallback 机制 | 必须 | P0 |
| F-04 | 后端健康检查间隔 ≤ 5 秒 | 应该 | P1 |
| F-05 | 后端崩溃后应自动重启（最多 3 次） | 应该 | P1 |
| F-06 | 启动超时时间可配置，默认 15 秒 | 应该 | P1 |

### 3.2 性能约束

| ID | 约束 | 类型 | 优先级 |
|----|------|------|--------|
| P-01 | 后端启动时间 ≤ 5 秒（桌面端）| 应该 | P1 |
| P-02 | 后端启动时间 ≤ 10 秒（移动端）| 应该 | P1 |
| P-03 | 后端内存占用 ≤ 200MB（基础状态）| 应该 | P1 |
| P-04 | 首次启动允许额外 10 秒用于解压/初始化 | 可以 | P2 |

### 3.3 兼容性约束

| ID | 约束 | 类型 | 优先级 |
|----|------|------|--------|
| C-01 | 桌面端支持 Windows 10+、macOS 10.15+、Ubuntu 20.04+ | 必须 | P0 |
| C-02 | 移动端支持 Android 8.0+ (API 26)、iOS 12.0+ | 必须 | P0 |
| C-03 | 现有直连模式必须保留作为 fallback | 必须 | P0 |
| C-04 | 后端 API 必须兼容 OpenAI 格式 | 必须 | P0 |

### 3.4 安全约束

| ID | 约束 | 类型 | 优先级 |
|----|------|------|--------|
| S-01 | 后端只绑定 localhost，不暴露外网 | 必须 | P0 |
| S-02 | API Key 仅在请求中传递，后端不持久化 | 必须 | P0 |
| S-03 | 移动端使用 Unix Domain Socket 替代 TCP | 应该 | P1 |

---

## 4. 技术方案

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Flutter App                           │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              BackendLifecycleService                 │    │
│  │  - start() / stop() / restart()                     │    │
│  │  - healthCheck() / waitForReady()                   │    │
│  │  - onCrash() callback                               │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                 │
│           ┌───────────────┴───────────────┐                 │
│           ▼                               ▼                 │
│  ┌─────────────────┐           ┌─────────────────┐          │
│  │ Desktop Backend │           │ Mobile Backend  │          │
│  │ (PyInstaller)   │           │ (serious_python)│          │
│  │                 │           │                 │          │
│  │ Process.start() │           │ SeriousPython   │          │
│  │ subprocess mgmt │           │   .run()        │          │
│  └─────────────────┘           └─────────────────┘          │
│           │                               │                 │
│           └───────────────┬───────────────┘                 │
│                           ▼                                 │
│                  http://localhost:8765                      │
│                  (or Unix Domain Socket)                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Backend (FastAPI)                  │
│                                                              │
│   /api/health          - 健康检查                           │
│   /v1/chat/completions - LLM 代理                           │
│   /v1/models           - 模型列表                           │
│                                                              │
│   (Future: MCP Host, RAG Service)                           │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 桌面端实现

```dart
// lib/services/backend_lifecycle_desktop.dart

class DesktopBackendLifecycle implements BackendLifecycle {
  Process? _process;
  final String _executablePath;
  final int _port;
  int _restartCount = 0;
  static const _maxRestarts = 3;

  Future<void> start() async {
    // 1. 解压可执行文件（首次或版本更新时）
    await _extractExecutable();

    // 2. 设置可执行权限（macOS/Linux）
    if (!Platform.isWindows) {
      await Process.run('chmod', ['u+x', _executablePath]);
    }

    // 3. 启动进程
    _process = await Process.start(
      _executablePath,
      ['--port', '$_port'],
      mode: ProcessStartMode.detached,
    );

    // 4. 监听退出
    _process!.exitCode.then((code) => _onProcessExit(code));

    // 5. 等待就绪
    await _waitForReady(timeout: Duration(seconds: 15));
  }

  Future<void> stop() async {
    if (Platform.isWindows) {
      await Process.run('taskkill', ['/F', '/IM', _executableName]);
    } else {
      await Process.run('pkill', ['-f', _executableName]);
    }
    _process = null;
  }
}
```

### 4.3 移动端实现

```dart
// lib/services/backend_lifecycle_mobile.dart

class MobileBackendLifecycle implements BackendLifecycle {
  static const _port = 8765;

  Future<void> start() async {
    // 使用 serious_python 启动 Python 后端
    await SeriousPython.run(
      'assets/backend/app.zip',
      appFileName: 'main.py',
      environmentVariables: {
        'CHATBOX_BACKEND_PORT': '$_port',
        'CHATBOX_BACKEND_HOST': '127.0.0.1',
      },
    );

    // 等待就绪
    await _waitForReady(timeout: Duration(seconds: 15));
  }

  Future<void> stop() async {
    // serious_python 会在 App 退出时自动清理
    // 但可以通过发送 shutdown 请求主动关闭
    try {
      await http.post(Uri.parse('http://localhost:$_port/api/shutdown'));
    } catch (_) {}
  }
}
```

### 4.4 打包流程

#### 桌面端（PyInstaller）

```bash
# backend/scripts/build_desktop.sh
cd backend
pyinstaller --onefile --name chatbox-backend main.py

# 输出:
# - Windows: dist/chatbox-backend.exe
# - macOS:   dist/chatbox-backend
# - Linux:   dist/chatbox-backend
```

#### 移动端（serious_python）

```bash
# 设置环境变量
export SERIOUS_PYTHON_SITE_PACKAGES=$(pwd)/build/site-packages

# 打包 Android
dart run serious_python:main package backend/src \
  -p Android \
  --asset assets/backend/app.zip \
  --requirements fastapi,uvicorn,pydantic

# 打包 iOS
dart run serious_python:main package backend/src \
  -p iOS \
  --asset assets/backend/app.zip \
  --requirements fastapi,uvicorn,pydantic
```

---

## 5. 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| uvicorn 不支持移动端 | 高 | 中 | 使用 Hypercorn（纯 Python ASGI）或 Flask（WSGI） |
| FastAPI 依赖链过长 | 中 | 低 | 验证 PoC，必要时简化为 Flask |
| 首次启动解压慢 | 低 | 中 | 显示加载动画，后台预解压 |
| 移动端内存不足 | 中 | 低 | 限制并发，启用内存监控 |

---

## 6. 待验证项

### PoC 1: FastAPI + uvicorn 移动端可行性

```bash
# 目标：验证 FastAPI 在 serious_python 下能否正常运行
# 步骤：
# 1. 创建最小 FastAPI app
# 2. 用 serious_python 打包
# 3. 在 Android/iOS 真机测试
# 预期结果：/api/health 返回 200
```

### PoC 2: 桌面端进程生命周期

```bash
# 目标：验证 PyInstaller 打包 + subprocess 管理
# 步骤：
# 1. PyInstaller 打包 FastAPI 后端
# 2. Flutter 启动时 spawn
# 3. Flutter 关闭时 graceful shutdown
# 预期结果：进程正确启动/关闭，无僵尸进程
```

---

## 7. 实施阶段

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **Phase A** | PoC 验证 | 无 |
| **Phase B** | 桌面端集成 | Phase A |
| **Phase C** | 移动端集成 | Phase A |
| **Phase D** | UI 集成（设置页面）| Phase B, C |
| **Phase E** | 测试与优化 | Phase D |

---

## 相关文档

- [IMPLEMENTATION_PLAN.md](../llm-backend-migration/IMPLEMENTATION_PLAN.md) - 原始后端迁移计划
- [IMPLEMENTATION_ARCHIVE.md](../llm-backend-migration/IMPLEMENTATION_ARCHIVE.md) - 已完成的实现
- [serious_python README](https://github.com/flet-dev/serious-python) - 官方文档
