import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:chatboxapp/services/model_service_manager.dart';
import 'package:chatboxapp/models/provider_config.dart';
import 'package:chatboxapp/models/model_config.dart';
import 'package:chatboxapp/models/conversation_settings.dart';

/// ModelServiceManager 单元测试
///
/// 测试 Provider/Model 的 CRUD 操作、持久化和配置管理功能。
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ModelServiceManager', () {
    late ModelServiceManager manager;

    setUp(() async {
      // 每个测试前重置 SharedPreferences
      SharedPreferences.setMockInitialValues({
        'config_version': 2, // 跳过迁移
      });
      final prefs = await SharedPreferences.getInstance();
      manager = ModelServiceManager(prefs);
      await manager.initialize();
    });

    // ============ 初始化测试 ============
    group('initialize', () {
      test('should initialize with empty data when no saved data', () async {
        expect(manager.getProviders(), isEmpty);
        expect(manager.getModels(), isEmpty);
      });

      test('should load saved providers and models', () async {
        // Arrange
        final now = DateTime.now().toIso8601String();
        SharedPreferences.setMockInitialValues({
          'config_version': 2,
          'providers':
              '[{"id":"p1","name":"Test","type":"openai","apiUrl":"https://api.test.com","apiKey":"key","isEnabled":true,"createdAt":"$now","updatedAt":"$now","customHeaders":{}}]',
          'models':
              '[{"id":"m1","providerId":"p1","modelName":"gpt-4","displayName":"GPT-4","capabilities":["text"],"isEnabled":true,"createdAt":"$now","updatedAt":"$now"}]',
        });

        final prefs = await SharedPreferences.getInstance();
        final newManager = ModelServiceManager(prefs);
        await newManager.initialize();

        // Assert
        expect(newManager.getProviders().length, equals(1));
        expect(newManager.getModels().length, equals(1));
        expect(newManager.getProviders().first.name, equals('Test'));
        expect(newManager.getModels().first.displayName, equals('GPT-4'));
      });
    });

    // ============ Provider 管理测试 ============
    group('Provider CRUD', () {
      test('should add provider', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Test Provider',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
        );

        // Act
        await manager.addProvider(provider);

        // Assert
        expect(manager.getProviders().length, equals(1));
        expect(manager.getProvider('test-provider'), isNotNull);
        expect(manager.getProvider('test-provider')!.name, equals('Test Provider'));
      });

      test('should update provider', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Original Name',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
        );
        await manager.addProvider(provider);

        // Act
        final updatedProvider = provider.copyWith(name: 'Updated Name');
        await manager.updateProvider(updatedProvider);

        // Assert
        expect(manager.getProvider('test-provider')!.name, equals('Updated Name'));
      });

      test('should delete provider and its models', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Test Provider',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
        );
        await manager.addProvider(provider);

        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );
        await manager.addModel(model);

        // Act
        await manager.deleteProvider('test-provider');

        // Assert
        expect(manager.getProviders(), isEmpty);
        expect(manager.getModels(), isEmpty); // 关联的 Model 也应被删除
      });

      test('should get enabled providers only', () async {
        // Arrange
        final enabledProvider = ProviderConfig(
          id: 'enabled',
          name: 'Enabled',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'key',
          isEnabled: true,
        );
        final disabledProvider = ProviderConfig(
          id: 'disabled',
          name: 'Disabled',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'key',
          isEnabled: false,
        );
        await manager.addProvider(enabledProvider);
        await manager.addProvider(disabledProvider);

        // Act
        final enabledProviders = manager.getEnabledProviders();

        // Assert
        expect(enabledProviders.length, equals(1));
        expect(enabledProviders.first.id, equals('enabled'));
      });

      test('should return null for non-existent provider', () {
        expect(manager.getProvider('non-existent'), isNull);
      });
    });

    // ============ Model 管理测试 ============
    group('Model CRUD', () {
      late ProviderConfig testProvider;

      setUp(() async {
        testProvider = ProviderConfig(
          id: 'test-provider',
          name: 'Test Provider',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
        );
        await manager.addProvider(testProvider);
      });

      test('should add model', () async {
        // Arrange
        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );

        // Act
        await manager.addModel(model);

        // Assert
        expect(manager.getModels().length, equals(1));
        expect(manager.getModel('test-model'), isNotNull);
      });

      test('should add multiple models', () async {
        // Arrange
        final models = [
          ModelConfig(
            id: 'model-1',
            providerId: 'test-provider',
            modelName: 'gpt-4',
            displayName: 'GPT-4',
          ),
          ModelConfig(
            id: 'model-2',
            providerId: 'test-provider',
            modelName: 'gpt-3.5-turbo',
            displayName: 'GPT-3.5',
          ),
        ];

        // Act
        await manager.addModels(models);

        // Assert
        expect(manager.getModels().length, equals(2));
      });

      test('should update model', () async {
        // Arrange
        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'Original Name',
        );
        await manager.addModel(model);

        // Act
        final updatedModel = model.copyWith(displayName: 'Updated Name');
        await manager.updateModel(updatedModel);

        // Assert
        expect(manager.getModel('test-model')!.displayName, equals('Updated Name'));
      });

      test('should delete model', () async {
        // Arrange
        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );
        await manager.addModel(model);

        // Act
        await manager.deleteModel('test-model');

        // Assert
        expect(manager.getModels(), isEmpty);
      });

      test('should get models by provider', () async {
        // Arrange
        final anotherProvider = ProviderConfig(
          id: 'another-provider',
          name: 'Another',
          type: ProviderType.gemini,
          apiUrl: 'https://api.another.com',
          apiKey: 'key',
        );
        await manager.addProvider(anotherProvider);

        await manager.addModel(ModelConfig(
          id: 'model-1',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        ));
        await manager.addModel(ModelConfig(
          id: 'model-2',
          providerId: 'another-provider',
          modelName: 'gemini-pro',
          displayName: 'Gemini Pro',
        ));

        // Act
        final testProviderModels = manager.getModelsByProvider('test-provider');

        // Assert
        expect(testProviderModels.length, equals(1));
        expect(testProviderModels.first.id, equals('model-1'));
      });

      test('should get enabled models only', () async {
        // Arrange
        await manager.addModel(ModelConfig(
          id: 'enabled',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'Enabled',
          isEnabled: true,
        ));
        await manager.addModel(ModelConfig(
          id: 'disabled',
          providerId: 'test-provider',
          modelName: 'gpt-3.5',
          displayName: 'Disabled',
          isEnabled: false,
        ));

        // Act
        final enabledModels = manager.getEnabledModels();

        // Assert
        expect(enabledModels.length, equals(1));
        expect(enabledModels.first.id, equals('enabled'));
      });

      test('should return null for non-existent model', () {
        expect(manager.getModel('non-existent'), isNull);
      });
    });

    // ============ 对话配置测试 ============
    group('ConversationSettings', () {
      test('should return default settings for new conversation', () {
        // Act
        final settings = manager.getConversationSettings('new-conv');

        // Assert
        expect(settings.conversationId, equals('new-conv'));
      });

      test('should update conversation settings', () async {
        // Arrange
        final settings = ConversationSettings.createDefault('test-conv');
        final updatedSettings = settings.copyWith(contextLength: 20);

        // Act
        await manager.updateConversationSettings(updatedSettings);
        final loaded = manager.getConversationSettings('test-conv');

        // Assert
        expect(loaded.contextLength, equals(20));
      });

      test('should delete conversation settings', () async {
        // Arrange
        final settings = ConversationSettings.createDefault('test-conv');
        await manager.updateConversationSettings(settings);

        // Act
        await manager.deleteConversationSettings('test-conv');
        final loaded = manager.getConversationSettings('test-conv');

        // Assert - 应该返回默认设置
        expect(loaded.conversationId, equals('test-conv'));
      });
    });

    // ============ 工具方法测试 ============
    group('Utility methods', () {
      test('should get model with provider info', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Test Provider',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
        );
        await manager.addProvider(provider);

        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );
        await manager.addModel(model);

        // Act
        final result = manager.getModelWithProvider('test-model');

        // Assert
        expect(result, isNotNull);
        expect(result!.provider.id, equals('test-provider'));
        expect(result.model.id, equals('test-model'));
      });

      test('should return null for model with missing provider', () async {
        // Arrange
        final model = ModelConfig(
          id: 'orphan-model',
          providerId: 'non-existent-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );
        await manager.addModel(model);

        // Act
        final result = manager.getModelWithProvider('orphan-model');

        // Assert
        expect(result, isNull);
      });

      test('should validate provider-model pair', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'key',
        );
        await manager.addProvider(provider);

        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );
        await manager.addModel(model);

        // Assert
        expect(manager.isValidProviderModelPair('test-provider', 'test-model'), isTrue);
        expect(manager.isValidProviderModelPair('other-provider', 'test-model'), isFalse);
      });

      test('should get default provider and model', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'key',
          isEnabled: true,
        );
        await manager.addProvider(provider);

        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
          isEnabled: true,
        );
        await manager.addModel(model);

        // Act
        final result = manager.getDefaultProviderModel();

        // Assert
        expect(result.provider, isNotNull);
        expect(result.model, isNotNull);
        expect(result.provider!.id, equals('test-provider'));
        expect(result.model!.id, equals('test-model'));
      });

      test('should return null default when no enabled providers', () {
        final result = manager.getDefaultProviderModel();
        expect(result.provider, isNull);
        expect(result.model, isNull);
      });

      test('should generate unique IDs', () {
        final id1 = manager.generateId();
        final id2 = manager.generateId();
        expect(id1, isNot(equals(id2)));
      });

      test('should clear all data', () async {
        // Arrange
        final provider = ProviderConfig(
          id: 'test-provider',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'key',
        );
        await manager.addProvider(provider);

        final model = ModelConfig(
          id: 'test-model',
          providerId: 'test-provider',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );
        await manager.addModel(model);

        // Act
        await manager.clearAll();

        // Assert
        expect(manager.getProviders(), isEmpty);
        expect(manager.getModels(), isEmpty);
      });
    });
  });
}
