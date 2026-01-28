/// Context Compiler
///
/// Main orchestrator for compiling roleplay memory into prompt context.
/// POS: Services / Roleplay / Context Compiler

import '../rp_memory_repository.dart';
import 'rp_budget_broker.dart';
import 'rp_fragment.dart';
import 'rp_memory_reader.dart';
import 'rp_module.dart';
import 'rp_token_estimator.dart';
import '../modules/scene_module.dart';
import '../modules/character_module.dart';
import '../modules/state_module.dart';

/// Result of context compilation
class RpCompileResult {
  final RpPackedContext packed;
  final String renderedText;
  final bool hasP0Overflow;
  final Duration compileDuration;

  const RpCompileResult({
    required this.packed,
    required this.renderedText,
    required this.hasP0Overflow,
    required this.compileDuration,
  });

  bool get isEmpty => packed.allInjected.isEmpty;
}

/// Context compiler for roleplay memory
class RpContextCompiler {
  final RpMemoryRepository _repository;
  final RpModuleRegistry _registry;
  final RpTokenEstimator _estimator;

  RpContextCompiler({
    required RpMemoryRepository repository,
    RpModuleRegistry? registry,
    RpTokenEstimator? estimator,
  })  : _repository = repository,
        _registry = registry ?? _createDefaultRegistry(),
        _estimator = estimator ?? const RpTokenEstimator();

  /// Create default module registry with P0 modules
  static RpModuleRegistry _createDefaultRegistry() {
    final registry = RpModuleRegistry();
    registry.register(SceneModule());
    registry.register(CharacterModule());
    registry.register(StateModule());
    return registry;
  }

  /// Compile context for a story/branch
  Future<RpCompileResult> compile({
    required String storyId,
    required String branchId,
    required int maxTokensTotal,
    Map<String, dynamic>? hints,
  }) async {
    final stopwatch = Stopwatch()..start();

    // Load snapshots (foundation + story scope)
    final foundationSnapshot = await _repository.getLatestSnapshot(
      storyId, 0, branchId, // foundation scope
    );

    final storySnapshot = await _repository.getLatestSnapshot(
      storyId, 1, branchId, // story scope
    );

    // Create merged memory reader
    final reader = RpMergedMemoryReader(
      repository: _repository,
      foundationSnapshot: foundationSnapshot,
      storySnapshot: storySnapshot,
    );

    // Build fragment context
    final ctx = RpFragmentContext(
      reader: reader,
      estimator: _estimator,
      budgetHint: maxTokensTotal,
      hints: hints ?? const {},
    );

    // Collect fragments from all modules
    final allCandidates = <RpFragmentCandidate>[];
    for (final module in _registry.sortedByWeight) {
      final fragments = await module.buildFragments(ctx);
      allCandidates.addAll(fragments);
    }

    // Pack fragments using budget broker
    final broker = RpBudgetBroker(
      config: RpBudgetConfig(maxTokensTotal: maxTokensTotal),
    );
    final packed = broker.pack(allCandidates);

    // Check for P0 overflow
    final hasP0Overflow = broker.hasP0Overflow(packed);

    // Render final text
    final renderedText = render(packed);

    stopwatch.stop();

    return RpCompileResult(
      packed: packed,
      renderedText: renderedText,
      hasP0Overflow: hasP0Overflow,
      compileDuration: stopwatch.elapsed,
    );
  }

  /// Render packed context to text
  String render(RpPackedContext packed) {
    if (packed.allInjected.isEmpty) return '';

    final buffer = StringBuffer();
    buffer.writeln('# Roleplay Context');
    buffer.writeln();

    // Render by priority groups
    if (packed.injectedP0.isNotEmpty) {
      for (final fragment in packed.injectedP0) {
        buffer.writeln(fragment.text);
        buffer.writeln();
      }
    }

    if (packed.injectedP1.isNotEmpty) {
      for (final fragment in packed.injectedP1) {
        buffer.writeln(fragment.text);
        buffer.writeln();
      }
    }

    if (packed.injectedP2.isNotEmpty) {
      for (final fragment in packed.injectedP2) {
        buffer.writeln(fragment.text);
        buffer.writeln();
      }
    }

    return buffer.toString().trimRight();
  }

  /// Register a custom module
  void registerModule(RpModule module) {
    _registry.register(module);
  }

  /// Get module registry for inspection
  RpModuleRegistry get registry => _registry;
}
