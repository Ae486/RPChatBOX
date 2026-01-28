import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_registry.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_types.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/model_adapter.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/telemetry/agent_metrics.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_memory_snapshot.dart';

void main() {
  group('AgentRegistry', () {
    late AgentRegistry registry;

    setUp(() {
      registry = AgentRegistry();
    });

    test('registers and retrieves handler', () {
      registry.register('test_agent', (req) async {
        return AgentResult.success(agentId: req.agentId, proposals: []);
      });

      expect(registry.has('test_agent'), isTrue);
      expect(registry.get('test_agent'), isNotNull);
    });

    test('returns null for unregistered agent', () {
      expect(registry.has('unknown'), isFalse);
      expect(registry.get('unknown'), isNull);
    });

    test('executes registered agent', () async {
      registry.register('test_agent', (req) async {
        return AgentResult.success(
          agentId: req.agentId,
          proposals: [{'kind': 'TEST'}],
        );
      });

      final request = AgentRequest(
        agentId: 'test_agent',
        inputs: {},
        memoryReader: RpWorkerMemoryReader({}),
        modelId: 'test',
      );

      final result = await registry.execute(request);
      expect(result.ok, isTrue);
      expect(result.proposals.length, 1);
    });

    test('returns error for unregistered agent execution', () async {
      final request = AgentRequest(
        agentId: 'unknown',
        inputs: {},
        memoryReader: RpWorkerMemoryReader({}),
        modelId: 'test',
      );

      final result = await registry.execute(request);
      expect(result.ok, isFalse);
      expect(result.errorCode, isNotNull);
    });
  });

  group('ModelAdapter', () {
    late ModelAdapter adapter;

    setUp(() {
      adapter = ModelAdapter();
    });

    test('returns high tier for GPT-4', () {
      expect(adapter.getTier('gpt-4'), PromptTier.high);
      expect(adapter.getTier('gpt-4o'), PromptTier.high);
    });

    test('returns medium tier for GPT-3.5', () {
      expect(adapter.getTier('gpt-3.5-turbo'), PromptTier.medium);
    });

    test('returns high tier for Claude-3', () {
      expect(adapter.getTier('claude-3-opus'), PromptTier.high);
      expect(adapter.getTier('claude-3-sonnet'), PromptTier.high);
    });

    test('returns low tier for local models', () {
      expect(adapter.getTier('ollama'), PromptTier.low);
      expect(adapter.getTier('llama'), PromptTier.low);
    });

    test('returns medium tier for unknown models', () {
      expect(adapter.getTier('unknown-model'), PromptTier.medium);
    });

    test('identifies reliable JSON models', () {
      expect(adapter.isReliableJson('gpt-4'), isTrue);
      expect(adapter.isReliableJson('gpt-3.5'), isFalse);
      expect(adapter.isReliableJson('claude-3'), isTrue);
    });
  });

  group('AgentMetrics', () {
    late AgentMetrics metrics;

    setUp(() {
      metrics = AgentMetrics();
    });

    test('records success', () {
      metrics.recordSuccess('test', 100);
      metrics.recordSuccess('test', 200);

      expect(metrics.getSuccessCount('test'), 2);
      expect(metrics.getAvgDuration('test'), 150.0);
    });

    test('records failure', () {
      metrics.recordFailure('test', 'E101');
      metrics.recordFailure('test', 'E101');
      metrics.recordFailure('test', 'E102');

      expect(metrics.getFailureCount('test'), 3);
      final dist = metrics.getErrorDistribution('test');
      expect(dist['E101'], 2);
      expect(dist['E102'], 1);
    });

    test('calculates success rate', () {
      metrics.recordSuccess('test', 100);
      metrics.recordSuccess('test', 100);
      metrics.recordFailure('test', 'E101');

      expect(metrics.getSuccessRate('test'), closeTo(0.666, 0.01));
    });

    test('records repair stages', () {
      metrics.recordRepairStage('test', 0);
      metrics.recordRepairStage('test', 0);
      metrics.recordRepairStage('test', 3);

      final dist = metrics.getRepairStageDistribution('test');
      expect(dist[0], 2);
      expect(dist[3], 1);
    });

    test('exports all metrics', () {
      metrics.recordSuccess('agent1', 100);
      metrics.recordFailure('agent2', 'E101');

      final exported = metrics.exportAll();
      expect(exported.containsKey('agent1'), isTrue);
      expect(exported.containsKey('agent2'), isTrue);
    });
  });

  group('AgentResult', () {
    test('creates success result', () {
      final result = AgentResult.success(
        agentId: 'test',
        proposals: [{'kind': 'TEST'}],
      );

      expect(result.ok, isTrue);
      expect(result.proposals.length, 1);
      expect(result.errorCode, isNull);
    });

    test('creates failed result', () {
      final result = AgentResult.failed(
        agentId: 'test',
        errorCode: 'E101',
        errorMessage: 'Test error',
      );

      expect(result.ok, isFalse);
      expect(result.proposals, isEmpty);
      expect(result.errorCode, 'E101');
    });

    test('serializes to JSON', () {
      final result = AgentResult.success(
        agentId: 'test',
        proposals: [{'kind': 'TEST'}],
      );

      final json = result.toJson();
      expect(json['ok'], isTrue);
      expect(json['agentId'], 'test');
      expect(json['proposals'], isNotEmpty);
    });
  });
}
