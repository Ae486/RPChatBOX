import 'dart:async';
import 'package:hive_flutter/hive_flutter.dart';
import '../../models/roleplay/rp_story_meta.dart';
import '../../models/roleplay/rp_entry_blob.dart';
import '../../models/roleplay/rp_operation.dart';
import '../../models/roleplay/rp_snapshot.dart';
import '../../models/roleplay/rp_proposal.dart';
import '../../models/roleplay/rp_enums.dart';

/// Roleplay 记忆数据仓库
///
/// 管理所有 Roleplay 相关数据的持久化存储
/// Box 结构：
/// - rp_story_meta: StoryMeta (key=storyId)
/// - rp_entry_blobs: EntryBlob (key=blobId)
/// - rp_ops: Operation (key=$storyId|$scopeIndex|$branchId|$rev)
/// - rp_snapshots: Snapshot (key=$storyId|$scopeIndex|$branchId|$rev)
/// - rp_proposals: Proposal (key=proposalId)
class RpMemoryRepository {
  static const String _storyMetaBoxName = 'rp_story_meta';
  static const String _entryBlobsBoxName = 'rp_entry_blobs';
  static const String _opsBoxName = 'rp_ops';
  static const String _snapshotsBoxName = 'rp_snapshots';
  static const String _proposalsBoxName = 'rp_proposals';

  Box<RpStoryMeta>? _storyMetaBox;
  Box<RpEntryBlob>? _entryBlobsBox;
  Box<RpOperation>? _opsBox;
  Box<RpSnapshot>? _snapshotsBox;
  Box<RpProposal>? _proposalsBox;

  bool _initialized = false;
  Completer<void>? _initCompleter;

  /// 是否已初始化
  bool get isInitialized => _initialized;

  /// 初始化仓库（线程安全）
  Future<void> initialize() async {
    if (_initialized) return;
    if (_initCompleter != null) return _initCompleter!.future;

    _initCompleter = Completer<void>();
    try {
      await _registerAdapters();

      _storyMetaBox = await Hive.openBox<RpStoryMeta>(_storyMetaBoxName);
      _entryBlobsBox = await Hive.openBox<RpEntryBlob>(_entryBlobsBoxName);
      _opsBox = await Hive.openBox<RpOperation>(_opsBoxName);
      _snapshotsBox = await Hive.openBox<RpSnapshot>(_snapshotsBoxName);
      _proposalsBox = await Hive.openBox<RpProposal>(_proposalsBoxName);

      _initialized = true;
      _initCompleter!.complete();
    } catch (e) {
      _initCompleter = null;
      rethrow;
    }
  }

  Future<void> _registerAdapters() async {
    // TypeId 50-52: StoryMeta 系列
    if (!Hive.isAdapterRegistered(50)) {
      Hive.registerAdapter(RpStoryMetaAdapter());
    }
    if (!Hive.isAdapterRegistered(51)) {
      Hive.registerAdapter(RpHeadAdapter());
    }
    if (!Hive.isAdapterRegistered(52)) {
      Hive.registerAdapter(RpModuleStateAdapter());
    }

    // TypeId 53-54: EntryBlob 系列
    if (!Hive.isAdapterRegistered(53)) {
      Hive.registerAdapter(RpEntryBlobAdapter());
    }
    if (!Hive.isAdapterRegistered(54)) {
      Hive.registerAdapter(RpEvidenceRefAdapter());
    }

    // TypeId 55-56: Operation 系列
    if (!Hive.isAdapterRegistered(55)) {
      Hive.registerAdapter(RpOperationAdapter());
    }
    if (!Hive.isAdapterRegistered(56)) {
      Hive.registerAdapter(RpEntryChangeAdapter());
    }

    // TypeId 57: Snapshot
    if (!Hive.isAdapterRegistered(57)) {
      Hive.registerAdapter(RpSnapshotAdapter());
    }

    // TypeId 58-59: Proposal 系列
    if (!Hive.isAdapterRegistered(58)) {
      Hive.registerAdapter(RpProposalAdapter());
    }
    if (!Hive.isAdapterRegistered(59)) {
      Hive.registerAdapter(RpProposalTargetAdapter());
    }
  }

  void _ensureInitialized() {
    if (!_initialized) {
      throw StateError('RpMemoryRepository not initialized. Call initialize() first.');
    }
  }

  /// 关闭仓库
  Future<void> close() async {
    await _storyMetaBox?.close();
    await _entryBlobsBox?.close();
    await _opsBox?.close();
    await _snapshotsBox?.close();
    await _proposalsBox?.close();

    _storyMetaBox = null;
    _entryBlobsBox = null;
    _opsBox = null;
    _snapshotsBox = null;
    _proposalsBox = null;

    _initialized = false;
    _initCompleter = null;
  }

  // ==================== StoryMeta CRUD ====================

  Future<RpStoryMeta?> getStoryMeta(String storyId) async {
    _ensureInitialized();
    return _storyMetaBox!.get(storyId);
  }

  Future<void> saveStoryMeta(RpStoryMeta meta) async {
    _ensureInitialized();
    await _storyMetaBox!.put(meta.storyId, meta);
  }

  Future<void> deleteStoryMeta(String storyId) async {
    _ensureInitialized();
    await _storyMetaBox!.delete(storyId);
  }

  Future<List<RpStoryMeta>> listAllStories() async {
    _ensureInitialized();
    return _storyMetaBox!.values.toList();
  }

  // ==================== EntryBlob CRUD ====================

  Future<RpEntryBlob?> getBlob(String blobId) async {
    _ensureInitialized();
    return _entryBlobsBox!.get(blobId);
  }

  Future<void> saveBlob(RpEntryBlob blob) async {
    _ensureInitialized();
    await _entryBlobsBox!.put(blob.blobId, blob);
  }

  Future<void> saveBlobs(List<RpEntryBlob> blobs) async {
    _ensureInitialized();
    final map = {for (final blob in blobs) blob.blobId: blob};
    await _entryBlobsBox!.putAll(map);
  }

  Future<void> deleteBlob(String blobId) async {
    _ensureInitialized();
    await _entryBlobsBox!.delete(blobId);
  }

  Future<List<RpEntryBlob>> getBlobsByLogicalId(String storyId, String logicalId) async {
    _ensureInitialized();
    return _entryBlobsBox!.values
        .where((blob) => blob.storyId == storyId && blob.logicalId == logicalId)
        .toList();
  }

  Future<List<RpEntryBlob>> getBlobsByStory(String storyId) async {
    _ensureInitialized();
    return _entryBlobsBox!.values
        .where((blob) => blob.storyId == storyId)
        .toList();
  }

  // ==================== Operation CRUD ====================

  String _buildOpKey(String storyId, int scopeIndex, String branchId, int rev) {
    return '$storyId|$scopeIndex|$branchId|$rev';
  }

  Future<RpOperation?> getOperation(
    String storyId,
    int scopeIndex,
    String branchId,
    int rev,
  ) async {
    _ensureInitialized();
    final key = _buildOpKey(storyId, scopeIndex, branchId, rev);
    return _opsBox!.get(key);
  }

  Future<void> saveOperation(RpOperation op) async {
    _ensureInitialized();
    await _opsBox!.put(op.key, op);
  }

  Future<List<RpOperation>> getOperationRange(
    String storyId,
    int scopeIndex,
    String branchId,
    int fromRev,
    int toRev,
  ) async {
    _ensureInitialized();
    final results = <RpOperation>[];
    for (int rev = fromRev; rev <= toRev; rev++) {
      final key = _buildOpKey(storyId, scopeIndex, branchId, rev);
      final op = _opsBox!.get(key);
      if (op != null) results.add(op);
    }
    return results;
  }

  Future<List<RpOperation>> getOperationsByStory(String storyId) async {
    _ensureInitialized();
    return _opsBox!.values
        .where((op) => op.storyId == storyId)
        .toList();
  }

  // ==================== Snapshot CRUD ====================

  String _buildSnapshotKey(String storyId, int scopeIndex, String branchId, int rev) {
    return '$storyId|$scopeIndex|$branchId|$rev';
  }

  Future<RpSnapshot?> getSnapshot(
    String storyId,
    int scopeIndex,
    String branchId,
    int rev,
  ) async {
    _ensureInitialized();
    final key = _buildSnapshotKey(storyId, scopeIndex, branchId, rev);
    return _snapshotsBox!.get(key);
  }

  Future<void> saveSnapshot(RpSnapshot snapshot) async {
    _ensureInitialized();
    await _snapshotsBox!.put(snapshot.key, snapshot);
  }

  Future<RpSnapshot?> getLatestSnapshot(
    String storyId,
    int scopeIndex,
    String branchId,
  ) async {
    _ensureInitialized();

    // 优先从 StoryMeta.head.lastSnapshotRev 获取
    final meta = await getStoryMeta(storyId);
    final head = meta?.getHead(scopeIndex, branchId);

    if (head != null && head.lastSnapshotRev > 0) {
      final key = _buildSnapshotKey(storyId, scopeIndex, branchId, head.lastSnapshotRev);
      final snapshot = _snapshotsBox!.get(key);
      if (snapshot != null) return snapshot;
    }

    // Fallback: 扫描所有匹配前缀的快照
    final prefix = '$storyId|$scopeIndex|$branchId|';
    RpSnapshot? latest;
    for (final key in _snapshotsBox!.keys) {
      if (key.toString().startsWith(prefix)) {
        final snapshot = _snapshotsBox!.get(key);
        if (snapshot != null && (latest == null || snapshot.rev > latest.rev)) {
          latest = snapshot;
        }
      }
    }
    return latest;
  }

  // ==================== Proposal CRUD ====================

  Future<RpProposal?> getProposal(String proposalId) async {
    _ensureInitialized();
    return _proposalsBox!.get(proposalId);
  }

  Future<void> saveProposal(RpProposal proposal) async {
    _ensureInitialized();
    await _proposalsBox!.put(proposal.proposalId, proposal);
  }

  Future<void> deleteProposal(String proposalId) async {
    _ensureInitialized();
    await _proposalsBox!.delete(proposalId);
  }

  Future<List<RpProposal>> getPendingProposals(String storyId) async {
    _ensureInitialized();
    return _proposalsBox!.values
        .where((p) =>
            p.storyId == storyId &&
            p.decisionIndex == RpProposalDecision.pending.index)
        .toList();
  }

  Future<List<RpProposal>> getProposalsByStory(String storyId) async {
    _ensureInitialized();
    return _proposalsBox!.values
        .where((p) => p.storyId == storyId)
        .toList();
  }

  Future<void> updateProposalDecision(
    String proposalId,
    RpProposalDecision decision, {
    String? decidedBy,
    String? decisionNote,
  }) async {
    _ensureInitialized();
    final proposal = _proposalsBox!.get(proposalId);
    if (proposal == null) return;

    proposal.decisionIndex = decision.index;
    proposal.decidedAtMs = DateTime.now().millisecondsSinceEpoch;
    proposal.decidedBy = decidedBy;
    proposal.decisionNote = decisionNote;

    await _proposalsBox!.put(proposalId, proposal);
  }

  // ==================== 事务性写入 (崩溃容错) ====================

  /// 原子性写入变更
  ///
  /// 写入顺序（崩溃容错）：
  /// 1. saveBlob(s) → rp_entry_blobs
  /// 2. saveOperation → rp_ops (关键一步，权威日志)
  /// 3. saveStoryMeta (更新 heads) → rp_story_meta
  /// 4. saveSnapshot (可选) → rp_snapshots
  Future<void> commitChanges({
    required List<RpEntryBlob> blobs,
    required RpOperation operation,
    required RpStoryMeta updatedMeta,
    RpSnapshot? snapshot,
  }) async {
    _ensureInitialized();

    // Step 1: 写入所有 blob
    final blobMap = {for (final blob in blobs) blob.blobId: blob};
    await _entryBlobsBox!.putAll(blobMap);

    // Step 2: 写入 Operation (权威日志)
    await _opsBox!.put(operation.key, operation);

    // Step 3: 更新 StoryMeta
    await _storyMetaBox!.put(updatedMeta.storyId, updatedMeta);

    // Step 4: 可选写入 Snapshot
    if (snapshot != null) {
      await _snapshotsBox!.put(snapshot.key, snapshot);
    }
  }

  // ==================== 清理操作 ====================

  /// 删除故事及其所有关联数据
  Future<void> deleteStoryWithData(String storyId) async {
    _ensureInitialized();

    // 删除 blobs (需要读取内容判断 storyId)
    final blobKeys = _entryBlobsBox!.keys
        .where((k) => _entryBlobsBox!.get(k)?.storyId == storyId)
        .toList();
    await _entryBlobsBox!.deleteAll(blobKeys);

    // 删除 operations (key 前缀匹配)
    final opKeys = _opsBox!.keys
        .where((k) => k.toString().startsWith('$storyId|'))
        .toList();
    await _opsBox!.deleteAll(opKeys);

    // 删除 snapshots (key 前缀匹配)
    final snapshotKeys = _snapshotsBox!.keys
        .where((k) => k.toString().startsWith('$storyId|'))
        .toList();
    await _snapshotsBox!.deleteAll(snapshotKeys);

    // 删除 proposals (需要读取内容判断 storyId)
    final proposalKeys = _proposalsBox!.keys
        .where((k) => _proposalsBox!.get(k)?.storyId == storyId)
        .toList();
    await _proposalsBox!.deleteAll(proposalKeys);

    // 删除 meta
    await _storyMetaBox!.delete(storyId);
  }
}
