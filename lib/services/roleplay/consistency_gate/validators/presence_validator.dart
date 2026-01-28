/// Presence Validator
///
/// Light-weight validator that detects presence consistency violations
/// (absent character actions, departed character dialogue).
/// POS: Services / Roleplay / Consistency Gate / Validators

import '../rp_validator.dart';
import '../rp_violation.dart';
import '../rp_validation_context.dart';
import '../utils/rp_text_extractor.dart';
import '../utils/rp_blob_parser.dart';
import '../../../../models/roleplay/rp_entry_blob.dart';

/// Validates character presence consistency
class PresenceValidator extends RpValidator {
  @override
  String get id => 'presence';

  @override
  String get displayName => 'Presence Validator';

  @override
  ValidatorWeight get weight => ValidatorWeight.light;

  @override
  double get defaultThreshold => ValidatorThresholds.presence;

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    final violations = <RpViolation>[];
    final text = ctx.getTextForValidation();

    // Get scene data to find present characters
    final sceneLogicalIds = ctx.memory.logicalIdsByDomain('sc').toList();

    final presentCharacters = <String>{};
    final absentCharacters = <String>{};
    final deceasedCharacters = <String>{};
    String? sceneLogicalId;

    for (final logicalId in sceneLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      sceneLogicalId = logicalId;
      final sceneData = blob.safeParseJson();

      // Get present characters
      if (sceneData['presentCharacters'] is List) {
        presentCharacters.addAll(
            (sceneData['presentCharacters'] as List).map((e) => e.toString()));
      }
      if (sceneData['present'] is List) {
        presentCharacters
            .addAll((sceneData['present'] as List).map((e) => e.toString()));
      }
      if (sceneData['characters'] is List) {
        presentCharacters
            .addAll((sceneData['characters'] as List).map((e) => e.toString()));
      }

      // Get absent/departed characters
      if (sceneData['absentCharacters'] is List) {
        absentCharacters.addAll(
            (sceneData['absentCharacters'] as List).map((e) => e.toString()));
      }
      if (sceneData['departed'] is List) {
        absentCharacters
            .addAll((sceneData['departed'] as List).map((e) => e.toString()));
      }
    }

    // Check character data for deceased status
    final characterLogicalIds = ctx.memory.logicalIdsByDomain('ch').toList();
    for (final logicalId in characterLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      final charData = blob.safeParseJson();
      final name = charData['name']?.toString();
      final status = charData['status']?.toString()?.toLowerCase();

      if (name != null && (status == 'deceased' || status == 'dead')) {
        deceasedCharacters.add(name);
      }
    }

    // Get all known characters for reference
    final allKnownCharacters = <String>{
      ...presentCharacters,
      ...absentCharacters,
      ...deceasedCharacters
    };

    // Extract character references from text
    final characterRefs = RpTextExtractor.extractCharacterRefs(
      text,
      allKnownCharacters.toList(),
    );

    // Check for violations
    for (final ref in characterRefs) {
      // Check deceased characters
      if (deceasedCharacters.contains(ref.name)) {
        if (ref.type == CharacterRefType.dialogue ||
            ref.type == CharacterRefType.action) {
          violations.add(_createViolation(
            code: ViolationCode.characterDeceased,
            severity: ViolationSeverity.error,
            characterName: ref.name,
            refType: ref.type,
            reason: 'Character is deceased',
            sceneLogicalId: sceneLogicalId,
            confidence: 0.95,
          ));
        }
      }
      // Check absent characters
      else if (absentCharacters.contains(ref.name)) {
        if (ref.type == CharacterRefType.dialogue) {
          violations.add(_createViolation(
            code: ViolationCode.characterLeft,
            severity: ViolationSeverity.warn,
            characterName: ref.name,
            refType: ref.type,
            reason: 'Character has left the scene',
            sceneLogicalId: sceneLogicalId,
            confidence: 0.85,
          ));
        } else if (ref.type == CharacterRefType.action) {
          violations.add(_createViolation(
            code: ViolationCode.characterLeft,
            severity: ViolationSeverity.warn,
            characterName: ref.name,
            refType: ref.type,
            reason: 'Character has left the scene',
            sceneLogicalId: sceneLogicalId,
            confidence: 0.8,
          ));
        }
      }
      // Check if character is not in present list (and we have a present list)
      else if (presentCharacters.isNotEmpty &&
          !presentCharacters.contains(ref.name) &&
          !absentCharacters.contains(ref.name) &&
          !deceasedCharacters.contains(ref.name)) {
        // Unknown character performing action - might be new character
        if (ref.type == CharacterRefType.dialogue ||
            ref.type == CharacterRefType.action) {
          violations.add(_createViolation(
            code: ViolationCode.characterAbsent,
            severity: ViolationSeverity.info,
            characterName: ref.name,
            refType: ref.type,
            reason: 'Character not listed as present in scene',
            sceneLogicalId: sceneLogicalId,
            confidence: 0.6, // Lower confidence since might be new character
          ));
        }
      }
    }

    return filterByThreshold(violations);
  }

  /// Create a presence violation
  RpViolation _createViolation({
    required String code,
    required ViolationSeverity severity,
    required String characterName,
    required CharacterRefType refType,
    required String reason,
    String? sceneLogicalId,
    required double confidence,
  }) {
    final actionDescription = switch (refType) {
      CharacterRefType.dialogue => 'speaking',
      CharacterRefType.action => 'performing actions',
      CharacterRefType.mention => 'mentioned',
    };

    return RpViolation(
      code: code,
      severity: severity,
      message: 'Character "$characterName" is $actionDescription but $reason',
      expected: 'Character present in scene',
      found: 'Character $reason',
      confidence: confidence,
      evidence: sceneLogicalId != null
          ? [
              RpEvidenceRef(
                type: 'validator',
                refId: sceneLogicalId,
                note: 'presence',
              )
            ]
          : [],
      recommended: [
        if (code != ViolationCode.characterDeceased)
          ProposeMemoryPatch(
            domain: 'sc',
            logicalId: sceneLogicalId ?? 'current',
            patch: {
              'presentCharacters': [characterName]
            },
            description: 'Add "$characterName" to present characters',
          ),
        SuggestUserCorrection(
          'Character "$characterName" should not be $actionDescription as they are $reason',
        ),
      ],
      validatorId: id,
      detectedAt: DateTime.now(),
    );
  }
}
