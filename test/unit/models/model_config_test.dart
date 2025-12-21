import 'package:flutter_test/flutter_test.dart';
import 'package:chatboxapp/models/model_config.dart';

/// ModelConfig 序列化测试
///
/// 测试 Model 配置的 JSON 序列化/反序列化功能。
void main() {
  group('ModelConfig', () {
    // ============ 构造函数测试 ============
    group('constructor', () {
      test('should create with required fields', () {
        final model = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
        );

        expect(model.id, equals('test-id'));
        expect(model.providerId, equals('provider-id'));
        expect(model.modelName, equals('gpt-4'));
        expect(model.displayName, equals('GPT-4'));
        expect(model.isEnabled, isTrue); // 默认值
        expect(model.capabilities, contains(ModelCapability.text)); // 默认值
      });

      test('should create with all fields', () {
        final now = DateTime.now();
        final model = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'gpt-4-vision',
          displayName: 'GPT-4 Vision',
          capabilities: {ModelCapability.text, ModelCapability.vision},
          defaultParams: const ModelParameters(temperature: 0.5),
          isEnabled: false,
          description: 'Multimodal model',
          createdAt: now,
          updatedAt: now,
        );

        expect(model.capabilities.length, equals(2));
        expect(model.capabilities.contains(ModelCapability.vision), isTrue);
        expect(model.defaultParams.temperature, equals(0.5));
        expect(model.isEnabled, isFalse);
        expect(model.description, equals('Multimodal model'));
      });
    });

    // ============ JSON 序列化测试 ============
    group('JSON serialization', () {
      test('should serialize to JSON', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final model = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
          capabilities: {ModelCapability.text, ModelCapability.tool},
          defaultParams: const ModelParameters(temperature: 0.8, maxTokens: 4096),
          isEnabled: true,
          description: 'Test model',
          createdAt: now,
          updatedAt: now,
        );

        final json = model.toJson();

        expect(json['id'], equals('test-id'));
        expect(json['providerId'], equals('provider-id'));
        expect(json['modelName'], equals('gpt-4'));
        expect(json['displayName'], equals('GPT-4'));
        expect(json['capabilities'], containsAll(['text', 'tool']));
        expect(json['defaultParams']['temperature'], equals(0.8));
        expect(json['defaultParams']['maxTokens'], equals(4096));
        expect(json['isEnabled'], isTrue);
        expect(json['description'], equals('Test model'));
      });

      test('should deserialize from JSON', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final json = {
          'id': 'test-id',
          'providerId': 'provider-id',
          'modelName': 'gpt-4',
          'displayName': 'GPT-4',
          'capabilities': ['text', 'vision'],
          'defaultParams': {'temperature': 0.5, 'maxTokens': 2048},
          'isEnabled': true,
          'description': 'Test model',
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
        };

        final model = ModelConfig.fromJson(json);

        expect(model.id, equals('test-id'));
        expect(model.providerId, equals('provider-id'));
        expect(model.modelName, equals('gpt-4'));
        expect(model.displayName, equals('GPT-4'));
        expect(model.capabilities.contains(ModelCapability.text), isTrue);
        expect(model.capabilities.contains(ModelCapability.vision), isTrue);
        expect(model.defaultParams.temperature, equals(0.5));
        expect(model.isEnabled, isTrue);
        expect(model.description, equals('Test model'));
      });

      test('should handle missing optional fields in JSON', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final json = {
          'id': 'test-id',
          'providerId': 'provider-id',
          'modelName': 'gpt-4',
          'displayName': 'GPT-4',
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
        };

        final model = ModelConfig.fromJson(json);

        expect(model.isEnabled, isTrue); // 默认值
        expect(model.capabilities, contains(ModelCapability.text)); // 默认值
        expect(model.description, isNull);
      });

      test('should handle unknown capability', () {
        final now = DateTime(2024, 1, 1, 12, 0, 0);
        final json = {
          'id': 'test-id',
          'providerId': 'provider-id',
          'modelName': 'gpt-4',
          'displayName': 'GPT-4',
          'capabilities': ['text', 'unknown_capability'],
          'createdAt': now.toIso8601String(),
          'updatedAt': now.toIso8601String(),
        };

        final model = ModelConfig.fromJson(json);

        // 未知能力应该回退到 text
        expect(model.capabilities.contains(ModelCapability.text), isTrue);
      });

      test('should roundtrip serialize/deserialize', () {
        final original = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'claude-3-opus',
          displayName: 'Claude 3 Opus',
          capabilities: {ModelCapability.text, ModelCapability.vision, ModelCapability.tool},
          defaultParams: const ModelParameters(
            temperature: 0.7,
            maxTokens: 4096,
            topP: 0.9,
          ),
          isEnabled: true,
          description: 'Most capable Claude model',
        );

        final json = original.toJson();
        final restored = ModelConfig.fromJson(json);

        expect(restored.id, equals(original.id));
        expect(restored.providerId, equals(original.providerId));
        expect(restored.modelName, equals(original.modelName));
        expect(restored.displayName, equals(original.displayName));
        expect(restored.capabilities.length, equals(original.capabilities.length));
        expect(restored.defaultParams.temperature, equals(original.defaultParams.temperature));
        expect(restored.isEnabled, equals(original.isEnabled));
        expect(restored.description, equals(original.description));
      });
    });

    // ============ copyWith 测试 ============
    group('copyWith', () {
      test('should copy with modified fields', () {
        final original = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'gpt-4',
          displayName: 'Original Name',
        );

        final copied = original.copyWith(
          displayName: 'New Name',
          isEnabled: false,
        );

        expect(copied.id, equals('test-id')); // 未修改
        expect(copied.displayName, equals('New Name')); // 已修改
        expect(copied.isEnabled, isFalse); // 已修改
        expect(copied.modelName, equals('gpt-4')); // 未修改
      });
    });

    // ============ 能力检查测试 ============
    group('capability checks', () {
      test('should check for specific capability', () {
        final model = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'gpt-4-vision',
          displayName: 'GPT-4 Vision',
          capabilities: {ModelCapability.text, ModelCapability.vision},
        );

        expect(model.hasCapability(ModelCapability.text), isTrue);
        expect(model.hasCapability(ModelCapability.vision), isTrue);
        expect(model.hasCapability(ModelCapability.audio), isFalse);
      });

      test('should detect multimodal model', () {
        final textOnly = ModelConfig(
          id: 'text-only',
          providerId: 'provider-id',
          modelName: 'gpt-3.5',
          displayName: 'GPT-3.5',
          capabilities: {ModelCapability.text},
        );

        final multimodal = ModelConfig(
          id: 'multimodal',
          providerId: 'provider-id',
          modelName: 'gpt-4-vision',
          displayName: 'GPT-4 Vision',
          capabilities: {ModelCapability.text, ModelCapability.vision},
        );

        expect(textOnly.isMultimodal, isFalse);
        expect(multimodal.isMultimodal, isTrue);
      });

      test('should get capability icons', () {
        final model = ModelConfig(
          id: 'test-id',
          providerId: 'provider-id',
          modelName: 'gpt-4',
          displayName: 'GPT-4',
          capabilities: {ModelCapability.text, ModelCapability.tool},
        );

        final icons = model.capabilityIcons;
        expect(icons.length, equals(2));
      });
    });

    // ============ 相等性测试 ============
    group('equality', () {
      test('should compare by id', () {
        final model1 = ModelConfig(
          id: 'same-id',
          providerId: 'provider-1',
          modelName: 'model-1',
          displayName: 'Model 1',
        );

        final model2 = ModelConfig(
          id: 'same-id',
          providerId: 'provider-2',
          modelName: 'model-2',
          displayName: 'Model 2',
        );

        expect(model1, equals(model2));
        expect(model1.hashCode, equals(model2.hashCode));
      });
    });
  });

  // ============ ModelParameters 测试 ============
  group('ModelParameters', () {
    test('should create with default values', () {
      const params = ModelParameters();

      expect(params.temperature, equals(0.7));
      expect(params.maxTokens, equals(2048));
      expect(params.topP, equals(1.0));
      expect(params.frequencyPenalty, equals(0.0));
      expect(params.presencePenalty, equals(0.0));
      expect(params.streamOutput, isTrue);
    });

    test('should serialize to JSON', () {
      const params = ModelParameters(
        temperature: 0.5,
        maxTokens: 4096,
        topP: 0.9,
        frequencyPenalty: 0.1,
        presencePenalty: 0.2,
        streamOutput: false,
      );

      final json = params.toJson();

      expect(json['temperature'], equals(0.5));
      expect(json['maxTokens'], equals(4096));
      expect(json['topP'], equals(0.9));
      expect(json['frequencyPenalty'], equals(0.1));
      expect(json['presencePenalty'], equals(0.2));
      expect(json['streamOutput'], isFalse);
    });

    test('should deserialize from JSON', () {
      final json = {
        'temperature': 0.5,
        'maxTokens': 4096,
        'topP': 0.9,
        'frequencyPenalty': 0.1,
        'presencePenalty': 0.2,
        'streamOutput': false,
      };

      final params = ModelParameters.fromJson(json);

      expect(params.temperature, equals(0.5));
      expect(params.maxTokens, equals(4096));
      expect(params.topP, equals(0.9));
      expect(params.frequencyPenalty, equals(0.1));
      expect(params.presencePenalty, equals(0.2));
      expect(params.streamOutput, isFalse);
    });

    test('should validate parameters', () {
      const validParams = ModelParameters();
      expect(validParams.validate(), isNull);

      const invalidTemp = ModelParameters(temperature: 3.0);
      expect(invalidTemp.validate(), isNotNull);

      const invalidTokens = ModelParameters(maxTokens: 0);
      expect(invalidTokens.validate(), isNotNull);

      const invalidTopP = ModelParameters(topP: 1.5);
      expect(invalidTopP.validate(), isNotNull);
    });

    test('should copy with modified fields', () {
      const original = ModelParameters();
      final copied = original.copyWith(temperature: 0.5, maxTokens: 4096);

      expect(copied.temperature, equals(0.5));
      expect(copied.maxTokens, equals(4096));
      expect(copied.topP, equals(1.0)); // 未修改
    });
  });

  // ============ ModelCapability 测试 ============
  group('ModelCapability', () {
    test('should have correct display names', () {
      expect(ModelCapability.text.displayName, equals('文本'));
      expect(ModelCapability.vision.displayName, equals('视觉'));
      expect(ModelCapability.network.displayName, equals('联网'));
      expect(ModelCapability.tool.displayName, equals('工具'));
      expect(ModelCapability.audio.displayName, equals('音频'));
      expect(ModelCapability.video.displayName, equals('视频'));
    });

    test('should have icons', () {
      for (final cap in ModelCapability.values) {
        expect(cap.icon, isNotNull);
      }
    });

    test('should have colors', () {
      for (final cap in ModelCapability.values) {
        expect(cap.color, isNotNull);
      }
    });
  });
}
