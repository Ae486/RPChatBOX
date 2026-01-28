/// Scene Module (P0)
///
/// Provides current scene state as high-priority context fragment.
/// POS: Services / Roleplay / Modules

import '../context_compiler/rp_fragment.dart';
import '../context_compiler/rp_module.dart';

/// Scene memory module - P0 priority
class SceneModule implements RpModule {
  static const String moduleId = 'scene';
  static const String domainCodeValue = 'sc';
  static const int weight = 100;

  /// Logical ID for current scene state
  static const String currentSceneLogicalId = 'rp:v1:sc:current:state';

  @override
  String get id => moduleId;

  @override
  String get displayName => 'Scene';

  @override
  String get domainCode => domainCodeValue;

  @override
  int get domainWeight => weight;

  @override
  Set<String> get softDependencies => const {};

  @override
  Future<List<RpFragmentCandidate>> buildFragments(RpFragmentContext ctx) async {
    final fragments = <RpFragmentCandidate>[];

    // Read current scene state
    final blob = await ctx.reader.getByLogicalId(currentSceneLogicalId);
    if (blob == null) return fragments;

    final content = blob.contentJson;
    if (content.isEmpty) return fragments;

    // Use pre-calculated tokens if available, otherwise estimate
    final tokens = blob.approxTokens ?? ctx.estimator.estimate(content);

    fragments.add(RpFragmentCandidate(
      id: '${moduleId}_current_state',
      moduleId: moduleId,
      viewId: 'state',
      priority: RpPriority.p0,
      text: _formatSceneContent(content, blob.preview),
      costTokens: tokens,
      score: _calculateScore(tokens),
      required: true,
      dedupeKey: currentSceneLogicalId,
      attrs: {
        'logicalId': blob.logicalId,
        'sourceRev': blob.sourceRev.toString(),
      },
    ));

    return fragments;
  }

  /// Format scene content for context injection
  String _formatSceneContent(String contentJson, String? preview) {
    // Use preview if available for compact representation
    if (preview != null && preview.isNotEmpty) {
      return '## Current Scene\n$preview';
    }
    // Otherwise use full content
    return '## Current Scene\n$contentJson';
  }

  /// Calculate utility score for scene fragment
  double _calculateScore(int costTokens) {
    // Base score for P0 required fragment
    const priorityBase = 1000.0;
    // Scene domain has highest weight
    final domainBonus = weight.toDouble();
    // Required flag bonus
    const requiredBonus = 60.0;

    return priorityBase + domainBonus + requiredBonus;
  }
}
