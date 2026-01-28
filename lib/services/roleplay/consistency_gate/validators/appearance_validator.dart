/// Appearance Validator
///
/// Light-weight validator that detects appearance description mismatches
/// (hair color, eye color, height, gender, distinctive marks).
/// POS: Services / Roleplay / Consistency Gate / Validators

import '../rp_validator.dart';
import '../rp_violation.dart';
import '../rp_validation_context.dart';
import '../utils/rp_text_extractor.dart';
import '../utils/rp_pattern_matcher.dart';
import '../utils/rp_blob_parser.dart';
import '../../../../models/roleplay/rp_entry_blob.dart';

/// Validates appearance consistency
class AppearanceValidator extends RpValidator {
  @override
  String get id => 'appearance';

  @override
  String get displayName => 'Appearance Validator';

  @override
  ValidatorWeight get weight => ValidatorWeight.light;

  @override
  double get defaultThreshold => ValidatorThresholds.appearance;

  /// Fields to check
  static const checkFields = [
    'hair_color',
    'eye_color',
    'height',
    'gender',
    'distinctive_marks',
  ];

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    final violations = <RpViolation>[];
    final text = ctx.getTextForValidation();

    // Get all character entries from memory
    final characterLogicalIds = ctx.memory.logicalIdsByDomain('ch').toList();

    for (final logicalId in characterLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      // Parse character appearance data
      final appearance = _parseAppearance(blob);
      if (appearance.isEmpty) continue;

      final characterName = _extractCharacterName(blob);

      // Check if this character is mentioned in the text
      if (characterName != null && !text.contains(characterName)) {
        continue; // Skip characters not mentioned
      }

      // Extract appearance references from text
      final appearanceRefs = RpTextExtractor.extractAppearanceRefs(text);

      // Check each appearance attribute
      for (final ref in appearanceRefs) {
        if (!checkFields.contains(ref.attribute)) continue;

        final expectedValue = appearance[ref.attribute];
        if (expectedValue == null) continue;

        // Compare values
        final violation = _checkMismatch(
          attribute: ref.attribute,
          expected: expectedValue,
          found: ref.value,
          characterName: characterName,
          logicalId: logicalId,
          position: ref.position,
          confidence: ref.confidence,
        );

        if (violation != null) {
          violations.add(violation);
        }
      }
    }

    return filterByThreshold(violations);
  }

  /// Parse appearance data from blob
  Map<String, String> _parseAppearance(RpEntryBlob blob) {
    final result = <String, String>{};
    final data = blob.safeParseJson();

    if (data.isEmpty) return result;

    // Extract appearance fields from nested object
    if (data['appearance'] is Map) {
      final appearance = data['appearance'] as Map<String, dynamic>;
      for (final field in checkFields) {
        if (appearance[field] != null) {
          result[field] = appearance[field].toString().toLowerCase();
        }
      }
    }

    // Direct fields
    for (final field in checkFields) {
      if (data[field] != null && !result.containsKey(field)) {
        result[field] = data[field].toString().toLowerCase();
      }
    }

    return result;
  }

  /// Extract character name from blob
  String? _extractCharacterName(RpEntryBlob blob) {
    final data = blob.safeParseJson();
    if (data.isEmpty) return null;
    return data['name']?.toString() ?? data['characterName']?.toString();
  }

  /// Check for mismatch and create violation if found
  RpViolation? _checkMismatch({
    required String attribute,
    required String expected,
    required String found,
    String? characterName,
    required String logicalId,
    required int position,
    required double confidence,
  }) {
    // Normalize and compare
    final normalizedExpected = expected.toLowerCase().trim();
    final normalizedFound = found.toLowerCase().trim();

    // For colors, use synonym matching
    if (attribute.contains('color')) {
      if (RpPatternMatcher.areColorsEquivalent(
          normalizedExpected, normalizedFound)) {
        return null; // Colors match
      }
    } else {
      // Direct comparison
      if (normalizedExpected == normalizedFound) {
        return null;
      }
    }

    // Create violation
    final code = _getViolationCode(attribute);
    final characterInfo =
        characterName != null ? ' for character "$characterName"' : '';

    return RpViolation(
      code: code,
      severity: ViolationSeverity.warn,
      message: 'Appearance mismatch$characterInfo: $attribute is "$expected" '
          'in memory but "$found" in output',
      expected: expected,
      found: found,
      confidence: confidence,
      evidence: [
        RpEvidenceRef(
          type: 'validator',
          refId: logicalId,
          note: 'appearance.$attribute',
        ),
      ],
      recommended: [
        ProposeMemoryPatch(
          domain: 'ch',
          logicalId: logicalId,
          patch: {attribute: found},
          description: 'Update $attribute from "$expected" to "$found"',
        ),
        SuggestUserCorrection(
          'The character\'s $attribute should be "$expected", not "$found"',
        ),
      ],
      validatorId: id,
      detectedAt: DateTime.now(),
    );
  }

  /// Get violation code for attribute
  String _getViolationCode(String attribute) {
    switch (attribute) {
      case 'hair_color':
        return ViolationCode.hairColorMismatch;
      case 'eye_color':
        return ViolationCode.eyeColorMismatch;
      case 'height':
        return ViolationCode.heightMismatch;
      case 'gender':
        return ViolationCode.genderMismatch;
      default:
        return ViolationCode.distinctiveMarkMismatch;
    }
  }
}
