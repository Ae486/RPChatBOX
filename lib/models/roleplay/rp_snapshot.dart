import 'package:hive/hive.dart';

part 'rp_snapshot.g.dart';

/// 快照指针
///
/// 记录某个版本时刻的完整状态映射，用于快速重建和回滚
/// Box: rp_snapshots, Key: $storyId|$scopeIndex|$branchId|$rev
@HiveType(typeId: 57)
class RpSnapshot {
  @HiveField(0)
  final String storyId;

  /// RpScope.index
  @HiveField(1)
  final int scopeIndex;

  @HiveField(2)
  final String branchId;

  /// 版本号（与 Operation.rev 对应）
  @HiveField(3)
  final int rev;

  @HiveField(4)
  final int createdAtMs;

  /// 关联的对话源版本号
  @HiveField(5)
  final int sourceRev;

  /// 条目指针映射: logicalId → blobId
  @HiveField(6)
  final Map<String, String> pointers;

  /// 领域索引: domain → [logicalId]
  @HiveField(7)
  final Map<String, List<String>> byDomain;

  RpSnapshot({
    required this.storyId,
    required this.scopeIndex,
    required this.branchId,
    required this.rev,
    int? createdAtMs,
    required this.sourceRev,
    Map<String, String>? pointers,
    Map<String, List<String>>? byDomain,
  })  : createdAtMs = createdAtMs ?? DateTime.now().millisecondsSinceEpoch,
        pointers = pointers ?? {},
        byDomain = byDomain ?? {};

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

  /// 获取指定 logicalId 的 blobId
  String? getBlobId(String logicalId) => pointers[logicalId];

  /// 获取指定领域的所有 logicalId
  List<String> getLogicalIdsByDomain(String domain) => byDomain[domain] ?? [];

  /// 条目总数
  int get entryCount => pointers.length;

  /// 领域列表
  List<String> get domains => byDomain.keys.toList();

  /// 应用变更创建新快照
  RpSnapshot applyChanges({
    required int newRev,
    required int newSourceRev,
    required List<({String logicalId, String domain, String? blobId})> changes,
  }) {
    final newPointers = Map<String, String>.from(pointers);
    final newByDomain = <String, List<String>>{};

    // 复制现有领域索引
    for (final entry in byDomain.entries) {
      newByDomain[entry.key] = List<String>.from(entry.value);
    }

    // 应用变更
    for (final change in changes) {
      final logicalId = change.logicalId;
      final domain = change.domain;
      final blobId = change.blobId;

      if (blobId != null) {
        // 新增或更新
        newPointers[logicalId] = blobId;
        if (!newByDomain.containsKey(domain)) {
          newByDomain[domain] = [];
        }
        if (!newByDomain[domain]!.contains(logicalId)) {
          newByDomain[domain]!.add(logicalId);
        }
      } else {
        // 删除
        newPointers.remove(logicalId);
        newByDomain[domain]?.remove(logicalId);
        if (newByDomain[domain]?.isEmpty ?? false) {
          newByDomain.remove(domain);
        }
      }
    }

    return RpSnapshot(
      storyId: storyId,
      scopeIndex: scopeIndex,
      branchId: branchId,
      rev: newRev,
      sourceRev: newSourceRev,
      pointers: newPointers,
      byDomain: newByDomain,
    );
  }
}
