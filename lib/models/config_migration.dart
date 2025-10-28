import 'package:uuid/uuid.dart';
import '../models/chat_settings.dart';
import 'provider_config.dart';
import 'model_config.dart';
import 'conversation_settings.dart';

/// 配置迁移工具
/// 处理从旧版ChatSettings到新版Provider/Model系统的迁移
class ConfigMigration {
  static const _uuid = Uuid();

  /// 从旧版ChatSettings迁移到新版Provider和Model配置
  static MigrationResult migrateFromChatSettings(ChatSettings oldSettings) {
    // 创建Provider配置
    final provider = _createProviderFromSettings(oldSettings);

    // 创建Model配置
    final model = _createModelFromSettings(oldSettings, provider.id);

    // 创建默认对话配置
    final conversationSettings = ConversationSettings.createDefault('default');
    final updatedConversationSettings = conversationSettings.copyWith(
      selectedProviderId: provider.id,
      selectedModelId: model.id,
      parameters: ModelParameters(
        temperature: oldSettings.temperature,
        maxTokens: oldSettings.maxTokens,
        topP: oldSettings.topP,
        streamOutput: true,
      ),
    );

    return MigrationResult(
      provider: provider,
      model: model,
      conversationSettings: updatedConversationSettings,
    );
  }

  /// 从Provider名称推断类型
  static ProviderType _inferProviderType(String providerName) {
    final nameLower = providerName.toLowerCase();
    if (nameLower.contains('openai')) return ProviderType.openai;
    if (nameLower.contains('azure')) return ProviderType.openai;
    if (nameLower.contains('gemini')) return ProviderType.gemini;
    if (nameLower.contains('deepseek')) return ProviderType.deepseek;
    if (nameLower.contains('claude') || nameLower.contains('anthropic')) {
      return ProviderType.claude;
    }
    return ProviderType.custom;
  }

  /// 从模型名称推断能力
  static Set<ModelCapability> _inferCapabilities(String modelName) {
    final capabilities = <ModelCapability>{ModelCapability.text};
    final modelLower = modelName.toLowerCase();

    // 视觉能力
    if (modelLower.contains('vision') ||
        modelLower.contains('gpt-4') ||
        modelLower.contains('claude-3') ||
        modelLower.contains('gemini')) {
      capabilities.add(ModelCapability.vision);
    }

    // 工具能力（大多数现代模型支持）
    if (modelLower.contains('gpt-4') ||
        modelLower.contains('gpt-3.5') ||
        modelLower.contains('claude') ||
        modelLower.contains('gemini')) {
      capabilities.add(ModelCapability.tool);
    }

    return capabilities;
  }

  /// 创建Provider配置
  static ProviderConfig _createProviderFromSettings(ChatSettings settings) {
    final providerType = _inferProviderType(settings.providerName);

    return ProviderConfig(
      id: _uuid.v4(),
      name: settings.providerName,
      type: providerType,
      apiUrl: settings.apiUrl,
      apiKey: settings.apiKey,
      isEnabled: true,
      description: '从旧配置迁移',
    );
  }

  /// 创建Model配置
  static ModelConfig _createModelFromSettings(
    ChatSettings settings,
    String providerId,
  ) {
    final capabilities = _inferCapabilities(settings.model);

    return ModelConfig(
      id: _uuid.v4(),
      providerId: providerId,
      modelName: settings.model,
      displayName: settings.model,
      capabilities: capabilities,
      defaultParams: ModelParameters(
        temperature: settings.temperature,
        maxTokens: settings.maxTokens,
        topP: settings.topP,
      ),
      isEnabled: true,
      description: '从旧配置迁移',
    );
  }

  /// 将新版配置转换回旧版ChatSettings（向后兼容）
  static ChatSettings convertToLegacySettings({
    required ProviderConfig provider,
    required ModelConfig model,
    required ModelParameters parameters,
  }) {
    return ChatSettings(
      apiUrl: provider.apiUrl,
      apiKey: provider.apiKey,
      model: model.modelName,
      providerName: provider.name,
      temperature: parameters.temperature,
      topP: parameters.topP,
      maxTokens: parameters.maxTokens,
    );
  }

  /// 检测是否需要迁移
  static bool needsMigration(Map<String, dynamic>? storedData) {
    if (storedData == null) return false;

    // 如果存在旧版的chat_settings键，且不存在新版的providers键
    return storedData.containsKey('chat_settings') &&
        !storedData.containsKey('providers');
  }

  /// 批量迁移多个对话配置
  static List<ConversationSettings> migrateConversations(
    List<Map<String, dynamic>> oldConversations,
    String defaultProviderId,
    String defaultModelId,
  ) {
    return oldConversations.map((conv) {
      final conversationId = conv['id'] as String? ?? _uuid.v4();
      return ConversationSettings.createDefault(conversationId).copyWith(
        selectedProviderId: defaultProviderId,
        selectedModelId: defaultModelId,
      );
    }).toList();
  }
}

/// 迁移结果
class MigrationResult {
  final ProviderConfig provider;
  final ModelConfig model;
  final ConversationSettings conversationSettings;

  MigrationResult({
    required this.provider,
    required this.model,
    required this.conversationSettings,
  });

  Map<String, dynamic> toJson() {
    return {
      'provider': provider.toJson(),
      'model': model.toJson(),
      'conversationSettings': conversationSettings.toJson(),
    };
  }
}

/// 迁移版本信息
class MigrationVersion {
  static const int current = 2;
  static const int legacy = 1;

  /// 获取存储的版本号
  static int getStoredVersion(Map<String, dynamic>? data) {
    return data?['config_version'] as int? ?? legacy;
  }

  /// 是否为最新版本
  static bool isLatest(Map<String, dynamic>? data) {
    return getStoredVersion(data) >= current;
  }
}
