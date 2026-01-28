/// Sleeptime 管理器
///
/// 管理后台维护任务
/// POS: Services / Roleplay / Worker / Idle
library;

import 'dart:async';
import 'idle_detector.dart';
import '../rp_task_scheduler.dart';
import '../rp_task_spec.dart';

/// 后台维护任务类型
enum IdleTaskType {
  /// 摘要压缩
  summarize,

  /// 伏笔链接刷新
  foreshadowRefresh,

  /// 目标清理
  goalCleanup,

  /// Memory GC
  memoryGc,
}

/// 空闲任务
class IdleTask {
  final IdleTaskType type;
  final Map<String, dynamic> params;
  final DateTime createdAt;

  IdleTask({
    required this.type,
    this.params = const {},
    DateTime? createdAt,
  }) : createdAt = createdAt ?? DateTime.now();

  Map<String, dynamic> toJson() => {
        'type': type.name,
        'params': params,
        'createdAt': createdAt.toIso8601String(),
      };

  /// 转换为 RpTaskSpec
  RpTaskSpec toTaskSpec({
    required String storyId,
    required String branchId,
    required int sourceRev,
    required int foundationRev,
    required int storyRev,
  }) {
    final taskType = switch (type) {
      IdleTaskType.summarize => RpTaskType.summarize,
      IdleTaskType.foreshadowRefresh => RpTaskType.foreshadowLink,
      IdleTaskType.goalCleanup => RpTaskType.goalsUpdate,
      IdleTaskType.memoryGc => RpTaskType.summarize, // GC 复用 summarize
    };

    return RpTaskSpec(
      taskId: '${DateTime.now().millisecondsSinceEpoch}_idle',
      storyId: storyId,
      branchId: branchId,
      dedupeKey: '$storyId|$branchId|idle|${type.name}',
      priority: RpTaskPriority.idle,
      requiredSourceRev: sourceRev,
      requiredFoundationRev: foundationRev,
      requiredStoryRev: storyRev,
      tasks: [taskType],
      inputs: params,
    );
  }
}

/// 任务入队回调
typedef TaskEnqueueCallback = void Function(IdleTask task);

/// Sleeptime 管理器
class SleeptimeManager {
  final IdleDetector _idleDetector;
  final TaskEnqueueCallback? _onEnqueue;
  final RpTaskScheduler? _scheduler;

  Timer? _ticker;
  final Duration _tickInterval;

  /// 当前故事上下文
  String? _currentStoryId;
  String? _currentBranchId;
  int _sourceRev = 0;
  int _foundationRev = 0;
  int _storyRev = 0;

  /// 待处理任务标记
  final Set<IdleTaskType> _pendingTasks = {};

  /// 已完成任务时间戳
  final Map<IdleTaskType, DateTime> _lastCompleted = {};

  /// 任务最小间隔
  final Duration _taskMinInterval;

  SleeptimeManager({
    IdleDetector? idleDetector,
    TaskEnqueueCallback? onEnqueue,
    RpTaskScheduler? scheduler,
    Duration tickInterval = const Duration(seconds: 10),
    Duration taskMinInterval = const Duration(minutes: 5),
  })  : _idleDetector = idleDetector ?? IdleDetector(),
        _onEnqueue = onEnqueue,
        _scheduler = scheduler,
        _tickInterval = tickInterval,
        _taskMinInterval = taskMinInterval;

  /// 设置当前故事上下文
  void setContext({
    required String storyId,
    required String branchId,
    required int sourceRev,
    required int foundationRev,
    required int storyRev,
  }) {
    _currentStoryId = storyId;
    _currentBranchId = branchId;
    _sourceRev = sourceRev;
    _foundationRev = foundationRev;
    _storyRev = storyRev;
  }

  /// 启动
  void start() {
    _idleDetector.start();
    _ticker?.cancel();
    _ticker = Timer.periodic(_tickInterval, (_) => _tick());
  }

  /// 停止
  void stop() {
    _ticker?.cancel();
    _ticker = null;
    _idleDetector.stop();
  }

  /// 标记任务待处理
  void markPending(IdleTaskType type) {
    _pendingTasks.add(type);
  }

  /// 标记任务完成
  void markCompleted(IdleTaskType type) {
    _pendingTasks.remove(type);
    _lastCompleted[type] = DateTime.now();
  }

  /// 定时检查
  void _tick() {
    if (!_idleDetector.isIdle) return;

    // 获取可执行的任务
    final task = _getNextTask();
    if (task == null) return;

    // 入队到调度器
    if (_scheduler != null && _currentStoryId != null && _currentBranchId != null) {
      final taskSpec = task.toTaskSpec(
        storyId: _currentStoryId!,
        branchId: _currentBranchId!,
        sourceRev: _sourceRev,
        foundationRev: _foundationRev,
        storyRev: _storyRev,
      );
      _scheduler.enqueue(taskSpec);
    }

    // 回调
    _onEnqueue?.call(task);
  }

  /// 获取下一个可执行任务
  IdleTask? _getNextTask() {
    final now = DateTime.now();

    // 按优先级检查
    for (final type in IdleTaskType.values) {
      if (!_pendingTasks.contains(type)) continue;

      // 检查最小间隔
      final lastTime = _lastCompleted[type];
      if (lastTime != null && now.difference(lastTime) < _taskMinInterval) {
        continue;
      }

      return IdleTask(type: type);
    }

    return null;
  }

  /// 获取空闲检测器
  IdleDetector get idleDetector => _idleDetector;

  /// 是否正在运行
  bool get isRunning => _ticker != null;

  /// 待处理任务数
  int get pendingCount => _pendingTasks.length;
}
