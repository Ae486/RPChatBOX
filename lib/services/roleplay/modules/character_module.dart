/// Character Module (P0)
///
/// Provides character cards and appearance as high-priority context fragments.
/// POS: Services / Roleplay / Modules

import '../context_compiler/rp_fragment.dart';
import '../context_compiler/rp_module.dart';

/// Character memory module - P0 priority
class CharacterModule implements RpModule {
  static const String moduleId = 'character';
  static const String domainCodeValue = 'ch';
  static const int weight = 90;

  /// Entry types handled by this module
  static const Set<String> supportedEntryTypes = {
    'card.base',
    'card.delta',
    'appearance',
  };

  @override
  String get id => moduleId;

  @override
  String get displayName => 'Character';

  @override
  String get domainCode => domainCodeValue;

  @override
  int get domainWeight => weight;

  @override
  Set<String> get softDependencies => const {};

  @override
  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx) async {
    final fragments = <RpFragmentCandidate>[];

    // Get all character entries
    final logicalIds = ctx.reader.logicalIdsByDomain('character');

    for (final logicalId in logicalIds) {
      final blob = await ctx.reader.getByLogicalId(logicalId);
      if (blob == null) continue;

      // Only process supported entry types
      if (!supportedEntryTypes.contains(blob.entryType)) continue;

      final content = blob.contentJson;
      if (content.isEmpty) continue;

      final tokens = blob.approxTokens ?? ctx.estimator.estimate(content);
      final priority = _getPriorityForEntryType(blob.entryType);
      final isRequired = blob.entryType == 'card.base';

      fragments.add(RpFragmentCandidate(
        id: '${moduleId}_${blob.entryType}_${_extractEntityKey(logicalId)}',
        moduleId: moduleId,
        viewId: blob.entryType,
        priority: priority,
        text: _formatCharacterContent(blob.entryType, content, blob.preview),
        costTokens: tokens,
        score: _calculateScore(blob.entryType, tokens, isRequired),
        required: isRequired,
        dedupeKey: logicalId,
        attrs: {
          'logicalId': logicalId,
          'entryType': blob.entryType,
          'sourceRev': blob.sourceRev.toString(),
        },
      ));
    }

    // Sort by entry type priority: card.base > card.delta > appearance
    fragments.sort((a, b) {
      final typeOrder = {'card.base': 0, 'card.delta': 1, 'appearance': 2};
      final orderA = typeOrder[a.viewId] ?? 99;
      final orderB = typeOrder[b.viewId] ?? 99;
      return orderA.compareTo(orderB);
    });

    return fragments;
  }

  /// Get priority tier for entry type
  RpPriority _getPriorityForEntryType(String entryType) {
    switch (entryType) {
      case 'card.base':
        return RpPriority.p0;
      case 'card.delta':
        return RpPriority.p0;
      case 'appearance':
        return RpPriority.p1;
      default:
        return RpPriority.p2;
    }
  }

  /// Format character content for context injection
  String _formatCharacterContent(String entryType, String contentJson, String? preview) {
    final header = _getHeaderForEntryType(entryType);
    final content = preview ?? contentJson;
    return '## $header\n$content';
  }

  /// Get display header for entry type
  String _getHeaderForEntryType(String entryType) {
    switch (entryType) {
      case 'card.base':
        return 'Character Profile';
      case 'card.delta':
        return 'Character Updates';
      case 'appearance':
        return 'Current Appearance';
      default:
        return 'Character';
    }
  }

  /// Extract entity key from logical ID
  String _extractEntityKey(String logicalId) {
    // Format: rp:v1:ch:<entityKey>:<entryType>
    final parts = logicalId.split(':');
    if (parts.length >= 4) {
      return parts[3];
    }
    return 'unknown';
  }

  /// Calculate utility score for character fragment
  double _calculateScore(String entryType, int costTokens, bool isRequired) {
    const priorityBase = 1000.0;
    final domainBonus = weight.toDouble();
    final requiredBonus = isRequired ? 60.0 : 0.0;

    // Entry type bonus
    double typeBonus;
    switch (entryType) {
      case 'card.base':
        typeBonus = 50.0;
        break;
      case 'card.delta':
        typeBonus = 40.0;
        break;
      case 'appearance':
        typeBonus = 20.0;
        break;
      default:
        typeBonus = 0.0;
    }

    return priorityBase + domainBonus + requiredBonus + typeBonus;
  }
}
