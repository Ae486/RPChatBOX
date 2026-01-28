import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_task_spec.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_task_scheduler.dart';

void main() {
  group('RpTaskSpec', () {
    test('创建任务规格', () {
      final task = RpTaskSpec(
        taskId: 'task_001',
        storyId: 'story_001',
        branchId: 'main',
        dedupeKey: 'story_001|main|test',
        priority: RpTaskPriority.normal,
        requiredSourceRev: 5,
        requiredFoundationRev: 3,
        requiredStoryRev: 2,
        tasks: ['scene_detect'],
      );

      expect(task.taskId, 'task_001');
      expect(task.priority, RpTaskPriority.normal);
      expect(task.isUrgent, false);
      expect(task.isIdle, false);
    });

    test('isUrgent 和 isIdle', () {
      final urgent = RpTaskSpec(
        taskId: 'u1',
        storyId: 's1',
        branchId: 'b1',
        dedupeKey: 'd1',
        priority: RpTaskPriority.urgent,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: [],
      );
      expect(urgent.isUrgent, true);
      expect(urgent.isIdle, false);

      final idle = urgent.copyWith(
        taskId: 'i1',
        dedupeKey: 'd2',
        priority: RpTaskPriority.idle,
      );
      expect(idle.isUrgent, false);
      expect(idle.isIdle, true);
    });

    test('默认超时时间根据任务类型计算', () {
      final summarizeTask = RpTaskSpec(
        taskId: 't1',
        storyId: 's1',
        branchId: 'b1',
        dedupeKey: 'd1',
        priority: RpTaskPriority.idle,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: ['summarize'],
      );
      expect(summarizeTask.timeoutMs, 60000);

      final normalTask = RpTaskSpec(
        taskId: 't2',
        storyId: 's1',
        branchId: 'b1',
        dedupeKey: 'd2',
        priority: RpTaskPriority.normal,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: ['scene_detect'],
      );
      expect(normalTask.timeoutMs, 30000);
    });

    test('相等性比较基于 taskId', () {
      final t1 = RpTaskSpec(
        taskId: 'same_id',
        storyId: 's1',
        branchId: 'b1',
        dedupeKey: 'd1',
        priority: RpTaskPriority.normal,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: [],
      );

      final t2 = RpTaskSpec(
        taskId: 'same_id',
        storyId: 's2',
        branchId: 'b2',
        dedupeKey: 'd2',
        priority: RpTaskPriority.urgent,
        requiredSourceRev: 1,
        requiredFoundationRev: 1,
        requiredStoryRev: 1,
        tasks: ['different'],
      );

      expect(t1, equals(t2));
      expect(t1.hashCode, equals(t2.hashCode));
    });
  });

  group('RpTaskType', () {
    test('getDefaultPriority', () {
      expect(
        RpTaskType.getDefaultPriority(RpTaskType.consistencyHeavy),
        RpTaskPriority.urgent,
      );
      expect(
        RpTaskType.getDefaultPriority(RpTaskType.sceneDetect),
        RpTaskPriority.normal,
      );
      expect(
        RpTaskType.getDefaultPriority(RpTaskType.foreshadowLink),
        RpTaskPriority.idle,
      );
    });

    test('getDefaultTimeout', () {
      expect(RpTaskType.getDefaultTimeout(RpTaskType.summarize), 60000);
      expect(RpTaskType.getDefaultTimeout(RpTaskType.consistencyHeavy), 45000);
      expect(RpTaskType.getDefaultTimeout(RpTaskType.sceneDetect), 30000);
    });
  });

  group('RpTaskScheduler', () {
    late RpTaskScheduler scheduler;

    setUp(() {
      scheduler = RpTaskScheduler(maxQueueSize: 5);
    });

    RpTaskSpec createTask({
      required String taskId,
      RpTaskPriority priority = RpTaskPriority.normal,
      String dedupeKey = '',
      int? enqueuedAtMs,
    }) {
      return RpTaskSpec(
        taskId: taskId,
        storyId: 'story_001',
        branchId: 'main',
        dedupeKey: dedupeKey.isEmpty ? taskId : dedupeKey,
        priority: priority,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: ['test'],
        enqueuedAtMs: enqueuedAtMs,
      );
    }

    test('入队和出队', () {
      final task = createTask(taskId: 't1');
      scheduler.enqueue(task);

      expect(scheduler.queueLength, 1);
      expect(scheduler.isEmpty, false);

      final dequeued = scheduler.dequeue();
      expect(dequeued?.taskId, 't1');
      expect(scheduler.hasInFlight, true);
    });

    test('优先级排序：urgent > normal > idle', () {
      final idle = createTask(taskId: 'idle', priority: RpTaskPriority.idle);
      final normal = createTask(taskId: 'normal', priority: RpTaskPriority.normal);
      final urgent = createTask(taskId: 'urgent', priority: RpTaskPriority.urgent);

      // 以不同顺序入队
      scheduler.enqueue(idle);
      scheduler.enqueue(normal);
      scheduler.enqueue(urgent);

      // 出队顺序应该是 urgent, normal, idle
      expect(scheduler.dequeue()?.taskId, 'urgent');
      scheduler.complete('urgent');
      expect(scheduler.dequeue()?.taskId, 'normal');
      scheduler.complete('normal');
      expect(scheduler.dequeue()?.taskId, 'idle');
    });

    test('同优先级按入队时间排序（FIFO）', () {
      final t1 = createTask(taskId: 't1', enqueuedAtMs: 1000);
      final t2 = createTask(taskId: 't2', enqueuedAtMs: 2000);
      final t3 = createTask(taskId: 't3', enqueuedAtMs: 3000);

      scheduler.enqueue(t3);
      scheduler.enqueue(t1);
      scheduler.enqueue(t2);

      expect(scheduler.dequeue()?.taskId, 't1');
      scheduler.complete('t1');
      expect(scheduler.dequeue()?.taskId, 't2');
      scheduler.complete('t2');
      expect(scheduler.dequeue()?.taskId, 't3');
    });

    test('去重：相同 dedupeKey 只保留最新', () {
      final t1 = createTask(taskId: 't1', dedupeKey: 'same_key');
      final t2 = createTask(taskId: 't2', dedupeKey: 'same_key');

      scheduler.enqueue(t1);
      expect(scheduler.queueLength, 1);

      scheduler.enqueue(t2);
      expect(scheduler.queueLength, 1);

      final dequeued = scheduler.dequeue();
      expect(dequeued?.taskId, 't2');
    });

    test('出队时如果有执行中任务则返回 null', () {
      scheduler.enqueue(createTask(taskId: 't1'));
      scheduler.enqueue(createTask(taskId: 't2'));

      final first = scheduler.dequeue();
      expect(first?.taskId, 't1');

      // 未 complete，再次 dequeue 返回 null
      expect(scheduler.dequeue(), isNull);

      // complete 后可以继续 dequeue
      scheduler.complete('t1');
      expect(scheduler.dequeue()?.taskId, 't2');
    });

    test('背压处理：丢弃 idle 任务', () {
      // 填满队列
      for (int i = 0; i < 5; i++) {
        scheduler.enqueue(createTask(taskId: 'n$i'));
      }
      expect(scheduler.queueLength, 5);

      // 添加 idle 任务触发背压
      scheduler.enqueue(createTask(
        taskId: 'idle1',
        priority: RpTaskPriority.idle,
      ));

      // 队列应该保持在 maxQueueSize
      expect(scheduler.queueLength, lessThanOrEqualTo(5));
    });

    test('背压处理：urgent 任务不被丢弃', () {
      // 填满队列全是 urgent
      for (int i = 0; i < 5; i++) {
        scheduler.enqueue(createTask(
          taskId: 'u$i',
          priority: RpTaskPriority.urgent,
        ));
      }

      // 再添加一个 urgent
      scheduler.enqueue(createTask(
        taskId: 'u5',
        priority: RpTaskPriority.urgent,
      ));

      // 所有 urgent 都应该保留
      expect(scheduler.queueLength, 6);
    });

    test('取消任务', () {
      scheduler.enqueue(createTask(taskId: 't1'));
      scheduler.enqueue(createTask(taskId: 't2'));

      scheduler.cancel('t1');
      expect(scheduler.queueLength, 1);

      final dequeued = scheduler.dequeue();
      expect(dequeued?.taskId, 't2');
    });

    test('取消执行中的任务', () {
      scheduler.enqueue(createTask(taskId: 't1'));
      scheduler.dequeue();
      expect(scheduler.hasInFlight, true);

      scheduler.cancel('t1');
      expect(scheduler.hasInFlight, false);
    });

    test('清空队列', () {
      scheduler.enqueue(createTask(taskId: 't1'));
      scheduler.enqueue(createTask(taskId: 't2'));
      scheduler.dequeue();

      scheduler.clear();

      expect(scheduler.queueLength, 0);
      expect(scheduler.hasInFlight, false);
      expect(scheduler.isEmpty, true);
    });

    test('removeByStoryId', () {
      scheduler.enqueue(RpTaskSpec(
        taskId: 't1',
        storyId: 'story_a',
        branchId: 'main',
        dedupeKey: 'd1',
        priority: RpTaskPriority.normal,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: [],
      ));
      scheduler.enqueue(RpTaskSpec(
        taskId: 't2',
        storyId: 'story_b',
        branchId: 'main',
        dedupeKey: 'd2',
        priority: RpTaskPriority.normal,
        requiredSourceRev: 0,
        requiredFoundationRev: 0,
        requiredStoryRev: 0,
        tasks: [],
      ));

      scheduler.removeByStoryId('story_a');

      expect(scheduler.queueLength, 1);
      expect(scheduler.dequeue()?.taskId, 't2');
    });

    test('stats', () {
      scheduler.enqueue(createTask(taskId: 'u1', priority: RpTaskPriority.urgent));
      scheduler.enqueue(createTask(taskId: 'n1', priority: RpTaskPriority.normal));
      scheduler.enqueue(createTask(taskId: 'i1', priority: RpTaskPriority.idle));
      scheduler.dequeue(); // urgent in flight

      final stats = scheduler.stats;
      expect(stats.total, 2);
      expect(stats.urgent, 0); // dequeued
      expect(stats.normal, 1);
      expect(stats.idle, 1);
      expect(stats.hasInFlight, true);
    });
  });

  group('RpTaskSpecBuilder', () {
    late RpTaskSpecBuilder builder;

    setUp(() {
      builder = RpTaskSpecBuilder(
        storyId: 'story_001',
        branchId: 'main',
        sourceRev: 10,
        foundationRev: 5,
        storyRev: 8,
      );
    });

    test('buildTurnEndTask', () {
      final task = builder.buildTurnEndTask();

      expect(task.storyId, 'story_001');
      expect(task.branchId, 'main');
      expect(task.priority, RpTaskPriority.normal);
      expect(task.tasks, contains('scene_detect'));
      expect(task.tasks, contains('state_update'));
      expect(task.requiredSourceRev, 10);
    });

    test('buildConsistencyCheckTask', () {
      final task = builder.buildConsistencyCheckTask(
        messageId: 'msg_001',
        content: 'test content',
      );

      expect(task.priority, RpTaskPriority.urgent);
      expect(task.tasks, contains('consistency_heavy'));
      expect(task.inputs['messageId'], 'msg_001');
      expect(task.inputs['content'], 'test content');
    });

    test('buildIdleMaintenanceTask', () {
      final task = builder.buildIdleMaintenanceTask();

      expect(task.priority, RpTaskPriority.idle);
      expect(task.tasks, contains('foreshadow_link'));
      expect(task.tasks, contains('goals_update'));
    });

    test('buildSummarizeTask', () {
      final task = builder.buildSummarizeTask(
        targetLogicalId: 'rp:v1:ch:ent_001:card.base',
      );

      expect(task.priority, RpTaskPriority.idle);
      expect(task.tasks, contains('summarize'));
      expect(task.inputs['targetLogicalId'], 'rp:v1:ch:ent_001:card.base');
    });
  });
}
