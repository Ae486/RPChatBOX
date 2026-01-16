import 'package:hive/hive.dart';

part 'rp_story_meta.g.dart';

/// 故事元数据
///
/// 存储故事的顶层信息，包括分支头指针和模块状态
/// Box: rp_story_meta, Key: storyId
@HiveType(typeId: 50)
class RpStoryMeta extends HiveObject {
  @HiveField(0)
  final String storyId;

  @HiveField(1)
  final int schemaVersion;

  @HiveField(2)
  String activeBranchId;

  @HiveField(3)
  int sourceRev;

  @HiveField(4)
  final List<RpHead> heads;

  @HiveField(5)
  final List<RpModuleState> modules;

  @HiveField(6)
  final Map<String, String> moduleConfigJson;

  @HiveField(7)
  int updatedAtMs;

  RpStoryMeta({
    required this.storyId,
    this.schemaVersion = 1,
    required this.activeBranchId,
    this.sourceRev = 0,
    List<RpHead>? heads,
    List<RpModuleState>? modules,
    Map<String, String>? moduleConfigJson,
    int? updatedAtMs,
  })  : heads = heads ?? [],
        modules = modules ?? [],
        moduleConfigJson = moduleConfigJson ?? {},
        updatedAtMs = updatedAtMs ?? DateTime.now().millisecondsSinceEpoch;

  RpHead? getHead(int scopeIndex, String branchId) {
    return heads.cast<RpHead?>().firstWhere(
          (h) => h?.scopeIndex == scopeIndex && h?.branchId == branchId,
          orElse: () => null,
        );
  }

  RpModuleState? getModuleState(String moduleId) {
    return modules.cast<RpModuleState?>().firstWhere(
          (m) => m?.moduleId == moduleId,
          orElse: () => null,
        );
  }
}

/// 分支头指针
///
/// 记录每个 (scope, branch) 组合的当前版本号
@HiveType(typeId: 51)
class RpHead {
  /// RpScope.index
  @HiveField(0)
  final int scopeIndex;

  @HiveField(1)
  final String branchId;

  @HiveField(2)
  int rev;

  @HiveField(3)
  int lastSnapshotRev;

  RpHead({
    required this.scopeIndex,
    required this.branchId,
    this.rev = 0,
    this.lastSnapshotRev = 0,
  });
}

/// 模块状态
///
/// 记录每个记忆模块的启用状态和脏标记
@HiveType(typeId: 52)
class RpModuleState {
  @HiveField(0)
  final String moduleId;

  @HiveField(1)
  bool enabled;

  @HiveField(2)
  int lastDerivedSourceRev;

  @HiveField(3)
  bool dirty;

  @HiveField(4)
  int dirtySinceSourceRev;

  @HiveField(5)
  String? dirtyFromMessageId;

  @HiveField(6)
  int updatedAtMs;

  RpModuleState({
    required this.moduleId,
    this.enabled = true,
    this.lastDerivedSourceRev = 0,
    this.dirty = false,
    this.dirtySinceSourceRev = 0,
    this.dirtyFromMessageId,
    int? updatedAtMs,
  }) : updatedAtMs = updatedAtMs ?? DateTime.now().millisecondsSinceEpoch;

  void markDirty(int sourceRev, String? messageId) {
    if (!dirty) {
      dirty = true;
      dirtySinceSourceRev = sourceRev;
      dirtyFromMessageId = messageId;
    }
    updatedAtMs = DateTime.now().millisecondsSinceEpoch;
  }

  void clearDirty(int derivedSourceRev) {
    dirty = false;
    lastDerivedSourceRev = derivedSourceRev;
    dirtyFromMessageId = null;
    updatedAtMs = DateTime.now().millisecondsSinceEpoch;
  }
}
