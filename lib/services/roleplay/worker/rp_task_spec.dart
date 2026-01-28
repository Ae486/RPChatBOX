/// Worker 任务规格定义
///
/// 定义后台任务的规格、优先级和去重策略
/// POS: Services / Roleplay / Worker
library;

/// 任务优先级
enum RpTaskPriority {
  /// 紧急：用户主动触发（如手动一致性检查）
  urgent,

  /// 正常：回合结束触发（如场景检测、状态更新）
  normal,

  /// 空闲：sleeptime 维护（如伏笔链接、摘要压缩）
  idle,
}

/// 任务类型常量
abstract class RpTaskType {
  /// 场景检测
  static const String sceneDetect = 'scene_detect';

  /// 状态更新
  static const String stateUpdate = 'state_update';

  /// 关键事件提取
  static const String keyEventExtract = 'key_event_extract';

  /// 重量闸门检测（需要 LLM）
  static const String consistencyHeavy = 'consistency_heavy';

  /// 伏笔链接
  static const String foreshadowLink = 'foreshadow_link';

  /// 目标更新
  static const String goalsUpdate = 'goals_update';

  /// 摘要压缩
  static const String summarize = 'summarize';

  /// 编辑解释
  static const String editInterpret = 'edit_interpret';

  /// 获取任务默认优先级
  static RpTaskPriority getDefaultPriority(String taskType) {
    switch (taskType) {
      case consistencyHeavy:
        return RpTaskPriority.urgent;
      case sceneDetect:
      case stateUpdate:
      case keyEventExtract:
      case editInterpret:
        return RpTaskPriority.normal;
      case foreshadowLink:
      case goalsUpdate:
      case summarize:
        return RpTaskPriority.idle;
      default:
        return RpTaskPriority.normal;
    }
  }

  /// 获取任务默认超时时间（毫秒）
  static int getDefaultTimeout(String taskType) {
    switch (taskType) {
      case summarize:
        return 60000; // 1 分钟
      case consistencyHeavy:
        return 45000; // 45 秒
      case sceneDetect:
      case stateUpdate:
        return 30000; // 30 秒
      default:
        return 30000;
    }
  }
}

/// 任务规格
///
/// 描述一个待执行的后台任务
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

  /// 版本要求：对话源版本号
  final int requiredSourceRev;

  /// 版本要求：Foundation 版本号
  final int requiredFoundationRev;

  /// 版本要求：Story 版本号
  final int requiredStoryRev;

  /// 任务类型列表
  final List<String> tasks;

  /// 输入数据
  final Map<String, dynamic> inputs;

  /// 入队时间戳
  final int enqueuedAtMs;

  /// 超时时间 (毫秒)
  final int timeoutMs;

  RpTaskSpec({
    required this.taskId,
    required this.storyId,
    required this.branchId,
    required this.dedupeKey,
    required this.priority,
    required this.requiredSourceRev,
    required this.requiredFoundationRev,
    required this.requiredStoryRev,
    required this.tasks,
    this.inputs = const {},
    int? enqueuedAtMs,
    int? timeoutMs,
  })  : enqueuedAtMs = enqueuedAtMs ?? DateTime.now().millisecondsSinceEpoch,
        timeoutMs = timeoutMs ?? _calculateDefaultTimeout(tasks);

  /// 根据任务列表计算默认超时时间
  static int _calculateDefaultTimeout(List<String> tasks) {
    if (tasks.isEmpty) return 30000;
    return tasks
        .map((t) => RpTaskType.getDefaultTimeout(t))
        .reduce((a, b) => a > b ? a : b);
  }

  /// 是否为紧急任务
  bool get isUrgent => priority == RpTaskPriority.urgent;

  /// 是否为空闲任务
  bool get isIdle => priority == RpTaskPriority.idle;

  /// 复制并修改
  RpTaskSpec copyWith({
    String? taskId,
    String? storyId,
    String? branchId,
    String? dedupeKey,
    RpTaskPriority? priority,
    int? requiredSourceRev,
    int? requiredFoundationRev,
    int? requiredStoryRev,
    List<String>? tasks,
    Map<String, dynamic>? inputs,
    int? enqueuedAtMs,
    int? timeoutMs,
  }) {
    return RpTaskSpec(
      taskId: taskId ?? this.taskId,
      storyId: storyId ?? this.storyId,
      branchId: branchId ?? this.branchId,
      dedupeKey: dedupeKey ?? this.dedupeKey,
      priority: priority ?? this.priority,
      requiredSourceRev: requiredSourceRev ?? this.requiredSourceRev,
      requiredFoundationRev:
          requiredFoundationRev ?? this.requiredFoundationRev,
      requiredStoryRev: requiredStoryRev ?? this.requiredStoryRev,
      tasks: tasks ?? this.tasks,
      inputs: inputs ?? this.inputs,
      enqueuedAtMs: enqueuedAtMs ?? this.enqueuedAtMs,
      timeoutMs: timeoutMs ?? this.timeoutMs,
    );
  }

  @override
  String toString() => 'RpTaskSpec($taskId, tasks=$tasks, priority=$priority)';

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpTaskSpec &&
          runtimeType == other.runtimeType &&
          taskId == other.taskId;

  @override
  int get hashCode => taskId.hashCode;
}

/// 任务构建器
///
/// 便捷创建常见任务规格
class RpTaskSpecBuilder {
  final String _storyId;
  final String _branchId;
  final int _sourceRev;
  final int _foundationRev;
  final int _storyRev;

  RpTaskSpecBuilder({
    required String storyId,
    required String branchId,
    required int sourceRev,
    required int foundationRev,
    required int storyRev,
  })  : _storyId = storyId,
        _branchId = branchId,
        _sourceRev = sourceRev,
        _foundationRev = foundationRev,
        _storyRev = storyRev;

  /// 生成唯一任务 ID
  String _generateTaskId() {
    return '${DateTime.now().millisecondsSinceEpoch}_${_storyId.hashCode.toRadixString(16)}';
  }

  /// 创建回合后任务（场景检测 + 状态更新）
  RpTaskSpec buildTurnEndTask() {
    return RpTaskSpec(
      taskId: _generateTaskId(),
      storyId: _storyId,
      branchId: _branchId,
      dedupeKey: '$_storyId|$_branchId|turn_end',
      priority: RpTaskPriority.normal,
      requiredSourceRev: _sourceRev,
      requiredFoundationRev: _foundationRev,
      requiredStoryRev: _storyRev,
      tasks: [RpTaskType.sceneDetect, RpTaskType.stateUpdate],
    );
  }

  /// 创建一致性重检任务（用户手动触发）
  RpTaskSpec buildConsistencyCheckTask({
    required String messageId,
    required String content,
  }) {
    return RpTaskSpec(
      taskId: _generateTaskId(),
      storyId: _storyId,
      branchId: _branchId,
      dedupeKey: '$_storyId|$_branchId|consistency|$messageId',
      priority: RpTaskPriority.urgent,
      requiredSourceRev: _sourceRev,
      requiredFoundationRev: _foundationRev,
      requiredStoryRev: _storyRev,
      tasks: [RpTaskType.consistencyHeavy],
      inputs: {
        'messageId': messageId,
        'content': content,
      },
    );
  }

  /// 创建空闲维护任务
  RpTaskSpec buildIdleMaintenanceTask() {
    return RpTaskSpec(
      taskId: _generateTaskId(),
      storyId: _storyId,
      branchId: _branchId,
      dedupeKey: '$_storyId|$_branchId|idle_maintenance',
      priority: RpTaskPriority.idle,
      requiredSourceRev: _sourceRev,
      requiredFoundationRev: _foundationRev,
      requiredStoryRev: _storyRev,
      tasks: [RpTaskType.foreshadowLink, RpTaskType.goalsUpdate],
    );
  }

  /// 创建摘要压缩任务
  RpTaskSpec buildSummarizeTask({required String targetLogicalId}) {
    return RpTaskSpec(
      taskId: _generateTaskId(),
      storyId: _storyId,
      branchId: _branchId,
      dedupeKey: '$_storyId|$_branchId|summarize|$targetLogicalId',
      priority: RpTaskPriority.idle,
      requiredSourceRev: _sourceRev,
      requiredFoundationRev: _foundationRev,
      requiredStoryRev: _storyRev,
      tasks: [RpTaskType.summarize],
      inputs: {'targetLogicalId': targetLogicalId},
    );
  }

  /// 创建编辑解释任务
  RpTaskSpec buildEditInterpretTask({
    required String messageId,
    required String originalContent,
    required String editedContent,
  }) {
    return RpTaskSpec(
      taskId: _generateTaskId(),
      storyId: _storyId,
      branchId: _branchId,
      dedupeKey: '$_storyId|$_branchId|edit|$messageId',
      priority: RpTaskPriority.normal,
      requiredSourceRev: _sourceRev,
      requiredFoundationRev: _foundationRev,
      requiredStoryRev: _storyRev,
      tasks: [RpTaskType.editInterpret],
      inputs: {
        'messageId': messageId,
        'originalContent': originalContent,
        'editedContent': editedContent,
      },
    );
  }
}
