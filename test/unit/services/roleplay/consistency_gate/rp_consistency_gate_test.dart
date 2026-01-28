import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/services/roleplay/consistency_gate/rp_consistency_gate.dart';
import 'package:chatboxapp/services/roleplay/consistency_gate/rp_validator.dart';
import 'package:chatboxapp/services/roleplay/consistency_gate/rp_violation.dart';
import 'package:chatboxapp/services/roleplay/consistency_gate/rp_validation_context.dart';
import 'package:chatboxapp/services/roleplay/context_compiler/rp_memory_reader.dart';
import 'package:chatboxapp/models/roleplay/rp_entry_blob.dart';

void main() {
  group('RpConsistencyGate', () {
    late RpConsistencyGate gate;

    setUp(() {
      gate = RpConsistencyGate();
    });

    test('should create with default validators', () {
      expect(gate.validators.length, 5); // 3 light + 2 heavy
    });

    test('should have correct light validators', () {
      final lightIds = gate.validators
          .where((v) => v.weight == ValidatorWeight.light)
          .map((v) => v.id)
          .toSet();

      expect(lightIds.contains('appearance'), true);
      expect(lightIds.contains('state'), true);
      expect(lightIds.contains('presence'), true);
    });

    test('should have correct heavy validators', () {
      final heavyIds = gate.validators
          .where((v) => v.weight == ValidatorWeight.heavy)
          .map((v) => v.id)
          .toSet();

      expect(heavyIds.contains('timeline'), true);
      expect(heavyIds.contains('knowledge'), true);
    });

    test('shouldRunHeavy should return true when utilization is high', () {
      final ctx = RpValidationContext(
        storyId: 'test',
        branchId: 'main',
        outputText: 'Test output',
        memory: _MockMemoryReader(),
        promptUtilization: 0.9,
        headroomTokens: 1000,
      );

      expect(gate.shouldRunHeavy(ctx), true);
    });

    test('shouldRunHeavy should return true when headroom is low', () {
      final ctx = RpValidationContext(
        storyId: 'test',
        branchId: 'main',
        outputText: 'Test output',
        memory: _MockMemoryReader(),
        promptUtilization: 0.5,
        headroomTokens: 500,
      );

      expect(gate.shouldRunHeavy(ctx), true);
    });

    test('shouldRunHeavy should return false when both are normal', () {
      final ctx = RpValidationContext(
        storyId: 'test',
        branchId: 'main',
        outputText: 'Test output',
        memory: _MockMemoryReader(),
        promptUtilization: 0.5,
        headroomTokens: 1000,
      );

      expect(gate.shouldRunHeavy(ctx), false);
    });

    test('getValidator should return correct validator', () {
      final validator = gate.getValidator('appearance');
      expect(validator, isNotNull);
      expect(validator?.id, 'appearance');
    });

    test('getValidator should return null for unknown id', () {
      final validator = gate.getValidator('unknown');
      expect(validator, isNull);
    });
  });

  group('RpGateDegradationPolicy', () {
    test('should start with empty state', () {
      const policy = RpGateDegradationPolicy();

      expect(policy.dismissCount, isEmpty);
      expect(policy.temporarilyDisabled, isEmpty);
      expect(policy.confidenceBoost, isEmpty);
      expect(policy.silentMode, false);
    });

    test('withDismiss should increment count', () {
      const policy = RpGateDegradationPolicy();
      final updated = policy.withDismiss('appearance');

      expect(updated.dismissCount['appearance'], 1);
    });

    test('withDismiss should disable after 3 dismisses', () {
      var policy = const RpGateDegradationPolicy();
      policy = policy.withDismiss('appearance');
      policy = policy.withDismiss('appearance');
      policy = policy.withDismiss('appearance');

      expect(policy.isDisabled('appearance'), true);
      expect(policy.dismissCount['appearance'], 0); // Reset after disable
    });

    test('withConfidenceBoost should increase threshold', () {
      const policy = RpGateDegradationPolicy();
      final updated = policy.withConfidenceBoost('appearance');

      expect(updated.confidenceBoost['appearance'], 0.2);
    });

    test('getAdjustedThreshold should apply boost', () {
      var policy = const RpGateDegradationPolicy();
      policy = policy.withConfidenceBoost('appearance');

      final adjusted = policy.getAdjustedThreshold('appearance', 0.7);
      expect(adjusted, closeTo(0.9, 0.0001));
    });

    test('getAdjustedThreshold should clamp to 1.0', () {
      var policy = const RpGateDegradationPolicy();
      policy = policy.withConfidenceBoost('appearance');
      policy = policy.withConfidenceBoost('appearance');

      final adjusted = policy.getAdjustedThreshold('appearance', 0.7);
      expect(adjusted, 1.0);
    });
  });

  group('RpConsistencyPreferences', () {
    test('should have correct defaults', () {
      const prefs = RpConsistencyPreferences();

      expect(prefs.enabled, true);
      expect(prefs.validators, isEmpty);
      expect(prefs.notifyLevel, NotificationLevel.always);
    });

    test('isValidatorEnabled should respect global enabled', () {
      const prefs = RpConsistencyPreferences(enabled: false);

      expect(prefs.isValidatorEnabled('appearance'), false);
    });

    test('isValidatorEnabled should respect per-validator setting', () {
      const prefs = RpConsistencyPreferences(
        enabled: true,
        validators: {'appearance': false, 'state': true},
      );

      expect(prefs.isValidatorEnabled('appearance'), false);
      expect(prefs.isValidatorEnabled('state'), true);
      expect(prefs.isValidatorEnabled('presence'), true); // default true
    });
  });

  group('buildOutputFixProposal', () {
    late RpConsistencyGate gate;

    setUp(() {
      gate = RpConsistencyGate();
    });

    test('should return null for empty violations', () {
      final proposal = gate.buildOutputFixProposal(
        [],
        storyId: 'test',
        branchId: 'main',
      );

      expect(proposal, isNull);
    });

    test('should create proposal for warnings', () {
      final violations = [
        RpViolation(
          code: ViolationCode.hairColorMismatch,
          severity: ViolationSeverity.warn,
          message: 'Hair color mismatch',
          confidence: 0.8,
          evidence: [],
          recommended: [
            const ProposeMemoryPatch(
              domain: 'ch',
              logicalId: 'rp:v1:ch:char1:card.base',
              patch: {'hair_color': 'gold'},
              description: 'Update hair color',
            ),
          ],
          validatorId: 'appearance',
          detectedAt: DateTime.now(),
        ),
      ];

      final proposal = gate.buildOutputFixProposal(
        violations,
        storyId: 'test',
        branchId: 'main',
      );

      expect(proposal, isNotNull);
      expect(proposal?.kindIndex, 5); // OUTPUT_FIX
      expect(proposal?.policyTierIndex, 1); // notifyApply for warnings
    });

    test('should create proposal with reviewRequired for errors', () {
      final violations = [
        RpViolation(
          code: ViolationCode.characterDeceased,
          severity: ViolationSeverity.error,
          message: 'Deceased character acting',
          confidence: 0.95,
          evidence: [],
          recommended: [],
          validatorId: 'presence',
          detectedAt: DateTime.now(),
        ),
      ];

      final proposal = gate.buildOutputFixProposal(
        violations,
        storyId: 'test',
        branchId: 'main',
      );

      expect(proposal, isNotNull);
      expect(proposal?.policyTierIndex, 2); // reviewRequired for errors
    });

    test('should return null for info-only violations', () {
      final violations = [
        RpViolation(
          code: ViolationCode.metagaming,
          severity: ViolationSeverity.info,
          message: 'Possible metagaming',
          confidence: 0.5,
          evidence: [],
          recommended: [],
          validatorId: 'knowledge',
          detectedAt: DateTime.now(),
        ),
      ];

      final proposal = gate.buildOutputFixProposal(
        violations,
        storyId: 'test',
        branchId: 'main',
      );

      expect(proposal, isNull); // info level doesn't create proposals
    });
  });
}

class _MockMemoryReader implements RpMemoryReader {
  @override
  Future<RpEntryBlob?> getByLogicalId(String logicalId) async => null;

  @override
  Iterable<String> logicalIdsByDomain(String domain) => [];

  @override
  int get foundationRev => 0;

  @override
  int get storyRev => 0;

  @override
  String get branchId => 'main';

  @override
  String get storyId => 'test';
}
