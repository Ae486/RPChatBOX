# M0 Foundation Spec

> 版本: 1.1.0
> 创建日期: 2026-01-15
> 完成日期: 2026-01-15
> 状态: ✅ 已完成

---

## 1. 目标

为 Roleplay Feature 建立数据持久化基础设施：
- Hive 数据模型定义（TypeId 50-59）
- CRUD 操作封装
- 版本控制支持（COW 模式）

---

## 2. 设计决策

### 2.1 TypeId 分配

| TypeId | 类型 | 用途 |
|--------|------|------|
| 50 | RpStoryMeta | 故事元数据 |
| 51 | RpHead | 分支头指针 |
| 52 | RpModuleState | 模块状态 |
| 53 | RpEntryBlob | 条目内容（不可变） |
| 54 | RpEvidenceRef | 证据引用 |
| 55 | RpOperation | 操作日志 |
| 56 | RpEntryChange | 条目变更 |
| 57 | RpSnapshot | 快照指针 |
| 58 | RpProposal | 提议 |
| 59 | RpProposalTarget | 提议目标 |

### 2.2 Box 结构

```
rp_story_meta     - key: storyId
rp_entry_blobs    - key: blobId
rp_ops            - key: $storyId|$scopeIndex|$branchId|$rev
rp_snapshots      - key: $storyId|$scopeIndex|$branchId|$rev
rp_proposals      - key: proposalId
rp_logs           - key: logId
```

### 2.3 枚举存储策略

枚举使用 `index` 存储（int），避免字符串膨胀：
- `RpScope.foundation.index` → 0
- `RpScope.story.index` → 1

### 2.4 大内容存储

`contentJsonUtf8` 字段使用 `Uint8List` 存储 UTF-8 编码的 JSON：
- 避免 Hive 字符串编码问题
- 支持高效的二进制存储
- 解析时按需 decode

---

## 3. 数据模型定义

### 3.1 枚举 (rp_enums.dart)

```dart
/// 条目作用域
enum RpScope {
  foundation, // 基底（跨分支共享）
  story,      // 剧情（分支隔离）
}

/// 条目状态
enum RpStatus {
  confirmed,  // 已确认（权威）
  draft,      // 草稿（待审核）
}

/// 提议策略层级
enum RpPolicyTier {
  silent,         // 静默应用
  notifyApply,    // 通知后应用
  reviewRequired, // 需要审核
}

/// 提议类型
enum RpProposalKind {
  confirmedWrite,
  draftUpdate,
  linkUpdate,
  sceneTransition,
  compressionUpdate,
  outputFix,
  userEditInterpretation,
}

/// 提议决策
enum RpProposalDecision {
  pending,
  applied,
  rejected,
  superseded,
}

/// 变更原因
enum RpChangeReason {
  agentProposal,
  userDirect,
  systemMerge,
  rollback,
}
```

### 3.2 RpStoryMeta (TypeId 50-52)

```dart
@HiveType(typeId: 50)
class RpStoryMeta extends HiveObject {
  @HiveField(0) final String storyId;
  @HiveField(1) final int schemaVersion;
  @HiveField(2) String activeBranchId;
  @HiveField(3) int sourceRev;
  @HiveField(4) final List<RpHead> heads;
  @HiveField(5) final List<RpModuleState> modules;
  @HiveField(6) final Map<String, String> moduleConfigJson;
  @HiveField(7) int updatedAtMs;
}

@HiveType(typeId: 51)
class RpHead {
  @HiveField(0) final int scopeIndex;      // RpScope.index
  @HiveField(1) final String branchId;
  @HiveField(2) int rev;
  @HiveField(3) int lastSnapshotRev;
}

@HiveType(typeId: 52)
class RpModuleState {
  @HiveField(0) final String moduleId;
  @HiveField(1) bool enabled;
  @HiveField(2) int lastDerivedSourceRev;
  @HiveField(3) bool dirty;
  @HiveField(4) int dirtySinceSourceRev;
  @HiveField(5) String? dirtyFromMessageId;
  @HiveField(6) int updatedAtMs;
}
```

### 3.3 RpEntryBlob (TypeId 53-54)

```dart
@HiveType(typeId: 53)
class RpEntryBlob {
  @HiveField(0) final String blobId;
  @HiveField(1) final String storyId;
  @HiveField(2) final String logicalId;
  @HiveField(3) final int scopeIndex;
  @HiveField(4) final String branchId;
  @HiveField(5) final int statusIndex;
  @HiveField(6) final String domain;
  @HiveField(7) final String entryType;
  @HiveField(8) final Uint8List contentJsonUtf8;
  @HiveField(9) final String? preview;
  @HiveField(10) final List<String> tags;
  @HiveField(11) final List<RpEvidenceRef> evidence;
  @HiveField(12) final int createdAtMs;
  @HiveField(13) final int sourceRev;
  @HiveField(14) final int? approxTokens;
}

@HiveType(typeId: 54)
class RpEvidenceRef {
  @HiveField(0) final String type;  // 'msg' | 'op' | 'user_edit' | 'external'
  @HiveField(1) final String refId;
  @HiveField(2) final int? start;
  @HiveField(3) final int? end;
  @HiveField(4) final String? note;
}
```

### 3.4 RpOperation (TypeId 55-56)

```dart
@HiveType(typeId: 55)
class RpOperation {
  @HiveField(0) final String storyId;
  @HiveField(1) final int scopeIndex;
  @HiveField(2) final String branchId;
  @HiveField(3) final int rev;
  @HiveField(4) final int createdAtMs;
  @HiveField(5) final int sourceRev;
  @HiveField(6) final String? agent;
  @HiveField(7) final String? jobId;
  @HiveField(8) final List<RpEntryChange> changes;
}

@HiveType(typeId: 56)
class RpEntryChange {
  @HiveField(0) final String logicalId;
  @HiveField(1) final String domain;
  @HiveField(2) final String? beforeBlobId;
  @HiveField(3) final String? afterBlobId;
  @HiveField(4) final int reasonKindIndex;  // RpChangeReason.index
  @HiveField(5) final List<RpEvidenceRef> evidence;
  @HiveField(6) final String? note;
}
```

### 3.5 RpSnapshot (TypeId 57)

```dart
@HiveType(typeId: 57)
class RpSnapshot {
  @HiveField(0) final String storyId;
  @HiveField(1) final int scopeIndex;
  @HiveField(2) final String branchId;
  @HiveField(3) final int rev;
  @HiveField(4) final int createdAtMs;
  @HiveField(5) final int sourceRev;
  @HiveField(6) final Map<String, String> pointers;  // logicalId → blobId
  @HiveField(7) final Map<String, List<String>> byDomain;  // domain → [logicalId]
}
```

### 3.6 RpProposal (TypeId 58-59)

```dart
@HiveType(typeId: 58)
class RpProposal {
  @HiveField(0) final String proposalId;
  @HiveField(1) final String storyId;
  @HiveField(2) final String branchId;
  @HiveField(3) final int createdAtMs;
  @HiveField(4) final int kindIndex;  // RpProposalKind.index
  @HiveField(5) final String domain;
  @HiveField(6) final int policyTierIndex;  // RpPolicyTier.index
  @HiveField(7) final RpProposalTarget target;
  @HiveField(8) final Uint8List payloadJsonUtf8;
  @HiveField(9) final List<RpEvidenceRef> evidence;
  @HiveField(10) final String reason;
  @HiveField(11) final int sourceRev;
  @HiveField(12) final int expectedFoundationRev;
  @HiveField(13) final int expectedStoryRev;
  @HiveField(14) int decisionIndex;  // RpProposalDecision.index
  @HiveField(15) int? decidedAtMs;
  @HiveField(16) String? decidedBy;
  @HiveField(17) String? decisionNote;
}

@HiveType(typeId: 59)
class RpProposalTarget {
  @HiveField(0) final int scopeIndex;
  @HiveField(1) final String branchId;
  @HiveField(2) final int statusIndex;
  @HiveField(3) final String logicalId;
}
```

---

## 4. 服务层接口

### 4.1 RpMemoryRepository

```dart
class RpMemoryRepository {
  // Box 引用
  late Box<RpStoryMeta> _storyMetaBox;
  late Box<RpEntryBlob> _entryBlobsBox;
  late Box<RpOperation> _opsBox;
  late Box<RpSnapshot> _snapshotsBox;
  late Box<RpProposal> _proposalsBox;

  // 初始化
  Future<void> initialize();
  Future<void> close();

  // StoryMeta CRUD
  Future<RpStoryMeta?> getStoryMeta(String storyId);
  Future<void> saveStoryMeta(RpStoryMeta meta);
  Future<void> deleteStoryMeta(String storyId);
  Future<List<RpStoryMeta>> listAllStories();

  // EntryBlob CRUD
  Future<RpEntryBlob?> getBlob(String blobId);
  Future<void> saveBlob(RpEntryBlob blob);
  Future<void> deleteBlob(String blobId);
  Future<List<RpEntryBlob>> getBlobsByLogicalId(String storyId, String logicalId);

  // Operation CRUD
  Future<RpOperation?> getOperation(String storyId, int scopeIndex, String branchId, int rev);
  Future<void> saveOperation(RpOperation op);
  Future<List<RpOperation>> getOperationRange(
    String storyId, int scopeIndex, String branchId, int fromRev, int toRev);

  // Snapshot CRUD
  Future<RpSnapshot?> getSnapshot(String storyId, int scopeIndex, String branchId, int rev);
  Future<void> saveSnapshot(RpSnapshot snapshot);
  Future<RpSnapshot?> getLatestSnapshot(String storyId, int scopeIndex, String branchId);

  // Proposal CRUD
  Future<RpProposal?> getProposal(String proposalId);
  Future<void> saveProposal(RpProposal proposal);
  Future<List<RpProposal>> getPendingProposals(String storyId);
  Future<void> updateProposalDecision(String proposalId, RpProposalDecision decision, ...);
}
```

### 4.2 写入顺序（崩溃容错）

```
1. saveBlob(s) → rp_entry_blobs
2. saveOperation → rp_ops (关键一步，权威日志)
3. saveStoryMeta (更新 heads) → rp_story_meta
4. saveSnapshot (可选，每 N 个 rev) → rp_snapshots
```

---

## 5. 文件结构

```
lib/models/roleplay/
├── rp_enums.dart              # 枚举定义
├── rp_story_meta.dart         # StoryMeta + Head + ModuleState
├── rp_story_meta.g.dart       # 生成的适配器
├── rp_entry_blob.dart         # EntryBlob + EvidenceRef
├── rp_entry_blob.g.dart
├── rp_operation.dart          # Operation + EntryChange
├── rp_operation.g.dart
├── rp_snapshot.dart           # Snapshot
├── rp_snapshot.g.dart
├── rp_proposal.dart           # Proposal + Target
└── rp_proposal.g.dart

lib/services/roleplay/
└── rp_memory_repository.dart  # Hive CRUD 封装
```

---

## 6. 测试计划

### 6.1 单元测试

| 测试 | 验收标准 |
|------|----------|
| 模型序列化/反序列化 | 所有字段正确保存和读取 |
| Box 键格式 | 复合键正确生成和解析 |
| CRUD 操作 | 创建/读取/更新/删除正确 |
| 写入顺序 | 崩溃恢复后数据完整 |

### 6.2 测试文件

```
test/models/roleplay/
├── rp_story_meta_test.dart
├── rp_entry_blob_test.dart
├── rp_operation_test.dart
├── rp_snapshot_test.dart
└── rp_proposal_test.dart

test/services/roleplay/
└── rp_memory_repository_test.dart
```

---

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| TypeId 冲突 | 使用 50-59 段，与现有 0-3 隔离 |
| Hive 性能瓶颈 | COW + 周期性 Snapshot，避免全量重写 |
| 数据迁移复杂 | schemaVersion 字段支持未来迁移 |

---

## 8. 依赖

- hive: ^2.2.3
- hive_flutter: ^1.1.0
- ulid: ^2.0.0 (待添加，用于 ID 生成)

---

## 9. 进度追踪

| 任务 | 状态 | 完成日期 |
|------|------|----------|
| Spec 文档 | ✅ 完成 | 2026-01-15 |
| rp_enums.dart | ✅ 完成 | 2026-01-15 |
| rp_story_meta.dart | ✅ 完成 | 2026-01-15 |
| rp_entry_blob.dart | ✅ 完成 | 2026-01-15 |
| rp_operation.dart | ✅ 完成 | 2026-01-15 |
| rp_snapshot.dart | ✅ 完成 | 2026-01-15 |
| rp_proposal.dart | ✅ 完成 | 2026-01-15 |
| rp_memory_repository.dart | ✅ 完成 | 2026-01-15 |
| 单元测试 (33 tests) | ✅ 完成 | 2026-01-15 |
| Code Review + 修复 | ✅ 完成 | 2026-01-15 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-01-15 | 初版 |
| 1.1.0 | 2026-01-15 | M0 实现完成，更新进度追踪 |

---

## 10. 实现总结

### 10.1 产出文件

| 文件 | 路径 | 说明 |
|------|------|------|
| rp_enums.dart | lib/models/roleplay/ | 6 个枚举 + fromIndex 扩展 |
| rp_story_meta.dart | lib/models/roleplay/ | TypeId 50-52 |
| rp_entry_blob.dart | lib/models/roleplay/ | TypeId 53-54 |
| rp_operation.dart | lib/models/roleplay/ | TypeId 55-56 |
| rp_snapshot.dart | lib/models/roleplay/ | TypeId 57 |
| rp_proposal.dart | lib/models/roleplay/ | TypeId 58-59 |
| rp_memory_repository.dart | lib/services/roleplay/ | Hive CRUD |
| rp_memory_repository_test.dart | test/unit/services/ | 33 个单元测试 |
| rp_test_data.dart | test/helpers/ | 测试数据工厂 |

### 10.2 关键设计实现

1. **竞态条件防护**: `initialize()` 使用 Completer 模式
2. **批量操作优化**: `saveBlobs()` 和 `deleteStoryWithData()` 使用 `putAll`/`deleteAll`
3. **资源清理**: `close()` 清理 Box 引用和 Completer
4. **崩溃容错**: 写入顺序 blobs → ops → meta → snapshot

### 10.3 测试覆盖

- 初始化/关闭生命周期
- 5 种数据类型的 CRUD 操作
- 事务性写入 (commitChanges)
- 级联删除 (deleteStoryWithData)
- 边界条件和错误处理
