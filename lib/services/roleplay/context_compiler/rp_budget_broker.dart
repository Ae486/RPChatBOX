/// Budget Broker
///
/// Allocates token budget across fragments using priority-based packing.
/// POS: Services / Roleplay / Context Compiler

import 'rp_fragment.dart';

/// Configuration for budget allocation
class RpBudgetConfig {
  final int maxTokensTotal;
  final int p0ReservePct;
  final int p1ReservePct;

  const RpBudgetConfig({
    required this.maxTokensTotal,
    this.p0ReservePct = 60,
    this.p1ReservePct = 30,
  });

  int get p0Budget => (maxTokensTotal * p0ReservePct / 100).floor();
  int get p1Budget => (maxTokensTotal * p1ReservePct / 100).floor();
  int get p2Budget => maxTokensTotal - p0Budget - p1Budget;
}

/// Budget broker for context packing
class RpBudgetBroker {
  final RpBudgetConfig config;

  const RpBudgetBroker({required this.config});

  /// Pack fragments into budget
  RpPackedContext pack(List<RpFragmentCandidate> candidates) {
    final injectedP0 = <RpFragmentCandidate>[];
    final injectedP1 = <RpFragmentCandidate>[];
    final injectedP2 = <RpFragmentCandidate>[];
    final dropped = <RpDroppedFragment>[];
    final seenDedupeKeys = <String>{};

    var usedTokens = 0;

    // Separate by priority
    final p0Candidates = candidates.where((f) => f.priority == RpPriority.p0).toList();
    final p1Candidates = candidates.where((f) => f.priority == RpPriority.p1).toList();
    final p2Candidates = candidates.where((f) => f.priority == RpPriority.p2).toList();

    // Sort P0 by required first, then by score
    p0Candidates.sort((a, b) {
      if (a.required != b.required) {
        return b.required ? 1 : -1;
      }
      return b.score.compareTo(a.score);
    });

    // Sort P1/P2 by packing score (utility / cost)
    p1Candidates.sort((a, b) => b.packingScore.compareTo(a.packingScore));
    p2Candidates.sort((a, b) => b.packingScore.compareTo(a.packingScore));

    // Phase 1: Pack P0 (required fragments)
    for (final fragment in p0Candidates) {
      // Dedupe check
      if (fragment.dedupeKey != null && seenDedupeKeys.contains(fragment.dedupeKey)) {
        dropped.add(RpDroppedFragment(fragment, 'duplicate'));
        continue;
      }

      // Budget check for P0 - use total budget, not just P0 reserve
      if (usedTokens + fragment.costTokens > config.maxTokensTotal) {
        if (fragment.required) {
          // Required P0 that doesn't fit - hard fail scenario
          dropped.add(RpDroppedFragment(fragment, 'p0_overflow'));
        } else {
          dropped.add(RpDroppedFragment(fragment, 'budget_exceeded'));
        }
        continue;
      }

      injectedP0.add(fragment);
      usedTokens += fragment.costTokens;
      if (fragment.dedupeKey != null) {
        seenDedupeKeys.add(fragment.dedupeKey!);
      }
    }

    // Phase 2: Pack P1 with remaining budget
    final remainingAfterP0 = config.maxTokensTotal - usedTokens;
    final p1Limit = remainingAfterP0.clamp(0, config.p1Budget + config.p2Budget);

    var p1Used = 0;
    for (final fragment in p1Candidates) {
      if (fragment.dedupeKey != null && seenDedupeKeys.contains(fragment.dedupeKey)) {
        dropped.add(RpDroppedFragment(fragment, 'duplicate'));
        continue;
      }

      if (p1Used + fragment.costTokens > p1Limit) {
        dropped.add(RpDroppedFragment(fragment, 'p1_budget_exceeded'));
        continue;
      }

      injectedP1.add(fragment);
      usedTokens += fragment.costTokens;
      p1Used += fragment.costTokens;
      if (fragment.dedupeKey != null) {
        seenDedupeKeys.add(fragment.dedupeKey!);
      }
    }

    // Phase 3: Pack P2 with remaining budget
    for (final fragment in p2Candidates) {
      if (fragment.dedupeKey != null && seenDedupeKeys.contains(fragment.dedupeKey)) {
        dropped.add(RpDroppedFragment(fragment, 'duplicate'));
        continue;
      }

      if (usedTokens + fragment.costTokens > config.maxTokensTotal) {
        dropped.add(RpDroppedFragment(fragment, 'p2_budget_exceeded'));
        continue;
      }

      injectedP2.add(fragment);
      usedTokens += fragment.costTokens;
      if (fragment.dedupeKey != null) {
        seenDedupeKeys.add(fragment.dedupeKey!);
      }
    }

    return RpPackedContext(
      injectedP0: injectedP0,
      injectedP1: injectedP1,
      injectedP2: injectedP2,
      dropped: dropped,
      totalTokens: usedTokens,
    );
  }

  /// Check if P0 overflow occurred (critical error)
  bool hasP0Overflow(RpPackedContext context) {
    return context.dropped.any((d) => d.reason == 'p0_overflow');
  }

  /// Get dropped fragments by reason
  List<RpDroppedFragment> getDroppedByReason(RpPackedContext context, String reason) {
    return context.dropped.where((d) => d.reason == reason).toList();
  }
}
