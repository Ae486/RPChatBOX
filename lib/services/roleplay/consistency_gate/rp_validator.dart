/// Validator Interface and Registry
///
/// Defines the base validator interface and provides a registry
/// for managing validators.
/// POS: Services / Roleplay / Consistency Gate

import 'rp_violation.dart';
import 'rp_validation_context.dart';

/// Validator weight category
enum ValidatorWeight {
  /// Light validators run on every output
  light,

  /// Heavy validators run only when triggered
  heavy,
}

/// Base interface for all consistency validators
abstract class RpValidator {
  /// Unique identifier for this validator
  String get id;

  /// Human-readable display name
  String get displayName;

  /// Weight category (light or heavy)
  ValidatorWeight get weight;

  /// Default confidence threshold
  double get defaultThreshold;

  /// Whether this validator is enabled by default
  bool get enabledByDefault => true;

  /// Validate the output and return any violations
  Future<List<RpViolation>> validate(RpValidationContext ctx);

  /// Filter violations by threshold
  List<RpViolation> filterByThreshold(
    List<RpViolation> violations, {
    double? threshold,
  }) {
    final t = threshold ?? defaultThreshold;
    return violations.where((v) => v.passesThreshold(t)).toList();
  }
}

/// Registry for managing validators
class RpValidatorRegistry {
  final Map<String, RpValidator> _validators = {};

  /// Register a validator
  void register(RpValidator validator) {
    _validators[validator.id] = validator;
  }

  /// Unregister a validator
  void unregister(String id) {
    _validators.remove(id);
  }

  /// Get a validator by ID
  RpValidator? get(String id) => _validators[id];

  /// Check if a validator is registered
  bool has(String id) => _validators.containsKey(id);

  /// Get all registered validators
  Iterable<RpValidator> get all => _validators.values;

  /// Get all light validators
  Iterable<RpValidator> get lightValidators =>
      _validators.values.where((v) => v.weight == ValidatorWeight.light);

  /// Get all heavy validators
  Iterable<RpValidator> get heavyValidators =>
      _validators.values.where((v) => v.weight == ValidatorWeight.heavy);

  /// Get validators sorted by weight (light first, then heavy)
  List<RpValidator> get sortedByWeight {
    final list = _validators.values.toList();
    list.sort((a, b) {
      if (a.weight != b.weight) {
        return a.weight == ValidatorWeight.light ? -1 : 1;
      }
      return a.id.compareTo(b.id);
    });
    return list;
  }

  /// Clear all validators
  void clear() {
    _validators.clear();
  }

  /// Get validator count
  int get count => _validators.length;
}

/// Creates a default registry with built-in validators
RpValidatorRegistry createDefaultRegistry() {
  final registry = RpValidatorRegistry();
  // Validators will be registered by the ConsistencyGate service
  return registry;
}
