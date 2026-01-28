import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_module.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_fragment.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_memory_reader.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_token_estimator.dart';
import 'package:chatboxapp/models/roleplay/rp_entry_blob.dart';

class MockModule implements RpModule {
  @override
  String get id => 'mock';

  @override
  String get displayName => 'Mock Module';

  @override
  String get domainCode => 'mk';

  @override
  int get domainWeight => 50;

  @override
  Set<String> get softDependencies => const {};

  @override
  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx) async {
    return [
      const RpFragmentCandidate(
        id: 'mock_fragment',
        moduleId: 'mock',
        viewId: 'test',
        priority: RpPriority.p1,
        text: 'Mock content',
        costTokens: 50,
        score: 100,
      ),
    ];
  }
}

class HighWeightModule implements RpModule {
  @override
  String get id => 'high';

  @override
  String get displayName => 'High Weight';

  @override
  String get domainCode => 'hw';

  @override
  int get domainWeight => 100;

  @override
  Set<String> get softDependencies => const {};

  @override
  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx) async {
    return [];
  }
}

void main() {
  group('RpFragmentContext', () {
    test('should create with required parameters', () {
      final ctx = RpFragmentContext(
        reader: _MockMemoryReader(),
        estimator: const RpTokenEstimator(),
        budgetHint: 1000,
      );

      expect(ctx.budgetHint, 1000);
      expect(ctx.hints, isEmpty);
    });

    test('getHint should return typed value', () {
      final ctx = RpFragmentContext(
        reader: _MockMemoryReader(),
        estimator: const RpTokenEstimator(),
        budgetHint: 1000,
        hints: {'count': 5, 'name': 'test'},
      );

      expect(ctx.getHint<int>('count'), 5);
      expect(ctx.getHint<String>('name'), 'test');
      expect(ctx.getHint<int>('name'), null); // wrong type
      expect(ctx.getHint<String>('missing'), null); // missing key
    });
  });

  group('RpModuleRegistry', () {
    test('should register and retrieve modules', () {
      final registry = RpModuleRegistry();
      final module = MockModule();

      registry.register(module);

      expect(registry.get('mock'), module);
      expect(registry.has('mock'), true);
      expect(registry.has('nonexistent'), false);
    });

    test('all should return all registered modules', () {
      final registry = RpModuleRegistry();
      registry.register(MockModule());
      registry.register(HighWeightModule());

      expect(registry.all.length, 2);
    });

    test('sortedByWeight should return modules in descending weight order', () {
      final registry = RpModuleRegistry();
      registry.register(MockModule()); // weight 50
      registry.register(HighWeightModule()); // weight 100

      final sorted = registry.sortedByWeight;

      expect(sorted.first.id, 'high');
      expect(sorted.last.id, 'mock');
    });
  });

  group('RpModule interface', () {
    test('module should implement all required properties', () {
      final module = MockModule();

      expect(module.id, 'mock');
      expect(module.displayName, 'Mock Module');
      expect(module.domainCode, 'mk');
      expect(module.domainWeight, 50);
      expect(module.softDependencies, isEmpty);
    });

    test('buildFragments should return fragments', () async {
      final module = MockModule();
      final ctx = RpFragmentContext(
        reader: _MockMemoryReader(),
        estimator: const RpTokenEstimator(),
        budgetHint: 1000,
      );

      final fragments = await module.buildFragments(ctx);

      expect(fragments.length, 1);
      expect(fragments.first.moduleId, 'mock');
    });
  });
}

class _MockMemoryReader implements RpMemoryReader {
  @override
  Future<RpEntryBlob?> getByLogicalId(String logicalId) async => null;

  @override
  Iterable<String> logicalIdsByDomain(String domain) => [];

  @override
  int get foundationRev => 0;

  @override
  int get storyRev => 0;

  @override
  String get branchId => 'main';

  @override
  String get storyId => 'test';
}
