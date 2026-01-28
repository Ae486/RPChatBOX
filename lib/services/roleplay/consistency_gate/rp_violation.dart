/// Violation Data Structures
///
/// Defines the data structures for consistency violations including
/// severity levels, evidence references, and recommendations.
/// POS: Services / Roleplay / Consistency Gate

import '../../../models/roleplay/rp_entry_blob.dart';

/// Violation severity levels
enum ViolationSeverity {
  /// Informational - no action required
  info,

  /// Warning - may need attention
  warn,

  /// Error - likely needs correction
  error,
}

/// Violation codes for different error types
class ViolationCode {
  ViolationCode._();

  // Appearance category
  static const hairColorMismatch = 'APPEARANCE_HAIR_COLOR';
  static const eyeColorMismatch = 'APPEARANCE_EYE_COLOR';
  static const heightMismatch = 'APPEARANCE_HEIGHT';
  static const genderMismatch = 'APPEARANCE_GENDER';
  static const distinctiveMarkMismatch = 'APPEARANCE_DISTINCTIVE_MARK';

  // State category
  static const itemNotOwned = 'STATE_ITEM_NOT_OWNED';
  static const injuryIgnored = 'STATE_INJURY_IGNORED';
  static const abilityExceeded = 'STATE_ABILITY_EXCEEDED';
  static const statusIgnored = 'STATE_STATUS_IGNORED';

  // Presence category
  static const characterAbsent = 'PRESENCE_CHARACTER_ABSENT';
  static const characterLeft = 'PRESENCE_CHARACTER_LEFT';
  static const characterDeceased = 'PRESENCE_CHARACTER_DECEASED';

  // Timeline category (Heavy)
  static const eventNotOccurred = 'TIMELINE_EVENT_NOT_OCCURRED';
  static const timeSequenceError = 'TIMELINE_SEQUENCE_ERROR';
  static const eventConflict = 'TIMELINE_EVENT_CONFLICT';

  // Knowledge category (Heavy)
  static const knowledgeLeak = 'KNOWLEDGE_LEAK';
  static const metagaming = 'KNOWLEDGE_METAGAMING';
}

/// Default confidence thresholds for each validator
class ValidatorThresholds {
  ValidatorThresholds._();

  /// Appearance validator threshold (may have modifier interference)
  static const appearance = 0.7;

  /// State validator threshold (relatively certain)
  static const state = 0.8;

  /// Presence validator threshold (should be high confidence)
  static const presence = 0.9;

  /// Timeline validator threshold (complex)
  static const timeline = 0.85;

  /// Knowledge validator threshold (fuzzy boundaries)
  static const knowledge = 0.75;
}

/// A consistency violation detected by a validator
class RpViolation {
  /// Violation code (e.g., 'APPEARANCE_HAIR_COLOR')
  final String code;

  /// Severity level
  final ViolationSeverity severity;

  /// Human-readable message
  final String message;

  /// Expected value (from memory)
  final String? expected;

  /// Found value (from output)
  final String? found;

  /// Confidence score (0.0 ~ 1.0)
  final double confidence;

  /// Evidence chain
  final List<RpEvidenceRef> evidence;

  /// Recommended fixes
  final List<RpRecommendation> recommended;

  /// Validator ID that detected this violation
  final String validatorId;

  /// Timestamp when violation was detected
  final DateTime detectedAt;

  const RpViolation({
    required this.code,
    required this.severity,
    required this.message,
    this.expected,
    this.found,
    required this.confidence,
    required this.evidence,
    required this.recommended,
    required this.validatorId,
    required this.detectedAt,
  });

  /// Check if this violation passes the given threshold
  bool passesThreshold(double threshold) => confidence >= threshold;

  /// Create a copy with updated fields
  RpViolation copyWith({
    String? code,
    ViolationSeverity? severity,
    String? message,
    String? expected,
    String? found,
    double? confidence,
    List<RpEvidenceRef>? evidence,
    List<RpRecommendation>? recommended,
    String? validatorId,
    DateTime? detectedAt,
  }) {
    return RpViolation(
      code: code ?? this.code,
      severity: severity ?? this.severity,
      message: message ?? this.message,
      expected: expected ?? this.expected,
      found: found ?? this.found,
      confidence: confidence ?? this.confidence,
      evidence: evidence ?? this.evidence,
      recommended: recommended ?? this.recommended,
      validatorId: validatorId ?? this.validatorId,
      detectedAt: detectedAt ?? this.detectedAt,
    );
  }

  @override
  String toString() {
    return 'RpViolation(code: $code, severity: $severity, confidence: $confidence, message: $message)';
  }
}

/// Base class for recommendations
sealed class RpRecommendation {
  const RpRecommendation();
}

/// Recommend patching memory entry
class ProposeMemoryPatch extends RpRecommendation {
  /// Domain code (e.g., 'ch' for character)
  final String domain;

  /// Logical ID of the entry to patch
  final String logicalId;

  /// Patch content
  final Map<String, dynamic> patch;

  /// Description of what this patch does
  final String description;

  const ProposeMemoryPatch({
    required this.domain,
    required this.logicalId,
    required this.patch,
    required this.description,
  });

  @override
  String toString() =>
      'ProposeMemoryPatch(domain: $domain, logicalId: $logicalId)';
}

/// Suggest user correction
class SuggestUserCorrection extends RpRecommendation {
  /// Suggestion text for the user
  final String text;

  /// Optional corrected text suggestion
  final String? correctedText;

  const SuggestUserCorrection(this.text, {this.correctedText});

  @override
  String toString() => 'SuggestUserCorrection(text: $text)';
}

/// Suggest retry generation with additional constraints
class SuggestRetryGeneration extends RpRecommendation {
  /// Reason for suggesting retry
  final String reason;

  /// Additional constraints to add to the prompt
  final List<String>? constraintsToAdd;

  const SuggestRetryGeneration({
    required this.reason,
    this.constraintsToAdd,
  });

  @override
  String toString() => 'SuggestRetryGeneration(reason: $reason)';
}

/// Suggest ignoring this violation
class SuggestIgnore extends RpRecommendation {
  /// Reason why ignoring might be acceptable
  final String reason;

  const SuggestIgnore(this.reason);

  @override
  String toString() => 'SuggestIgnore(reason: $reason)';
}
