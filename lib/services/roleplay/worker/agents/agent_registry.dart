/// 轻量 Agent 注册表
///
/// 纯元数据目录，不执行逻辑
/// 执行由 AgentExecutor 统一处理
/// POS: Services / Roleplay / Worker / Agents
library;

import 'model_adapter.dart';

/// Agent 描述符
///
/// 包含 Agent 的完整配置信息
class AgentDescriptor {
  /// 唯一 ID
  final String id;

  /// 提示词键（关联 AgentPrompts）
  final String promptKey;

  /// 输出 Schema 版本
  final String schemaVersion;

  /// Proposal 转换器 ID
  final String transformerId;

  /// 描述
  final String description;

  /// 是否需要 LLM 调用
  final bool requiresLlm;

  /// 默认超时（毫秒）
  final int defaultTimeoutMs;

  /// 最大重试次数
  final int maxRetries;

  /// 模型配置覆盖（可选）
  final ModelSpec? modelSpec;

  /// 是否默认启用
  final bool enabledByDefault;

  const AgentDescriptor({
    required this.id,
    required this.promptKey,
    this.schemaVersion = '1.0',
    String? transformerId,
    this.description = '',
    this.requiresLlm = true,
    this.defaultTimeoutMs = 30000,
    this.maxRetries = 2,
    this.modelSpec,
    this.enabledByDefault = true,
  }) : transformerId = transformerId ?? id;

  @override
  String toString() => 'AgentDescriptor($id)';
}

/// 模型配置
class ModelSpec {
  /// 模型 ID 覆盖（为空则使用默认）
  final String? modelId;

  /// 温度覆盖
  final double? temperature;

  /// 最大输出 token 覆盖
  final int? maxOutputTokens;

  /// 提示词层级覆盖
  final PromptTier? promptTier;

  const ModelSpec({
    this.modelId,
    this.temperature,
    this.maxOutputTokens,
    this.promptTier,
  });
}

/// 轻量 Agent 注册表
///
/// 职责：
/// - 注册/查询 Agent 元数据
/// - 校验唯一性
/// - 提供配置给 AgentExecutor
///
/// 不执行逻辑，执行由 AgentExecutor 统一处理
class AgentRegistry {
  final Map<String, AgentDescriptor> _descriptors = {};

  /// 注册 Agent
  void register(AgentDescriptor descriptor) {
    if (_descriptors.containsKey(descriptor.id)) {
      throw StateError('Duplicate agentId: ${descriptor.id}');
    }
    _descriptors[descriptor.id] = descriptor;
  }

  /// 批量注册
  void registerAll(List<AgentDescriptor> descriptors) {
    for (final d in descriptors) {
      register(d);
    }
  }

  /// 获取 Agent 描述符
  AgentDescriptor? get(String agentId) => _descriptors[agentId];

  /// 获取 Agent 描述符（抛出异常如果不存在）
  AgentDescriptor getOrThrow(String agentId) {
    final descriptor = _descriptors[agentId];
    if (descriptor == null) {
      throw StateError('Agent not registered: $agentId');
    }
    return descriptor;
  }

  /// 检查是否已注册
  bool has(String agentId) => _descriptors.containsKey(agentId);

  /// 获取所有已注册的 Agent ID
  List<String> get registeredAgents => _descriptors.keys.toList();

  /// 获取所有描述符
  Iterable<AgentDescriptor> get allDescriptors => _descriptors.values;

  /// 获取启用的 Agent
  List<AgentDescriptor> get enabledAgents =>
      _descriptors.values.where((d) => d.enabledByDefault).toList();

  /// 注销 Agent
  void unregister(String agentId) {
    _descriptors.remove(agentId);
  }

  /// 清空所有注册
  void clear() {
    _descriptors.clear();
  }
}

/// 全局 Agent 注册表实例
AgentRegistry? _globalRegistry;

/// 获取全局注册表
AgentRegistry get agentRegistry {
  _globalRegistry ??= AgentRegistry();
  return _globalRegistry!;
}

/// 初始化全局注册表
void initAgentRegistry(AgentRegistry registry) {
  _globalRegistry = registry;
}

/// 重置全局注册表（仅用于测试）
void resetAgentRegistry() {
  _globalRegistry = null;
}

// ===========================================================================
// 预定义 Agent 描述符
// ===========================================================================

/// 场景检测器
const sceneDetectorDescriptor = AgentDescriptor(
  id: 'scene_detector',
  promptKey: 'scene_detector',
  transformerId: 'scene_detector',
  description: '检测场景转换',
  defaultTimeoutMs: 30000,
);

/// 状态更新器
const stateUpdaterDescriptor = AgentDescriptor(
  id: 'state_updater',
  promptKey: 'state_updater',
  transformerId: 'state_updater',
  description: '检测状态更新',
  defaultTimeoutMs: 30000,
);

/// 关键事件提取器
const keyEventExtractorDescriptor = AgentDescriptor(
  id: 'key_event_extractor',
  promptKey: 'key_event_extractor',
  transformerId: 'key_event_extractor',
  description: '提取关键事件',
  defaultTimeoutMs: 30000,
);

/// 一致性重检测器
const consistencyHeavyDescriptor = AgentDescriptor(
  id: 'consistency_heavy',
  promptKey: 'consistency_heavy',
  transformerId: 'consistency_heavy',
  description: '重量级一致性检测',
  defaultTimeoutMs: 45000,
  maxRetries: 1,
);

/// 所有预定义 Agent 描述符
const allAgentDescriptors = [
  sceneDetectorDescriptor,
  stateUpdaterDescriptor,
  keyEventExtractorDescriptor,
  consistencyHeavyDescriptor,
];

/// 初始化默认 Agent 注册
void initDefaultAgents(AgentRegistry registry) {
  registry.registerAll(allAgentDescriptors);
}
