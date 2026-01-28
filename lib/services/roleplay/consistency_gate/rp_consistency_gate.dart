/// Consistency Gate Service
///
/// Main service that orchestrates validators and manages violation detection.
/// POS: Services / Roleplay / Consistency Gate

import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:typed_data';

import '../../../models/roleplay/rp_proposal.dart';
import '../../../models/roleplay/rp_entry_blob.dart';
import '../../../models/roleplay/rp_enums.dart';
import 'rp_validator.dart';
import 'rp_violation.dart';
import 'rp_validation_context.dart';
import 'validators/appearance_validator.dart';
import 'validators/state_validator.dart';
import 'validators/presence_validator.dart';
import 'validators/timeline_validator.dart';
import 'validators/knowledge_validator.dart';

/// Degradation policy for managing validator behavior
class RpGateDegradationPolicy {
  /// Dismiss count per validator
  final Map<String, int> dismissCount;

  /// Temporarily disabled validators (with expiry time)
  final Map<String, DateTime> temporarilyDisabled;

  /// Confidence boost per validator (threshold increase)
  final Map<String, double> confidenceBoost;

  /// Silent mode flag
  final bool silentMode;

  const RpGateDegradationPolicy({
    this.dismissCount = const {},
    this.temporarilyDisabled = const {},
    this.confidenceBoost = const {},
    this.silentMode = false,
  });

  /// Check if a validator is currently disabled
  bool isDisabled(String validatorId) {
    final expiry = temporarilyDisabled[validatorId];
    if (expiry == null) return false;
    return DateTime.now().isBefore(expiry);
  }

  /// Get adjusted threshold for a validator
  double getAdjustedThreshold(String validatorId, double baseThreshold) {
    final boost = confidenceBoost[validatorId] ?? 0.0;
    return (baseThreshold + boost).clamp(0.0, 1.0);
  }

  /// Create a copy with updated dismiss count
  RpGateDegradationPolicy withDismiss(String validatorId) {
    final newCount = Map<String, int>.from(dismissCount);
    newCount[validatorId] = (newCount[validatorId] ?? 0) + 1;

    // Check if should disable (3 consecutive dismisses)
    Map<String, DateTime>? newDisabled;
    if ((newCount[validatorId] ?? 0) >= 3) {
      newDisabled = Map<String, DateTime>.from(temporarilyDisabled);
      newDisabled[validatorId] = DateTime.now().add(const Duration(hours: 24));
      newCount[validatorId] = 0; // Reset count
    }

    return RpGateDegradationPolicy(
      dismissCount: newCount,
      temporarilyDisabled: newDisabled ?? temporarilyDisabled,
      confidenceBoost: confidenceBoost,
      silentMode: silentMode,
    );
  }

  /// Create a copy with increased confidence boost
  RpGateDegradationPolicy withConfidenceBoost(String validatorId) {
    final newBoost = Map<String, double>.from(confidenceBoost);
    newBoost[validatorId] = (newBoost[validatorId] ?? 0.0) + 0.2;
    return RpGateDegradationPolicy(
      dismissCount: dismissCount,
      temporarilyDisabled: temporarilyDisabled,
      confidenceBoost: newBoost,
      silentMode: silentMode,
    );
  }
}

/// User preferences for consistency checking
class RpConsistencyPreferences {
  /// Whether consistency checking is enabled
  final bool enabled;

  /// Per-validator enable/disable state
  final Map<String, bool> validators;

  /// Notification level
  final NotificationLevel notifyLevel;

  const RpConsistencyPreferences({
    this.enabled = true,
    this.validators = const {},
    this.notifyLevel = NotificationLevel.always,
  });

  /// Check if a specific validator is enabled
  bool isValidatorEnabled(String validatorId) {
    return enabled && (validators[validatorId] ?? true);
  }
}

/// Notification level options
enum NotificationLevel {
  /// Notify for all violations
  always,

  /// Only notify for error-level violations
  errorOnly,

  /// Silent mode - log only
  silent,
}

/// Main consistency gate service
class RpConsistencyGate {
  final RpValidatorRegistry _registry;
  RpGateDegradationPolicy _degradationPolicy;
  RpConsistencyPreferences _preferences;

  RpConsistencyGate({
    RpValidatorRegistry? registry,
    RpGateDegradationPolicy? degradationPolicy,
    RpConsistencyPreferences? preferences,
  })  : _registry = registry ?? _createDefaultRegistry(),
        _degradationPolicy = degradationPolicy ?? const RpGateDegradationPolicy(),
        _preferences = preferences ?? const RpConsistencyPreferences();

  /// Get current degradation policy
  RpGateDegradationPolicy get degradationPolicy => _degradationPolicy;

  /// Get current preferences
  RpConsistencyPreferences get preferences => _preferences;

  /// Update preferences
  void updatePreferences(RpConsistencyPreferences prefs) {
    _preferences = prefs;
  }

  /// Execute light validation (always runs)
  Future<List<RpViolation>> validateLight(RpValidationContext ctx) async {
    if (!_preferences.enabled) return [];
    if (_preferences.notifyLevel == NotificationLevel.silent) return [];

    final activeValidators = _registry.lightValidators
        .where(_isValidatorActive)
        .toList();

    // Run validators in parallel with error isolation
    final results = await Future.wait(
      activeValidators.map((validator) async {
        try {
          final violations = await validator.validate(ctx);
          final threshold = _degradationPolicy.getAdjustedThreshold(
            validator.id,
            validator.defaultThreshold,
          );
          return violations.where((v) => v.passesThreshold(threshold)).toList();
        } catch (e, stackTrace) {
          developer.log(
            'Error in validator ${validator.id}: $e',
            name: 'RpConsistencyGate',
            error: e,
            stackTrace: stackTrace,
          );
          return <RpViolation>[];
        }
      }),
    );

    return _filterByNotificationLevel(results.expand((v) => v).toList());
  }

  /// Execute heavy validation (triggered conditionally)
  Future<List<RpViolation>> validateHeavy(RpValidationContext ctx) async {
    if (!_preferences.enabled) return [];
    if (_preferences.notifyLevel == NotificationLevel.silent) return [];

    final activeValidators = _registry.heavyValidators
        .where(_isValidatorActive)
        .toList();

    // Run validators in parallel with error isolation
    final results = await Future.wait(
      activeValidators.map((validator) async {
        try {
          final violations = await validator.validate(ctx);
          final threshold = _degradationPolicy.getAdjustedThreshold(
            validator.id,
            validator.defaultThreshold,
          );
          return violations.where((v) => v.passesThreshold(threshold)).toList();
        } catch (e, stackTrace) {
          developer.log(
            'Error in validator ${validator.id}: $e',
            name: 'RpConsistencyGate',
            error: e,
            stackTrace: stackTrace,
          );
          return <RpViolation>[];
        }
      }),
    );

    return _filterByNotificationLevel(results.expand((v) => v).toList());
  }

  /// Check if heavy validation should be triggered
  bool shouldRunHeavy(RpValidationContext ctx) {
    return ctx.shouldTriggerHeavyValidation;
  }

  /// Run all applicable validations
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    final violations = <RpViolation>[];

    // Always run light validators
    violations.addAll(await validateLight(ctx));

    // Conditionally run heavy validators
    if (shouldRunHeavy(ctx)) {
      violations.addAll(await validateHeavy(ctx));
    }

    return violations;
  }

  /// Build OUTPUT_FIX proposal from violations
  RpProposal? buildOutputFixProposal(
    List<RpViolation> violations, {
    required String storyId,
    required String branchId,
    int sourceRev = 0,
    int expectedFoundationRev = 0,
    int expectedStoryRev = 0,
  }) {
    if (violations.isEmpty) return null;

    // Group by severity
    final errors = violations
        .where((v) => v.severity == ViolationSeverity.error)
        .toList();
    final warnings = violations
        .where((v) => v.severity == ViolationSeverity.warn)
        .toList();

    if (errors.isEmpty && warnings.isEmpty) return null;

    // Determine policy based on severity
    final policyTierIndex = errors.isNotEmpty
        ? RpPolicyTier.reviewRequired.index
        : RpPolicyTier.notifyApply.index;

    // Build target from first violation
    final firstViolation = errors.isNotEmpty ? errors.first : warnings.first;
    String targetLogicalId = 'output_fix';
    for (final rec in firstViolation.recommended) {
      if (rec is ProposeMemoryPatch) {
        targetLogicalId = rec.logicalId;
        break;
      }
    }

    // Build payload
    final payload = {
      'violationCount': violations.length,
      'errorCount': errors.length,
      'warningCount': warnings.length,
      'violations': violations
          .map((v) => {
                'code': v.code,
                'severity': v.severity.name,
                'message': v.message,
                'expected': v.expected,
                'found': v.found,
                'confidence': v.confidence,
                'validatorId': v.validatorId,
              })
          .toList(),
    };

    // Build evidence list from violations
    final evidence = <RpEvidenceRef>[];
    for (final v in violations) {
      evidence.addAll(v.evidence);
    }

    return RpProposal(
      proposalId: 'prop_outputfix_${DateTime.now().millisecondsSinceEpoch}',
      storyId: storyId,
      branchId: branchId,
      kindIndex: RpProposalKind.outputFix.index,
      domain: 'consistency',
      policyTierIndex: policyTierIndex,
      target: RpProposalTarget.storyDraft(branchId, targetLogicalId),
      payloadJsonUtf8: Uint8List.fromList(utf8.encode(jsonEncode(payload))),
      evidence: evidence,
      reason: 'Consistency gate detected ${violations.length} violations',
      sourceRev: sourceRev,
      expectedFoundationRev: expectedFoundationRev,
      expectedStoryRev: expectedStoryRev,
    );
  }

  /// Record a user dismissing a violation
  void recordDismiss(String validatorId) {
    _degradationPolicy = _degradationPolicy.withDismiss(validatorId);
  }

  /// Record a false positive (increases threshold)
  void recordFalsePositive(String validatorId) {
    _degradationPolicy = _degradationPolicy.withConfidenceBoost(validatorId);
  }

  /// Check if a validator is currently active
  bool _isValidatorActive(RpValidator validator) {
    if (!_preferences.isValidatorEnabled(validator.id)) return false;
    if (_degradationPolicy.isDisabled(validator.id)) return false;
    if (_degradationPolicy.silentMode) return false;
    return true;
  }

  /// Filter violations by notification level
  List<RpViolation> _filterByNotificationLevel(List<RpViolation> violations) {
    switch (_preferences.notifyLevel) {
      case NotificationLevel.always:
        return violations;
      case NotificationLevel.errorOnly:
        return violations
            .where((v) => v.severity == ViolationSeverity.error)
            .toList();
      case NotificationLevel.silent:
        return [];
    }
  }

  /// Get all registered validators
  Iterable<RpValidator> get validators => _registry.all;

  /// Get validator by ID
  RpValidator? getValidator(String id) => _registry.get(id);
}

/// Create default registry with built-in validators
RpValidatorRegistry _createDefaultRegistry() {
  final registry = RpValidatorRegistry();

  // Light validators
  registry.register(AppearanceValidator());
  registry.register(StateValidator());
  registry.register(PresenceValidator());

  // Heavy validators
  registry.register(TimelineValidator());
  registry.register(KnowledgeValidator());

  return registry;
}
