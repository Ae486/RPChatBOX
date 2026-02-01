import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/agent_registry.dart';
import 'package:chatboxapp/services/roleplay/worker/agents/proposal_transformer.dart';
import 'package:chatboxapp/services/roleplay/worker/rp_memory_snapshot.dart';

void main() {
  group('ProposalTransformerRegistry', () {
    late ProposalTransformerRegistry registry;

    setUp(() {
      registry = ProposalTransformerRegistry();
    });

    test('register adds transformer', () {
      final transformer = SceneDetectorTransformer();
      registry.register(transformer);
      expect(registry.has('scene_detector'), isTrue);
    });

    test('register throws on duplicate', () {
      registry.register(SceneDetectorTransformer());
      expect(
        () => registry.register(SceneDetectorTransformer()),
        throwsA(isA<StateError>()),
      );
    });

    test('registerAll adds multiple transformers', () {
      registry.registerAll([
        SceneDetectorTransformer(),
        StateUpdaterTransformer(),
      ]);
      expect(registry.has('scene_detector'), isTrue);
      expect(registry.has('state_updater'), isTrue);
    });

    test('get returns transformer if exists', () {
      registry.register(SceneDetectorTransformer());
      expect(registry.get('scene_detector'), isNotNull);
      expect(registry.get('unknown'), isNull);
    });

    test('getOrThrow throws if not exists', () {
      expect(
        () => registry.getOrThrow('unknown'),
        throwsA(isA<StateError>()),
      );
    });

    test('clear removes all transformers', () {
      registry.registerAll(allBuiltInTransformers);
      expect(registry.has('scene_detector'), isTrue);
      registry.clear();
      expect(registry.has('scene_detector'), isFalse);
    });
  });

  group('initDefaultTransformers', () {
    test('registers all 4 built-in transformers', () {
      final registry = ProposalTransformerRegistry();
      initDefaultTransformers(registry);

      expect(registry.has('scene_detector'), isTrue);
      expect(registry.has('state_updater'), isTrue);
      expect(registry.has('key_event_extractor'), isTrue);
      expect(registry.has('consistency_heavy'), isTrue);
    });
  });

  group('SceneDetectorTransformer', () {
    late SceneDetectorTransformer transformer;
    late TransformContext ctx;

    setUp(() {
      transformer = SceneDetectorTransformer();
      ctx = createMockContext();
    });

    test('transforms detected scene transition', () {
      final data = {
        'detected': true,
        'transition_type': 'location_change',
        'confidence': 0.9,
        'evidence': 'They walked into the forest',
        'proposal': {
          'from_scene_id': 'scene_001',
          'to_scene': {
            'location': 'Dark Forest',
            'time': 'Evening',
            'atmosphere': 'Mysterious',
          },
        },
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result, hasLength(1));
      expect(result.first['kind'], 'SCENE_TRANSITION');
      expect(result.first['domain'], 'scene');
      expect(result.first['policyTier'], 'reviewRequired');
      expect(result.first['payload']['toScene']['location'], 'Dark Forest');
      expect(result.first['payload']['fromSceneId'], 'scene_001');
      expect(result.first['reason'], contains('location_change'));
    });

    test('returns empty when not detected', () {
      final data = {'detected': false};
      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, isEmpty);
    });

    test('returns empty when to_scene is null', () {
      final data = {
        'detected': true,
        'proposal': {'from_scene_id': 'scene_001'},
      };
      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, isEmpty);
    });

    test('includes version info from context', () {
      final data = {
        'detected': true,
        'proposal': {
          'to_scene': {'location': 'Forest'},
        },
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result.first['sourceRev'], 1);
      expect(result.first['expectedFoundationRev'], 1);
      expect(result.first['expectedStoryRev'], 1);
    });
  });

  group('StateUpdaterTransformer', () {
    late StateUpdaterTransformer transformer;
    late TransformContext ctx;

    setUp(() {
      transformer = StateUpdaterTransformer();
      ctx = createMockContext();
    });

    test('transforms single update', () {
      final data = {
        'updates': [
          {
            'domain': 'character',
            'targetId': 'char_alice',
            'field': 'health',
            'oldValue': 100,
            'newValue': 80,
            'evidence': 'Alice took damage',
            'reason': 'Combat injury',
          },
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result, hasLength(1));
      expect(result.first['kind'], 'DRAFT_UPDATE');
      expect(result.first['domain'], 'character');
      expect(result.first['policyTier'], 'notifyApply');
      expect(result.first['payload']['field'], 'health');
      expect(result.first['payload']['oldValue'], 100);
      expect(result.first['payload']['newValue'], 80);
      expect(result.first['reason'], 'Combat injury');
    });

    test('transforms multiple updates', () {
      final data = {
        'updates': [
          {'domain': 'character', 'targetId': 'char_1', 'field': 'health', 'newValue': 80},
          {'domain': 'state', 'targetId': 'item_1', 'field': 'count', 'newValue': 5},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result, hasLength(2));
      expect(result[0]['domain'], 'character');
      expect(result[1]['domain'], 'state');
    });

    test('returns empty when no updates', () {
      final data = {'updates': []};
      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, isEmpty);
    });

    test('returns empty when updates is null', () {
      final data = <String, dynamic>{};
      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, isEmpty);
    });

    test('generates targetId when not provided', () {
      final data = {
        'updates': [
          {'field': 'health', 'newValue': 50},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result.first['target']['logicalId'], startsWith('state_'));
    });

    test('uses default domain when not specified', () {
      final data = {
        'updates': [
          {'field': 'value', 'newValue': 10},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);
      expect(result.first['domain'], 'state');
    });
  });

  group('KeyEventExtractorTransformer', () {
    late KeyEventExtractorTransformer transformer;
    late TransformContext ctx;

    setUp(() {
      transformer = KeyEventExtractorTransformer();
      ctx = createMockContext();
    });

    test('transforms single event', () {
      final data = {
        'events': [
          {
            'summary': 'Alice discovered the artifact',
            'tags': ['discovery', 'plot'],
            'timestamp': 'Day 3, Evening',
            'participants': ['Alice'],
            'evidence': 'She found the glowing stone',
          },
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result, hasLength(1));
      expect(result.first['kind'], 'CONFIRMED_WRITE');
      expect(result.first['domain'], 'timeline');
      expect(result.first['policyTier'], 'silent');
      expect(result.first['payload']['summary'], 'Alice discovered the artifact');
      expect(result.first['payload']['tags'], ['discovery', 'plot']);
      expect(result.first['payload']['participants'], ['Alice']);
    });

    test('transforms multiple events', () {
      final data = {
        'events': [
          {'summary': 'Event 1'},
          {'summary': 'Event 2'},
          {'summary': 'Event 3'},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, hasLength(3));
    });

    test('returns empty when no events', () {
      final data = {'events': []};
      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, isEmpty);
    });

    test('uses empty defaults for optional fields', () {
      final data = {
        'events': [
          {'summary': 'Simple event'},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result.first['payload']['tags'], isEmpty);
      expect(result.first['payload']['participants'], isEmpty);
    });

    test('generates event IDs with prefix', () {
      final data = {
        'events': [
          {'summary': 'Event 1'},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);
      expect(result.first['payload']['eventId'], startsWith('ev_'));
    });
  });

  group('ConsistencyHeavyTransformer', () {
    late ConsistencyHeavyTransformer transformer;
    late TransformContext ctx;

    setUp(() {
      transformer = ConsistencyHeavyTransformer();
      ctx = createMockContext();
    });

    test('transforms single violation', () {
      final data = {
        'violations': [
          {
            'type': 'character',
            'domain': 'appearance',
            'description': 'Hair color changed',
            'evidence': 'Her black hair flowed',
            'suggestedFix': 'Change to blonde hair',
            'confidence': 0.95,
          },
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);

      expect(result, hasLength(1));
      expect(result.first['kind'], 'OUTPUT_FIX');
      expect(result.first['domain'], 'appearance');
      expect(result.first['policyTier'], 'reviewRequired');
      expect(result.first['payload']['violationType'], 'character');
      expect(result.first['payload']['suggestedFix'], 'Change to blonde hair');
      expect(result.first['payload']['confidence'], 0.95);
    });

    test('transforms multiple violations', () {
      final data = {
        'violations': [
          {'type': 'character', 'description': 'Hair issue'},
          {'type': 'timeline', 'description': 'Date conflict'},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, hasLength(2));
    });

    test('returns empty when no violations', () {
      final data = {'violations': []};
      final result = transformer.transform(data: data, ctx: ctx);
      expect(result, isEmpty);
    });

    test('uses default domain when not specified', () {
      final data = {
        'violations': [
          {'type': 'generic', 'description': 'Some issue'},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);
      expect(result.first['domain'], 'consistency');
    });

    test('uses output_span evidence type', () {
      final data = {
        'violations': [
          {'type': 'test', 'evidence': 'Test evidence'},
        ],
      };

      final result = transformer.transform(data: data, ctx: ctx);
      expect(result.first['evidence'].first['type'], 'output_span');
    });
  });

  group('TransformContext', () {
    test('provides version info from memory reader', () {
      final ctx = createMockContext();
      expect(ctx.sourceRev, 1);
      expect(ctx.foundationRev, 1);
      expect(ctx.storyRev, 1);
    });

    test('handles null version gracefully', () {
      final memoryReader = RpWorkerMemoryReader({
        'meta': {'storyId': 'test'},
        'entries': {},
      });
      final ctx = TransformContext(
        agent: const AgentDescriptor(
          id: 'test',
          promptKey: 'test',
          description: 'Test agent',
          transformerId: 'test',
        ),
        memoryReader: memoryReader,
        inputs: {},
      );

      expect(ctx.sourceRev, 0);
      expect(ctx.foundationRev, 0);
      expect(ctx.storyRev, 0);
    });
  });
}

/// Create mock context for testing
TransformContext createMockContext() {
  final memoryReader = RpWorkerMemoryReader({
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
  });

  return TransformContext(
    agent: const AgentDescriptor(
      id: 'test_agent',
      promptKey: 'test_agent',
      description: 'Agent for testing',
      transformerId: 'test',
    ),
    memoryReader: memoryReader,
    inputs: {},
  );
}
