/// Context Compiler Fragment Types
///
/// Data structures for context compilation and budget allocation.
/// POS: Services / Roleplay / Context Compiler

/// Fragment priority levels for budget allocation
enum RpPriority {
  /// P0: Required fragments (always included if budget allows)
  p0,

  /// P1: Important fragments (included based on score/cost)
  p1,

  /// P2: Optional fragments (included only with remaining budget)
  p2,
}

/// A candidate fragment for context injection
class RpFragmentCandidate {
  final String id;
  final String moduleId;
  final String viewId;
  final RpPriority priority;
  final String text;
  final int costTokens;
  final double score;
  final bool required;
  final String? dedupeKey;
  final Map<String, String> attrs;

  const RpFragmentCandidate({
    required this.id,
    required this.moduleId,
    required this.viewId,
    required this.priority,
    required this.text,
    required this.costTokens,
    required this.score,
    this.required = false,
    this.dedupeKey,
    this.attrs = const {},
  });

  RpFragmentCandidate copyWith({
    String? id,
    String? moduleId,
    String? viewId,
    RpPriority? priority,
    String? text,
    int? costTokens,
    double? score,
    bool? required,
    String? dedupeKey,
    Map<String, String>? attrs,
  }) {
    return RpFragmentCandidate(
      id: id ?? this.id,
      moduleId: moduleId ?? this.moduleId,
      viewId: viewId ?? this.viewId,
      priority: priority ?? this.priority,
      text: text ?? this.text,
      costTokens: costTokens ?? this.costTokens,
      score: score ?? this.score,
      required: required ?? this.required,
      dedupeKey: dedupeKey ?? this.dedupeKey,
      attrs: attrs ?? this.attrs,
    );
  }

  /// Packing score: utility / cost (higher is better)
  double get packingScore => score / (costTokens > 0 ? costTokens : 1);
}

/// A fragment that was dropped during packing
class RpDroppedFragment {
  final RpFragmentCandidate fragment;
  final String reason;

  const RpDroppedFragment(this.fragment, this.reason);
}

/// Result of context packing
class RpPackedContext {
  final List<RpFragmentCandidate> injectedP0;
  final List<RpFragmentCandidate> injectedP1;
  final List<RpFragmentCandidate> injectedP2;
  final List<RpDroppedFragment> dropped;
  final int totalTokens;

  const RpPackedContext({
    required this.injectedP0,
    required this.injectedP1,
    required this.injectedP2,
    required this.dropped,
    required this.totalTokens,
  });

  /// All injected fragments in order
  List<RpFragmentCandidate> get allInjected => [
        ...injectedP0,
        ...injectedP1,
        ...injectedP2,
      ];

  /// Whether any fragments were dropped
  bool get hasDropped => dropped.isNotEmpty;

  /// Empty context (no fragments)
  static const empty = RpPackedContext(
    injectedP0: [],
    injectedP1: [],
    injectedP2: [],
    dropped: [],
    totalTokens: 0,
  );
}
