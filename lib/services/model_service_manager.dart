import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../models/conversation_settings.dart';
import '../models/config_migration.dart';
import '../models/chat_settings.dart';
import '../adapters/ai_provider.dart';

/// 模型服务管理器
/// 负责Provider和Model的CRUD操作、持久化和迁移
class ModelServiceManager {
  static const String _keyProviders = 'providers';
  static const String _keyModels = 'models';
  static const String _keyConversationSettings = 'conversation_settings';
  static const String _keyConfigVersion = 'config_version';
  static const String _keyLegacySettings = 'chat_settings';

  final _uuid = const Uuid();
  final SharedPreferences _prefs;

  List<ProviderConfig> _providers = [];
  List<ModelConfig> _models = [];
  Map<String, ConversationSettings> _conversationSettings = {};

  ModelServiceManager(this._prefs);

  /// 初始化服务
  Future<void> initialize() async {
    // 检查是否需要迁移
    final needsMigration = await _checkMigration();

    if (needsMigration) {
      await _performMigration();
    } else {
      await _loadData();
    }
  }

  /// 检查是否需要迁移
  Future<bool> _checkMigration() async {
    final version = _prefs.getInt(_keyConfigVersion) ?? 1;
    return version < MigrationVersion.current;
  }

  /// 执行迁移
  Future<void> _performMigration() async {
    final legacyJson = _prefs.getString(_keyLegacySettings);
    if (legacyJson != null) {
      final legacySettings = ChatSettings.fromJson(
        json.decode(legacyJson) as Map<String, dynamic>,
      );

      final migrationResult = ConfigMigration.migrateFromChatSettings(legacySettings);

      // 保存迁移后的数据
      _providers = [migrationResult.provider];
      _models = [migrationResult.model];
      _conversationSettings = {
        'default': migrationResult.conversationSettings,
      };

      await _saveData();
      await _prefs.setInt(_keyConfigVersion, MigrationVersion.current);
    } else {
      await _loadData();
    }
  }

  /// 加载数据
  Future<void> _loadData() async {
    // 加载Providers
    final providersJson = _prefs.getString(_keyProviders);
    if (providersJson != null) {
      final list = json.decode(providersJson) as List;
      _providers = list
          .map((item) => ProviderConfig.fromJson(item as Map<String, dynamic>))
          .toList();
    }

    // 加载Models
    final modelsJson = _prefs.getString(_keyModels);
    if (modelsJson != null) {
      final list = json.decode(modelsJson) as List;
      _models = list
          .map((item) => ModelConfig.fromJson(item as Map<String, dynamic>))
          .toList();
    }

    // 加载对话配置
    final settingsJson = _prefs.getString(_keyConversationSettings);
    if (settingsJson != null) {
      final map = json.decode(settingsJson) as Map<String, dynamic>;
      _conversationSettings = map.map(
        (key, value) => MapEntry(
          key,
          ConversationSettings.fromJson(value as Map<String, dynamic>),
        ),
      );
    }
  }

  /// 保存数据
  Future<void> _saveData() async {
    // 保存Providers
    await _prefs.setString(
      _keyProviders,
      json.encode(_providers.map((p) => p.toJson()).toList()),
    );

    // 保存Models
    await _prefs.setString(
      _keyModels,
      json.encode(_models.map((m) => m.toJson()).toList()),
    );

    // 保存对话配置
    await _prefs.setString(
      _keyConversationSettings,
      json.encode(
        _conversationSettings.map((key, value) => MapEntry(key, value.toJson())),
      ),
    );
  }

  // ============ Provider管理 ============

  /// 获取所有Providers
  List<ProviderConfig> getProviders() => List.unmodifiable(_providers);

  /// 获取启用的Providers
  List<ProviderConfig> getEnabledProviders() {
    return _providers.where((p) => p.isEnabled).toList();
  }

  /// 根据ID获取Provider
  ProviderConfig? getProvider(String id) {
    try {
      return _providers.firstWhere((p) => p.id == id);
    } catch (e) {
      return null;
    }
  }

  /// 添加Provider
  Future<ProviderConfig> addProvider(ProviderConfig provider) async {
    _providers.add(provider);
    await _saveData();
    return provider;
  }

  /// 更新Provider
  Future<void> updateProvider(ProviderConfig provider) async {
    final index = _providers.indexWhere((p) => p.id == provider.id);
    if (index != -1) {
      _providers[index] = provider;
      await _saveData();
    }
  }

  /// 删除Provider
  Future<void> deleteProvider(String providerId) async {
    _providers.removeWhere((p) => p.id == providerId);
    // 同时删除该Provider下的所有Models
    _models.removeWhere((m) => m.providerId == providerId);
    await _saveData();
  }

  /// 测试Provider连接
  Future<ProviderTestResult> testProvider(ProviderConfig provider) async {
    final aiProvider = ProviderFactory.createProvider(provider);
    return await aiProvider.testConnection();
  }

  /// 测试Provider与指定模型的连接
  /// 发送实际测试请求来验证模型是否可用
  Future<ProviderTestResult> testProviderWithModel(
    ProviderConfig provider,
    String modelName,
  ) async {
    final aiProvider = ProviderFactory.createProvider(provider);
    return await aiProvider.testModel(modelName);
  }

  // ============ Model管理 ============

  /// 获取所有Models
  List<ModelConfig> getModels() => List.unmodifiable(_models);

  /// 获取启用的Models
  List<ModelConfig> getEnabledModels() {
    return _models.where((m) => m.isEnabled).toList();
  }

  /// 获取指定Provider的Models
  List<ModelConfig> getModelsByProvider(String providerId) {
    return _models.where((m) => m.providerId == providerId).toList();
  }

  /// 根据ID获取Model
  ModelConfig? getModel(String id) {
    try {
      return _models.firstWhere((m) => m.id == id);
    } catch (e) {
      return null;
    }
  }

  /// 添加Model
  Future<ModelConfig> addModel(ModelConfig model) async {
    _models.add(model);
    await _saveData();
    return model;
  }

  /// 批量添加Models
  Future<void> addModels(List<ModelConfig> models) async {
    _models.addAll(models);
    await _saveData();
  }

  /// 更新Model
  Future<void> updateModel(ModelConfig model) async {
    final index = _models.indexWhere((m) => m.id == model.id);
    if (index != -1) {
      _models[index] = model;
      await _saveData();
    }
  }

  /// 删除Model
  Future<void> deleteModel(String modelId) async {
    _models.removeWhere((m) => m.id == modelId);
    await _saveData();
  }

  // ============ 对话配置管理 ============

  /// 获取对话配置
  ConversationSettings getConversationSettings(String conversationId) {
    return _conversationSettings[conversationId] ??
        ConversationSettings.createDefault(conversationId);
  }

  /// 更新对话配置
  Future<void> updateConversationSettings(
    ConversationSettings settings,
  ) async {
    _conversationSettings[settings.conversationId] = settings;
    await _saveData();
  }

  /// 删除对话配置
  Future<void> deleteConversationSettings(String conversationId) async {
    _conversationSettings.remove(conversationId);
    await _saveData();
  }

  // ============ 工具方法 ============

  /// 创建Provider实例
  AIProvider createProviderInstance(String providerId) {
    final provider = getProvider(providerId);
    if (provider == null) {
      throw Exception('Provider not found: $providerId');
    }
    return ProviderFactory.createProviderWithRouting(provider);
  }

  /// 获取Model的完整信息（包含Provider信息）
  ({ProviderConfig provider, ModelConfig model})? getModelWithProvider(
    String modelId,
  ) {
    final model = getModel(modelId);
    if (model == null) return null;

    final provider = getProvider(model.providerId);
    if (provider == null) return null;

    return (provider: provider, model: model);
  }

  /// 验证Provider和Model组合有效性
  bool isValidProviderModelPair(String providerId, String modelId) {
    final model = getModel(modelId);
    return model?.providerId == providerId;
  }

  /// 获取默认Provider和Model
  ({ProviderConfig? provider, ModelConfig? model}) getDefaultProviderModel() {
    final enabledProviders = getEnabledProviders();
    if (enabledProviders.isEmpty) return (provider: null, model: null);

    final defaultProvider = enabledProviders.first;
    final providerModels = getModelsByProvider(defaultProvider.id)
        .where((m) => m.isEnabled)
        .toList();

    if (providerModels.isEmpty) return (provider: null, model: null);

    return (provider: defaultProvider, model: providerModels.first);
  }

  /// 生成唯一ID
  String generateId() => _uuid.v4();

  /// 清空所有数据（慎用）
  Future<void> clearAll() async {
    _providers.clear();
    _models.clear();
    _conversationSettings.clear();
    await _saveData();
  }
}
