/// RpModule Interface
///
/// Abstract interface for memory modules that generate context fragments.
/// POS: Services / Roleplay / Context Compiler

import 'rp_fragment.dart';
import 'rp_memory_reader.dart';
import 'rp_token_estimator.dart';

/// Context provided to modules for fragment generation
class RpFragmentContext {
  final RpMemoryReader reader;
  final RpTokenEstimator estimator;
  final int budgetHint;
  final Map<String, dynamic> hints;

  const RpFragmentContext({
    required this.reader,
    required this.estimator,
    required this.budgetHint,
    this.hints = const {},
  });

  /// Get a hint value with type safety
  T? getHint<T>(String key) {
    final value = hints[key];
    return value is T ? value : null;
  }
}

/// Abstract interface for memory modules
abstract class RpModule {
  /// Unique module identifier
  String get id;

  /// Human-readable display name
  String get displayName;

  /// Domain code for memory entries (e.g., 'ch', 'sc', 'st')
  String get domainCode;

  /// Domain weight for scoring (higher = more important)
  int get domainWeight;

  /// Modules this depends on (soft dependencies, not blocking)
  Set<String> get softDependencies => const {};

  /// Build fragments from memory entries
  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx);
}

/// Module registry for managing available modules
class RpModuleRegistry {
  final Map<String, RpModule> _modules = {};

  /// Register a module
  void register(RpModule module) {
    _modules[module.id] = module;
  }

  /// Get module by ID
  RpModule? get(String id) => _modules[id];

  /// Get all registered modules
  Iterable<RpModule> get all => _modules.values;

  /// Get modules sorted by domain weight (descending)
  List<RpModule> get sortedByWeight {
    final list = _modules.values.toList();
    list.sort((a, b) => b.domainWeight.compareTo(a.domainWeight));
    return list;
  }

  /// Check if module exists
  bool has(String id) => _modules.containsKey(id);
}
