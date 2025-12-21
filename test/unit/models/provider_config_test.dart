import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/models/provider_config.dart';

/// ProviderConfig 序列化测试
///
/// 测试 Provider 配置的 JSON 序列化/反序列化功能。
void main() {
  group('ProviderConfig', () {
    // ============ 构造函数测试 ============
    group('constructor', () {
      test('should create with required fields', () {
        final provider = ProviderConfig(
          id: 'test-id',
          name: 'Test Provider',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
        );

        expect(provider.id, equals('test-id'));
        expect(provider.name, equals('Test Provider'));
        expect(provider.type, equals(ProviderType.openai));
        expect(provider.apiUrl, equals('https://api.test.com/v1'));
        expect(provider.apiKey, equals('test-key'));
        expect(provider.isEnabled, isTrue); // 默认值
        expect(provider.customHeaders, isEmpty); // 默认值
      });

      test('should create with all fields', () {
        final now = DateTime.now();
        final provider = ProviderConfig(
          id: 'test-id',
          name: 'Test Provider',
          type: ProviderType.gemini,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
          isEnabled: false,
          createdAt: now,
          updatedAt: now,
          customHeaders: {'X-Custom': 'value'},
          description: 'Test description',
        );

        expect(provider.isEnabled, isFalse);
        expect(provider.createdAt, equals(now));
        expect(provider.customHeaders['X-Custom'], equals('value'));
        expect(provider.description, equals('Test description'));
      });
    });

    // ============ JSON 序列化测试 ============
    group('JSON serialization', () {
      test('should serialize to JSON', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final provider = ProviderConfig(
          id: 'test-id',
          name: 'Test Provider',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'test-key',
          isEnabled: true,
          createdAt: now,
          updatedAt: now,
          customHeaders: {'X-Custom': 'value'},
          description: 'Test description',
        );

        final json = provider.toJson();

        expect(json['id'], equals('test-id'));
        expect(json['name'], equals('Test Provider'));
        expect(json['type'], equals('openai'));
        expect(json['apiUrl'], equals('https://api.test.com/v1'));
        expect(json['apiKey'], equals('test-key'));
        expect(json['isEnabled'], isTrue);
        expect(json['createdAt'], equals(now.toIso8601String()));
        expect(json['updatedAt'], equals(now.toIso8601String()));
        expect(json['customHeaders']['X-Custom'], equals('value'));
        expect(json['description'], equals('Test description'));
      });

      test('should deserialize from JSON', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final json = {
          'id': 'test-id',
          'name': 'Test Provider',
          'type': 'openai',
          'apiUrl': 'https://api.test.com/v1',
          'apiKey': 'test-key',
          'isEnabled': true,
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
          'customHeaders': {'X-Custom': 'value'},
          'description': 'Test description',
        };

        final provider = ProviderConfig.fromJson(json);

        expect(provider.id, equals('test-id'));
        expect(provider.name, equals('Test Provider'));
        expect(provider.type, equals(ProviderType.openai));
        expect(provider.apiUrl, equals('https://api.test.com/v1'));
        expect(provider.apiKey, equals('test-key'));
        expect(provider.isEnabled, isTrue);
        expect(provider.createdAt, equals(now));
        expect(provider.customHeaders['X-Custom'], equals('value'));
        expect(provider.description, equals('Test description'));
      });

      test('should handle missing optional fields in JSON', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final json = {
          'id': 'test-id',
          'name': 'Test Provider',
          'type': 'openai',
          'apiUrl': 'https://api.test.com/v1',
          'apiKey': 'test-key',
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
        };

        final provider = ProviderConfig.fromJson(json);

        expect(provider.isEnabled, isTrue); // 默认值
        expect(provider.customHeaders, isEmpty); // 默认值
        expect(provider.description, isNull);
      });

      test('should handle unknown provider type', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final json = {
          'id': 'test-id',
          'name': 'Test Provider',
          'type': 'unknown_type',
          'apiUrl': 'https://api.test.com/v1',
          'apiKey': 'test-key',
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
        };

        final provider = ProviderConfig.fromJson(json);

        // 应该回退到默认类型
        expect(provider.type, equals(ProviderType.openai));
      });

      test('should roundtrip serialize/deserialize', () {
        final original = ProviderConfig(
          id: 'test-id',
          name: 'Test Provider',
          type: ProviderType.deepseek,
          apiUrl: 'https://api.deepseek.com/v1',
          apiKey: 'test-key',
          isEnabled: false,
          customHeaders: {'Authorization': 'Bearer token'},
          description: 'DeepSeek API',
        );

        final json = original.toJson();
        final restored = ProviderConfig.fromJson(json);

        expect(restored.id, equals(original.id));
        expect(restored.name, equals(original.name));
        expect(restored.type, equals(original.type));
        expect(restored.apiUrl, equals(original.apiUrl));
        expect(restored.apiKey, equals(original.apiKey));
        expect(restored.isEnabled, equals(original.isEnabled));
        expect(restored.description, equals(original.description));
      });
    });

    // ============ copyWith 测试 ============
    group('copyWith', () {
      test('should copy with modified fields', () {
        final original = ProviderConfig(
          id: 'test-id',
          name: 'Original Name',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'original-key',
        );

        final copied = original.copyWith(
          name: 'New Name',
          apiKey: 'new-key',
        );

        expect(copied.id, equals('test-id')); // 未修改
        expect(copied.name, equals('New Name')); // 已修改
        expect(copied.apiKey, equals('new-key')); // 已修改
        expect(copied.type, equals(ProviderType.openai)); // 未修改
      });

      test('should update updatedAt when copying', () {
        final original = ProviderConfig(
          id: 'test-id',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'key',
          updatedAt: DateTime(2024, 1, 1),
        );

        final copied = original.copyWith(name: 'New Name');

        expect(copied.updatedAt.isAfter(original.updatedAt), isTrue);
      });
    });

    // ============ 工具方法测试 ============
    group('utility methods', () {
      test('should mask API key correctly', () {
        final provider = ProviderConfig(
          id: 'test-id',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'sk-1234567890abcdef',
        );

        expect(provider.maskedApiKey, equals('sk-1••••cdef'));
      });

      test('should mask short API key', () {
        final provider = ProviderConfig(
          id: 'test-id',
          name: 'Test',
          type: ProviderType.openai,
          apiUrl: 'https://api.test.com/v1',
          apiKey: 'short',
        );

        expect(provider.maskedApiKey, equals('••••••••'));
      });

      test('should compare by id', () {
        final provider1 = ProviderConfig(
          id: 'same-id',
          name: 'Provider 1',
          type: ProviderType.openai,
          apiUrl: 'https://api1.test.com/v1',
          apiKey: 'key1',
        );

        final provider2 = ProviderConfig(
          id: 'same-id',
          name: 'Provider 2',
          type: ProviderType.gemini,
          apiUrl: 'https://api2.test.com/v1',
          apiKey: 'key2',
        );

        expect(provider1, equals(provider2));
        expect(provider1.hashCode, equals(provider2.hashCode));
      });
    });
  });

  // ============ ProviderType 测试 ============
  group('ProviderType', () {
    test('should have correct display names', () {
      expect(ProviderType.openai.displayName, equals('OpenAI格式'));
      expect(ProviderType.gemini.displayName, equals('Gemini格式'));
      expect(ProviderType.deepseek.displayName, equals('DeepSeek格式'));
      expect(ProviderType.claude.displayName, equals('Claude格式'));
    });

    test('should have correct default API URLs', () {
      expect(ProviderType.openai.defaultApiUrl, contains('openai.com'));
      expect(ProviderType.gemini.defaultApiUrl, contains('googleapis.com'));
      expect(ProviderType.deepseek.defaultApiUrl, contains('deepseek.com'));
      expect(ProviderType.claude.defaultApiUrl, contains('anthropic.com'));
    });
  });
}
