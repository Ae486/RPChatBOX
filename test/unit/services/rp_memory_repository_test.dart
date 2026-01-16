import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:chatboxapp/models/roleplay/rp_story_meta.dart';
import 'package:chatboxapp/models/roleplay/rp_entry_blob.dart';
import 'package:chatboxapp/models/roleplay/rp_operation.dart';
import 'package:chatboxapp/models/roleplay/rp_snapshot.dart';
import 'package:chatboxapp/models/roleplay/rp_proposal.dart';
import 'package:chatboxapp/models/roleplay/rp_enums.dart';
import 'package:chatboxapp/services/roleplay/rp_memory_repository.dart';
import 'dart:io';
import '../../helpers/rp_test_data.dart';

/// RpMemoryRepository 单元测试
///
/// 测试 Roleplay 数据持久化功能：
/// - 初始化和关闭
/// - StoryMeta CRUD
/// - EntryBlob CRUD
/// - Operation CRUD
/// - Snapshot CRUD
/// - Proposal CRUD
/// - 事务性写入
/// - 级联删除
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RpMemoryRepository', () {
    late RpMemoryRepository repository;
    late Directory tempDirectory;

    setUp(() async {
      tempDirectory = await Directory.systemTemp.createTemp('rp_memory_test_');
      Hive.init(tempDirectory.path);
      repository = RpMemoryRepository();
    });

    tearDown(() async {
      await repository.close();
      await Hive.close();
      await tempDirectory.delete(recursive: true);
    });

    // ==================== 初始化测试 ====================
    group('initialize', () {
      test('should initialize and open all boxes', () async {
        await repository.initialize();

        expect(repository.isInitialized, isTrue);
        expect(Hive.isBoxOpen('rp_story_meta'), isTrue);
        expect(Hive.isBoxOpen('rp_entry_blobs'), isTrue);
        expect(Hive.isBoxOpen('rp_ops'), isTrue);
        expect(Hive.isBoxOpen('rp_snapshots'), isTrue);
        expect(Hive.isBoxOpen('rp_proposals'), isTrue);
      });

      test('should be idempotent (multiple calls succeed)', () async {
        await repository.initialize();
        await expectLater(repository.initialize(), completes);
        expect(repository.isInitialized, isTrue);
      });

      test('should handle concurrent initialization calls', () async {
        final futures = [
          repository.initialize(),
          repository.initialize(),
          repository.initialize(),
        ];
        await Future.wait(futures);
        expect(repository.isInitialized, isTrue);
      });
    });

    // ==================== close 测试 ====================
    group('close', () {
      test('should close all boxes and reset state', () async {
        await repository.initialize();
        await repository.close();

        expect(repository.isInitialized, isFalse);
      });

      test('should allow re-initialization after close', () async {
        await repository.initialize();
        await repository.close();
        await repository.initialize();

        expect(repository.isInitialized, isTrue);
      });
    });

    // ==================== StoryMeta CRUD ====================
    group('StoryMeta CRUD', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should save and retrieve StoryMeta', () async {
        final meta = RpTestData.createStoryMeta(storyId: 'story-001');

        await repository.saveStoryMeta(meta);
        final retrieved = await repository.getStoryMeta('story-001');

        expect(retrieved, isNotNull);
        expect(retrieved!.storyId, equals('story-001'));
        expect(retrieved.activeBranchId, equals('main'));
        expect(retrieved.heads.length, equals(2));
      });

      test('should return null for non-existent StoryMeta', () async {
        final result = await repository.getStoryMeta('non-existent');
        expect(result, isNull);
      });

      test('should delete StoryMeta', () async {
        final meta = RpTestData.createStoryMeta(storyId: 'story-to-delete');
        await repository.saveStoryMeta(meta);
        await repository.deleteStoryMeta('story-to-delete');

        final result = await repository.getStoryMeta('story-to-delete');
        expect(result, isNull);
      });

      test('should list all stories', () async {
        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: 's1'));
        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: 's2'));
        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: 's3'));

        final stories = await repository.listAllStories();
        expect(stories.length, equals(3));
        expect(stories.map((s) => s.storyId).toSet(), equals({'s1', 's2', 's3'}));
      });

      test('should update existing StoryMeta', () async {
        final meta = RpTestData.createStoryMeta(storyId: 'story-update');
        await repository.saveStoryMeta(meta);

        meta.activeBranchId = 'branch-new';
        await repository.saveStoryMeta(meta);

        final retrieved = await repository.getStoryMeta('story-update');
        expect(retrieved!.activeBranchId, equals('branch-new'));
      });
    });

    // ==================== EntryBlob CRUD ====================
    group('EntryBlob CRUD', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should save and retrieve blob', () async {
        final blob = RpTestData.createBlob(
          blobId: 'blob-001',
          storyId: 'story-001',
          logicalId: 'rp:v1:scene:main:state',
        );

        await repository.saveBlob(blob);
        final retrieved = await repository.getBlob('blob-001');

        expect(retrieved, isNotNull);
        expect(retrieved!.blobId, equals('blob-001'));
        expect(retrieved.storyId, equals('story-001'));
        expect(retrieved.domain, equals('scene'));
      });

      test('should save multiple blobs in batch', () async {
        final blobs = [
          RpTestData.createBlob(blobId: 'b1', storyId: 's1'),
          RpTestData.createBlob(blobId: 'b2', storyId: 's1'),
          RpTestData.createBlob(blobId: 'b3', storyId: 's1'),
        ];

        await repository.saveBlobs(blobs);

        for (final id in ['b1', 'b2', 'b3']) {
          final blob = await repository.getBlob(id);
          expect(blob, isNotNull);
        }
      });

      test('should get blobs by storyId', () async {
        await repository.saveBlobs([
          RpTestData.createBlob(blobId: 'b1', storyId: 'story-A'),
          RpTestData.createBlob(blobId: 'b2', storyId: 'story-A'),
          RpTestData.createBlob(blobId: 'b3', storyId: 'story-B'),
        ]);

        final blobsA = await repository.getBlobsByStory('story-A');
        expect(blobsA.length, equals(2));

        final blobsB = await repository.getBlobsByStory('story-B');
        expect(blobsB.length, equals(1));
      });

      test('should get blobs by logicalId', () async {
        await repository.saveBlobs([
          RpTestData.createBlob(blobId: 'v1', storyId: 's1', logicalId: 'lid-1'),
          RpTestData.createBlob(blobId: 'v2', storyId: 's1', logicalId: 'lid-1'),
          RpTestData.createBlob(blobId: 'v3', storyId: 's1', logicalId: 'lid-2'),
        ]);

        final blobs = await repository.getBlobsByLogicalId('s1', 'lid-1');
        expect(blobs.length, equals(2));
      });

      test('should delete blob', () async {
        final blob = RpTestData.createBlob(blobId: 'to-delete');
        await repository.saveBlob(blob);
        await repository.deleteBlob('to-delete');

        final result = await repository.getBlob('to-delete');
        expect(result, isNull);
      });
    });

    // ==================== Operation CRUD ====================
    group('Operation CRUD', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should save and retrieve operation', () async {
        final op = RpTestData.createOperation(
          storyId: 'story-001',
          scopeIndex: 1,
          branchId: 'main',
          rev: 5,
        );

        await repository.saveOperation(op);
        final retrieved = await repository.getOperation('story-001', 1, 'main', 5);

        expect(retrieved, isNotNull);
        expect(retrieved!.rev, equals(5));
        expect(retrieved.changes.length, equals(1));
      });

      test('should return null for non-existent operation', () async {
        final result = await repository.getOperation('none', 0, 'main', 999);
        expect(result, isNull);
      });

      test('should get operation range', () async {
        for (int i = 1; i <= 10; i++) {
          await repository.saveOperation(RpTestData.createOperation(
            storyId: 'story-001',
            rev: i,
          ));
        }

        final range = await repository.getOperationRange('story-001', 1, 'main', 3, 7);
        expect(range.length, equals(5));
        expect(range.map((o) => o.rev).toList(), equals([3, 4, 5, 6, 7]));
      });

      test('should get operations by story', () async {
        await repository.saveOperation(RpTestData.createOperation(storyId: 's1', rev: 1));
        await repository.saveOperation(RpTestData.createOperation(storyId: 's1', rev: 2));
        await repository.saveOperation(RpTestData.createOperation(storyId: 's2', rev: 1));

        final ops = await repository.getOperationsByStory('s1');
        expect(ops.length, equals(2));
      });
    });

    // ==================== Snapshot CRUD ====================
    group('Snapshot CRUD', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should save and retrieve snapshot', () async {
        final snapshot = RpTestData.createSnapshot(
          storyId: 'story-001',
          scopeIndex: 1,
          branchId: 'main',
          rev: 10,
        );

        await repository.saveSnapshot(snapshot);
        final retrieved = await repository.getSnapshot('story-001', 1, 'main', 10);

        expect(retrieved, isNotNull);
        expect(retrieved!.rev, equals(10));
        expect(retrieved.pointers.containsKey('rp:v1:scene:main:state'), isTrue);
      });

      test('should get latest snapshot from StoryMeta head', () async {
        // 设置 StoryMeta 指向最新快照
        final meta = RpTestData.createStoryMeta(
          storyId: 'story-001',
          heads: [
            RpHead(scopeIndex: 1, branchId: 'main', rev: 15, lastSnapshotRev: 10),
          ],
        );
        await repository.saveStoryMeta(meta);

        // 保存快照
        await repository.saveSnapshot(RpTestData.createSnapshot(
          storyId: 'story-001',
          rev: 5,
        ));
        await repository.saveSnapshot(RpTestData.createSnapshot(
          storyId: 'story-001',
          rev: 10,
        ));

        final latest = await repository.getLatestSnapshot('story-001', 1, 'main');
        expect(latest, isNotNull);
        expect(latest!.rev, equals(10));
      });

      test('should fallback to scanning when head not set', () async {
        // 无 StoryMeta，靠扫描
        await repository.saveSnapshot(RpTestData.createSnapshot(rev: 3));
        await repository.saveSnapshot(RpTestData.createSnapshot(rev: 7));
        await repository.saveSnapshot(RpTestData.createSnapshot(rev: 5));

        final latest = await repository.getLatestSnapshot(
          RpTestData.defaultStoryId,
          1,
          'main',
        );
        expect(latest, isNotNull);
        expect(latest!.rev, equals(7));
      });
    });

    // ==================== Proposal CRUD ====================
    group('Proposal CRUD', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should save and retrieve proposal', () async {
        final proposal = RpTestData.createProposal(proposalId: 'prop-001');

        await repository.saveProposal(proposal);
        final retrieved = await repository.getProposal('prop-001');

        expect(retrieved, isNotNull);
        expect(retrieved!.proposalId, equals('prop-001'));
        expect(retrieved.isPending, isTrue);
      });

      test('should get pending proposals', () async {
        await repository.saveProposal(RpTestData.createProposal(
          proposalId: 'p1',
          storyId: 's1',
          decisionIndex: 0, // pending
        ));
        await repository.saveProposal(RpTestData.createProposal(
          proposalId: 'p2',
          storyId: 's1',
          decisionIndex: 1, // applied
        ));
        await repository.saveProposal(RpTestData.createProposal(
          proposalId: 'p3',
          storyId: 's1',
          decisionIndex: 0, // pending
        ));

        final pending = await repository.getPendingProposals('s1');
        expect(pending.length, equals(2));
      });

      test('should update proposal decision', () async {
        await repository.saveProposal(RpTestData.createProposal(proposalId: 'prop-update'));

        await repository.updateProposalDecision(
          'prop-update',
          RpProposalDecision.applied,
          decidedBy: 'user',
          decisionNote: 'Approved by user',
        );

        final updated = await repository.getProposal('prop-update');
        expect(updated!.isApplied, isTrue);
        expect(updated.decidedBy, equals('user'));
        expect(updated.decisionNote, equals('Approved by user'));
      });

      test('should delete proposal', () async {
        await repository.saveProposal(RpTestData.createProposal(proposalId: 'to-delete'));
        await repository.deleteProposal('to-delete');

        final result = await repository.getProposal('to-delete');
        expect(result, isNull);
      });
    });

    // ==================== 事务性写入测试 ====================
    group('commitChanges', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should atomically commit blobs, operation, meta, and snapshot', () async {
        final blobs = [
          RpTestData.createBlob(blobId: 'commit-b1'),
          RpTestData.createBlob(blobId: 'commit-b2'),
        ];
        final operation = RpTestData.createOperation(rev: 1);
        final meta = RpTestData.createStoryMeta();
        final snapshot = RpTestData.createSnapshot(rev: 1);

        await repository.commitChanges(
          blobs: blobs,
          operation: operation,
          updatedMeta: meta,
          snapshot: snapshot,
        );

        // 验证所有数据都已写入
        expect(await repository.getBlob('commit-b1'), isNotNull);
        expect(await repository.getBlob('commit-b2'), isNotNull);
        expect(await repository.getOperation(
          RpTestData.defaultStoryId, 1, 'main', 1,
        ), isNotNull);
        expect(await repository.getStoryMeta(RpTestData.defaultStoryId), isNotNull);
        expect(await repository.getSnapshot(
          RpTestData.defaultStoryId, 1, 'main', 1,
        ), isNotNull);
      });

      test('should work without snapshot (optional)', () async {
        await repository.commitChanges(
          blobs: [RpTestData.createBlob(blobId: 'no-snap-blob')],
          operation: RpTestData.createOperation(rev: 2),
          updatedMeta: RpTestData.createStoryMeta(),
        );

        expect(await repository.getBlob('no-snap-blob'), isNotNull);
      });
    });

    // ==================== 级联删除测试 ====================
    group('deleteStoryWithData', () {
      setUp(() async {
        await repository.initialize();
      });

      test('should delete story and all associated data', () async {
        const storyId = 'story-to-cascade-delete';

        // 创建关联数据
        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: storyId));
        await repository.saveBlobs([
          RpTestData.createBlob(blobId: 'del-b1', storyId: storyId),
          RpTestData.createBlob(blobId: 'del-b2', storyId: storyId),
        ]);
        await repository.saveOperation(RpTestData.createOperation(storyId: storyId, rev: 1));
        await repository.saveOperation(RpTestData.createOperation(storyId: storyId, rev: 2));
        await repository.saveSnapshot(RpTestData.createSnapshot(storyId: storyId, rev: 1));
        await repository.saveProposal(RpTestData.createProposal(
          proposalId: 'del-prop-1',
          storyId: storyId,
        ));

        // 执行级联删除
        await repository.deleteStoryWithData(storyId);

        // 验证所有数据都已删除
        expect(await repository.getStoryMeta(storyId), isNull);
        expect(await repository.getBlob('del-b1'), isNull);
        expect(await repository.getBlob('del-b2'), isNull);
        expect(await repository.getOperation(storyId, 1, 'main', 1), isNull);
        expect(await repository.getOperation(storyId, 1, 'main', 2), isNull);
        expect(await repository.getSnapshot(storyId, 1, 'main', 1), isNull);
        expect(await repository.getProposal('del-prop-1'), isNull);
      });

      test('should not affect other stories', () async {
        // 创建两个故事
        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: 'keep'));
        await repository.saveBlob(RpTestData.createBlob(blobId: 'keep-blob', storyId: 'keep'));

        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: 'delete'));
        await repository.saveBlob(RpTestData.createBlob(blobId: 'del-blob', storyId: 'delete'));

        // 只删除一个
        await repository.deleteStoryWithData('delete');

        // 验证另一个仍存在
        expect(await repository.getStoryMeta('keep'), isNotNull);
        expect(await repository.getBlob('keep-blob'), isNotNull);
      });
    });

    // ==================== 边界条件测试 ====================
    group('edge cases', () {
      test('should throw StateError when not initialized', () async {
        expect(
          () => repository.getStoryMeta('any'),
          throwsA(isA<StateError>()),
        );
      });

      test('should handle empty lists gracefully', () async {
        await repository.initialize();

        final stories = await repository.listAllStories();
        expect(stories, isEmpty);

        final pending = await repository.getPendingProposals('none');
        expect(pending, isEmpty);
      });

      test('should handle special characters in IDs', () async {
        await repository.initialize();

        const specialId = 'story|with|pipes';
        await repository.saveStoryMeta(RpTestData.createStoryMeta(storyId: specialId));

        final retrieved = await repository.getStoryMeta(specialId);
        expect(retrieved, isNotNull);
        expect(retrieved!.storyId, equals(specialId));
      });
    });
  });
}
