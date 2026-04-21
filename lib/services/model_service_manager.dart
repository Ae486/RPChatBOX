import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../models/conversation_settings.dart';
import '../models/config_migration.dart';
import '../models/chat_settings.dart';
import '../models/backend_mode.dart';
import '../adapters/ai_provider.dart';
import 'backend_conversation_service.dart';
import 'backend_model_registry_service.dart';
import 'backend_provider_registry_service.dart';

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
  final BackendProviderRegistryService _backendProviderRegistryService =
      BackendProviderRegistryService();
  final BackendModelRegistryService _backendModelRegistryService =
      BackendModelRegistryService();
  final BackendConversationService _backendConversationService =
      BackendConversationService();

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

    if (ProviderFactory.pythonBackendEnabled) {
      try {
        await refreshBackendMirrors();
      } catch (e) {
        debugPrint('[ModelServiceManager] backend mirror bootstrap failed: $e');
      }
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

      final migrationResult = ConfigMigration.migrateFromChatSettings(
        legacySettings,
      );

      // 保存迁移后的数据
      _providers = [migrationResult.provider];
      _models = [migrationResult.model];
      _conversationSettings = {'default': migrationResult.conversationSettings};

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
        _conversationSettings.map(
          (key, value) => MapEntry(key, value.toJson()),
        ),
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
    if (!ProviderFactory.pythonBackendEnabled) {
      _providers.add(provider);
      await _saveData();
      return provider;
    }

    final summary = await _backendProviderRegistryService.upsertProvider(
      provider,
    );
    final merged = _mergeProviderMirror(provider, summary);
    _providers = [
      ..._providers.where((entry) => entry.id != merged.id),
      merged,
    ];
    await _saveRuntimeState();
    return merged;
  }

  /// 更新Provider
  Future<void> updateProvider(ProviderConfig provider) async {
    final index = _providers.indexWhere((p) => p.id == provider.id);
    if (index != -1) {
      if (!ProviderFactory.pythonBackendEnabled) {
        _providers[index] = provider;
        await _saveData();
        return;
      }

      final summary = await _backendProviderRegistryService.upsertProvider(
        provider,
      );
      _providers[index] = _mergeProviderMirror(provider, summary);
      await _saveRuntimeState();
    }
  }

  /// 删除Provider
  Future<void> deleteProvider(String providerId) async {
    final provider = getProvider(providerId);
    if (provider == null) return;

    if (ProviderFactory.pythonBackendEnabled) {
      await _backendProviderRegistryService.deleteProvider(provider);
    }

    _providers.removeWhere((p) => p.id == providerId);
    _models.removeWhere((m) => m.providerId == providerId);
    await _saveRuntimeState();
  }

  /// 测试Provider连接
  Future<ProviderTestResult> testProvider(ProviderConfig provider) async {
    final aiProvider = ProviderFactory.createProviderWithRouting(provider);
    return await aiProvider.testConnection();
  }

  /// 测试Provider与指定模型的连接
  /// 发送实际测试请求来验证模型是否可用
  Future<ProviderTestResult> testProviderWithModel(
    ProviderConfig provider,
    String modelName,
  ) async {
    final aiProvider = ProviderFactory.createProviderWithRouting(provider);
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
    if (!ProviderFactory.pythonBackendEnabled) {
      _models.add(model);
      await _saveData();
      return model;
    }

    final provider = getProvider(model.providerId);
    if (provider == null) {
      throw Exception('Provider not found for model: ${model.providerId}');
    }

    final summary = await _backendModelRegistryService.upsertModel(
      provider: provider,
      model: model,
    );
    final merged = _mergeModelMirror(model, summary);
    _models = [..._models.where((entry) => entry.id != merged.id), merged];
    await _saveRuntimeState();
    return merged;
  }

  /// 批量添加Models
  Future<void> addModels(List<ModelConfig> models) async {
    if (!ProviderFactory.pythonBackendEnabled) {
      _models.addAll(models);
      await _saveData();
      return;
    }
    for (final model in models) {
      await addModel(model);
    }
  }

  /// 更新Model
  Future<void> updateModel(ModelConfig model) async {
    final index = _models.indexWhere((m) => m.id == model.id);
    if (index != -1) {
      if (!ProviderFactory.pythonBackendEnabled) {
        _models[index] = model;
        await _saveData();
        return;
      }

      final provider = getProvider(model.providerId);
      if (provider == null) {
        throw Exception('Provider not found for model: ${model.providerId}');
      }

      final summary = await _backendModelRegistryService.upsertModel(
        provider: provider,
        model: model,
      );
      _models[index] = _mergeModelMirror(model, summary);
      await _saveRuntimeState();
    }
  }

  /// 删除Model
  Future<void> deleteModel(String modelId) async {
    final model = getModel(modelId);
    if (model == null) return;

    if (ProviderFactory.pythonBackendEnabled) {
      final provider = getProvider(model.providerId);
      if (provider == null) {
        throw Exception('Provider not found for model: ${model.providerId}');
      }
      await _backendModelRegistryService.deleteModel(
        provider: provider,
        model: model,
      );
    }

    _models.removeWhere((m) => m.id == modelId);
    await _saveRuntimeState();
  }

  // ============ 对话配置管理 ============

  /// 获取对话配置
  ConversationSettings getConversationSettings(String conversationId) {
    return _conversationSettings[conversationId] ??
        ConversationSettings.createDefault(conversationId);
  }

  /// 从 backend 拉取并缓存会话配置。
  Future<ConversationSettings> refreshConversationSettingsFromBackend(
    String conversationId,
  ) async {
    if (!ProviderFactory.pythonBackendEnabled) {
      return getConversationSettings(conversationId);
    }

    final summary = await _backendConversationService.getConversationSettings(
      conversationId,
    );
    final settings = summary.toConversationSettings();
    _conversationSettings[conversationId] = settings;
    await _saveRuntimeState();
    return settings;
  }

  /// 更新对话配置
  Future<void> updateConversationSettings(ConversationSettings settings) async {
    if (ProviderFactory.pythonBackendEnabled) {
      final summary = await _backendConversationService.updateConversationSettings(
        settings,
      );
      _conversationSettings[settings.conversationId] =
          summary.toConversationSettings();
      await _saveRuntimeState();
      return;
    }

    _conversationSettings[settings.conversationId] = settings;
    await _saveData();
  }

  /// 删除对话配置
  Future<void> deleteConversationSettings(String conversationId) async {
    _conversationSettings.remove(conversationId);
    await _saveRuntimeState();
  }

  // ============ 工具方法 ============

  /// 创建Provider实例
  AIProvider createProviderInstance(
    String providerId, {
    bool forceDirect = false,
  }) {
    final provider = getProvider(providerId);
    if (provider == null) {
      throw Exception('Provider not found: $providerId');
    }
    return ProviderFactory.createProviderWithRouting(
      provider,
      forceDirect: forceDirect,
    );
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
    final providerModels = getModelsByProvider(
      defaultProvider.id,
    ).where((m) => m.isEnabled).toList();

    if (providerModels.isEmpty) return (provider: null, model: null);

    return (provider: defaultProvider, model: providerModels.first);
  }

  /// 生成唯一ID
  String generateId() => _uuid.v4();

  /// 清空所有数据（慎用）
  Future<void> clearAll() async {
    final providers = List<ProviderConfig>.from(_providers);
    _providers.clear();
    _models.clear();
    _conversationSettings.clear();
    await _saveData();
    if (ProviderFactory.pythonBackendEnabled) {
      for (final provider in providers) {
        await _backendProviderRegistryService.deleteProvider(provider);
      }
    }
  }

  /// 主动将当前本地 provider 集合同步到 backend registry。
  Future<void> syncProvidersToBackend() async {
    if (!ProviderFactory.pythonBackendEnabled) return;
    for (final provider in _providers) {
      if (provider.apiKey.trim().isEmpty) continue;
      await _trySyncProviderToBackend(provider);
    }
  }

  /// 主动将当前本地 model 集合同步到 backend registry。
  Future<void> syncModelsToBackend() async {
    if (!ProviderFactory.pythonBackendEnabled) return;
    for (final model in _models) {
      await _trySyncModelToBackend(model);
    }
  }

  /// 在 backend 模式下，统一执行 provider/model 的 sync + refresh。
  ///
  /// 当前仍属于迁移期实现：
  /// - backend 作为运行时真源逐步收口
  /// - 本地仍保留镜像/回滚层
  Future<void> refreshBackendMirrors({bool sync = true}) async {
    if (!ProviderFactory.pythonBackendEnabled) return;

    if (sync) {
      await syncProvidersToBackend();
      await syncModelsToBackend();
    }

    await refreshProviderMirrorsFromBackend();
    await refreshModelMirrorsFromBackend();
  }

  /// 从 backend provider registry 拉取 summary，并以 backend 结果校准本地镜像。
  ///
  /// backend 是 provider 的真单源；Flutter 仅保留可回滚的本地缓存字段
  /// （例如本地已输入的 secret / proxy 配置）。
  Future<void> refreshProviderMirrorsFromBackend() async {
    if (!ProviderFactory.pythonBackendEnabled) return;

    final summaries = await _backendProviderRegistryService.listProviders();
    final localById = {
      for (final provider in _providers) provider.id: provider,
    };
    final updatedProviders = summaries
        .map((summary) => _mergeProviderMirror(localById[summary.id], summary))
        .toList();

    if (_providers.length == updatedProviders.length) {
      var unchanged = true;
      for (var i = 0; i < _providers.length; i++) {
        if (!_isProviderMirrorEquivalent(_providers[i], updatedProviders[i])) {
          unchanged = false;
          break;
        }
      }
      if (unchanged) return;
    }

    _providers = updatedProviders;
    await _saveRuntimeState();
  }

  /// 从 backend model registry 拉取 summary，并以 backend 结果校准本地镜像。
  ///
  /// backend 是 model 的真单源；Flutter 只保留本地缓存层。
  Future<void> refreshModelMirrorsFromBackend() async {
    if (!ProviderFactory.pythonBackendEnabled) return;
    if (_providers.isEmpty) {
      if (_models.isEmpty) return;
      _models = [];
      await _saveRuntimeState();
      return;
    }

    final mergedModels = <ModelConfig>[];

    for (final provider in _providers) {
      final localModels = getModelsByProvider(provider.id);
      final summaries = await _backendModelRegistryService.listModels(
        provider: provider,
      );

      final localById = {for (final model in localModels) model.id: model};

      for (final summary in summaries) {
        final local = localById.remove(summary.id);
        final merged = _mergeModelMirror(local, summary);
        mergedModels.add(merged);
      }
    }

    if (_models.length == mergedModels.length) {
      var unchanged = true;
      for (var i = 0; i < _models.length; i++) {
        if (!_isModelMirrorEquivalent(_models[i], mergedModels[i])) {
          unchanged = false;
          break;
        }
      }
      if (unchanged) return;
    }

    _models = mergedModels;
    await _saveRuntimeState();
  }

  Future<void> _trySyncProviderToBackend(ProviderConfig provider) async {
    if (!ProviderFactory.pythonBackendEnabled) return;
    try {
      await _backendProviderRegistryService.upsertProvider(provider);
    } catch (e) {
      debugPrint('[ProviderRegistry] sync failed for ${provider.id}: $e');
    }
  }

  Future<void> _trySyncModelToBackend(ModelConfig model) async {
    if (!ProviderFactory.pythonBackendEnabled) return;
    final provider = getProvider(model.providerId);
    if (provider == null) return;
    try {
      await _backendModelRegistryService.upsertModel(
        provider: provider,
        model: model,
      );
    } catch (e) {
      debugPrint('[ModelRegistry] sync failed for ${model.id}: $e');
    }
  }

  Future<void> _saveRuntimeState() async {
    _reconcileConversationSelections();
    await _saveData();
  }

  void _reconcileConversationSelections() {
    if (_conversationSettings.isEmpty) return;

    final enabledProviderIds = {
      for (final provider in _providers.where((entry) => entry.isEnabled))
        provider.id: provider,
    };
    final enabledModelIds = {
      for (final model in _models.where((entry) => entry.isEnabled))
        model.id: model,
    };

    _conversationSettings = _conversationSettings.map((
      conversationId,
      settings,
    ) {
      var selectedProviderId = settings.selectedProviderId;
      var selectedModelId = settings.selectedModelId;

      final selectedModel = selectedModelId != null
          ? enabledModelIds[selectedModelId]
          : null;

      if (selectedModel != null) {
        final provider = enabledProviderIds[selectedModel.providerId];
        if (provider == null) {
          selectedProviderId = null;
          selectedModelId = null;
        } else {
          selectedProviderId = provider.id;
          selectedModelId = selectedModel.id;
        }
      } else if (selectedModelId != null) {
        selectedProviderId = null;
        selectedModelId = null;
      } else if (selectedProviderId != null &&
          !enabledProviderIds.containsKey(selectedProviderId)) {
        selectedProviderId = null;
      }

      if (selectedProviderId == settings.selectedProviderId &&
          selectedModelId == settings.selectedModelId) {
        return MapEntry(conversationId, settings);
      }

      return MapEntry(
        conversationId,
        settings.copyWith(
          selectedProviderId: selectedProviderId,
          selectedModelId: selectedModelId,
        ),
      );
    });
  }

  ProviderConfig _mergeProviderMirror(
    ProviderConfig? local,
    BackendProviderSummary summary,
  ) {
    return (local ??
            ProviderConfig(
              id: summary.id,
              name: summary.name,
              type: summary.type,
              apiUrl: summary.apiUrl,
              apiKey: '',
              isEnabled: summary.isEnabled,
              createdAt: summary.createdAt,
              updatedAt: summary.updatedAt,
              customHeaders: summary.customHeaders,
              description: summary.description,
              backendMode: summary.backendMode ?? BackendMode.direct,
              proxyApiUrl: _defaultProxyApiUrl(),
              proxyApiKey: _defaultProxyApiKey(),
              proxyHeaders: _defaultProxyHeaders(),
              fallbackEnabled: summary.fallbackEnabled ?? true,
              fallbackTimeoutMs: summary.fallbackTimeoutMs ?? 5000,
            ))
        .copyWith(
          name: summary.name,
          type: summary.type,
          apiUrl: summary.apiUrl,
          isEnabled: summary.isEnabled,
          createdAt: summary.createdAt ?? local?.createdAt,
          updatedAt: summary.updatedAt ?? local?.updatedAt,
          customHeaders: summary.customHeaders,
          description: summary.description ?? local?.description,
          backendMode: summary.backendMode ?? local?.backendMode,
          fallbackEnabled: summary.fallbackEnabled ?? local?.fallbackEnabled,
          fallbackTimeoutMs:
              summary.fallbackTimeoutMs ?? local?.fallbackTimeoutMs,
        );
  }

  String? _defaultProxyApiUrl() {
    for (final provider in _providers) {
      if (provider.proxyApiUrl != null && provider.proxyApiUrl!.isNotEmpty) {
        return provider.proxyApiUrl;
      }
    }
    return null;
  }

  String? _defaultProxyApiKey() {
    for (final provider in _providers) {
      if (provider.proxyApiKey != null && provider.proxyApiKey!.isNotEmpty) {
        return provider.proxyApiKey;
      }
    }
    return null;
  }

  Map<String, dynamic>? _defaultProxyHeaders() {
    for (final provider in _providers) {
      final headers = provider.proxyHeaders;
      if (headers != null && headers.isNotEmpty) {
        return headers;
      }
    }
    return null;
  }

  bool _isProviderMirrorEquivalent(ProviderConfig left, ProviderConfig right) {
    return left.id == right.id &&
        left.name == right.name &&
        left.type == right.type &&
        left.apiUrl == right.apiUrl &&
        left.isEnabled == right.isEnabled &&
        mapEquals(left.customHeaders, right.customHeaders) &&
        left.description == right.description &&
        left.backendMode == right.backendMode &&
        left.fallbackEnabled == right.fallbackEnabled &&
        left.fallbackTimeoutMs == right.fallbackTimeoutMs;
  }

  ModelConfig _mergeModelMirror(
    ModelConfig? local,
    BackendModelSummary summary,
  ) {
    return (local ??
            ModelConfig(
              id: summary.id,
              providerId: summary.providerId,
              modelName: summary.modelName,
              displayName: summary.displayName,
              capabilities: summary.capabilities,
              defaultParams: summary.defaultParams,
              isEnabled: summary.isEnabled,
              description: summary.description,
              createdAt: summary.createdAt,
              updatedAt: summary.updatedAt,
            ))
        .copyWith(
          providerId: summary.providerId,
          modelName: summary.modelName,
          displayName: summary.displayName,
          capabilities: summary.capabilities,
          defaultParams: summary.defaultParams,
          isEnabled: summary.isEnabled,
          description: summary.description,
          createdAt: summary.createdAt ?? local?.createdAt,
          updatedAt: summary.updatedAt ?? local?.updatedAt,
        );
  }

  bool _isModelMirrorEquivalent(ModelConfig left, ModelConfig right) {
    return left.id == right.id &&
        left.providerId == right.providerId &&
        left.modelName == right.modelName &&
        left.displayName == right.displayName &&
        setEquals(left.capabilities, right.capabilities) &&
        left.defaultParams.temperature == right.defaultParams.temperature &&
        left.defaultParams.maxTokens == right.defaultParams.maxTokens &&
        left.defaultParams.topP == right.defaultParams.topP &&
        left.defaultParams.frequencyPenalty ==
            right.defaultParams.frequencyPenalty &&
        left.defaultParams.presencePenalty ==
            right.defaultParams.presencePenalty &&
        left.defaultParams.streamOutput == right.defaultParams.streamOutput &&
        left.isEnabled == right.isEnabled &&
        left.description == right.description;
  }
}
