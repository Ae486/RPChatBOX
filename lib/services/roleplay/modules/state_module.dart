/// State Module (P0)
///
/// Provides character state entries (injuries, inventory, flags) as context fragments.
/// POS: Services / Roleplay / Modules

import '../context_compiler/rp_fragment.dart';
import '../context_compiler/rp_module.dart';

/// State memory module - P0 priority
class StateModule implements RpModule {
  static const String moduleId = 'state';
  static const String domainCodeValue = 'st';
  static const int weight = 85;

  /// Entry types handled by this module
  static const Set<String> supportedEntryTypes = {
    'injury',
    'inventory',
    'flag',
    'status',
  };

  @override
  String get id => moduleId;

  @override
  String get displayName => 'State';

  @override
  String get domainCode => domainCodeValue;

  @override
  int get domainWeight => weight;

  @override
  Set<String> get softDependencies => {'character'};

  @override
  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx) async {
    final fragments = <RpFragmentCandidate>[];

    // Get all state entries
    final logicalIds = ctx.reader.logicalIdsByDomain('state');

    for (final logicalId in logicalIds) {
      final blob = await ctx.reader.getByLogicalId(logicalId);
      if (blob == null) continue;

      // Only process supported entry types
      if (!supportedEntryTypes.contains(blob.entryType)) continue;

      final content = blob.contentJson;
      if (content.isEmpty) continue;

      final tokens = blob.approxTokens ?? ctx.estimator.estimate(content);
      final priority = _getPriorityForEntryType(blob.entryType);

      fragments.add(RpFragmentCandidate(
        id: '${moduleId}_${blob.entryType}_${_extractEntityKey(logicalId)}',
        moduleId: moduleId,
        viewId: blob.entryType,
        priority: priority,
        text: _formatStateContent(blob.entryType, content, blob.preview),
        costTokens: tokens,
        score: _calculateScore(blob.entryType, tokens),
        required: priority == RpPriority.p0,
        dedupeKey: logicalId,
        attrs: {
          'logicalId': logicalId,
          'entryType': blob.entryType,
          'sourceRev': blob.sourceRev.toString(),
        },
      ));
    }

    // Sort by entry type priority
    fragments.sort((a, b) {
      final typeOrder = {'injury': 0, 'status': 1, 'inventory': 2, 'flag': 3};
      final orderA = typeOrder[a.viewId] ?? 99;
      final orderB = typeOrder[b.viewId] ?? 99;
      return orderA.compareTo(orderB);
    });

    return fragments;
  }

  /// Get priority tier for entry type
  RpPriority _getPriorityForEntryType(String entryType) {
    switch (entryType) {
      case 'injury':
        return RpPriority.p0; // Injuries are critical
      case 'status':
        return RpPriority.p0; // Status effects are critical
      case 'inventory':
        return RpPriority.p1; // Inventory is important
      case 'flag':
        return RpPriority.p2; // Flags are optional
      default:
        return RpPriority.p2;
    }
  }

  /// Format state content for context injection
  String _formatStateContent(String entryType, String contentJson, String? preview) {
    final header = _getHeaderForEntryType(entryType);
    final content = preview ?? contentJson;
    return '## $header\n$content';
  }

  /// Get display header for entry type
  String _getHeaderForEntryType(String entryType) {
    switch (entryType) {
      case 'injury':
        return 'Current Injuries';
      case 'status':
        return 'Status Effects';
      case 'inventory':
        return 'Inventory';
      case 'flag':
        return 'Story Flags';
      default:
        return 'State';
    }
  }

  /// Extract entity key from logical ID
  String _extractEntityKey(String logicalId) {
    // Format: rp:v1:st:<entityKey>:<entryType>
    final parts = logicalId.split(':');
    if (parts.length >= 4) {
      return parts[3];
    }
    return 'unknown';
  }

  /// Calculate utility score for state fragment
  double _calculateScore(String entryType, int costTokens) {
    const priorityBase = 1000.0;
    final domainBonus = weight.toDouble();

    // Entry type bonus
    double typeBonus;
    switch (entryType) {
      case 'injury':
        typeBonus = 50.0; // Injuries are most critical
        break;
      case 'status':
        typeBonus = 45.0;
        break;
      case 'inventory':
        typeBonus = 30.0;
        break;
      case 'flag':
        typeBonus = 10.0;
        break;
      default:
        typeBonus = 0.0;
    }

    return priorityBase + domainBonus + typeBonus;
  }
}
