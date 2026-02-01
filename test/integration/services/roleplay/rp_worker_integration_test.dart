import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_worker_protocol.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_memory_snapshot.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_registry.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_types.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_executor.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/proposal_transformer.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/model_adapter.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_pipeline.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/output/output_truncator.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/telemetry/agent_metrics.dart';

void main() {
  group('RpWorkerProtocol', () {
    group('Envelope serialization', () {
      test('request envelope round-trips correctly', () {
        final request = RpWorkerRequest(
          requestId: 'req_001',
          storyId: 'story_001',
          branchId: 'main',
          sourceRev: 1,
          foundationRev: 1,
          storyRev: 1,
          tasks: ['scene_detector', 'state_updater'],
          inputs: {'modelId': 'gpt-4'},
          memorySnapshot: {'entries': {}},
        );

        final envelope = RpWorkerEnvelope.request(request);
        final json = envelope.toJson();
        final restored = RpWorkerEnvelope.fromJson(json);

        expect(restored.type, RpMessageType.request);
        expect(restored.schemaVersion, kRpWorkerProtocolVersion);

        final restoredRequest = RpWorkerRequest.fromJson(restored.payload);
        expect(restoredRequest.requestId, 'req_001');
        expect(restoredRequest.tasks, ['scene_detector', 'state_updater']);
      });

      test('response envelope round-trips correctly', () {
        final response = RpWorkerResponse.success(
          requestId: 'req_001',
          proposals: [
            {'kind': 'SCENE_TRANSITION', 'domain': 'scene'},
          ],
          logs: [
            {'level': 'info', 'message': 'Task started'},
          ],
          metrics: RpWorkerMetrics(
            durationMs: 1500,
            llmCallCount: 1,
          ),
        );

        final envelope = RpWorkerEnvelope.response(response);
        final json = envelope.toJson();
        final restored = RpWorkerEnvelope.fromJson(json);

        expect(restored.type, RpMessageType.response);

        final restoredResponse = RpWorkerResponse.fromJson(restored.payload);
        expect(restoredResponse.ok, isTrue);
        expect(restoredResponse.proposals, hasLength(1));
        expect(restoredResponse.metrics.durationMs, 1500);
      });

      test('control envelope round-trips correctly', () {
        final control = RpWorkerControl.llmRequest(
          callId: 'llm_001',
          systemPrompt: 'You are a scene detector',
          userPrompt: 'Analyze this scene',
          modelId: 'gpt-4',
        );

        final envelope = RpWorkerEnvelope.control(control);
        final json = envelope.toJson();
        final restored = RpWorkerEnvelope.fromJson(json);

        expect(restored.type, RpMessageType.control);

        final restoredControl = RpWorkerControl.fromJson(restored.payload);
        expect(restoredControl.controlType, RpWorkerControlType.llmRequest);
        expect(restoredControl.data?['callId'], 'llm_001');
      });
    });

    group('Control messages', () {
      test('cancel message has correct format', () {
        final cancel = RpWorkerControl.cancel('req_001');
        expect(cancel.controlType, RpWorkerControlType.cancel);
        expect(cancel.data?['requestId'], 'req_001');
      });

      test('ping/pong messages', () {
        final ping = RpWorkerControl.ping();
        final pong = RpWorkerControl.pong();

        expect(ping.controlType, RpWorkerControlType.ping);
        expect(pong.controlType, RpWorkerControlType.pong);
      });

      test('shutdown message', () {
        final shutdown = RpWorkerControl.shutdown();
        expect(shutdown.controlType, RpWorkerControlType.shutdown);
      });

      test('LLM response message', () {
        final llmResponse = RpWorkerControl.llmResponse(
          callId: 'llm_001',
          ok: true,
          output: '{"detected": false}',
        );

        expect(llmResponse.controlType, RpWorkerControlType.llmResponse);
        expect(llmResponse.data?['ok'], isTrue);
        expect(llmResponse.data?['output'], '{"detected": false}');
      });
    });

    group('Progress reporting', () {
      test('progress message serialization', () {
        final progress = RpWorkerProgress(
          requestId: 'req_001',
          stageCode: RpTaskStage.analyzing.code,
          attempt: 1,
        );

        final json = progress.toJson();
        final restored = RpWorkerProgress.fromJson(json);

        expect(restored.requestId, 'req_001');
        expect(restored.stage, RpTaskStage.analyzing);
        expect(restored.attempt, 1);
      });

      test('all task stages have display names', () {
        for (final stage in RpTaskStage.values) {
          expect(stage.displayName, isNotEmpty);
          expect(stage.code, isNotEmpty);
        }
      });
    });

    group('Metrics', () {
      test('metrics serialization', () {
        final metrics = RpWorkerMetrics(
          durationMs: 2500,
          llmCallCount: 3,
          inputTokens: 1000,
          outputTokens: 500,
        );

        final json = metrics.toJson();
        final restored = RpWorkerMetrics.fromJson(json);

        expect(restored.durationMs, 2500);
        expect(restored.llmCallCount, 3);
        expect(restored.inputTokens, 1000);
        expect(restored.outputTokens, 500);
      });

      test('metrics copyWith', () {
        final metrics = RpWorkerMetrics(durationMs: 1000);
        final updated = metrics.copyWith(llmCallCount: 5);

        expect(updated.durationMs, 1000);
        expect(updated.llmCallCount, 5);
      });
    });
  });

  group('Agent Routing Integration', () {
    late AgentRegistry registry;
    late ProposalTransformerRegistry transformerRegistry;
    late AgentMetrics metrics;

    setUp(() {
      registry = AgentRegistry();
      initDefaultAgents(registry);

      transformerRegistry = ProposalTransformerRegistry();
      initDefaultTransformers(transformerRegistry);

      metrics = AgentMetrics();
    });

    AgentExecutor createExecutor({
      required Future<String> Function({
        required String systemPrompt,
        required String userPrompt,
        required String modelId,
        int? maxTokens,
        double? temperature,
      }) llmCall,
    }) {
      return AgentExecutor(
        registry: registry,
        transformerRegistry: transformerRegistry,
        modelAdapter: ModelAdapter(),
        jsonPipeline: JsonPipeline(),
        truncator: OutputTruncator(),
        metrics: metrics,
        llmCall: llmCall,
      );
    }

    RpWorkerMemoryReader createMemoryReader() {
      return RpWorkerMemoryReader({
        'meta': {
          'storyId': 'test_story',
          'activeBranchId': 'main',
          'sourceRev': 1,
        },
        'version': {
          'sourceRev': 1,
          'foundationRev': 1,
          'storyRev': 1,
        },
        'entries': {},
        'recentMessages': [
          {'role': 'assistant', 'content': 'They walked into the forest.'},
        ],
      });
    }

    test('all 4 agents are registered', () {
      expect(registry.has('scene_detector'), isTrue);
      expect(registry.has('state_updater'), isTrue);
      expect(registry.has('key_event_extractor'), isTrue);
      expect(registry.has('consistency_heavy'), isTrue);
    });

    test('all 4 transformers are registered', () {
      expect(transformerRegistry.has('scene_detector'), isTrue);
      expect(transformerRegistry.has('state_updater'), isTrue);
      expect(transformerRegistry.has('key_event_extractor'), isTrue);
      expect(transformerRegistry.has('consistency_heavy'), isTrue);
    });

    test('agent descriptors have valid configuration', () {
      final agents = ['scene_detector', 'state_updater', 'key_event_extractor', 'consistency_heavy'];

      for (final agentId in agents) {
        final descriptor = registry.get(agentId);
        expect(descriptor, isNotNull, reason: 'Agent $agentId should exist');
        expect(descriptor!.promptKey, isNotEmpty, reason: 'Agent $agentId should have promptKey');
        expect(descriptor.transformerId, isNotEmpty, reason: 'Agent $agentId should have transformerId');
      }
    });

    test('ModelAdapter maps models to tiers correctly', () {
      final adapter = ModelAdapter();

      // GPT-4 should be high tier
      expect(adapter.getTier('gpt-4'), PromptTier.high);
      expect(adapter.getTier('gpt-4-turbo'), PromptTier.high);

      // Claude models
      expect(adapter.getTier('claude-3-opus'), PromptTier.high);
      expect(adapter.getTier('claude-3-sonnet'), PromptTier.high);
      expect(adapter.getTier('claude-3-haiku'), PromptTier.medium);
    });

    test('JsonPipeline can extract JSON from text', () async {
      final pipeline = JsonPipeline();

      final result = await pipeline.process('{"test": true}');
      expect(result.success, isTrue);
      expect(result.data?['test'], isTrue);
    });

    test('JsonPipeline can extract JSON from markdown', () async {
      final pipeline = JsonPipeline();

      final result = await pipeline.process('''
Here is the result:

```json
{"detected": false}
```

That's my analysis.
''');
      expect(result.success, isTrue);
      expect(result.data?['detected'], isFalse);
    });

    test('JsonPipeline repairs trailing commas', () async {
      final pipeline = JsonPipeline();

      final result = await pipeline.process('{"test": true,}');
      expect(result.success, isTrue);
    });

    test('AgentRequest can be created with all fields', () {
      final request = AgentRequest(
        agentId: 'scene_detector',
        inputs: {'key': 'value'},
        memoryReader: createMemoryReader(),
        modelId: 'gpt-4',
        requestId: 'req_001',
      );

      expect(request.agentId, 'scene_detector');
      expect(request.modelId, 'gpt-4');
      expect(request.requestId, 'req_001');
    });
  });

  group('RpWorkerSerializer', () {
    test('estimates JSON size correctly', () {
      final small = {'key': 'value'};
      final large = {'key': 'x' * 1000};

      final smallSize = RpWorkerSerializer.estimateJsonSize(small);
      final largeSize = RpWorkerSerializer.estimateJsonSize(large);

      expect(smallSize, lessThan(50));
      expect(largeSize, greaterThan(1000));
    });

    test('detects oversized snapshots', () {
      final small = {'key': 'value'};
      final large = {'key': 'x' * (600 * 1024)};

      expect(RpWorkerSerializer.isSnapshotOversized(small), isFalse);
      expect(RpWorkerSerializer.isSnapshotOversized(large), isTrue);
    });
  });

  group('Exception types', () {
    test('RpWorkerException', () {
      final exception = RpWorkerException('Test error');
      expect(exception.message, 'Test error');
      expect(exception.toString(), contains('Test error'));
    });

    test('RpWorkerTimeoutException', () {
      final exception = RpWorkerTimeoutException('req_001', const Duration(seconds: 30));
      expect(exception.timeout, const Duration(seconds: 30));
      expect(exception.message, contains('req_001'));
    });
  });

  group('RpWorkerMemoryReader', () {
    test('reads meta correctly', () {
      final reader = RpWorkerMemoryReader({
        'meta': {
          'storyId': 'test_story',
          'activeBranchId': 'main',
          'sourceRev': 5,
        },
        'entries': {},
      });

      expect(reader.storyId, 'test_story');
      expect(reader.activeBranchId, 'main');
      expect(reader.sourceRev, 5);
    });

    test('reads version correctly', () {
      final reader = RpWorkerMemoryReader({
        'version': {
          'sourceRev': 10,
          'foundationRev': 5,
          'storyRev': 3,
        },
        'entries': {},
      });

      expect(reader.version?.sourceRev, 10);
      expect(reader.version?.foundationRev, 5);
      expect(reader.version?.storyRev, 3);
    });

    test('reads entries by domain', () {
      final reader = RpWorkerMemoryReader({
        'entries': {
          'scene': [
            {'logicalId': 'scene_001', 'preview': 'Village'},
          ],
          'character': [
            {'logicalId': 'char_001', 'preview': 'Alice'},
            {'logicalId': 'char_002', 'preview': 'Bob'},
          ],
        },
      });

      final scenes = reader.getEntriesByDomain('scene');
      final characters = reader.getEntriesByDomain('character');

      expect(scenes, hasLength(1));
      expect(characters, hasLength(2));
    });

    test('reads recent messages', () {
      final reader = RpWorkerMemoryReader({
        'entries': {},
        'recentMessages': [
          {'role': 'user', 'content': 'Hello'},
          {'role': 'assistant', 'content': 'Hi there'},
        ],
      });

      final messages = reader.getRecentMessages();
      expect(messages, hasLength(2));
      expect(messages.first['role'], 'user');
    });

    test('handles missing data gracefully', () {
      final reader = RpWorkerMemoryReader({});

      expect(reader.meta, isNull);
      expect(reader.version, isNull);
      expect(reader.getEntriesByDomain('scene'), isEmpty);
      expect(reader.getRecentMessages(), isEmpty);
    });

    test('gets entry by logicalId', () {
      final reader = RpWorkerMemoryReader({
        'entries': {
          'character': [
            {'logicalId': 'char_alice', 'preview': 'Alice'},
            {'logicalId': 'char_bob', 'preview': 'Bob'},
          ],
        },
      });

      final alice = reader.getEntryByLogicalId('char_alice');
      expect(alice?['preview'], 'Alice');

      final unknown = reader.getEntryByLogicalId('unknown');
      expect(unknown, isNull);
    });

    test('gets current scene', () {
      final reader = RpWorkerMemoryReader({
        'entries': {
          'scene': [
            {'logicalId': 'scene_001', 'preview': 'Village', 'contentJson': '{"location":"Village Square"}'},
          ],
        },
      });

      final scene = reader.getCurrentScene();
      expect(scene?['location'], 'Village Square');
    });

    test('gets characters', () {
      final reader = RpWorkerMemoryReader({
        'entries': {
          'character': [
            {'logicalId': 'char_001', 'preview': 'Alice', 'contentJson': '{"name":"Alice","role":"hero"}'},
          ],
        },
      });

      final chars = reader.getCharacters();
      expect(chars, hasLength(1));
      expect(chars.first['name'], 'Alice');
    });
  });
}
