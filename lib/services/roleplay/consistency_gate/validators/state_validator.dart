/// State Validator
///
/// Light-weight validator that detects state constraint violations
/// (item usage, injury ignored, ability exceeded).
/// POS: Services / Roleplay / Consistency Gate / Validators

import '../rp_validator.dart';
import '../rp_violation.dart';
import '../rp_validation_context.dart';
import '../utils/rp_text_extractor.dart';
import '../utils/rp_blob_parser.dart';
import '../../../../models/roleplay/rp_entry_blob.dart';

/// Validates state consistency
class StateValidator extends RpValidator {
  @override
  String get id => 'state';

  @override
  String get displayName => 'State Validator';

  @override
  ValidatorWeight get weight => ValidatorWeight.light;

  @override
  double get defaultThreshold => ValidatorThresholds.state;

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    final violations = <RpViolation>[];
    final text = ctx.getTextForValidation();

    // Get state entries
    final stateLogicalIds = ctx.memory.logicalIdsByDomain('st').toList();

    // Collect all owned items and active states
    final ownedItems = <String>{};
    final activeInjuries = <String>[];
    final activeStatuses = <String>[];
    String? stateLogicalId;

    for (final logicalId in stateLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      stateLogicalId = logicalId;
      final stateData = blob.safeParseJson();

      if (stateData['inventory'] is List) {
        ownedItems.addAll(
            (stateData['inventory'] as List).map((e) => e.toString()));
      }
      if (stateData['items'] is List) {
        ownedItems.addAll((stateData['items'] as List).map((e) => e.toString()));
      }
      if (stateData['injuries'] is List) {
        activeInjuries
            .addAll((stateData['injuries'] as List).map((e) => e.toString()));
      }
      if (stateData['statuses'] is List) {
        activeStatuses
            .addAll((stateData['statuses'] as List).map((e) => e.toString()));
      }
    }

    // Also check character inventory
    final characterLogicalIds = ctx.memory.logicalIdsByDomain('ch').toList();
    for (final logicalId in characterLogicalIds) {
      final blob = await ctx.memory.getByLogicalId(logicalId);
      if (blob == null) continue;

      final charData = blob.safeParseJson();
      if (charData['inventory'] is List) {
        ownedItems
            .addAll((charData['inventory'] as List).map((e) => e.toString()));
      }
    }

    // Check for items being used that aren't owned
    // Use pattern matching to detect item references in action contexts
    final commonItems = _getCommonItemPatterns();
    for (final pattern in commonItems) {
      final regex = RegExp(pattern, caseSensitive: false);
      final matches = regex.allMatches(text);

      for (final match in matches) {
        final itemName = match.group(0)!;

        // Check if this is an action context
        final context = _extractContext(text, match.start, match.end);
        if (_isActionContext(context)) {
          // Check if item is owned
          final isOwned =
              ownedItems.any((item) => item.toLowerCase().contains(
                    itemName.toLowerCase(),
                  ));

          if (!isOwned) {
            violations.add(RpViolation(
              code: ViolationCode.itemNotOwned,
              severity: ViolationSeverity.warn,
              message: 'Character uses "$itemName" but does not own it',
              expected: 'Item in inventory',
              found: itemName,
              confidence: 0.7,
              evidence: stateLogicalId != null
                  ? [
                      RpEvidenceRef(
                        type: 'validator',
                        refId: stateLogicalId,
                        note: 'inventory',
                      )
                    ]
                  : [],
              recommended: [
                ProposeMemoryPatch(
                  domain: 'st',
                  logicalId: stateLogicalId ?? 'unknown',
                  patch: {
                    'inventory': [...ownedItems, itemName]
                  },
                  description: 'Add "$itemName" to inventory',
                ),
                SuggestUserCorrection(
                  'The character does not have "$itemName" in their inventory',
                ),
              ],
              validatorId: id,
              detectedAt: DateTime.now(),
            ));
          }
        }
      }
    }

    // Check if injuries are being ignored
    if (activeInjuries.isNotEmpty) {
      final mentionsInjury = RpTextExtractor.containsInjuryMention(text);
      final hasPhysicalAction = _hasPhysicalAction(text);

      // If there are active injuries and physical actions but no injury mention
      // this might be a violation (low confidence)
      if (hasPhysicalAction && !mentionsInjury) {
        for (final injury in activeInjuries) {
          if (_injuryAffectsAction(injury, text)) {
            violations.add(RpViolation(
              code: ViolationCode.injuryIgnored,
              severity: ViolationSeverity.info,
              message: 'Character has injury "$injury" but output ignores it',
              expected: 'Injury acknowledged in action',
              found: 'No injury mention',
              confidence: 0.5, // Low confidence since this is heuristic
              evidence: stateLogicalId != null
                  ? [
                      RpEvidenceRef(
                        type: 'validator',
                        refId: stateLogicalId,
                        note: 'injuries',
                      )
                    ]
                  : [],
              recommended: [
                SuggestIgnore(
                    'Injury may not affect the current action'),
              ],
              validatorId: id,
              detectedAt: DateTime.now(),
            ));
          }
        }
      }
    }

    return filterByThreshold(violations);
  }

  /// Get common item patterns to look for
  List<String> _getCommonItemPatterns() {
    return [
      r'剑|刀|枪|弓|矛|斧|锤',
      r'杖|法杖|魔杖|权杖',
      r'盾|盾牌',
      r'药水|药剂',
      r'钥匙|锁',
      r'书|卷轴',
      r'sword|blade|dagger',
      r'staff|wand|rod',
      r'shield',
      r'potion|elixir',
      r'key|lock',
      r'book|scroll',
    ];
  }

  /// Check if context suggests item action
  bool _isActionContext(String context) {
    final actionPatterns = [
      r'拔出',
      r'挥舞',
      r'使用',
      r'握着',
      r'拿起',
      r'抽出',
      r'drew',
      r'wielded',
      r'used',
      r'gripped',
      r'grabbed',
      r'pulled out',
    ];

    for (final pattern in actionPatterns) {
      if (RegExp(pattern, caseSensitive: false).hasMatch(context)) {
        return true;
      }
    }
    return false;
  }

  /// Extract context around a match
  String _extractContext(String text, int start, int end, {int radius = 30}) {
    final contextStart = (start - radius).clamp(0, text.length);
    final contextEnd = (end + radius).clamp(0, text.length);
    return text.substring(contextStart, contextEnd);
  }

  /// Check if text contains physical actions
  bool _hasPhysicalAction(String text) {
    final patterns = [
      r'跑|走|跳|爬|游泳|攀登',
      r'打|踢|推|拉|抓|举',
      r'挥|砍|刺|射',
      r'ran|walked|jumped|climbed|swam',
      r'hit|kicked|pushed|pulled|grabbed|lifted',
      r'swung|slashed|stabbed|shot',
    ];

    for (final pattern in patterns) {
      if (RegExp(pattern, caseSensitive: false).hasMatch(text)) {
        return true;
      }
    }
    return false;
  }

  /// Check if injury would affect the described action
  bool _injuryAffectsAction(String injury, String text) {
    final injuryLower = injury.toLowerCase();
    final textLower = text.toLowerCase();

    // Leg/foot injuries affect movement
    if (injuryLower.contains('腿') ||
        injuryLower.contains('脚') ||
        injuryLower.contains('leg') ||
        injuryLower.contains('foot')) {
      if (textLower.contains('跑') ||
          textLower.contains('走') ||
          textLower.contains('跳') ||
          textLower.contains('ran') ||
          textLower.contains('walked') ||
          textLower.contains('jumped')) {
        return true;
      }
    }

    // Arm/hand injuries affect manipulation
    if (injuryLower.contains('手') ||
        injuryLower.contains('臂') ||
        injuryLower.contains('arm') ||
        injuryLower.contains('hand')) {
      if (textLower.contains('挥') ||
          textLower.contains('拿') ||
          textLower.contains('握') ||
          textLower.contains('swung') ||
          textLower.contains('grabbed') ||
          textLower.contains('held')) {
        return true;
      }
    }

    return false;
  }
}
