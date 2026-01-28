/// Proposal 转换器
///
/// 将 Agent 的 JSON 输出转换为 Proposal 列表
/// POS: Services / Roleplay / Worker / Agents
library;

import 'agent_registry.dart';
import '../rp_memory_snapshot.dart';

/// Proposal 转换上下文
class TransformContext {
  /// Agent 描述符
  final AgentDescriptor agent;

  /// 内存读取器
  final RpWorkerMemoryReader memoryReader;

  /// 原始输入
  final Map<String, dynamic> inputs;

  const TransformContext({
    required this.agent,
    required this.memoryReader,
    required this.inputs,
  });

  /// 获取版本信息
  int get sourceRev => memoryReader.version?.sourceRev ?? 0;
  int get foundationRev => memoryReader.version?.foundationRev ?? 0;
  int get storyRev => memoryReader.version?.storyRev ?? 0;
}

/// Proposal 转换器接口
abstract class ProposalTransformer {
  /// 转换器 ID
  String get id;

  /// 转换 LLM 解析结果为 Proposal 列表
  List<Map<String, dynamic>> transform({
    required Map<String, dynamic> data,
    required TransformContext ctx,
  });
}

/// Proposal 转换器注册表
class ProposalTransformerRegistry {
  final Map<String, ProposalTransformer> _transformers = {};

  /// 注册转换器
  void register(ProposalTransformer transformer) {
    if (_transformers.containsKey(transformer.id)) {
      throw StateError('Duplicate transformerId: ${transformer.id}');
    }
    _transformers[transformer.id] = transformer;
  }

  /// 批量注册
  void registerAll(List<ProposalTransformer> transformers) {
    for (final t in transformers) {
      register(t);
    }
  }

  /// 获取转换器
  ProposalTransformer? get(String id) => _transformers[id];

  /// 获取转换器（抛出异常如果不存在）
  ProposalTransformer getOrThrow(String id) {
    final transformer = _transformers[id];
    if (transformer == null) {
      throw StateError('Transformer not registered: $id');
    }
    return transformer;
  }

  /// 检查是否已注册
  bool has(String id) => _transformers.containsKey(id);

  /// 清空
  void clear() {
    _transformers.clear();
  }
}

/// 全局转换器注册表
ProposalTransformerRegistry? _globalTransformerRegistry;

ProposalTransformerRegistry get proposalTransformerRegistry {
  _globalTransformerRegistry ??= ProposalTransformerRegistry();
  return _globalTransformerRegistry!;
}

void initProposalTransformerRegistry(ProposalTransformerRegistry registry) {
  _globalTransformerRegistry = registry;
}

void resetTransformerRegistry() {
  _globalTransformerRegistry = null;
}

// ===========================================================================
// 内置转换器实现
// ===========================================================================

/// 生成唯一 ID
String _generateId(String prefix) =>
    '${prefix}_${DateTime.now().millisecondsSinceEpoch}';

/// 场景检测器转换器
class SceneDetectorTransformer implements ProposalTransformer {
  @override
  String get id => 'scene_detector';

  @override
  List<Map<String, dynamic>> transform({
    required Map<String, dynamic> data,
    required TransformContext ctx,
  }) {
    if (data['detected'] != true) return [];

    final toScene = data['proposal']?['to_scene'];
    if (toScene == null) return [];

    final sceneId = _generateId('scene');
    return [
      {
        'kind': 'SCENE_TRANSITION',
        'domain': 'scene',
        'policyTier': 'reviewRequired',
        'target': {
          'scopeIndex': 1, // story
          'statusIndex': 0, // confirmed
          'logicalId': sceneId,
        },
        'payload': {
          'fromSceneId': data['proposal']?['from_scene_id'],
          'toScene': toScene,
        },
        'evidence': [
          {'type': 'message_span', 'note': data['evidence']},
        ],
        'reason': 'Detected ${data['transition_type']} transition',
        'sourceRev': ctx.sourceRev,
        'expectedFoundationRev': ctx.foundationRev,
        'expectedStoryRev': ctx.storyRev,
      },
    ];
  }
}

/// 状态更新器转换器
class StateUpdaterTransformer implements ProposalTransformer {
  @override
  String get id => 'state_updater';

  @override
  List<Map<String, dynamic>> transform({
    required Map<String, dynamic> data,
    required TransformContext ctx,
  }) {
    final updates = data['updates'] as List? ?? [];
    if (updates.isEmpty) return [];

    return updates.map<Map<String, dynamic>>((u) {
      final targetId =
          u['targetId'] as String? ?? _generateId('state');
      return {
        'kind': 'DRAFT_UPDATE',
        'domain': u['domain'] ?? 'state',
        'policyTier': 'notifyApply',
        'target': {
          'scopeIndex': 1, // story
          'statusIndex': 1, // draft
          'logicalId': targetId,
        },
        'payload': {
          'targetId': targetId,
          'field': u['field'],
          'oldValue': u['oldValue'],
          'newValue': u['newValue'],
        },
        'evidence': [
          {'type': 'message_span', 'note': u['evidence']},
        ],
        'reason': u['reason'] ?? 'State update detected',
        'sourceRev': ctx.sourceRev,
        'expectedFoundationRev': ctx.foundationRev,
        'expectedStoryRev': ctx.storyRev,
      };
    }).toList();
  }
}

/// 关键事件提取器转换器
class KeyEventExtractorTransformer implements ProposalTransformer {
  @override
  String get id => 'key_event_extractor';

  @override
  List<Map<String, dynamic>> transform({
    required Map<String, dynamic> data,
    required TransformContext ctx,
  }) {
    final events = data['events'] as List? ?? [];
    if (events.isEmpty) return [];

    return events.map<Map<String, dynamic>>((e) {
      final eventId = _generateId('ev');
      return {
        'kind': 'CONFIRMED_WRITE',
        'domain': 'timeline',
        'policyTier': 'silent',
        'target': {
          'scopeIndex': 1, // story
          'statusIndex': 0, // confirmed
          'logicalId': eventId,
        },
        'payload': {
          'eventId': eventId,
          'summary': e['summary'],
          'tags': e['tags'] ?? [],
          'timestamp': e['timestamp'],
          'participants': e['participants'] ?? [],
        },
        'evidence': [
          {'type': 'message_span', 'note': e['evidence']},
        ],
        'reason': 'Extracted key event',
        'sourceRev': ctx.sourceRev,
        'expectedFoundationRev': ctx.foundationRev,
        'expectedStoryRev': ctx.storyRev,
      };
    }).toList();
  }
}

/// 一致性检测器转换器
class ConsistencyHeavyTransformer implements ProposalTransformer {
  @override
  String get id => 'consistency_heavy';

  @override
  List<Map<String, dynamic>> transform({
    required Map<String, dynamic> data,
    required TransformContext ctx,
  }) {
    final violations = data['violations'] as List? ?? [];
    if (violations.isEmpty) return [];

    return violations.map<Map<String, dynamic>>((v) {
      final fixId = _generateId('fix');
      return {
        'kind': 'OUTPUT_FIX',
        'domain': v['domain'] ?? 'consistency',
        'policyTier': 'reviewRequired',
        'target': {
          'scopeIndex': 1, // story
          'statusIndex': 1, // draft
          'logicalId': fixId,
        },
        'payload': {
          'violationType': v['type'],
          'description': v['description'],
          'suggestedFix': v['suggestedFix'],
          'confidence': v['confidence'],
        },
        'evidence': [
          {'type': 'output_span', 'note': v['evidence']},
        ],
        'reason': 'Consistency violation detected',
        'sourceRev': ctx.sourceRev,
        'expectedFoundationRev': ctx.foundationRev,
        'expectedStoryRev': ctx.storyRev,
      };
    }).toList();
  }
}

/// 所有内置转换器
final allBuiltInTransformers = <ProposalTransformer>[
  SceneDetectorTransformer(),
  StateUpdaterTransformer(),
  KeyEventExtractorTransformer(),
  ConsistencyHeavyTransformer(),
];

/// 初始化默认转换器
void initDefaultTransformers(ProposalTransformerRegistry registry) {
  registry.registerAll(allBuiltInTransformers);
}
