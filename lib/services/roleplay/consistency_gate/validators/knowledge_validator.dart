/// Knowledge Validator
///
/// Heavy validator that detects knowledge boundary violations
/// (character knowing information they shouldn't, metagaming).
/// POS: Services / Roleplay / Consistency Gate / Validators

import '../rp_validator.dart';
import '../rp_violation.dart';
import '../rp_validation_context.dart';
import '../utils/rp_blob_parser.dart';
import '../../../../models/roleplay/rp_entry_blob.dart';

/// Validates knowledge boundaries (Heavy - triggered only when needed)
class KnowledgeValidator extends RpValidator {
  @override
  String get id => 'knowledge';

  @override
  String get displayName => 'Knowledge Validator';

  @override
  ValidatorWeight get weight => ValidatorWeight.heavy;

  @override
  double get defaultThreshold => ValidatorThresholds.knowledge;

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    final violations = <RpViolation>[];
    final text = ctx.getTextForValidation();

    // Get character knowledge data
    final characterLogicalIds = ctx.memory.logicalIdsByDomain('ch').toList();

    final characters = <_CharacterKnowledge>[];

    for (final logicalId in characterLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      final charData = blob.safeParseJson();
      if (charData.isNotEmpty) {
        characters.add(_CharacterKnowledge(
          logicalId: logicalId,
          name: charData['name']?.toString() ?? '',
          secretsKnown: _extractSecrets(charData, 'secretsKnown'),
          secretsUnknown: _extractSecrets(charData, 'secretsUnknown'),
        ));
      }
    }

    if (characters.isEmpty) {
      return []; // No character data to validate
    }

    // Get world secrets/hidden information
    final worldLogicalIds = ctx.memory.logicalIdsByDomain('wd').toList();
    final hiddenInfo = <_HiddenInfo>[];

    for (final logicalId in worldLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      final worldData = blob.safeParseJson();
      if (worldData['secrets'] is List) {
        for (final secret in worldData['secrets'] as List) {
          if (secret is Map) {
            hiddenInfo.add(_HiddenInfo(
              logicalId: logicalId,
              content: secret['content']?.toString() ?? '',
              keywords: _extractSecretKeywords(secret),
              knownBy: (secret['knownBy'] as List?)
                      ?.map((e) => e.toString())
                      .toSet() ??
                  {},
            ));
          }
        }
      }
    }

    // Check for knowledge leaks in character dialogue/thoughts
    for (final character in characters) {
      // Skip if character not mentioned in text
      if (character.name.isEmpty || !text.contains(character.name)) {
        continue;
      }

      // Check if character reveals unknown secrets
      for (final secret in character.secretsUnknown) {
        if (_mentionsSecret(text, secret, character.name)) {
          violations.add(RpViolation(
            code: ViolationCode.knowledgeLeak,
            severity: ViolationSeverity.warn,
            message: 'Character "${character.name}" reveals information '
                'about "$secret" which they should not know',
            expected: 'Character unaware of secret',
            found: 'Character reveals secret knowledge',
            confidence: 0.7,
            evidence: [
              RpEvidenceRef(
                type: 'validator',
                refId: character.logicalId,
                note: 'knowledge.secrets',
              ),
            ],
            recommended: [
              ProposeMemoryPatch(
                domain: 'ch',
                logicalId: character.logicalId,
                patch: {
                  'secretsKnown': [...character.secretsKnown, secret]
                },
                description:
                    'Mark "${character.name}" as knowing about "$secret"',
              ),
              SuggestUserCorrection(
                'Character "${character.name}" should not know about "$secret"',
              ),
            ],
            validatorId: id,
            detectedAt: DateTime.now(),
          ));
        }
      }

      // Check world secrets
      for (final secret in hiddenInfo) {
        if (!secret.knownBy.contains(character.name) &&
            _mentionsSecretInfo(text, secret, character.name)) {
          violations.add(RpViolation(
            code: ViolationCode.knowledgeLeak,
            severity: ViolationSeverity.warn,
            message: 'Character "${character.name}" references hidden '
                'information they should not know',
            expected: 'Character unaware of hidden info',
            found: 'Character reveals hidden knowledge',
            confidence: 0.65,
            evidence: [
              RpEvidenceRef(
                type: 'validator',
                refId: secret.logicalId,
                note: 'world.secrets',
              ),
            ],
            recommended: [
              ProposeMemoryPatch(
                domain: 'wd',
                logicalId: secret.logicalId,
                patch: {
                  'knownBy': [...secret.knownBy, character.name]
                },
                description:
                    'Mark "${character.name}" as aware of this information',
              ),
              SuggestUserCorrection(
                'Character "${character.name}" should not have '
                'access to this information',
              ),
            ],
            validatorId: id,
            detectedAt: DateTime.now(),
          ));
        }
      }
    }

    // Check for metagaming patterns
    final metagamingViolations = _checkMetagaming(text, characters);
    violations.addAll(metagamingViolations);

    return filterByThreshold(violations);
  }

  /// Extract secrets list from character data
  List<String> _extractSecrets(Map<String, dynamic> data, String key) {
    if (data[key] is List) {
      return (data[key] as List).map((e) => e.toString()).toList();
    }
    return [];
  }

  /// Extract keywords from secret data
  List<String> _extractSecretKeywords(Map<dynamic, dynamic> secret) {
    final keywords = <String>[];

    if (secret['keywords'] is List) {
      keywords.addAll((secret['keywords'] as List).map((e) => e.toString()));
    }
    if (secret['content'] is String) {
      // Extract significant words (longer than 3 chars)
      final words = (secret['content'] as String)
          .split(RegExp(r'\s+'))
          .where((w) => w.length > 3);
      keywords.addAll(words);
    }

    return keywords;
  }

  /// Check if text mentions a secret in context of a character
  bool _mentionsSecret(String text, String secret, String characterName) {
    final textLower = text.toLowerCase();
    final secretLower = secret.toLowerCase();

    // Find character context (their dialogue or thoughts)
    final characterPatterns = [
      RegExp('$characterName[^。.]*?[说道问答].*?"[^"]*"', caseSensitive: false),
      RegExp('"[^"]*"[^。.]*?$characterName', caseSensitive: false),
      RegExp('$characterName.*?thought', caseSensitive: false),
    ];

    for (final pattern in characterPatterns) {
      final matches = pattern.allMatches(text);
      for (final match in matches) {
        final context = match.group(0)!.toLowerCase();
        if (context.contains(secretLower)) {
          return true;
        }
      }
    }

    return false;
  }

  /// Check if text mentions hidden info in context of a character
  bool _mentionsSecretInfo(
      String text, _HiddenInfo secret, String characterName) {
    // Check if any keywords appear near character's dialogue/actions
    for (final keyword in secret.keywords) {
      if (keyword.length > 3 && _mentionsSecret(text, keyword, characterName)) {
        return true;
      }
    }
    return false;
  }

  /// Check for metagaming patterns
  List<RpViolation> _checkMetagaming(
      String text, List<_CharacterKnowledge> characters) {
    final violations = <RpViolation>[];

    // Common metagaming patterns
    final metagamingPatterns = [
      // Player knowledge leaking into character
      RegExp(r'(?:know|知道).*?(?:player|玩家|author|作者)', caseSensitive: false),
      // Breaking fourth wall
      RegExp(r'(?:reader|读者|audience|观众)', caseSensitive: false),
      // Predicting based on story structure
      RegExp(r'(?:plot|剧情|story|故事).*?(?:require|需要|demand|要求)',
          caseSensitive: false),
    ];

    for (final pattern in metagamingPatterns) {
      if (pattern.hasMatch(text)) {
        violations.add(RpViolation(
          code: ViolationCode.metagaming,
          severity: ViolationSeverity.info,
          message: 'Potential metagaming detected - '
              'character may be using out-of-world knowledge',
          expected: 'In-character knowledge only',
          found: 'Possible metagaming reference',
          confidence: 0.5, // Low confidence for pattern matching
          evidence: [],
          recommended: [
            SuggestIgnore(
              'This may be intentional narrative technique',
            ),
          ],
          validatorId: id,
          detectedAt: DateTime.now(),
        ));
        break; // Only report once
      }
    }

    return violations;
  }
}

/// Internal class for character knowledge tracking
class _CharacterKnowledge {
  final String logicalId;
  final String name;
  final List<String> secretsKnown;
  final List<String> secretsUnknown;

  const _CharacterKnowledge({
    required this.logicalId,
    required this.name,
    required this.secretsKnown,
    required this.secretsUnknown,
  });
}

/// Internal class for hidden world information
class _HiddenInfo {
  final String logicalId;
  final String content;
  final List<String> keywords;
  final Set<String> knownBy;

  const _HiddenInfo({
    required this.logicalId,
    required this.content,
    required this.keywords,
    required this.knownBy,
  });
}
