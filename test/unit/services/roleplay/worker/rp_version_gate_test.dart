import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/models/roleplay/rp_story_meta.dart';
import 'package:chatboxapp/models/roleplay/rp_enums.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_task_spec.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_version_gate.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_worker_protocol.dart';

void main() {
  group('RpVersionGate', () {
    late RpStoryMeta meta;

    setUp(() {
      meta = RpStoryMeta(
        storyId: 'story_001',
        activeBranchId: 'main',
        sourceRev: 10,
        heads: [
          RpHead(
            scopeIndex: RpScope.foundation.index,
            branchId: RpVersionGate.foundationBranchId,
            rev: 5,
          ),
          RpHead(
            scopeIndex: RpScope.story.index,
            branchId: 'main',
            rev: 8,
          ),
        ],
      );
    });

    RpTaskSpec createTask({
      int sourceRev = 10,
      int foundationRev = 5,
      int storyRev = 8,
      String branchId = 'main',
    }) {
      return RpTaskSpec(
        taskId: 'task_001',
        storyId: 'story_001',
        branchId: branchId,
        dedupeKey: 'test',
        priority: RpTaskPriority.normal,
        requiredSourceRev: sourceRev,
        requiredFoundationRev: foundationRev,
        requiredStoryRev: storyRev,
        tasks: ['test'],
      );
    }

    test('foundationBranchId 常量', () {
      expect(RpVersionGate.foundationBranchId, '-');
    });

    group('isTaskStale', () {
      test('版本匹配时不过期', () {
        final task = createTask();
        expect(RpVersionGate.isTaskStale(task, meta), false);
      });

      test('sourceRev 过期', () {
        final task = createTask(sourceRev: 9);
        expect(RpVersionGate.isTaskStale(task, meta), true);
      });

      test('foundationRev 过期', () {
        final task = createTask(foundationRev: 4);
        expect(RpVersionGate.isTaskStale(task, meta), true);
      });

      test('storyRev 过期', () {
        final task = createTask(storyRev: 7);
        expect(RpVersionGate.isTaskStale(task, meta), true);
      });

      test('版本更新时不过期', () {
        final task = createTask(sourceRev: 11, foundationRev: 6, storyRev: 9);
        expect(RpVersionGate.isTaskStale(task, meta), false);
      });

      test('不同分支的 storyRev 检查', () {
        // 添加另一个分支的 head
        meta.heads.add(RpHead(
          scopeIndex: RpScope.story.index,
          branchId: 'branch_b',
          rev: 3,
        ));

        // branch_b 的任务应该检查 branch_b 的 head
        final task = createTask(branchId: 'branch_b', storyRev: 2);
        expect(RpVersionGate.isTaskStale(task, meta), true);

        final validTask = createTask(branchId: 'branch_b', storyRev: 3);
        expect(RpVersionGate.isTaskStale(validTask, meta), false);
      });
    });

    group('isResponseStale', () {
      test('使用原始请求的版本信息进行验证', () {
        final request = RpWorkerRequest(
          requestId: 'req_001',
          storyId: 'story_001',
          branchId: 'main',
          sourceRev: 10,
          foundationRev: 5,
          storyRev: 8,
          tasks: ['test'],
        );
        final response = RpWorkerResponse.success(requestId: 'req_001');

        expect(RpVersionGate.isResponseStale(response, request, meta), false);
      });

      test('meta 更新后响应过期', () {
        final request = RpWorkerRequest(
          requestId: 'req_001',
          storyId: 'story_001',
          branchId: 'main',
          sourceRev: 9, // 旧版本
          foundationRev: 5,
          storyRev: 8,
          tasks: ['test'],
        );
        final response = RpWorkerResponse.success(requestId: 'req_001');

        expect(RpVersionGate.isResponseStale(response, request, meta), true);
      });
    });

    group('getCurrentSnapshot', () {
      test('获取当前版本快照', () {
        final snapshot = RpVersionGate.getCurrentSnapshot(meta, 'main');

        expect(snapshot.sourceRev, 10);
        expect(snapshot.foundationRev, 5);
        expect(snapshot.storyRev, 8);
      });

      test('不存在的分支返回 0', () {
        final snapshot = RpVersionGate.getCurrentSnapshot(meta, 'nonexistent');

        expect(snapshot.sourceRev, 10);
        expect(snapshot.foundationRev, 5);
        expect(snapshot.storyRev, 0);
      });
    });

    group('compareSnapshots', () {
      test('相同快照返回 0', () {
        final a = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);
        final b = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);

        expect(RpVersionGate.compareSnapshots(a, b), 0);
      });

      test('sourceRev 不同时优先比较', () {
        final older = RpVersionSnapshot(sourceRev: 4, foundationRev: 10, storyRev: 10);
        final newer = RpVersionSnapshot(sourceRev: 5, foundationRev: 1, storyRev: 1);

        expect(RpVersionGate.compareSnapshots(older, newer), lessThan(0));
        expect(RpVersionGate.compareSnapshots(newer, older), greaterThan(0));
      });

      test('sourceRev 相同时比较 foundationRev', () {
        final older = RpVersionSnapshot(sourceRev: 5, foundationRev: 2, storyRev: 10);
        final newer = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 1);

        expect(RpVersionGate.compareSnapshots(older, newer), lessThan(0));
      });

      test('sourceRev 和 foundationRev 相同时比较 storyRev', () {
        final older = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 1);
        final newer = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);

        expect(RpVersionGate.compareSnapshots(older, newer), lessThan(0));
      });
    });
  });

  group('RpVersionSnapshot', () {
    test('toJson 和 fromJson', () {
      final original = RpVersionSnapshot(
        sourceRev: 10,
        foundationRev: 5,
        storyRev: 8,
      );

      final json = original.toJson();
      final restored = RpVersionSnapshot.fromJson(json);

      expect(restored.sourceRev, 10);
      expect(restored.foundationRev, 5);
      expect(restored.storyRev, 8);
    });

    test('zero 常量', () {
      expect(RpVersionSnapshot.zero.sourceRev, 0);
      expect(RpVersionSnapshot.zero.foundationRev, 0);
      expect(RpVersionSnapshot.zero.storyRev, 0);
    });

    test('isOlderThan', () {
      final older = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);
      final newer = RpVersionSnapshot(sourceRev: 6, foundationRev: 3, storyRev: 2);

      expect(older.isOlderThan(newer), true);
      expect(newer.isOlderThan(older), false);
      expect(older.isOlderThan(older), false);
    });

    test('isSameAs', () {
      final a = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);
      final b = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);
      final c = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 3);

      expect(a.isSameAs(b), true);
      expect(a.isSameAs(c), false);
    });

    test('相等性和 hashCode', () {
      final a = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);
      final b = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);

      expect(a, equals(b));
      expect(a.hashCode, equals(b.hashCode));
    });

    test('toString', () {
      final snapshot = RpVersionSnapshot(sourceRev: 5, foundationRev: 3, storyRev: 2);
      expect(snapshot.toString(), contains('src=5'));
      expect(snapshot.toString(), contains('fnd=3'));
      expect(snapshot.toString(), contains('sty=2'));
    });
  });

  group('RpVersionCheckResult', () {
    test('valid 常量', () {
      expect(RpVersionCheckResult.valid.isStale, false);
      expect(RpVersionCheckResult.valid.reason, isNull);
    });

    test('stale 工厂方法', () {
      final result = RpVersionCheckResult.stale(
        RpStaleReason.sourceRevOutdated,
        details: 'task.sourceRev=5 < meta.sourceRev=10',
      );

      expect(result.isStale, true);
      expect(result.reason, RpStaleReason.sourceRevOutdated);
      expect(result.details, contains('sourceRev'));
    });
  });

  group('RpVersionGateDetailed', () {
    test('checkTaskStale 返回详细原因', () {
      final meta = RpStoryMeta(
        storyId: 'story_001',
        activeBranchId: 'main',
        sourceRev: 10,
        heads: [
          RpHead(
            scopeIndex: RpScope.foundation.index,
            branchId: RpVersionGate.foundationBranchId,
            rev: 5,
          ),
        ],
      );

      final staleTask = RpTaskSpec(
        taskId: 't1',
        storyId: 'story_001',
        branchId: 'main',
        dedupeKey: 'd1',
        priority: RpTaskPriority.normal,
        requiredSourceRev: 8, // 过期
        requiredFoundationRev: 5,
        requiredStoryRev: 0,
        tasks: [],
      );

      final result = RpVersionGateDetailed.checkTaskStale(staleTask, meta);

      expect(result.isStale, true);
      expect(result.reason, RpStaleReason.sourceRevOutdated);
      expect(result.details, contains('8'));
      expect(result.details, contains('10'));
    });
  });
}
