import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/consistency_gate/rp_violation.dart';
import 'package:chatboxapp/models/roleplay/rp_entry_blob.dart';

void main() {
  group('RpViolation', () {
    test('should create violation with all fields', () {
      final violation = RpViolation(
        code: ViolationCode.hairColorMismatch,
        severity: ViolationSeverity.warn,
        message: 'Hair color mismatch',
        expected: 'black',
        found: 'gold',
        confidence: 0.85,
        evidence: [
          RpEvidenceRef(
            type: 'validator',
            refId: 'rp:v1:ch:char1:card.base',
            note: 'appearance.hair_color',
          ),
        ],
        recommended: [
          const SuggestUserCorrection('Please correct the hair color'),
        ],
        validatorId: 'appearance',
        detectedAt: DateTime(2026, 1, 19),
      );

      expect(violation.code, ViolationCode.hairColorMismatch);
      expect(violation.severity, ViolationSeverity.warn);
      expect(violation.confidence, 0.85);
      expect(violation.evidence.length, 1);
      expect(violation.recommended.length, 1);
    });

    test('passesThreshold should return correct result', () {
      final violation = RpViolation(
        code: ViolationCode.hairColorMismatch,
        severity: ViolationSeverity.warn,
        message: 'Test',
        confidence: 0.75,
        evidence: [],
        recommended: [],
        validatorId: 'test',
        detectedAt: DateTime.now(),
      );

      expect(violation.passesThreshold(0.7), true);
      expect(violation.passesThreshold(0.75), true);
      expect(violation.passesThreshold(0.8), false);
    });

    test('copyWith should create modified copy', () {
      final original = RpViolation(
        code: ViolationCode.hairColorMismatch,
        severity: ViolationSeverity.warn,
        message: 'Original',
        confidence: 0.5,
        evidence: [],
        recommended: [],
        validatorId: 'test',
        detectedAt: DateTime.now(),
      );

      final modified = original.copyWith(
        confidence: 0.9,
        message: 'Modified',
      );

      expect(modified.code, original.code);
      expect(modified.confidence, 0.9);
      expect(modified.message, 'Modified');
    });
  });

  group('ViolationSeverity', () {
    test('should have correct values', () {
      expect(ViolationSeverity.info.index, 0);
      expect(ViolationSeverity.warn.index, 1);
      expect(ViolationSeverity.error.index, 2);
    });
  });

  group('ViolationCode', () {
    test('appearance codes should be defined', () {
      expect(ViolationCode.hairColorMismatch, 'APPEARANCE_HAIR_COLOR');
      expect(ViolationCode.eyeColorMismatch, 'APPEARANCE_EYE_COLOR');
      expect(ViolationCode.heightMismatch, 'APPEARANCE_HEIGHT');
      expect(ViolationCode.genderMismatch, 'APPEARANCE_GENDER');
    });

    test('state codes should be defined', () {
      expect(ViolationCode.itemNotOwned, 'STATE_ITEM_NOT_OWNED');
      expect(ViolationCode.injuryIgnored, 'STATE_INJURY_IGNORED');
    });

    test('presence codes should be defined', () {
      expect(ViolationCode.characterAbsent, 'PRESENCE_CHARACTER_ABSENT');
      expect(ViolationCode.characterLeft, 'PRESENCE_CHARACTER_LEFT');
      expect(ViolationCode.characterDeceased, 'PRESENCE_CHARACTER_DECEASED');
    });
  });

  group('ValidatorThresholds', () {
    test('should have correct default values', () {
      expect(ValidatorThresholds.appearance, 0.7);
      expect(ValidatorThresholds.state, 0.8);
      expect(ValidatorThresholds.presence, 0.9);
      expect(ValidatorThresholds.timeline, 0.85);
      expect(ValidatorThresholds.knowledge, 0.75);
    });
  });

  group('RpRecommendation types', () {
    test('ProposeMemoryPatch should hold patch data', () {
      const patch = ProposeMemoryPatch(
        domain: 'ch',
        logicalId: 'rp:v1:ch:char1:card.base',
        patch: {'hair_color': 'gold'},
        description: 'Update hair color',
      );

      expect(patch.domain, 'ch');
      expect(patch.logicalId, contains('char1'));
      expect(patch.patch['hair_color'], 'gold');
    });

    test('SuggestUserCorrection should hold text', () {
      const suggestion = SuggestUserCorrection(
        'Please fix the inconsistency',
        correctedText: 'Her black hair...',
      );

      expect(suggestion.text, 'Please fix the inconsistency');
      expect(suggestion.correctedText, 'Her black hair...');
    });

    test('SuggestRetryGeneration should hold constraints', () {
      const retry = SuggestRetryGeneration(
        reason: 'Too many inconsistencies',
        constraintsToAdd: ['Maintain hair color as black'],
      );

      expect(retry.reason, 'Too many inconsistencies');
      expect(retry.constraintsToAdd?.length, 1);
    });

    test('SuggestIgnore should hold reason', () {
      const ignore = SuggestIgnore('This may be intentional');

      expect(ignore.reason, 'This may be intentional');
    });
  });
}
