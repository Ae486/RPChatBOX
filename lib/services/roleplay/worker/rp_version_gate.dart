/// 版本闸门
///
/// 验证任务和响应是否因版本变化而过期
/// POS: Services / Roleplay / Worker
library;

import '../../../models/roleplay/rp_enums.dart';
import '../../../models/roleplay/rp_story_meta.dart';
import 'rp_task_spec.dart';
import 'rp_worker_protocol.dart';

/// 版本闸门
///
/// 确保后台任务在执行和响应时数据仍然有效
///
/// 版本语义：
/// - sourceRev: 对话版本号（消息树变化递增）
/// - foundationRev: Foundation scope 的操作版本号
/// - storyRev: Story scope 的操作版本号
class RpVersionGate {
  /// Foundation 的固定 branchId
  ///
  /// Foundation 是跨分支共享的，使用固定 branchId
  static const String foundationBranchId = '-';

  /// 验证任务是否过期
  ///
  /// 过期条件（任一满足即过期）：
  /// 1. 任务的 sourceRev 小于当前 meta.sourceRev
  /// 2. 任务的 foundationRev 小于当前 foundation head.rev
  /// 3. 任务的 storyRev 小于当前 story head.rev
  static bool isTaskStale(RpTaskSpec task, RpStoryMeta currentMeta) {
    return _isStale(
      sourceRev: task.requiredSourceRev,
      foundationRev: task.requiredFoundationRev,
      storyRev: task.requiredStoryRev,
      branchId: task.branchId,
      currentMeta: currentMeta,
    );
  }

  /// 验证响应是否过期
  ///
  /// 使用原始请求的版本信息进行验证
  static bool isResponseStale(
    RpWorkerResponse response,
    RpWorkerRequest originalRequest,
    RpStoryMeta currentMeta,
  ) {
    return _isStale(
      sourceRev: originalRequest.sourceRev,
      foundationRev: originalRequest.foundationRev,
      storyRev: originalRequest.storyRev,
      branchId: originalRequest.branchId,
      currentMeta: currentMeta,
    );
  }

  /// 验证版本号组合是否过期
  static bool isVersionStale({
    required int sourceRev,
    required int foundationRev,
    required int storyRev,
    required String branchId,
    required RpStoryMeta currentMeta,
  }) {
    return _isStale(
      sourceRev: sourceRev,
      foundationRev: foundationRev,
      storyRev: storyRev,
      branchId: branchId,
      currentMeta: currentMeta,
    );
  }

  /// 内部版本检查实现
  static bool _isStale({
    required int sourceRev,
    required int foundationRev,
    required int storyRev,
    required String branchId,
    required RpStoryMeta currentMeta,
  }) {
    // 1. 检查 sourceRev（对话版本）
    if (sourceRev < currentMeta.sourceRev) {
      return true;
    }

    // 2. 检查 foundation rev（使用固定 branchId）
    final foundationHead = currentMeta.getHead(
      RpScope.foundation.index,
      foundationBranchId,
    );
    if (foundationHead != null && foundationRev < foundationHead.rev) {
      return true;
    }

    // 3. 检查 story rev（使用任务的 branchId）
    final storyHead = currentMeta.getHead(
      RpScope.story.index,
      branchId,
    );
    if (storyHead != null && storyRev < storyHead.rev) {
      return true;
    }

    return false;
  }

  /// 获取当前版本快照
  ///
  /// 用于创建任务时获取当前版本号
  static RpVersionSnapshot getCurrentSnapshot(
    RpStoryMeta meta,
    String branchId,
  ) {
    final foundationHead = meta.getHead(
      RpScope.foundation.index,
      foundationBranchId,
    );
    final storyHead = meta.getHead(
      RpScope.story.index,
      branchId,
    );

    return RpVersionSnapshot(
      sourceRev: meta.sourceRev,
      foundationRev: foundationHead?.rev ?? 0,
      storyRev: storyHead?.rev ?? 0,
    );
  }

  /// 比较两个版本快照
  ///
  /// 返回值：
  /// - 负数：a 比 b 旧
  /// - 0：相同
  /// - 正数：a 比 b 新
  static int compareSnapshots(RpVersionSnapshot a, RpVersionSnapshot b) {
    // 首先比较 sourceRev
    final sourceCompare = a.sourceRev.compareTo(b.sourceRev);
    if (sourceCompare != 0) return sourceCompare;

    // 然后比较 foundationRev
    final foundationCompare = a.foundationRev.compareTo(b.foundationRev);
    if (foundationCompare != 0) return foundationCompare;

    // 最后比较 storyRev
    return a.storyRev.compareTo(b.storyRev);
  }
}

/// 版本快照
///
/// 记录某一时刻的完整版本信息
class RpVersionSnapshot {
  final int sourceRev;
  final int foundationRev;
  final int storyRev;

  const RpVersionSnapshot({
    required this.sourceRev,
    required this.foundationRev,
    required this.storyRev,
  });

  /// 零版本（用于初始状态）
  static const zero = RpVersionSnapshot(
    sourceRev: 0,
    foundationRev: 0,
    storyRev: 0,
  );

  /// 检查是否比另一个快照旧
  bool isOlderThan(RpVersionSnapshot other) {
    return RpVersionGate.compareSnapshots(this, other) < 0;
  }

  /// 检查是否与另一个快照相同
  bool isSameAs(RpVersionSnapshot other) {
    return sourceRev == other.sourceRev &&
        foundationRev == other.foundationRev &&
        storyRev == other.storyRev;
  }

  Map<String, dynamic> toJson() => {
        'sourceRev': sourceRev,
        'foundationRev': foundationRev,
        'storyRev': storyRev,
      };

  factory RpVersionSnapshot.fromJson(Map<String, dynamic> json) {
    return RpVersionSnapshot(
      sourceRev: json['sourceRev'] as int? ?? 0,
      foundationRev: json['foundationRev'] as int? ?? 0,
      storyRev: json['storyRev'] as int? ?? 0,
    );
  }

  @override
  String toString() =>
      'RpVersionSnapshot(src=$sourceRev, fnd=$foundationRev, sty=$storyRev)';

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RpVersionSnapshot &&
          runtimeType == other.runtimeType &&
          sourceRev == other.sourceRev &&
          foundationRev == other.foundationRev &&
          storyRev == other.storyRev;

  @override
  int get hashCode =>
      sourceRev.hashCode ^ foundationRev.hashCode ^ storyRev.hashCode;
}

/// 过期原因
enum RpStaleReason {
  /// 对话已更新
  sourceRevOutdated,

  /// Foundation 已更新
  foundationRevOutdated,

  /// Story 已更新
  storyRevOutdated,
}

/// 版本检查结果
class RpVersionCheckResult {
  final bool isStale;
  final RpStaleReason? reason;
  final String? details;

  const RpVersionCheckResult._({
    required this.isStale,
    this.reason,
    this.details,
  });

  /// 版本有效
  static const valid = RpVersionCheckResult._(isStale: false);

  /// 版本过期
  factory RpVersionCheckResult.stale(RpStaleReason reason, {String? details}) {
    return RpVersionCheckResult._(
      isStale: true,
      reason: reason,
      details: details,
    );
  }

  @override
  String toString() => isStale
      ? 'RpVersionCheckResult(stale: $reason, $details)'
      : 'RpVersionCheckResult(valid)';
}

/// 版本闸门扩展：详细检查
extension RpVersionGateDetailed on RpVersionGate {
  /// 详细验证任务是否过期（返回原因）
  static RpVersionCheckResult checkTaskStale(
    RpTaskSpec task,
    RpStoryMeta currentMeta,
  ) {
    // 1. 检查 sourceRev
    if (task.requiredSourceRev < currentMeta.sourceRev) {
      return RpVersionCheckResult.stale(
        RpStaleReason.sourceRevOutdated,
        details:
            'task.sourceRev=${task.requiredSourceRev} < meta.sourceRev=${currentMeta.sourceRev}',
      );
    }

    // 2. 检查 foundation rev
    final foundationHead = currentMeta.getHead(
      RpScope.foundation.index,
      RpVersionGate.foundationBranchId,
    );
    if (foundationHead != null &&
        task.requiredFoundationRev < foundationHead.rev) {
      return RpVersionCheckResult.stale(
        RpStaleReason.foundationRevOutdated,
        details:
            'task.foundationRev=${task.requiredFoundationRev} < head.rev=${foundationHead.rev}',
      );
    }

    // 3. 检查 story rev
    final storyHead = currentMeta.getHead(
      RpScope.story.index,
      task.branchId,
    );
    if (storyHead != null && task.requiredStoryRev < storyHead.rev) {
      return RpVersionCheckResult.stale(
        RpStaleReason.storyRevOutdated,
        details:
            'task.storyRev=${task.requiredStoryRev} < head.rev=${storyHead.rev}',
      );
    }

    return RpVersionCheckResult.valid;
  }
}
