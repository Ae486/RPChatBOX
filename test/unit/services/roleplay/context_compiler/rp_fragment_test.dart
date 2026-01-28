import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_fragment.dart';

void main() {
  group('RpPriority', () {
    test('should have correct enum values', () {
      expect(RpPriority.p0.index, 0);
      expect(RpPriority.p1.index, 1);
      expect(RpPriority.p2.index, 2);
    });
  });

  group('RpFragmentCandidate', () {
    test('should create with required parameters', () {
      const fragment = RpFragmentCandidate(
        id: 'test_id',
        moduleId: 'scene',
        viewId: 'state',
        priority: RpPriority.p0,
        text: 'Test content',
        costTokens: 100,
        score: 500.0,
      );

      expect(fragment.id, 'test_id');
      expect(fragment.moduleId, 'scene');
      expect(fragment.viewId, 'state');
      expect(fragment.priority, RpPriority.p0);
      expect(fragment.text, 'Test content');
      expect(fragment.costTokens, 100);
      expect(fragment.score, 500.0);
      expect(fragment.required, false);
      expect(fragment.dedupeKey, null);
      expect(fragment.attrs, isEmpty);
    });

    test('copyWith should create modified copy', () {
      const original = RpFragmentCandidate(
        id: 'test_id',
        moduleId: 'scene',
        viewId: 'state',
        priority: RpPriority.p0,
        text: 'Test content',
        costTokens: 100,
        score: 500.0,
      );

      final modified = original.copyWith(
        text: 'Modified content',
        score: 600.0,
      );

      expect(modified.id, original.id);
      expect(modified.text, 'Modified content');
      expect(modified.score, 600.0);
    });

    test('packingScore should calculate utility per cost', () {
      const fragment = RpFragmentCandidate(
        id: 'test',
        moduleId: 'test',
        viewId: 'test',
        priority: RpPriority.p1,
        text: 'test',
        costTokens: 50,
        score: 250.0,
      );

      expect(fragment.packingScore, 5.0);
    });
  });

  group('RpDroppedFragment', () {
    test('should store fragment and reason', () {
      const fragment = RpFragmentCandidate(
        id: 'dropped',
        moduleId: 'test',
        viewId: 'test',
        priority: RpPriority.p2,
        text: 'test',
        costTokens: 100,
        score: 50.0,
      );

      const dropped = RpDroppedFragment(fragment, 'budget_exceeded');

      expect(dropped.fragment.id, 'dropped');
      expect(dropped.reason, 'budget_exceeded');
    });
  });

  group('RpPackedContext', () {
    test('allInjected should combine all priority lists', () {
      const p0 = RpFragmentCandidate(
        id: 'p0', moduleId: 't', viewId: 't',
        priority: RpPriority.p0, text: 't', costTokens: 10, score: 100,
      );
      const p1 = RpFragmentCandidate(
        id: 'p1', moduleId: 't', viewId: 't',
        priority: RpPriority.p1, text: 't', costTokens: 10, score: 50,
      );
      const p2 = RpFragmentCandidate(
        id: 'p2', moduleId: 't', viewId: 't',
        priority: RpPriority.p2, text: 't', costTokens: 10, score: 25,
      );

      const context = RpPackedContext(
        injectedP0: [p0],
        injectedP1: [p1],
        injectedP2: [p2],
        dropped: [],
        totalTokens: 30,
      );

      expect(context.allInjected.length, 3);
      expect(context.allInjected[0].id, 'p0');
      expect(context.allInjected[1].id, 'p1');
      expect(context.allInjected[2].id, 'p2');
    });

    test('hasDropped should detect dropped fragments', () {
      const fragment = RpFragmentCandidate(
        id: 'dropped', moduleId: 't', viewId: 't',
        priority: RpPriority.p2, text: 't', costTokens: 100, score: 10,
      );

      const contextWithDropped = RpPackedContext(
        injectedP0: [],
        injectedP1: [],
        injectedP2: [],
        dropped: [RpDroppedFragment(fragment, 'test')],
        totalTokens: 0,
      );

      expect(contextWithDropped.hasDropped, true);
      expect(RpPackedContext.empty.hasDropped, false);
    });

    test('empty should have zero values', () {
      expect(RpPackedContext.empty.allInjected, isEmpty);
      expect(RpPackedContext.empty.dropped, isEmpty);
      expect(RpPackedContext.empty.totalTokens, 0);
    });
  });
}
