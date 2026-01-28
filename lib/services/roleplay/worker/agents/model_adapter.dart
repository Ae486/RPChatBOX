/// 模型能力适配器
///
/// 根据模型能力选择提示词版本和配置参数
/// POS: Services / Roleplay / Worker / Agents
library;

/// 提示词能力层级
enum PromptTier {
  /// 高能力模型（GPT-4, Claude-3, etc.）
  high,

  /// 中等能力模型（GPT-3.5, Gemini, Deepseek, etc.）
  medium,

  /// 低能力模型（本地模型, etc.）
  low,
}

/// 模型能力档案
class ModelProfile {
  /// 提示词层级
  final PromptTier tier;

  /// 是否可靠输出 JSON
  final bool reliableJson;

  /// 最大输出 token
  final int maxOutputTokens;

  /// 是否支持系统提示词
  final bool supportsSystemPrompt;

  const ModelProfile({
    required this.tier,
    this.reliableJson = false,
    this.maxOutputTokens = 4096,
    this.supportsSystemPrompt = true,
  });
}

/// 模型能力适配器
class ModelAdapter {
  /// 模型能力档案（静态配置）
  static const Map<String, ModelProfile> _profiles = {
    // OpenAI
    'gpt-4': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 8192,
    ),
    'gpt-4o': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 16384,
    ),
    'gpt-4-turbo': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 4096,
    ),
    'gpt-3.5': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: false,
      maxOutputTokens: 4096,
    ),
    'gpt-3.5-turbo': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: false,
      maxOutputTokens: 4096,
    ),

    // Anthropic
    'claude-3': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 4096,
    ),
    'claude-3-opus': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 4096,
    ),
    'claude-3-sonnet': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 4096,
    ),
    'claude-3-haiku': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: true,
      maxOutputTokens: 4096,
    ),

    // Google
    'gemini': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: true,
      maxOutputTokens: 8192,
    ),
    'gemini-pro': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: true,
      maxOutputTokens: 8192,
    ),
    'gemini-ultra': ModelProfile(
      tier: PromptTier.high,
      reliableJson: true,
      maxOutputTokens: 8192,
    ),

    // Deepseek
    'deepseek': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: false,
      maxOutputTokens: 4096,
    ),
    'deepseek-chat': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: false,
      maxOutputTokens: 4096,
    ),
    'deepseek-coder': ModelProfile(
      tier: PromptTier.medium,
      reliableJson: true,
      maxOutputTokens: 4096,
    ),

    // 本地模型
    'local': ModelProfile(
      tier: PromptTier.low,
      reliableJson: false,
      maxOutputTokens: 2048,
    ),
    'ollama': ModelProfile(
      tier: PromptTier.low,
      reliableJson: false,
      maxOutputTokens: 2048,
    ),
    'llama': ModelProfile(
      tier: PromptTier.low,
      reliableJson: false,
      maxOutputTokens: 2048,
    ),
  };

  /// 默认档案（中等能力）
  static const _defaultProfile = ModelProfile(
    tier: PromptTier.medium,
    reliableJson: false,
    maxOutputTokens: 4096,
  );

  /// 获取模型档案
  ModelProfile getProfile(String modelId) {
    // 精确匹配
    if (_profiles.containsKey(modelId)) {
      return _profiles[modelId]!;
    }

    // 标准化模型 ID（转小写）
    final normalizedId = modelId.toLowerCase();

    // 再次精确匹配
    if (_profiles.containsKey(normalizedId)) {
      return _profiles[normalizedId]!;
    }

    // 前缀匹配
    for (final entry in _profiles.entries) {
      if (normalizedId.startsWith(entry.key)) {
        return entry.value;
      }
    }

    // 包含匹配
    for (final entry in _profiles.entries) {
      if (normalizedId.contains(entry.key)) {
        return entry.value;
      }
    }

    // 返回默认档案
    return _defaultProfile;
  }

  /// 获取提示词层级
  PromptTier getTier(String modelId) => getProfile(modelId).tier;

  /// 是否可靠输出 JSON
  bool isReliableJson(String modelId) => getProfile(modelId).reliableJson;

  /// 获取最大输出 token
  int getMaxOutputTokens(String modelId) =>
      getProfile(modelId).maxOutputTokens;

  /// 是否支持系统提示词
  bool supportsSystemPrompt(String modelId) =>
      getProfile(modelId).supportsSystemPrompt;

  /// 根据模型选择提示词
  String selectPrompt(
    String modelId, {
    required String high,
    required String medium,
    required String low,
  }) {
    final tier = getTier(modelId);
    return switch (tier) {
      PromptTier.high => high,
      PromptTier.medium => medium,
      PromptTier.low => low,
    };
  }

  /// 获取推荐的 JSON 修复策略
  JsonRepairStrategy getJsonRepairStrategy(String modelId) {
    final profile = getProfile(modelId);
    if (profile.reliableJson) {
      return JsonRepairStrategy.minimal;
    }
    return switch (profile.tier) {
      PromptTier.high => JsonRepairStrategy.standard,
      PromptTier.medium => JsonRepairStrategy.aggressive,
      PromptTier.low => JsonRepairStrategy.aggressive,
    };
  }
}

/// JSON 修复策略
enum JsonRepairStrategy {
  /// 最小修复（仅清理）
  minimal,

  /// 标准修复（清理 + 结构修复）
  standard,

  /// 激进修复（清理 + 结构修复 + LLM 回退）
  aggressive,
}
