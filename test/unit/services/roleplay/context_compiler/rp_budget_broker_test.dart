import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_budget_broker.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_fragment.dart';

void main() {
  group('RpBudgetBroker', () {
    late RpBudgetBroker broker;

    setUp(() {
      broker = RpBudgetBroker(
        config: const RpBudgetConfig(maxTokensTotal: 1000),
      );
    });

    test('should pack P0 fragments first', () {
      final candidates = [
        const RpFragmentCandidate(
          id: 'p1_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p1,
          text: 'P1 content',
          costTokens: 100,
          score: 500,
        ),
        const RpFragmentCandidate(
          id: 'p0_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p0,
          text: 'P0 content',
          costTokens: 100,
          score: 1000,
          required: true,
        ),
      ];

      final result = broker.pack(candidates);

      expect(result.injectedP0.length, 1);
      expect(result.injectedP0.first.id, 'p0_1');
      expect(result.injectedP1.length, 1);
      expect(result.injectedP1.first.id, 'p1_1');
    });

    test('should deduplicate by dedupeKey', () {
      final candidates = [
        const RpFragmentCandidate(
          id: 'p0_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p0,
          text: 'First',
          costTokens: 100,
          score: 1000,
          dedupeKey: 'same_key',
        ),
        const RpFragmentCandidate(
          id: 'p0_2',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p0,
          text: 'Second',
          costTokens: 100,
          score: 900,
          dedupeKey: 'same_key',
        ),
      ];

      final result = broker.pack(candidates);

      expect(result.injectedP0.length, 1);
      expect(result.dropped.length, 1);
      expect(result.dropped.first.reason, 'duplicate');
    });

    test('should respect budget limits', () {
      final candidates = [
        const RpFragmentCandidate(
          id: 'p0_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p0,
          text: 'P0',
          costTokens: 600,
          score: 1000,
          required: true,
        ),
        const RpFragmentCandidate(
          id: 'p1_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p1,
          text: 'P1',
          costTokens: 500,
          score: 500,
        ),
      ];

      final result = broker.pack(candidates);

      expect(result.injectedP0.length, 1);
      expect(result.injectedP1.length, 0);
      expect(result.dropped.any((d) => d.reason == 'p1_budget_exceeded'), true);
    });

    test('should mark P0 overflow when required fragment exceeds budget', () {
      final candidates = [
        const RpFragmentCandidate(
          id: 'p0_large',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p0,
          text: 'Large required P0',
          costTokens: 1500,
          score: 1000,
          required: true,
        ),
      ];

      final result = broker.pack(candidates);

      expect(result.injectedP0.length, 0);
      expect(broker.hasP0Overflow(result), true);
    });

    test('should sort P1/P2 by packing score', () {
      final candidates = [
        const RpFragmentCandidate(
          id: 'p1_low_efficiency',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p1,
          text: 'Low efficiency',
          costTokens: 200,
          score: 100,
        ),
        const RpFragmentCandidate(
          id: 'p1_high_efficiency',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p1,
          text: 'High efficiency',
          costTokens: 50,
          score: 100,
        ),
      ];

      final result = broker.pack(candidates);

      expect(result.injectedP1.length, 2);
      expect(result.injectedP1.first.id, 'p1_high_efficiency');
    });

    test('should calculate total tokens correctly', () {
      final candidates = [
        const RpFragmentCandidate(
          id: 'p0_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p0,
          text: 'P0',
          costTokens: 100,
          score: 1000,
        ),
        const RpFragmentCandidate(
          id: 'p1_1',
          moduleId: 'test',
          viewId: 'test',
          priority: RpPriority.p1,
          text: 'P1',
          costTokens: 150,
          score: 500,
        ),
      ];

      final result = broker.pack(candidates);

      expect(result.totalTokens, 250);
    });

    test('should return empty context for empty candidates', () {
      final result = broker.pack([]);

      expect(result.allInjected.isEmpty, true);
      expect(result.totalTokens, 0);
    });
  });

  group('RpBudgetConfig', () {
    test('should calculate budget splits correctly', () {
      const config = RpBudgetConfig(
        maxTokensTotal: 1000,
        p0ReservePct: 60,
        p1ReservePct: 30,
      );

      expect(config.p0Budget, 600);
      expect(config.p1Budget, 300);
      expect(config.p2Budget, 100);
    });
  });

  group('RpFragmentCandidate', () {
    test('packingScore should be score divided by cost', () {
      const fragment = RpFragmentCandidate(
        id: 'test',
        moduleId: 'test',
        viewId: 'test',
        priority: RpPriority.p0,
        text: 'test',
        costTokens: 100,
        score: 500,
      );

      expect(fragment.packingScore, 5.0);
    });

    test('packingScore should handle zero cost', () {
      const fragment = RpFragmentCandidate(
        id: 'test',
        moduleId: 'test',
        viewId: 'test',
        priority: RpPriority.p0,
        text: 'test',
        costTokens: 0,
        score: 500,
      );

      expect(fragment.packingScore, 500.0);
    });
  });
}
