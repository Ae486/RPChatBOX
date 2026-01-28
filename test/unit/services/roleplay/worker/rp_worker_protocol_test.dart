import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_worker_protocol.dart';

void main() {
  group('RpWorkerEnvelope', () {
    test('序列化和反序列化 request envelope', () {
      final request = RpWorkerRequest(
        requestId: 'req_001',
        storyId: 'story_001',
        branchId: 'main',
        sourceRev: 5,
        foundationRev: 3,
        storyRev: 2,
        tasks: ['scene_detect', 'state_update'],
        inputs: {'key': 'value'},
        memorySnapshot: {'meta': {}},
        timeoutMs: 30000,
      );

      final envelope = RpWorkerEnvelope.request(request);
      final json = envelope.toJson();
      final restored = RpWorkerEnvelope.fromJson(json);

      expect(restored.type, RpMessageType.request);
      expect(restored.schemaVersion, kRpWorkerProtocolVersion);
      expect(restored.payload['requestId'], 'req_001');
      expect(restored.payload['tasks'], ['scene_detect', 'state_update']);
    });

    test('序列化和反序列化 response envelope', () {
      final response = RpWorkerResponse.success(
        requestId: 'req_001',
        proposals: [
          {'type': 'state_update', 'data': {}}
        ],
        logs: [
          {'level': 'info', 'message': 'test'}
        ],
        metrics: RpWorkerMetrics(
          durationMs: 1000,
          llmCallCount: 2,
          inputTokens: 500,
          outputTokens: 200,
        ),
      );

      final envelope = RpWorkerEnvelope.response(response);
      final json = envelope.toJson();
      final restored = RpWorkerEnvelope.fromJson(json);

      expect(restored.type, RpMessageType.response);
      expect(restored.payload['ok'], true);
      expect(restored.payload['proposals'], hasLength(1));
    });

    test('序列化和反序列化 control envelope', () {
      final control = RpWorkerControl.cancel('req_001');
      final envelope = RpWorkerEnvelope.control(control);
      final json = envelope.toJson();
      final restored = RpWorkerEnvelope.fromJson(json);

      expect(restored.type, RpMessageType.control);
      expect(restored.payload['controlType'], RpWorkerControlType.cancel);
      expect(restored.payload['data']['requestId'], 'req_001');
    });
  });

  group('RpWorkerRequest', () {
    test('创建请求并序列化', () {
      final request = RpWorkerRequest(
        requestId: 'req_002',
        storyId: 'story_001',
        branchId: 'branch_a',
        sourceRev: 10,
        foundationRev: 5,
        storyRev: 8,
        tasks: ['consistency_heavy'],
        inputs: {'messageId': 'msg_001', 'content': 'test content'},
        timeoutMs: 45000,
      );

      final json = request.toJson();
      final restored = RpWorkerRequest.fromJson(json);

      expect(restored.requestId, 'req_002');
      expect(restored.storyId, 'story_001');
      expect(restored.branchId, 'branch_a');
      expect(restored.sourceRev, 10);
      expect(restored.foundationRev, 5);
      expect(restored.storyRev, 8);
      expect(restored.tasks, ['consistency_heavy']);
      expect(restored.inputs['messageId'], 'msg_001');
      expect(restored.timeoutMs, 45000);
    });

    test('默认值处理', () {
      final json = {
        'requestId': 'req_003',
        'storyId': 'story_001',
        'branchId': 'main',
        'sourceRev': 1,
        'foundationRev': 0,
        'storyRev': 0,
        'tasks': <String>[],
      };

      final request = RpWorkerRequest.fromJson(json);

      expect(request.inputs, isEmpty);
      expect(request.memorySnapshot, isEmpty);
      expect(request.timeoutMs, 30000);
    });
  });

  group('RpWorkerResponse', () {
    test('创建成功响应', () {
      final response = RpWorkerResponse.success(
        requestId: 'req_001',
        proposals: [
          {'kind': 'confirmedWrite'}
        ],
      );

      expect(response.ok, true);
      expect(response.error, isNull);
      expect(response.proposals, hasLength(1));
    });

    test('创建错误响应', () {
      final response = RpWorkerResponse.error(
        requestId: 'req_001',
        error: 'Something went wrong',
        stackTrace: 'at line 42',
      );

      expect(response.ok, false);
      expect(response.error, 'Something went wrong');
      expect(response.stackTrace, 'at line 42');
      expect(response.proposals, isEmpty);
    });

    test('序列化保留所有字段', () {
      final response = RpWorkerResponse(
        requestId: 'req_001',
        ok: true,
        proposals: [
          {'a': 1}
        ],
        logs: [
          {'b': 2}
        ],
        metrics: RpWorkerMetrics(
          durationMs: 500,
          llmCallCount: 1,
          inputTokens: 100,
          outputTokens: 50,
        ),
      );

      final json = response.toJson();
      final restored = RpWorkerResponse.fromJson(json);

      expect(restored.requestId, 'req_001');
      expect(restored.ok, true);
      expect(restored.proposals, hasLength(1));
      expect(restored.logs, hasLength(1));
      expect(restored.metrics.durationMs, 500);
      expect(restored.metrics.llmCallCount, 1);
    });
  });

  group('RpWorkerControl', () {
    test('创建各类控制消息', () {
      expect(RpWorkerControl.ready().controlType, RpWorkerControlType.ready);
      expect(RpWorkerControl.shutdown().controlType, RpWorkerControlType.shutdown);
      expect(RpWorkerControl.ping().controlType, RpWorkerControlType.ping);
      expect(RpWorkerControl.pong().controlType, RpWorkerControlType.pong);

      final cancel = RpWorkerControl.cancel('req_123');
      expect(cancel.controlType, RpWorkerControlType.cancel);
      expect(cancel.data?['requestId'], 'req_123');
    });
  });

  group('RpWorkerMetrics', () {
    test('序列化和反序列化', () {
      final metrics = RpWorkerMetrics(
        durationMs: 1234,
        llmCallCount: 3,
        inputTokens: 1000,
        outputTokens: 500,
      );

      final json = metrics.toJson();
      final restored = RpWorkerMetrics.fromJson(json);

      expect(restored.durationMs, 1234);
      expect(restored.llmCallCount, 3);
      expect(restored.inputTokens, 1000);
      expect(restored.outputTokens, 500);
    });

    test('copyWith', () {
      final metrics = RpWorkerMetrics(durationMs: 100);
      final updated = metrics.copyWith(llmCallCount: 5);

      expect(updated.durationMs, 100);
      expect(updated.llmCallCount, 5);
    });
  });

  group('RpWorkerSerializer', () {
    test('估算 JSON 大小', () {
      final data = {'key': 'value', 'number': 123};
      final size = RpWorkerSerializer.estimateJsonSize(data);

      expect(size, greaterThan(0));
    });

    test('检查快照是否超过大小限制', () {
      final smallSnapshot = {'a': 'b'};
      expect(RpWorkerSerializer.isSnapshotOversized(smallSnapshot), false);

      // 创建一个大快照
      final largeSnapshot = <String, dynamic>{};
      for (int i = 0; i < 10000; i++) {
        largeSnapshot['key_$i'] = 'value_$i' * 100;
      }
      expect(RpWorkerSerializer.isSnapshotOversized(largeSnapshot), true);
    });
  });

  group('Exceptions', () {
    test('RpWorkerException', () {
      final exception = RpWorkerException('Test error', 'stack trace');
      expect(exception.message, 'Test error');
      expect(exception.stackTrace, 'stack trace');
      expect(exception.toString(), contains('Test error'));
    });

    test('RpWorkerTimeoutException', () {
      final exception = RpWorkerTimeoutException(
        'req_001',
        const Duration(seconds: 30),
      );
      expect(exception.timeout, const Duration(seconds: 30));
      expect(exception.message, contains('req_001'));
      expect(exception.message, contains('30000ms'));
    });
  });
}
