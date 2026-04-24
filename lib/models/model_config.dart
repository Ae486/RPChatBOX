import 'package:flutter/material.dart';
import '../chat_ui/owui/owui_icons.dart';

/// AI 模型配置
/// 包含模型能力、参数和显示属性
class ModelConfig {
  final String id;
  final String providerId;
  final String modelName;
  final String displayName;
  final Set<ModelCapability> capabilities;
  final String? capabilitySource;
  final ModelCapabilityProfile? capabilityProfile;
  final ModelParameters defaultParams;
  final bool isEnabled;
  final String? description;
  final DateTime createdAt;
  final DateTime updatedAt;

  ModelConfig({
    required this.id,
    required this.providerId,
    required this.modelName,
    required this.displayName,
    Set<ModelCapability>? capabilities,
    this.capabilitySource,
    this.capabilityProfile,
    ModelParameters? defaultParams,
    this.isEnabled = true,
    this.description,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) : capabilities = capabilities ?? const <ModelCapability>{},
       defaultParams = defaultParams ?? ModelParameters(),
       createdAt = createdAt ?? DateTime.now(),
       updatedAt = updatedAt ?? DateTime.now();

  /// 从 JSON 创建实例
  factory ModelConfig.fromJson(Map<String, dynamic> json) {
    return ModelConfig(
      id: json['id'] as String,
      providerId: json['providerId'] as String,
      modelName: json['modelName'] as String,
      displayName: json['displayName'] as String,
      capabilities:
          (json['capabilities'] as List<dynamic>?)
              ?.map((e) => ModelCapability.fromWire(e?.toString()))
              .whereType<ModelCapability>()
              .toSet() ??
          const <ModelCapability>{},
      capabilitySource: json['capabilitySource'] as String?,
      capabilityProfile: json['capabilityProfile'] != null
          ? ModelCapabilityProfile.fromJson(
              json['capabilityProfile'] as Map<String, dynamic>,
            )
          : null,
      defaultParams: json['defaultParams'] != null
          ? ModelParameters.fromJson(
              json['defaultParams'] as Map<String, dynamic>,
            )
          : ModelParameters(),
      isEnabled: json['isEnabled'] as bool? ?? true,
      description: json['description'] as String?,
      createdAt: json['createdAt'] != null
          ? DateTime.parse(json['createdAt'] as String)
          : null,
      updatedAt: json['updatedAt'] != null
          ? DateTime.parse(json['updatedAt'] as String)
          : null,
    );
  }

  /// 转换为 JSON
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'providerId': providerId,
      'modelName': modelName,
      'displayName': displayName,
      'capabilities': capabilities.map((e) => e.wireName).toList(),
      'capabilitySource': capabilitySource,
      'capabilityProfile': capabilityProfile?.toJson(),
      'defaultParams': defaultParams.toJson(),
      'isEnabled': isEnabled,
      'description': description,
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
    };
  }

  /// 复制并修改部分字段
  ModelConfig copyWith({
    String? id,
    String? providerId,
    String? modelName,
    String? displayName,
    Set<ModelCapability>? capabilities,
    String? capabilitySource,
    ModelCapabilityProfile? capabilityProfile,
    ModelParameters? defaultParams,
    bool? isEnabled,
    String? description,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return ModelConfig(
      id: id ?? this.id,
      providerId: providerId ?? this.providerId,
      modelName: modelName ?? this.modelName,
      displayName: displayName ?? this.displayName,
      capabilities: capabilities ?? this.capabilities,
      capabilitySource: capabilitySource ?? this.capabilitySource,
      capabilityProfile: capabilityProfile ?? this.capabilityProfile,
      defaultParams: defaultParams ?? this.defaultParams,
      isEnabled: isEnabled ?? this.isEnabled,
      description: description ?? this.description,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? DateTime.now(),
    );
  }

  /// 检查是否具有特定能力
  bool hasCapability(ModelCapability capability) {
    return capabilities.contains(capability);
  }

  bool get supportsFunctionCalling =>
      capabilityProfile?.supportsFunctionCalling ??
      hasCapability(ModelCapability.tool);

  bool get supportsVision =>
      capabilityProfile?.supportsVision ??
      hasCapability(ModelCapability.vision);

  bool get supportsToolChoice =>
      capabilityProfile?.supportsToolChoice ?? supportsFunctionCalling;

  bool get supportsResponseSchema =>
      capabilityProfile?.supportsResponseSchema ?? false;

  String? get resolvedMode {
    final profileMode = capabilityProfile?.mode;
    if (profileMode != null && profileMode.isNotEmpty) {
      return profileMode;
    }
    if (hasCapability(ModelCapability.rerank)) {
      return 'rerank';
    }
    if (hasCapability(ModelCapability.embedding)) {
      return 'embedding';
    }
    return 'chat';
  }

  bool get isEmbeddingModel =>
      resolvedMode == 'embedding' ||
      hasCapability(ModelCapability.embedding) ||
      modelName.toLowerCase().contains('embedding');

  bool get isRerankModel =>
      resolvedMode == 'rerank' ||
      hasCapability(ModelCapability.rerank) ||
      modelName.toLowerCase().contains('rerank');

  bool get isCrossEncoderRerankModel =>
      resolvedMode == 'cross_encoder_rerank' ||
      modelName.toLowerCase().contains('cross-encoder');

  bool get isAgentCapable {
    final mode = resolvedMode;
    if (mode != null && mode != 'chat' && mode != 'responses') {
      return false;
    }
    if (!supportsFunctionCalling) {
      return false;
    }
    final params = capabilityProfile?.supportedOpenaiParams ?? const <String>[];
    if (params.isEmpty) {
      return true;
    }
    return params.contains('tools') && params.contains('tool_choice');
  }

  /// 是否支持多模态
  bool get isMultimodal {
    if (capabilityProfile != null) {
      return supportsVision ||
          (capabilityProfile?.supportsAudioInput ?? false) ||
          (capabilityProfile?.supportsAudioOutput ?? false);
    }
    return capabilities.contains(ModelCapability.vision);
  }

  /// 获取能力图标列表
  List<IconData> get capabilityIcons {
    return capabilities.map((cap) => cap.icon).toList();
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ModelConfig && other.id == id;
  }

  @override
  int get hashCode => id.hashCode;
}

/// 模型能力枚举
enum ModelCapability {
  reasoning('推理', OwuiIcons.thinking, Color(0xFF4CAF50)),
  vision('视觉', OwuiIcons.visibility, Color(0xFF2196F3)),
  network('联网', OwuiIcons.globe, Color(0xFFFF9800)),
  tool('工具', OwuiIcons.tool, Color(0xFF9C27B0)),
  embedding('Embedding', OwuiIcons.link, Color(0xFF009688)),
  rerank('Rerank', OwuiIcons.sort, Color(0xFF795548));

  final String displayName;
  final IconData icon;
  final Color color;

  const ModelCapability(this.displayName, this.icon, this.color);

  String get wireName => name;

  static ModelCapability? fromWire(String? value) {
    final normalized = (value ?? '').trim().toLowerCase();
    if (normalized.isEmpty) return null;
    if (normalized == 'cross_encoder_rerank') {
      return ModelCapability.rerank;
    }
    if (normalized == 'text' || normalized == 'audio' || normalized == 'video') {
      return null;
    }
    for (final capability in ModelCapability.values) {
      if (capability.wireName == normalized || capability.name == normalized) {
        return capability;
      }
    }
    return null;
  }
}

class ModelCapabilityProfile {
  final bool known;
  final bool providerSupported;
  final String capabilitySource;
  final String? resolutionStrategy;
  final String? transportProviderType;
  final String? semanticProviderType;
  final String? semanticLookupModel;
  final String? mode;
  final int? maxInputTokens;
  final int? maxOutputTokens;
  final int? outputVectorSize;
  final bool? supportsFunctionCalling;
  final bool? supportsParallelFunctionCalling;
  final bool? supportsVision;
  final bool? supportsResponseSchema;
  final bool? supportsToolChoice;
  final bool? supportsReasoning;
  final bool? supportsPdfInput;
  final bool? supportsWebSearch;
  final bool? supportsAudioInput;
  final bool? supportsAudioOutput;
  final bool? supportsSystemMessages;
  final List<String> supportedOpenaiParams;
  final List<String> recommendedCapabilities;

  const ModelCapabilityProfile({
    required this.known,
    required this.providerSupported,
    required this.capabilitySource,
    this.resolutionStrategy,
    this.transportProviderType,
    this.semanticProviderType,
    this.semanticLookupModel,
    this.mode,
    this.maxInputTokens,
    this.maxOutputTokens,
    this.outputVectorSize,
    this.supportsFunctionCalling,
    this.supportsParallelFunctionCalling,
    this.supportsVision,
    this.supportsResponseSchema,
    this.supportsToolChoice,
    this.supportsReasoning,
    this.supportsPdfInput,
    this.supportsWebSearch,
    this.supportsAudioInput,
    this.supportsAudioOutput,
    this.supportsSystemMessages,
    this.supportedOpenaiParams = const [],
    this.recommendedCapabilities = const [],
  });

  factory ModelCapabilityProfile.fromJson(Map<String, dynamic> json) {
    List<String> readStringList(String snakeKey, String camelKey) {
      final snake = json[snakeKey] as List?;
      if (snake != null) {
        return snake
            .map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList();
      }
      final camel = json[camelKey] as List?;
      if (camel != null) {
        return camel
            .map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList();
      }
      return const [];
    }

    return ModelCapabilityProfile(
      known: json['known'] as bool? ?? false,
      providerSupported:
          json['provider_supported'] as bool? ??
          json['providerSupported'] as bool? ??
          false,
      capabilitySource:
          json['capability_source'] as String? ??
          json['capabilitySource'] as String? ??
          'default_unmapped',
      resolutionStrategy:
          json['resolution_strategy'] as String? ??
          json['resolutionStrategy'] as String?,
      transportProviderType:
          json['transport_provider_type'] as String? ??
          json['transportProviderType'] as String?,
      semanticProviderType:
          json['semantic_provider_type'] as String? ??
          json['semanticProviderType'] as String?,
      semanticLookupModel:
          json['semantic_lookup_model'] as String? ??
          json['semanticLookupModel'] as String?,
      mode: json['mode'] as String?,
      maxInputTokens:
          json['max_input_tokens'] as int? ?? json['maxInputTokens'] as int?,
      maxOutputTokens:
          json['max_output_tokens'] as int? ?? json['maxOutputTokens'] as int?,
      outputVectorSize:
          json['output_vector_size'] as int? ??
          json['outputVectorSize'] as int?,
      supportsFunctionCalling:
          json['supports_function_calling'] as bool? ??
          json['supportsFunctionCalling'] as bool?,
      supportsParallelFunctionCalling:
          json['supports_parallel_function_calling'] as bool? ??
          json['supportsParallelFunctionCalling'] as bool?,
      supportsVision:
          json['supports_vision'] as bool? ?? json['supportsVision'] as bool?,
      supportsResponseSchema:
          json['supports_response_schema'] as bool? ??
          json['supportsResponseSchema'] as bool?,
      supportsToolChoice:
          json['supports_tool_choice'] as bool? ??
          json['supportsToolChoice'] as bool?,
      supportsReasoning:
          json['supports_reasoning'] as bool? ??
          json['supportsReasoning'] as bool?,
      supportsPdfInput:
          json['supports_pdf_input'] as bool? ??
          json['supportsPdfInput'] as bool?,
      supportsWebSearch:
          json['supports_web_search'] as bool? ??
          json['supportsWebSearch'] as bool?,
      supportsAudioInput:
          json['supports_audio_input'] as bool? ??
          json['supportsAudioInput'] as bool?,
      supportsAudioOutput:
          json['supports_audio_output'] as bool? ??
          json['supportsAudioOutput'] as bool?,
      supportsSystemMessages:
          json['supports_system_messages'] as bool? ??
          json['supportsSystemMessages'] as bool?,
      supportedOpenaiParams: readStringList(
        'supported_openai_params',
        'supportedOpenaiParams',
      ),
      recommendedCapabilities: readStringList(
        'recommended_capabilities',
        'recommendedCapabilities',
      ),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'known': known,
      'provider_supported': providerSupported,
      'capability_source': capabilitySource,
      'resolution_strategy': resolutionStrategy,
      'transport_provider_type': transportProviderType,
      'semantic_provider_type': semanticProviderType,
      'semantic_lookup_model': semanticLookupModel,
      'mode': mode,
      'max_input_tokens': maxInputTokens,
      'max_output_tokens': maxOutputTokens,
      'output_vector_size': outputVectorSize,
      'supports_function_calling': supportsFunctionCalling,
      'supports_parallel_function_calling': supportsParallelFunctionCalling,
      'supports_vision': supportsVision,
      'supports_response_schema': supportsResponseSchema,
      'supports_tool_choice': supportsToolChoice,
      'supports_reasoning': supportsReasoning,
      'supports_pdf_input': supportsPdfInput,
      'supports_web_search': supportsWebSearch,
      'supports_audio_input': supportsAudioInput,
      'supports_audio_output': supportsAudioOutput,
      'supports_system_messages': supportsSystemMessages,
      'supported_openai_params': supportedOpenaiParams,
      'recommended_capabilities': recommendedCapabilities,
    };
  }
}

/// 模型参数配置
class ModelParameters {
  final double temperature;
  final int maxTokens;
  final double topP;
  final double frequencyPenalty;
  final double presencePenalty;
  final bool streamOutput;

  const ModelParameters({
    this.temperature = 0.7,
    this.maxTokens = 2048,
    this.topP = 1.0,
    this.frequencyPenalty = 0.0,
    this.presencePenalty = 0.0,
    this.streamOutput = true,
  });

  /// 从 JSON 创建实例
  factory ModelParameters.fromJson(Map<String, dynamic> json) {
    return ModelParameters(
      temperature: (json['temperature'] as num?)?.toDouble() ?? 0.7,
      maxTokens: json['maxTokens'] as int? ?? 2048,
      topP: (json['topP'] as num?)?.toDouble() ?? 1.0,
      frequencyPenalty: (json['frequencyPenalty'] as num?)?.toDouble() ?? 0.0,
      presencePenalty: (json['presencePenalty'] as num?)?.toDouble() ?? 0.0,
      streamOutput: json['streamOutput'] as bool? ?? true,
    );
  }

  /// 转换为 JSON
  Map<String, dynamic> toJson() {
    return {
      'temperature': temperature,
      'maxTokens': maxTokens,
      'topP': topP,
      'frequencyPenalty': frequencyPenalty,
      'presencePenalty': presencePenalty,
      'streamOutput': streamOutput,
    };
  }

  /// 复制并修改部分字段
  ModelParameters copyWith({
    double? temperature,
    int? maxTokens,
    double? topP,
    double? frequencyPenalty,
    double? presencePenalty,
    bool? streamOutput,
  }) {
    return ModelParameters(
      temperature: temperature ?? this.temperature,
      maxTokens: maxTokens ?? this.maxTokens,
      topP: topP ?? this.topP,
      frequencyPenalty: frequencyPenalty ?? this.frequencyPenalty,
      presencePenalty: presencePenalty ?? this.presencePenalty,
      streamOutput: streamOutput ?? this.streamOutput,
    );
  }

  /// 验证参数有效性
  String? validate() {
    if (temperature < 0.0 || temperature > 2.0) {
      return 'Temperature 必须在 0.0-2.0 之间';
    }
    if (maxTokens <= 0) {
      return 'MaxTokens 必须大于 0';
    }
    if (topP < 0.0 || topP > 1.0) {
      return 'TopP 必须在 0.0-1.0 之间';
    }
    if (frequencyPenalty < -2.0 || frequencyPenalty > 2.0) {
      return 'FrequencyPenalty 必须在 -2.0-2.0 之间';
    }
    if (presencePenalty < -2.0 || presencePenalty > 2.0) {
      return 'PresencePenalty 必须在 -2.0-2.0 之间';
    }
    return null;
  }
}
