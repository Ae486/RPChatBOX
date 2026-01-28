# M3: Worker Isolate 技术规格

> 状态：规划中
>
> 最后更新：2026-01-19

---

## 0. 概述

M3 Worker Isolate 实现后台 LLM Agent 任务处理，确保 UI 线程不被阻塞。

### 0.1 核心目标

| 目标 | 描述 |
|------|------|
| UI 不卡顿 | 所有 LLM 调用在 Worker Isolate 执行 |
| 写入隔离 | Main Isolate 是唯一 Hive 写入者 |
| 版本安全 | 过期任务自动丢弃 |
| 崩溃恢复 | Worker 崩溃后自动重启 |

### 0.2 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Isolate                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ UI + Streaming + Hive 写入（单一写入者）                  │   │
│  │ - RpMemoryRepository (write)                            │   │
│  │ - RpConsistencyGate (light validators)                  │   │
│  │ - RpContextCompiler                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                    SendPort/ReceivePort                         │
│                       JSON UTF-8 序列化                          │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                        Worker Isolate                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LLM Agents + JSON 解析 + 评分计算                        │   │
│  │ - 只读访问内存快照                                        │   │
│  │ - 返回 Proposals (不直接写入)                            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 文件结构

```
lib/services/roleplay/worker/
├── rp_worker_host.dart           # Main Isolate 侧的 Worker 管理器
├── rp_worker_entry.dart          # Worker Isolate 入口点
├── rp_task_scheduler.dart        # 任务调度器
├── rp_task_spec.dart             # 任务规格定义
├── rp_worker_protocol.dart       # 通信协议定义
├── rp_version_gate.dart          # 版本闸门
└── rp_memory_snapshot.dart       # 只读内存快照
```

---

## 2. 通信协议

### 2.1 协议 Envelope (统一消息格式)

所有消息使用统一的 envelope 格式，便于路由和版本兼容：

```dart
/// 协议 Envelope
class RpWorkerEnvelope {
  /// 消息类型: request | response | control
  final String type;

  /// 协议版本号
  final int schemaVersion;

  /// 消息载荷
  final Map<String, dynamic> payload;
}
```

**版本兼容策略**：
- `schemaVersion` 当前为 `1`
- Worker 收到高版本消息时，尝试降级解析；无法解析则返回错误
- Main 收到高版本响应时，记录警告并尝试解析

### 2.2 请求消息 (Main → Worker)

```dart
/// Worker 请求消息
/// Envelope: { type: "request", schemaVersion: 1, payload: RpWorkerRequest }
class RpWorkerRequest {
  /// 请求唯一标识
  final String requestId;

  /// 故事 ID
  final String storyId;

  /// 分支 ID
  final String branchId;

  /// 对话源版本号
  final int sourceRev;

  /// Foundation 版本号
  final int foundationRev;

  /// Story 版本号
  final int storyRev;

  /// 要执行的任务列表
  final List<String> tasks;

  /// 任务输入数据
  final Map<String, dynamic> inputs;

  /// 内存快照数据 (序列化的 Entry 数据)
  final Map<String, dynamic> memorySnapshot;

  /// 创建时间戳
  final int createdAtMs;

  /// 超时时间 (毫秒)
  final int timeoutMs;
}
```

### 2.3 响应消息 (Worker → Main)

```dart
/// Worker 响应消息
/// Envelope: { type: "response", schemaVersion: 1, payload: RpWorkerResponse }
class RpWorkerResponse {
  /// 对应的请求 ID
  final String requestId;

  /// 是否成功
  final bool ok;

  /// 错误信息 (ok=false 时)
  final String? error;

  /// 错误堆栈 (ok=false 时，可选)
  final String? stackTrace;

  /// 生成的提议列表
  final List<Map<String, dynamic>> proposals;

  /// 执行日志
  final List<Map<String, dynamic>> logs;

  /// 性能指标
  final RpWorkerMetrics metrics;
}

/// 性能指标
class RpWorkerMetrics {
  final int durationMs;
  final int llmCallCount;
  final int inputTokens;
  final int outputTokens;
}
```

**重要**：响应中不包含 `storyId/branchId`，通过 `requestId` 从 `_pending` map 中关联原始请求获取。

### 2.4 控制消息

```dart
/// 控制消息
/// Envelope: { type: "control", schemaVersion: 1, payload: RpWorkerControl }
class RpWorkerControl {
  /// 控制类型
  final String controlType;

  /// 相关数据
  final Map<String, dynamic>? data;
}

/// 控制类型常量
abstract class RpWorkerControlType {
  /// 初始化完成，data 包含 sendPort
  static const ready = 'ready';

  /// 取消指定任务，data.requestId 为目标
  static const cancel = 'cancel';

  /// 关闭 Worker
  static const shutdown = 'shutdown';

  /// 心跳
  static const ping = 'ping';

  /// 心跳响应
  static const pong = 'pong';
}
```

### 2.5 取消消息规范

```dart
// Main → Worker: 取消请求
{
  "type": "control",
  "schemaVersion": 1,
  "payload": {
    "controlType": "cancel",
    "data": { "requestId": "xxx" }
  }
}
```

Worker 收到后应：
1. 检查 `requestId` 是否在处理中
2. 尝试中断当前 LLM 调用（best-effort）
3. 不发送响应（已取消的请求不需要响应）

### 2.6 序列化策略

- 使用 JSON UTF-8 编码
- 大对象使用 `TransferableTypedData` 优化
- 避免传输 Hive 对象（不可跨 Isolate）
- 内存快照体积上限：**512KB**，超过则分页或降级

---

## 3. Worker Host (Main Isolate 侧)

### 3.1 类定义

```dart
/// Worker Isolate 管理器
///
/// 职责：
/// - 管理 Worker 生命周期
/// - 序列化/反序列化消息
/// - 处理错误和重启
class RpWorkerHost {
  /// 单例
  static final RpWorkerHost instance = RpWorkerHost._();

  /// Worker Isolate 引用
  Isolate? _worker;

  /// 发送端口
  SendPort? _sendPort;

  /// 接收端口
  ReceivePort? _receivePort;

  /// 是否就绪
  bool get isReady => _sendPort != null;

  /// 待处理请求 (requestId → Completer)
  final Map<String, Completer<RpWorkerResponse>> _pending = {};

  /// 启动 Worker
  Future<void> start();

  /// 停止 Worker
  Future<void> stop();

  /// 发送请求
  Future<RpWorkerResponse> send(RpWorkerRequest request);

  /// 取消请求
  void cancel(String requestId);
}
```

### 3.2 启动流程

```dart
Future<void> start() async {
  if (_worker != null) return;

  _receivePort = ReceivePort();

  // 启动 Worker Isolate
  _worker = await Isolate.spawn(
    _workerEntryPoint,
    _receivePort!.sendPort,
    onError: _receivePort!.sendPort,
    onExit: _receivePort!.sendPort,
    errorsAreFatal: false,
  );

  // 监听消息
  _receivePort!.listen(_handleMessage);

  // 等待 Worker 就绪
  final readyCompleter = Completer<void>();
  _readyCompleter = readyCompleter;
  await readyCompleter.future.timeout(
    Duration(seconds: 10),
    onTimeout: () => throw TimeoutException('Worker 启动超时'),
  );
}
```

### 3.3 崩溃恢复

```dart
void _handleMessage(dynamic message) {
  if (message is List && message.length == 2) {
    // Isolate 错误: [error, stackTrace]
    _handleWorkerError(message[0], message[1]);
    return;
  }

  if (message == null) {
    // Isolate 退出
    _handleWorkerExit();
    return;
  }

  // 正常消息处理...
}

void _handleWorkerError(dynamic error, dynamic stackTrace) {
  log('Worker 错误: $error', name: 'RpWorkerHost');
  _completePendingWithError('Worker 崩溃: $error');
  _resetWorkerState();
}

void _handleWorkerExit() {
  log('Worker 退出', name: 'RpWorkerHost');
  _completePendingWithError('Worker 意外退出');
  _resetWorkerState();
}

/// 完成所有待处理请求（以错误结束）
void _completePendingWithError(String errorMessage) {
  for (final entry in _pending.entries) {
    entry.value.completeError(
      RpWorkerException(errorMessage),
    );
  }
  _pending.clear();
}

/// 重置 Worker 状态（懒重启）
void _resetWorkerState() {
  _worker = null;
  _sendPort = null;
  // 下次调用 send() 时自动重启
}
```

**懒重启策略**：
- Worker 崩溃/退出后不立即重启
- 下一个 `send()` 调用时自动触发 `start()`
- 上一次 in-flight 任务不重试，由调度器重新 enqueue

### 3.4 超时处理

```dart
/// 发送请求（带超时）
Future<RpWorkerResponse> send(RpWorkerRequest request) async {
  if (!isReady) {
    await start();
  }

  final completer = Completer<RpWorkerResponse>();
  _pending[request.requestId] = completer;

  // 缓存原始请求用于版本闸门验证
  _requestCache[request.requestId] = request;

  // 发送请求
  _sendPort!.send(_wrapEnvelope('request', request.toJson()));

  // 超时处理
  return completer.future.timeout(
    Duration(milliseconds: request.timeoutMs),
    onTimeout: () {
      _pending.remove(request.requestId);
      _requestCache.remove(request.requestId);

      // 发送取消消息
      cancel(request.requestId);

      throw TimeoutException(
        '任务超时: ${request.requestId}',
        Duration(milliseconds: request.timeoutMs),
      );
    },
  );
}
```

---

## 4. Task Scheduler (任务调度器)

### 4.1 任务规格

```dart
/// 任务优先级
enum RpTaskPriority {
  /// 紧急：用户主动触发
  urgent,

  /// 正常：回合结束触发
  normal,

  /// 空闲：sleeptime 维护
  idle,
}

/// 任务规格
class RpTaskSpec {
  /// 任务唯一 ID
  final String taskId;

  /// 故事 ID
  final String storyId;

  /// 分支 ID
  final String branchId;

  /// 去重键（相同键的任务会合并）
  final String dedupeKey;

  /// 优先级
  final RpTaskPriority priority;

  /// 版本要求
  final int requiredSourceRev;
  final int requiredFoundationRev;
  final int requiredStoryRev;

  /// 任务类型列表
  final List<String> tasks;

  /// 输入数据
  final Map<String, dynamic> inputs;

  /// 入队时间
  final int enqueuedAtMs;

  /// 超时时间 (毫秒)
  final int timeoutMs;
}
```

### 4.2 调度器实现

```dart
/// 任务调度器
class RpTaskScheduler {
  /// 优先队列（按优先级 + 入队时间排序，避免饥饿）
  final PriorityQueue<RpTaskSpec> _queue = PriorityQueue(
    (a, b) {
      // 先按优先级排序
      final priorityCompare = a.priority.index.compareTo(b.priority.index);
      if (priorityCompare != 0) return priorityCompare;

      // 同优先级按入队时间排序（先入先出）
      return a.enqueuedAtMs.compareTo(b.enqueuedAtMs);
    },
  );

  /// 去重映射 (dedupeKey → taskId)
  final Map<String, String> _dedupeMap = {};

  /// 当前执行中的任务
  String? _inFlightTaskId;

  /// 最大并发数
  static const int maxInFlight = 1;

  /// 最大队列长度（超过触发背压）
  static const int maxQueueSize = 10;

  /// 入队任务
  void enqueue(RpTaskSpec task);

  /// 取消任务
  void cancel(String taskId);

  /// 获取下一个任务
  RpTaskSpec? dequeue();

  /// 背压处理：丢弃低优先级任务
  void applyBackpressure(int maxQueueSize);
}
```

### 4.3 去重策略

```dart
void enqueue(RpTaskSpec task) {
  // 检查去重
  final existingTaskId = _dedupeMap[task.dedupeKey];
  if (existingTaskId != null) {
    // 移除旧任务，保留新任务（版本更新）
    _queue.removeWhere((t) => t.taskId == existingTaskId);
  }

  _dedupeMap[task.dedupeKey] = task.taskId;
  _queue.add(task);
}
```

### 4.4 背压处理

```dart
void applyBackpressure(int maxQueueSize) {
  while (_queue.length > maxQueueSize) {
    // 优先丢弃 idle 任务
    final idleTasks = _queue.where((t) => t.priority == RpTaskPriority.idle);
    if (idleTasks.isNotEmpty) {
      final toDrop = idleTasks.first;
      _queue.remove(toDrop);
      _dedupeMap.remove(toDrop.dedupeKey);
      log('背压丢弃 idle 任务: ${toDrop.taskId}', name: 'RpTaskScheduler');
      continue;
    }

    // 再丢弃 normal 任务
    final normalTasks = _queue.where((t) => t.priority == RpTaskPriority.normal);
    if (normalTasks.isNotEmpty) {
      final toDrop = normalTasks.first;
      _queue.remove(toDrop);
      _dedupeMap.remove(toDrop.dedupeKey);
      log('背压丢弃 normal 任务: ${toDrop.taskId}', name: 'RpTaskScheduler');
      continue;
    }

    // urgent 任务不丢弃
    break;
  }
}
```

---

## 5. Version Gate (版本闸门)

### 5.1 版本语义定义

| 版本号 | 含义 | 比较对象 |
|--------|------|----------|
| `sourceRev` | 对话版本号（消息树变化递增） | `meta.sourceRev` |
| `foundationRev` | Foundation scope 的操作版本号 | `foundationHead.rev` |
| `storyRev` | Story scope 的操作版本号 | `storyHead.rev` |

**Foundation branchId 约定**：
- Foundation 是跨分支共享的，使用固定 `branchId = "-"`
- 获取 foundation head 时使用 `meta.getHead(RpScope.foundation.index, "-")`

### 5.2 版本验证

```dart
/// 版本闸门
class RpVersionGate {
  /// Foundation 的固定 branchId
  static const String foundationBranchId = '-';

  /// 验证任务是否过期
  static bool isTaskStale(RpTaskSpec task, RpStoryMeta currentMeta) {
    // 1. 检查 sourceRev（对话版本）
    if (task.requiredSourceRev < currentMeta.sourceRev) {
      return true; // 对话已更新，任务过期
    }

    // 2. 检查 foundation rev（使用固定 branchId）
    final foundationHead = currentMeta.getHead(
      RpScope.foundation.index,
      foundationBranchId,
    );
    if (foundationHead != null &&
        task.requiredFoundationRev < foundationHead.rev) {
      return true;
    }

    // 3. 检查 story rev（使用任务的 branchId）
    final storyHead = currentMeta.getHead(
      RpScope.story.index,
      task.branchId,
    );
    if (storyHead != null &&
        task.requiredStoryRev < storyHead.rev) {
      return true;
    }

    return false;
  }

  /// 验证响应是否过期
  static bool isResponseStale(
    RpWorkerResponse response,
    RpWorkerRequest originalRequest,
    RpStoryMeta currentMeta,
  ) {
    // 从原始请求构造验证参数
    return _isStale(
      sourceRev: originalRequest.sourceRev,
      foundationRev: originalRequest.foundationRev,
      storyRev: originalRequest.storyRev,
      branchId: originalRequest.branchId,
      currentMeta: currentMeta,
    );
  }

  static bool _isStale({
    required int sourceRev,
    required int foundationRev,
    required int storyRev,
    required String branchId,
    required RpStoryMeta currentMeta,
  }) {
    if (sourceRev < currentMeta.sourceRev) return true;

    final foundationHead = currentMeta.getHead(
      RpScope.foundation.index,
      foundationBranchId,
    );
    if (foundationHead != null && foundationRev < foundationHead.rev) {
      return true;
    }

    final storyHead = currentMeta.getHead(RpScope.story.index, branchId);
    if (storyHead != null && storyRev < storyHead.rev) {
      return true;
    }

    return false;
  }
}
```

### 5.3 过期处理策略

| 场景 | 处理 |
|------|------|
| 任务入队时过期 | 直接丢弃，不入队 |
| 任务出队时过期 | 丢弃，取下一个 |
| 响应返回时过期 | 丢弃响应，记录日志 |
| Worker 处理中版本变化 | Worker 完成后在 Main 侧检查 |

---

## 6. Memory Snapshot (内存快照)

### 6.1 快照创建

Worker 需要的数据通过快照传递，而非直接访问 Hive。

```dart
/// 创建 Worker 所需的内存快照
class RpMemorySnapshotBuilder {
  final RpMemoryRepository _repo;

  /// 构建快照
  Future<Map<String, dynamic>> build({
    required String storyId,
    required String branchId,
    required List<String> requiredDomains,
  }) async {
    final snapshot = <String, dynamic>{};

    // 获取 StoryMeta
    final meta = await _repo.getStoryMeta(storyId);
    if (meta == null) return snapshot;

    snapshot['meta'] = _serializeMeta(meta);

    // 获取相关 Entries
    final entries = <String, dynamic>{};
    for (final domain in requiredDomains) {
      final domainEntries = await _getEntriesByDomain(
        storyId, branchId, domain,
      );
      entries[domain] = domainEntries;
    }
    snapshot['entries'] = entries;

    return snapshot;
  }

  Map<String, dynamic> _serializeMeta(RpStoryMeta meta) {
    return {
      'storyId': meta.storyId,
      'activeBranchId': meta.activeBranchId,
      'sourceRev': meta.sourceRev,
      // ... 其他字段
    };
  }
}
```

### 6.2 Worker 侧读取

```dart
/// Worker 侧的只读内存访问
class RpWorkerMemoryReader {
  final Map<String, dynamic> _snapshot;

  RpWorkerMemoryReader(this._snapshot);

  /// 获取指定 domain 的 entries
  List<Map<String, dynamic>> getEntriesByDomain(String domain) {
    final entries = _snapshot['entries'] as Map<String, dynamic>?;
    if (entries == null) return [];
    return (entries[domain] as List?)?.cast<Map<String, dynamic>>() ?? [];
  }

  /// 获取 meta 信息
  Map<String, dynamic>? get meta =>
    _snapshot['meta'] as Map<String, dynamic>?;
}
```

---

## 7. Worker Entry Point

### 7.1 入口函数

```dart
/// Worker Isolate 入口点
///
/// 必须是顶层函数或静态方法
@pragma('vm:entry-point')
void rpWorkerEntryPoint(SendPort mainSendPort) {
  final receivePort = ReceivePort();

  // 发送 Worker 的 SendPort 给 Main
  mainSendPort.send({
    'type': 'ready',
    'sendPort': receivePort.sendPort,
  });

  // 监听请求
  receivePort.listen((message) {
    _handleMessage(message, mainSendPort);
  });
}

void _handleMessage(dynamic message, SendPort mainSendPort) {
  if (message is Map<String, dynamic>) {
    final type = message['type'] as String?;

    switch (type) {
      case 'request':
        _handleRequest(message, mainSendPort);
        break;
      case 'cancel':
        _handleCancel(message);
        break;
      case 'shutdown':
        Isolate.exit();
        break;
      case 'ping':
        mainSendPort.send({'type': 'pong'});
        break;
    }
  }
}
```

### 7.2 请求处理

```dart
Future<void> _handleRequest(
  Map<String, dynamic> message,
  SendPort mainSendPort,
) async {
  final requestId = message['requestId'] as String;
  final startTime = DateTime.now().millisecondsSinceEpoch;

  try {
    // 解析请求
    final request = RpWorkerRequest.fromJson(message);

    // 创建内存读取器
    final memoryReader = RpWorkerMemoryReader(request.memorySnapshot);

    // 执行任务
    final proposals = <Map<String, dynamic>>[];
    final logs = <Map<String, dynamic>>[];

    for (final taskType in request.tasks) {
      final result = await _executeTask(
        taskType,
        request,
        memoryReader,
      );
      proposals.addAll(result.proposals);
      logs.addAll(result.logs);
    }

    // 发送响应
    final endTime = DateTime.now().millisecondsSinceEpoch;
    mainSendPort.send({
      'type': 'response',
      'requestId': requestId,
      'ok': true,
      'proposals': proposals,
      'logs': logs,
      'metrics': {
        'durationMs': endTime - startTime,
        'llmCallCount': _llmCallCount,
        'inputTokens': _inputTokens,
        'outputTokens': _outputTokens,
      },
    });
  } catch (e, stackTrace) {
    mainSendPort.send({
      'type': 'response',
      'requestId': requestId,
      'ok': false,
      'error': e.toString(),
      'stackTrace': stackTrace.toString(),
      'proposals': [],
      'logs': [],
      'metrics': {
        'durationMs': DateTime.now().millisecondsSinceEpoch - startTime,
      },
    });
  }
}
```

---

## 8. 集成点

### 8.1 与 Orchestrator 集成

```dart
/// 调度器在每轮对话结束后调用
class RpOrchestrator {
  final RpWorkerHost _workerHost;
  final RpTaskScheduler _scheduler;
  final RpMemoryRepository _repo;

  /// 调度后台任务
  Future<void> scheduleBackgroundTasks({
    required String storyId,
    required String branchId,
    required int sourceRev,
    required List<String> suggestedTasks,
  }) async {
    final meta = await _repo.getStoryMeta(storyId);
    if (meta == null) return;

    final foundationHead = meta.getHead(RpScope.foundation.index, branchId);
    final storyHead = meta.getHead(RpScope.story.index, branchId);

    final task = RpTaskSpec(
      taskId: Ulid().toString(),
      storyId: storyId,
      branchId: branchId,
      dedupeKey: '$storyId|$branchId|background',
      priority: RpTaskPriority.normal,
      requiredSourceRev: sourceRev,
      requiredFoundationRev: foundationHead?.rev ?? 0,
      requiredStoryRev: storyHead?.rev ?? 0,
      tasks: suggestedTasks,
      inputs: {},
      enqueuedAtMs: DateTime.now().millisecondsSinceEpoch,
      timeoutMs: 30000,
    );

    // 版本闸门检查
    if (RpVersionGate.isTaskStale(task, meta)) {
      log('任务已过期，跳过: ${task.taskId}', name: 'RpOrchestrator');
      return;
    }

    _scheduler.enqueue(task);
    _processQueue();
  }
}
```

### 8.2 与 ProposalApplier 集成

```dart
/// 处理 Worker 响应
///
/// 注意：响应中不包含 storyId/branchId，需从 _requestCache 获取原始请求
Future<void> _handleWorkerResponse(RpWorkerResponse response) async {
  // 从缓存获取原始请求
  final originalRequest = _requestCache[response.requestId];
  if (originalRequest == null) {
    log('未找到原始请求: ${response.requestId}', name: 'RpOrchestrator');
    return;
  }

  // 清理缓存
  _requestCache.remove(response.requestId);

  if (!response.ok) {
    log('Worker 任务失败: ${response.error}', name: 'RpOrchestrator');
    return;
  }

  final meta = await _repo.getStoryMeta(originalRequest.storyId);
  if (meta == null) return;

  // 版本闸门检查（使用原始请求的版本信息）
  if (RpVersionGate.isResponseStale(response, originalRequest, meta)) {
    log('响应已过期，丢弃', name: 'RpOrchestrator');
    return;
  }

  // 转换为 RpProposal 并保存
  for (final proposalJson in response.proposals) {
    final proposal = RpProposal.fromJson(proposalJson);
    await _repo.saveProposal(proposal);

    // 根据 policyTier 处理
    if (proposal.policyTierIndex == RpPolicyTier.silent.index) {
      // 静默应用
      await _proposalApplier.apply(proposal);
    } else if (proposal.policyTierIndex == RpPolicyTier.notifyApply.index) {
      // 通知并应用
      _notifyUser(proposal);
      await _proposalApplier.apply(proposal);
    } else {
      // 需要用户审核
      _notifyUserForReview(proposal);
    }
  }
}
```

---

## 9. 测试策略

### 9.1 单元测试

| 测试场景 | 验收标准 |
|----------|----------|
| Worker 启动/停止 | 正确管理生命周期 |
| 消息序列化/反序列化 | JSON 往返正确 |
| 版本闸门 | 过期任务正确识别 |
| 任务调度 | 优先级排序正确 |
| 去重逻辑 | 相同 dedupeKey 合并 |
| 背压处理 | 低优先级任务正确丢弃 |

### 9.2 集成测试

| 测试场景 | 验收标准 |
|----------|----------|
| 完整请求-响应流程 | 端到端正确 |
| Worker 崩溃恢复 | 自动重启，请求不丢失 |
| 高频任务提交 | 背压机制生效 |
| 版本变化时的任务处理 | 过期任务正确丢弃 |

### 9.3 测试文件结构

```
test/unit/services/roleplay/worker/
├── rp_worker_host_test.dart
├── rp_task_scheduler_test.dart
├── rp_version_gate_test.dart
├── rp_worker_protocol_test.dart
└── rp_memory_snapshot_test.dart
```

---

## 10. 实现计划

### 10.1 任务分解

| 阶段 | 任务 | 输出 |
|------|------|------|
| 1 | 通信协议定义 | `rp_worker_protocol.dart` |
| 2 | Worker Host 实现 | `rp_worker_host.dart` |
| 3 | Worker Entry 实现 | `rp_worker_entry.dart` |
| 4 | Task Scheduler 实现 | `rp_task_scheduler.dart`, `rp_task_spec.dart` |
| 5 | Version Gate 实现 | `rp_version_gate.dart` |
| 6 | Memory Snapshot 实现 | `rp_memory_snapshot.dart` |
| 7 | 单元测试 | `test/unit/services/roleplay/worker/*.dart` |
| 8 | 集成测试 | 与 Orchestrator 集成验证 |

### 10.2 依赖关系

```
rp_worker_protocol.dart (无依赖)
        │
        ├── rp_task_spec.dart
        │
        ├── rp_version_gate.dart
        │       │
        │       └── rp_task_scheduler.dart
        │
        ├── rp_memory_snapshot.dart
        │
        └── rp_worker_entry.dart
                │
                └── rp_worker_host.dart
```

---

## 11. UI 集成规范

### 11.1 设计原则

**核心理念：非侵入式感知**

Worker 是幕后执行者，UI 设计应遵循：
- 只在产出有价值结果或响应用户主动请求时才显现
- 避免让用户产生"APP 在偷跑流量/电量"的焦虑
- 后台任务失败不应干扰主聊天流程

### 11.2 Worker 状态反馈

| 状态 | UI 表现 | 对应条件 |
|------|---------|----------|
| Idle | 指示器隐藏或灰色 | `_inFlightTaskId == null && _queue.isEmpty` |
| Working | 微弱呼吸动画 | `_inFlightTaskId != null` |
| Disconnected | 红色警告（仅开发模式） | `_worker == null && 重试失败` |

**建议实现**：
```dart
/// Worker 状态枚举（供 UI 使用）
enum RpWorkerUiStatus {
  idle,
  working,
  disconnected,
}

/// 状态通知器
class RpWorkerStatusNotifier extends ValueNotifier<RpWorkerUiStatus> {
  RpWorkerStatusNotifier() : super(RpWorkerUiStatus.idle);

  void updateStatus({
    required bool hasWorker,
    required bool hasInFlight,
    required bool hasQueue,
  }) {
    if (!hasWorker) {
      value = RpWorkerUiStatus.disconnected;
    } else if (hasInFlight || hasQueue) {
      value = RpWorkerUiStatus.working;
    } else {
      value = RpWorkerUiStatus.idle;
    }
  }
}
```

**UI 组件位置**：输入框右下角或顶部状态栏的微小图标（如"大脑"或"火花"）

### 11.3 Proposal 审核 UX

**异步"灵感气泡"机制**：

当 Worker 返回 `policyTierIndex == reviewRequired` 的 Proposal 时：

1. **不弹模态对话框** - 避免打断用户
2. **显示非侵入式通知** - 在输入框上方或侧边栏显示可点击的"灵感气泡"
3. **时效性标记** - 基于 `RpVersionGate` 逻辑，旧建议标记为"可能过时"

```dart
/// Proposal 通知数据
class RpProposalNotification {
  final String proposalId;
  final String summary;      // 如 "检测到 2 个状态更新建议"
  final String source;       // 任务类型：场景检测、状态更新等
  final bool isPotentiallyStale;  // 用户已进行新对话
  final DateTime createdAt;
}

/// 通知管理器
class RpProposalNotificationManager {
  final _notifications = ValueNotifier<List<RpProposalNotification>>([]);

  ValueListenable<List<RpProposalNotification>> get notifications => _notifications;

  void add(RpProposalNotification notification) {
    _notifications.value = [..._notifications.value, notification];
  }

  void markStale(int currentSourceRev) {
    _notifications.value = _notifications.value.map((n) {
      // 如果创建时的 sourceRev 小于当前值，标记为可能过时
      return n.copyWith(isPotentiallyStale: true);
    }).toList();
  }
}
```

**差异对比视图**：状态更新类建议使用并排（Side-by-Side）或红绿高亮展示修改前后的值。

### 11.4 错误状态展示

**分级错误反馈策略**：

| 优先级 | 失败时 UI | 原因 |
|--------|-----------|------|
| idle | **完全静默** | "伏笔链接提取失败"等非阻断性错误 |
| normal | **完全静默** | 回合后台任务失败不应打断用户 |
| urgent | **Toast/Snackbar** | 用户手动触发的任务需要反馈 |
| Worker 崩溃循环 | **设置页 Banner** | 避免用户对系统智能度产生怀疑 |

```dart
/// 错误反馈处理器
void handleTaskError(RpTaskPriority priority, String error) {
  switch (priority) {
    case RpTaskPriority.idle:
    case RpTaskPriority.normal:
      // 静默记录到日志
      log('后台任务失败（静默）: $error', name: 'RpWorker');
      break;
    case RpTaskPriority.urgent:
      // 用户可见的友好提示
      showSnackbar('无法完成一致性分析，请稍后重试', action: '重试');
      break;
  }
}
```

### 11.5 后台任务进度指示

**克制设计原则**：

| 场景 | UI 表现 |
|------|---------|
| 常规任务 | 仅"思维活跃度"呼吸动画，无具体进度 |
| 长任务（队列 > 5 或 summarize） | 极细线性进度条，不显示百分比 |
| 任务被丢弃（背压/版本过期） | **无感** - 无任何 UI 跳动或报错 |

```dart
/// 进度指示器显示逻辑
bool shouldShowLinearProgress(RpTaskScheduler scheduler) {
  // 队列积压超过阈值
  if (scheduler.queueLength > 5) return true;

  // 正在处理长时间任务
  final currentTask = scheduler.currentTask;
  if (currentTask != null && currentTask.tasks.contains('summarize')) {
    return true;
  }

  return false;
}
```

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Isolate 通信开销 | 性能 | 使用 TransferableTypedData；批量传输 |
| Worker 崩溃 | 可用性 | 懒重启；优雅降级（跳过后台任务） |
| 内存快照过大 | 性能 | 只传输必要 domains；增量更新 |
| 版本竞争 | 正确性 | 版本闸门严格检查 |

---

## 附录 A: 任务类型定义

| 任务类型 | 描述 | 优先级 |
|----------|------|--------|
| `scene_detect` | 场景检测 | normal |
| `state_update` | 状态更新 | normal |
| `key_event_extract` | 关键事件提取 | normal |
| `consistency_heavy` | 重量闸门检测 | urgent |
| `foreshadow_link` | 伏笔链接 | idle |
| `goals_update` | 目标更新 | idle |
| `summarize` | 摘要压缩 | idle |
| `edit_interpret` | 编辑解释 | normal |

---

## 附录 B: 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-19 | 初版规格 |
| 1.1 | 2026-01-20 | 多模型评审修订：协议 envelope、崩溃恢复、版本闸门语义、UI 集成规范 |
