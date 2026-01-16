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
    ModelParameters? defaultParams,
    this.isEnabled = true,
    this.description,
    DateTime? createdAt,
    DateTime? updatedAt,
  })  : capabilities = capabilities ?? {ModelCapability.text},
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
      capabilities: (json['capabilities'] as List<dynamic>?)
              ?.map((e) => ModelCapability.values.firstWhere(
                    (cap) => cap.name == e,
                    orElse: () => ModelCapability.text,
                  ))
              .toSet() ??
          {ModelCapability.text},
      defaultParams: json['defaultParams'] != null
          ? ModelParameters.fromJson(json['defaultParams'] as Map<String, dynamic>)
          : ModelParameters(),
      isEnabled: json['isEnabled'] as bool? ?? true,
      description: json['description'] as String?,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
    );
  }

  /// 转换为 JSON
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'providerId': providerId,
      'modelName': modelName,
      'displayName': displayName,
      'capabilities': capabilities.map((e) => e.name).toList(),
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

  /// 是否支持多模态
  bool get isMultimodal {
    return capabilities.any((cap) =>
        cap == ModelCapability.vision ||
        cap == ModelCapability.audio ||
        cap == ModelCapability.video);
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
  text('文本', OwuiIcons.text, Color(0xFF4CAF50)),
  vision('视觉', OwuiIcons.visibility, Color(0xFF2196F3)),
  network('联网', OwuiIcons.globe, Color(0xFFFF9800)),
  tool('工具', OwuiIcons.tool, Color(0xFF9C27B0)),
  audio('音频', OwuiIcons.mic, Color(0xFFE91E63)),
  video('视频', OwuiIcons.video, Color(0xFFF44336));

  final String displayName;
  final IconData icon;
  final Color color;

  const ModelCapability(this.displayName, this.icon, this.color);
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


