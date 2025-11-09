import '../models/model_config.dart';

/// 模型能力预设数据库
/// 根据模型名称自动识别其支持的能力
class ModelCapabilityPresets {
  /// 预设数据库：模型名称模式 -> 能力集合
  static final Map<String, Set<ModelCapability>> _presets = {
    // OpenAI GPT-4 系列
    'gpt-4o': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gpt-4o-mini': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gpt-4-turbo': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gpt-4-vision': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gpt-4': {ModelCapability.text, ModelCapability.tool},
    
    // OpenAI GPT-3.5 系列
    'gpt-3.5-turbo': {ModelCapability.text, ModelCapability.tool},
    'gpt-3.5': {ModelCapability.text, ModelCapability.tool},
    
    // Claude 3 系列
    'claude-3-opus': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'claude-3-sonnet': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'claude-3-haiku': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'claude-3.5-sonnet': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    
    // Claude 2 系列
    'claude-2': {ModelCapability.text, ModelCapability.tool},
    'claude-instant': {ModelCapability.text},
    
    // Gemini 系列
    'gemini-pro': {ModelCapability.text, ModelCapability.tool},
    'gemini-pro-vision': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gemini-1.5-pro': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gemini-1.5-flash': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    'gemini-ultra': {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
    
    // DeepSeek 系列
    'deepseek-chat': {ModelCapability.text, ModelCapability.tool},
    'deepseek-coder': {ModelCapability.text, ModelCapability.tool},
    
    // 其他常见模型
    'llama': {ModelCapability.text},
    'mistral': {ModelCapability.text, ModelCapability.tool},
    'mixtral': {ModelCapability.text, ModelCapability.tool},
  };

  /// 根据模型名称获取预设能力
  /// 
  /// 匹配规则：
  /// 1. 精确匹配
  /// 2. 前缀匹配（例如 gpt-4-0125-preview 匹配 gpt-4）
  /// 3. 包含匹配（例如 gpt-4-turbo-2024-04-09 匹配 gpt-4-turbo）
  static Set<ModelCapability> getCapabilities(String modelName) {
    final lowerName = modelName.toLowerCase();
    
    // 1. 精确匹配
    if (_presets.containsKey(lowerName)) {
      return Set.from(_presets[lowerName]!);
    }
    
    // 2. 前缀和包含匹配
    for (final entry in _presets.entries) {
      if (lowerName.startsWith(entry.key) || lowerName.contains(entry.key)) {
        return Set.from(entry.value);
      }
    }
    
    // 3. 默认返回仅文本能力
    return {ModelCapability.text};
  }

  /// 判断模型是否可能支持某个能力（基于名称）
  static bool maySupport(String modelName, ModelCapability capability) {
    final capabilities = getCapabilities(modelName);
    return capabilities.contains(capability);
  }

  /// 获取所有预设模型名称列表（用于自动完成）
  static List<String> getAllPresetModelNames() {
    return _presets.keys.toList()..sort();
  }

  /// 判断是否为已知模型
  static bool isKnownModel(String modelName) {
    final lowerName = modelName.toLowerCase();
    return _presets.keys.any((key) => 
      lowerName == key || 
      lowerName.startsWith(key) || 
      lowerName.contains(key)
    );
  }

  /// 获取模型建议的显示名称
  static String getSuggestedDisplayName(String modelId) {
    // 如果是已知模型，保持原名
    if (isKnownModel(modelId)) {
      return modelId;
    }
    
    // 否则尝试美化名称
    return modelId
        .replaceAll('-', ' ')
        .replaceAll('_', ' ')
        .split(' ')
        .map((word) => word.isEmpty ? '' : word[0].toUpperCase() + word.substring(1))
        .join(' ');
  }
}
