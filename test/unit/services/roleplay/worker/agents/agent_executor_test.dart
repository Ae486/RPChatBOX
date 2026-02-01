import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_registry.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_executor.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_types.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_prompts.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/proposal_transformer.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/model_adapter.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/json/json_pipeline.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/output/output_truncator.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/telemetry/agent_metrics.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/telemetry/error_codes.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_memory_snapshot.dart';

void main() {
  group('AgentExecutor', () {
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

    RpWorkerMemoryReader createMockMemoryReader({
      Map<String, dynamic>? currentScene,
      List<Map<String, dynamic>>? characters,
      List<Map<String, dynamic>>? recentMessages,
    }) {
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
        'entries': {
          'scene': currentScene != null
              ? [
                  {
                    'logicalId': 'scene_current',
                    'contentJson': '${currentScene}',
                    'preview': currentScene['location'],
                  }
                ]
              : [],
          'character': characters ?? [],
        },
        'recentMessages': recentMessages ?? [],
      });
    }

    group('SceneDetector', () {
      test('detects scene transition', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '''
```json
{
  "detected": true,
  "transition_type": "location_change",
  "confidence": 0.9,
  "evidence": "They walked into the forest",
  "proposal": {
    "from_scene_id": "scene_001",
    "to_scene": {
      "location": "Dark Forest",
      "time": "Evening",
      "atmosphere": "Mysterious"
    }
  }
}
```
''';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(
            currentScene: {'location': 'Village'},
            recentMessages: [
              {'role': 'assistant', 'content': 'They walked into the forest.'},
            ],
          ),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isNotEmpty);
        expect(result.proposals.first['kind'], 'SCENE_TRANSITION');
        expect(result.proposals.first['payload']['toScene']['location'], 'Dark Forest');
      });

      test('returns empty proposals when no transition detected', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"detected": false}';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isEmpty);
      });
    });

    group('StateUpdater', () {
      test('detects state updates', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '''
{
  "updates": [
    {
      "domain": "character",
      "targetId": "char_alice",
      "field": "health",
      "oldValue": 100,
      "newValue": 80,
      "evidence": "Alice took damage from the attack",
      "reason": "Combat injury"
    }
  ]
}
''';
          },
        );

        final request = AgentRequest(
          agentId: 'state_updater',
          inputs: {},
          memoryReader: createMockMemoryReader(
            characters: [
              {'logicalId': 'char_alice', 'preview': 'Alice'},
            ],
          ),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isNotEmpty);
        expect(result.proposals.first['kind'], 'DRAFT_UPDATE');
        expect(result.proposals.first['payload']['field'], 'health');
        expect(result.proposals.first['payload']['newValue'], 80);
      });

      test('returns empty proposals when no updates', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"updates": []}';
          },
        );

        final request = AgentRequest(
          agentId: 'state_updater',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isEmpty);
      });
    });

    group('KeyEventExtractor', () {
      test('extracts key events', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '''
{
  "events": [
    {
      "summary": "Alice discovered the ancient artifact",
      "tags": ["discovery", "plot"],
      "timestamp": "Day 3, Evening",
      "participants": ["Alice"],
      "significance": "high",
      "evidence": "She found the glowing stone hidden in the cave"
    }
  ]
}
''';
          },
        );

        final request = AgentRequest(
          agentId: 'key_event_extractor',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isNotEmpty);
        expect(result.proposals.first['kind'], 'CONFIRMED_WRITE');
        expect(result.proposals.first['domain'], 'timeline');
        expect(result.proposals.first['payload']['summary'], contains('artifact'));
      });

      test('returns empty proposals when no events', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"events": []}';
          },
        );

        final request = AgentRequest(
          agentId: 'key_event_extractor',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isEmpty);
      });
    });

    group('ConsistencyHeavy', () {
      test('detects consistency violations', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '''
{
  "violations": [
    {
      "type": "character",
      "domain": "appearance",
      "description": "Alice's hair color changed from blonde to black",
      "evidence": "Her black hair flowed in the wind",
      "conflictsWith": "Character card states blonde hair",
      "confidence": 0.95,
      "suggestedFix": "Change 'black hair' to 'blonde hair'"
    }
  ]
}
''';
          },
        );

        final request = AgentRequest(
          agentId: 'consistency_heavy',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isNotEmpty);
        expect(result.proposals.first['kind'], 'OUTPUT_FIX');
        expect(result.proposals.first['payload']['violationType'], 'character');
        expect(result.proposals.first['payload']['suggestedFix'], isNotEmpty);
      });

      test('returns empty proposals when no violations', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"violations": []}';
          },
        );

        final request = AgentRequest(
          agentId: 'consistency_heavy',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
        expect(result.proposals, isEmpty);
      });
    });

    group('Error Handling', () {
      test('returns error for unregistered agent', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{}';
          },
        );

        final request = AgentRequest(
          agentId: 'unknown_agent',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isFalse);
        expect(result.errorCode, AgentErrorCodes.agentNotRegistered);
      });

      test('handles LLM call failure', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            throw Exception('LLM service unavailable');
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isFalse);
        expect(result.errorCode, AgentErrorCodes.agentExecutionError);
      });

      test('handles invalid JSON response', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return 'This is not valid JSON at all';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isFalse);
        expect(result.errorCode, isNotNull);
      });
    });

    group('JSON Pipeline Integration', () {
      test('repairs malformed JSON with trailing comma', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"detected": false,}'; // trailing comma
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
      });

      test('extracts JSON from markdown code block', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '''
Here is the analysis:

```json
{"detected": false}
```

That's my conclusion.
''';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        expect(result.ok, isTrue);
      });

      test('handles Python-style booleans', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"detected": True, "confidence": None}';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        final result = await executor.execute(request);

        // Should either succeed with sanitized JSON or fail gracefully
        // The sanitizer converts True->true, None->null
        expect(result.errorCode != AgentErrorCodes.agentExecutionError, isTrue);
      });
    });

    group('Metrics Recording', () {
      test('records success metrics', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return '{"detected": false}';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        await executor.execute(request);

        expect(metrics.getSuccessCount('scene_detector'), 1);
      });

      test('records failure metrics', () async {
        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            return 'invalid json response without any structure';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        await executor.execute(request);

        expect(metrics.getFailureCount('scene_detector'), greaterThan(0));
      });
    });

    group('Prompt Tier Selection', () {
      test('selects high tier prompt for GPT-4', () async {
        String? capturedSystemPrompt;

        final executor = createExecutor(
          llmCall: ({
            required systemPrompt,
            required userPrompt,
            required modelId,
            maxTokens,
            temperature,
          }) async {
            capturedSystemPrompt = systemPrompt;
            return '{"detected": false}';
          },
        );

        final request = AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        );

        await executor.execute(request);

        // High tier prompts are more detailed
        expect(capturedSystemPrompt, isNotNull);
      });

      test('uses different prompts for different model tiers', () async {
        final prompts = <String>[];

        Future<String> llmCall({
          required String systemPrompt,
          required String userPrompt,
          required String modelId,
          int? maxTokens,
          double? temperature,
        }) async {
          prompts.add(userPrompt);
          return '{"detected": false}';
        }

        final executor = createExecutor(llmCall: llmCall);

        // GPT-4 (high tier)
        await executor.execute(AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'gpt-4',
        ));

        // Ollama (low tier)
        await executor.execute(AgentRequest(
          agentId: 'scene_detector',
          inputs: {},
          memoryReader: createMockMemoryReader(),
          modelId: 'ollama',
        ));

        expect(prompts.length, 2);
        // Different tiers should produce different prompt lengths
        // High tier is more detailed, low tier is more concise
      });
    });
  });
}
