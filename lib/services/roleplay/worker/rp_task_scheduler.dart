/// 任务调度器
///
/// 管理后台任务队列，支持优先级排序、去重和背压处理
/// POS: Services / Roleplay / Worker
library;

import 'dart:collection';
import 'dart:developer';

import 'rp_task_spec.dart';

/// 任务调度器
///
/// 职责：
/// - 管理待执行任务队列
/// - 按优先级+入队时间排序（避免饥饿）
/// - 去重（相同 dedupeKey 合并）
/// - 背压处理（队列满时丢弃低优先级任务）
class RpTaskScheduler {
  /// 优先队列（按优先级 + 入队时间排序）
  final SplayTreeSet<RpTaskSpec> _queue;

  /// 去重映射 (dedupeKey → taskId)
  final Map<String, String> _dedupeMap = {};

  /// 任务映射 (taskId → task)
  final Map<String, RpTaskSpec> _taskMap = {};

  /// 当前执行中的任务 ID
  String? _inFlightTaskId;

  /// 最大队列长度（超过触发背压）
  final int maxQueueSize;

  /// 创建调度器
  RpTaskScheduler({
    this.maxQueueSize = 10,
  }) : _queue = SplayTreeSet<RpTaskSpec>(_compareTask);

  /// 任务比较器：先按优先级，再按入队时间
  static int _compareTask(RpTaskSpec a, RpTaskSpec b) {
    // 先按优先级排序（urgent < normal < idle）
    final priorityCompare = a.priority.index.compareTo(b.priority.index);
    if (priorityCompare != 0) return priorityCompare;

    // 同优先级按入队时间排序（先入先出）
    final timeCompare = a.enqueuedAtMs.compareTo(b.enqueuedAtMs);
    if (timeCompare != 0) return timeCompare;

    // 最后用 taskId 保证唯一性
    return a.taskId.compareTo(b.taskId);
  }

  /// 当前队列长度
  int get queueLength => _queue.length;

  /// 是否有执行中的任务
  bool get hasInFlight => _inFlightTaskId != null;

  /// 当前执行中的任务
  RpTaskSpec? get currentTask =>
      _inFlightTaskId != null ? _taskMap[_inFlightTaskId] : null;

  /// 队列是否为空
  bool get isEmpty => _queue.isEmpty;

  /// 是否需要背压处理
  bool get needsBackpressure => _queue.length > maxQueueSize;

  /// 入队任务
  ///
  /// 自动处理去重和背压
  void enqueue(RpTaskSpec task) {
    // 检查去重
    final existingTaskId = _dedupeMap[task.dedupeKey];
    if (existingTaskId != null && existingTaskId != task.taskId) {
      // 移除旧任务，保留新任务（版本更新）
      _removeTask(existingTaskId);
      log(
        '去重替换任务: ${task.dedupeKey}',
        name: 'RpTaskScheduler',
      );
    }

    // 添加新任务
    _dedupeMap[task.dedupeKey] = task.taskId;
    _taskMap[task.taskId] = task;
    _queue.add(task);

    log(
      '入队任务: ${task.taskId}, priority=${task.priority}, queue=${_queue.length}',
      name: 'RpTaskScheduler',
    );

    // 检查背压
    if (needsBackpressure) {
      applyBackpressure();
    }
  }

  /// 出队任务（获取下一个待执行任务）
  ///
  /// 返回 null 表示队列为空或已有任务执行中
  RpTaskSpec? dequeue() {
    if (_queue.isEmpty) return null;
    if (_inFlightTaskId != null) return null;

    final task = _queue.first;
    _queue.remove(task);
    _inFlightTaskId = task.taskId;

    log(
      '出队任务: ${task.taskId}, remaining=${_queue.length}',
      name: 'RpTaskScheduler',
    );

    return task;
  }

  /// 标记任务完成
  void complete(String taskId) {
    if (_inFlightTaskId == taskId) {
      _inFlightTaskId = null;
      log('任务完成: $taskId', name: 'RpTaskScheduler');
    }

    // 清理映射
    final task = _taskMap.remove(taskId);
    if (task != null) {
      _dedupeMap.remove(task.dedupeKey);
    }
  }

  /// 取消任务
  void cancel(String taskId) {
    // 如果是执行中的任务
    if (_inFlightTaskId == taskId) {
      _inFlightTaskId = null;
      log('取消执行中任务: $taskId', name: 'RpTaskScheduler');
    }

    _removeTask(taskId);
  }

  /// 移除任务（内部方法）
  void _removeTask(String taskId) {
    final task = _taskMap.remove(taskId);
    if (task != null) {
      _queue.remove(task);
      _dedupeMap.remove(task.dedupeKey);
    }
  }

  /// 背压处理：丢弃低优先级任务
  ///
  /// 丢弃策略：idle → normal → 保留 urgent
  void applyBackpressure() {
    while (_queue.length > maxQueueSize) {
      // 优先丢弃 idle 任务（从队尾找）
      final idleTask = _findLowestPriorityTask(RpTaskPriority.idle);
      if (idleTask != null) {
        _removeTask(idleTask.taskId);
        log(
          '背压丢弃 idle 任务: ${idleTask.taskId}',
          name: 'RpTaskScheduler',
        );
        continue;
      }

      // 再丢弃 normal 任务
      final normalTask = _findLowestPriorityTask(RpTaskPriority.normal);
      if (normalTask != null) {
        _removeTask(normalTask.taskId);
        log(
          '背压丢弃 normal 任务: ${normalTask.taskId}',
          name: 'RpTaskScheduler',
        );
        continue;
      }

      // urgent 任务不丢弃
      log(
        '背压：队列仅剩 urgent 任务，停止丢弃',
        name: 'RpTaskScheduler',
      );
      break;
    }
  }

  /// 查找指定优先级的最旧任务（用于背压丢弃）
  RpTaskSpec? _findLowestPriorityTask(RpTaskPriority priority) {
    // 反向遍历找最旧的（入队时间最早）
    RpTaskSpec? oldest;
    for (final task in _queue) {
      if (task.priority == priority) {
        if (oldest == null || task.enqueuedAtMs < oldest.enqueuedAtMs) {
          oldest = task;
        }
      }
    }
    return oldest;
  }

  /// 清空队列
  void clear() {
    _queue.clear();
    _dedupeMap.clear();
    _taskMap.clear();
    _inFlightTaskId = null;
    log('队列已清空', name: 'RpTaskScheduler');
  }

  /// 获取队列快照（用于调试/UI）
  List<RpTaskSpec> get queueSnapshot => _queue.toList();

  /// 获取队列统计信息
  RpSchedulerStats get stats {
    int urgent = 0, normal = 0, idle = 0;
    for (final task in _queue) {
      switch (task.priority) {
        case RpTaskPriority.urgent:
          urgent++;
        case RpTaskPriority.normal:
          normal++;
        case RpTaskPriority.idle:
          idle++;
      }
    }
    return RpSchedulerStats(
      total: _queue.length,
      urgent: urgent,
      normal: normal,
      idle: idle,
      hasInFlight: hasInFlight,
    );
  }

  /// 按故事 ID 移除所有任务
  void removeByStoryId(String storyId) {
    // 先检查 in-flight 任务（在 _taskMap 被修改前）
    if (_inFlightTaskId != null) {
      final inFlight = _taskMap[_inFlightTaskId];
      if (inFlight?.storyId == storyId) {
        _inFlightTaskId = null;
      }
    }

    final toRemove = _taskMap.values
        .where((t) => t.storyId == storyId)
        .map((t) => t.taskId)
        .toList();

    for (final taskId in toRemove) {
      _removeTask(taskId);
    }

    log(
      '移除故事 $storyId 的 ${toRemove.length} 个任务',
      name: 'RpTaskScheduler',
    );
  }
}

/// 调度器统计信息
class RpSchedulerStats {
  final int total;
  final int urgent;
  final int normal;
  final int idle;
  final bool hasInFlight;

  const RpSchedulerStats({
    required this.total,
    required this.urgent,
    required this.normal,
    required this.idle,
    required this.hasInFlight,
  });

  @override
  String toString() =>
      'RpSchedulerStats(total=$total, urgent=$urgent, normal=$normal, idle=$idle, inFlight=$hasInFlight)';
}
