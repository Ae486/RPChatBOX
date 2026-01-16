import 'package:hive/hive.dart';
import 'rp_entry_blob.dart';

part 'rp_operation.g.dart';

/// 操作日志
///
/// 记录对记忆条目的变更操作，是版本控制的权威日志
/// Box: rp_ops, Key: $storyId|$scopeIndex|$branchId|$rev
@HiveType(typeId: 55)
class RpOperation {
  @HiveField(0)
  final String storyId;

  /// RpScope.index
  @HiveField(1)
  final int scopeIndex;

  @HiveField(2)
  final String branchId;

  /// 版本号（递增）
  @HiveField(3)
  final int rev;

  @HiveField(4)
  final int createdAtMs;

  /// 关联的对话源版本号
  @HiveField(5)
  final int sourceRev;

  /// 执行该操作的 Agent ID（可选）
  @HiveField(6)
  final String? agent;

  /// 关联的任务 ID（可选）
  @HiveField(7)
  final String? jobId;

  /// 变更列表
  @HiveField(8)
  final List<RpEntryChange> changes;

  RpOperation({
    required this.storyId,
    required this.scopeIndex,
    required this.branchId,
    required this.rev,
    int? createdAtMs,
    required this.sourceRev,
    this.agent,
    this.jobId,
    List<RpEntryChange>? changes,
  })  : createdAtMs = createdAtMs ?? DateTime.now().millisecondsSinceEpoch,
        changes = changes ?? [];

  /// 生成存储键
  String get key => '$storyId|$scopeIndex|$branchId|$rev';

  /// 从键解析组件
  static ({String storyId, int scopeIndex, String branchId, int rev})? parseKey(String key) {
    final parts = key.split('|');
    if (parts.length != 4) return null;
    return (
      storyId: parts[0],
      scopeIndex: int.tryParse(parts[1]) ?? 0,
      branchId: parts[2],
      rev: int.tryParse(parts[3]) ?? 0,
    );
  }

  /// 检查是否包含指定 logicalId 的变更
  bool hasChangeFor(String logicalId) {
    return changes.any((c) => c.logicalId == logicalId);
  }

  /// 获取指定 logicalId 的变更
  RpEntryChange? getChangeFor(String logicalId) {
    return changes.cast<RpEntryChange?>().firstWhere(
          (c) => c?.logicalId == logicalId,
          orElse: () => null,
        );
  }
}

/// 条目变更
///
/// 记录单个条目的变更详情
@HiveType(typeId: 56)
class RpEntryChange {
  /// 逻辑 ID
  @HiveField(0)
  final String logicalId;

  /// 领域标识
  @HiveField(1)
  final String domain;

  /// 变更前的 blobId（null 表示新增）
  @HiveField(2)
  final String? beforeBlobId;

  /// 变更后的 blobId（null 表示删除）
  @HiveField(3)
  final String? afterBlobId;

  /// RpChangeReason.index
  @HiveField(4)
  final int reasonKindIndex;

  /// 证据引用列表
  @HiveField(5)
  final List<RpEvidenceRef> evidence;

  /// 变更说明（可选）
  @HiveField(6)
  final String? note;

  RpEntryChange({
    required this.logicalId,
    required this.domain,
    this.beforeBlobId,
    this.afterBlobId,
    required this.reasonKindIndex,
    List<RpEvidenceRef>? evidence,
    this.note,
  }) : evidence = evidence ?? [];

  /// 是否为新增操作
  bool get isCreate => beforeBlobId == null && afterBlobId != null;

  /// 是否为更新操作
  bool get isUpdate => beforeBlobId != null && afterBlobId != null;

  /// 是否为删除操作
  bool get isDelete => beforeBlobId != null && afterBlobId == null;
}
