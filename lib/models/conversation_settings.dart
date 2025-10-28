import 'model_config.dart';
import 'attached_file.dart';

/// 对话级配置
/// 每个对话可以有独立的模型选择和参数配置
class ConversationSettings {
  final String conversationId;
  final String? selectedProviderId;
  final String? selectedModelId;
  final ModelParameters parameters;
  final List<AttachedFile> attachedFiles;
  final bool enableVision;
  final bool enableTools;
  final bool enableNetwork;
  final int contextLength;
  final DateTime createdAt;
  final DateTime updatedAt;

  ConversationSettings({
    required this.conversationId,
    this.selectedProviderId,
    this.selectedModelId,
    ModelParameters? parameters,
    List<AttachedFile>? attachedFiles,
    this.enableVision = false,
    this.enableTools = false,
    this.enableNetwork = false,
    this.contextLength = 10,
    DateTime? createdAt,
    DateTime? updatedAt,
  })  : parameters = parameters ?? const ModelParameters(),
        attachedFiles = attachedFiles ?? [],
        createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? DateTime.now();

  /// 从JSON创建实例
  factory ConversationSettings.fromJson(Map<String, dynamic> json) {
    return ConversationSettings(
      conversationId: json['conversationId'] as String,
      selectedProviderId: json['selectedProviderId'] as String?,
      selectedModelId: json['selectedModelId'] as String?,
      parameters: json['parameters'] != null
          ? ModelParameters.fromJson(json['parameters'] as Map<String, dynamic>)
          : const ModelParameters(),
      attachedFiles: (json['attachedFiles'] as List<dynamic>?)
              ?.map((e) => AttachedFile.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      enableVision: json['enableVision'] as bool? ?? false,
      enableTools: json['enableTools'] as bool? ?? false,
      enableNetwork: json['enableNetwork'] as bool? ?? false,
      contextLength: json['contextLength'] as int? ?? 10,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
    );
  }

  /// 转换为JSON
  Map<String, dynamic> toJson() {
    return {
      'conversationId': conversationId,
      'selectedProviderId': selectedProviderId,
      'selectedModelId': selectedModelId,
      'parameters': parameters.toJson(),
      'attachedFiles': attachedFiles.map((e) => e.toJson()).toList(),
      'enableVision': enableVision,
      'enableTools': enableTools,
      'enableNetwork': enableNetwork,
      'contextLength': contextLength,
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
    };
  }

  /// 复制并修改部分字段
  ConversationSettings copyWith({
    String? conversationId,
    String? selectedProviderId,
    String? selectedModelId,
    ModelParameters? parameters,
    List<AttachedFile>? attachedFiles,
    bool? enableVision,
    bool? enableTools,
    bool? enableNetwork,
    int? contextLength,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return ConversationSettings(
      conversationId: conversationId ?? this.conversationId,
      selectedProviderId: selectedProviderId ?? this.selectedProviderId,
      selectedModelId: selectedModelId ?? this.selectedModelId,
      parameters: parameters ?? this.parameters,
      attachedFiles: attachedFiles ?? this.attachedFiles,
      enableVision: enableVision ?? this.enableVision,
      enableTools: enableTools ?? this.enableTools,
      enableNetwork: enableNetwork ?? this.enableNetwork,
      contextLength: contextLength ?? this.contextLength,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? DateTime.now(),
    );
  }

  /// 添加附件
  ConversationSettings addFile(AttachedFile file) {
    return copyWith(
      attachedFiles: [...attachedFiles, file],
    );
  }

  /// 移除附件
  ConversationSettings removeFile(String fileId) {
    return copyWith(
      attachedFiles: attachedFiles.where((f) => f.id != fileId).toList(),
    );
  }

  /// 清空附件
  ConversationSettings clearFiles() {
    return copyWith(attachedFiles: []);
  }

  /// 是否有附件
  bool get hasAttachedFiles => attachedFiles.isNotEmpty;

  /// 图片附件数量
  int get imageFileCount => attachedFiles.where((f) => f.type == FileType.image).length;

  /// 文档附件数量
  int get documentFileCount => attachedFiles.where((f) => f.type == FileType.document).length;

  /// 代码附件数量
  int get codeFileCount => attachedFiles.where((f) => f.type == FileType.code).length;

  /// 验证配置有效性
  String? validate() {
    // 验证参数
    final paramError = parameters.validate();
    if (paramError != null) return paramError;

    // 验证上下文长度
    if (contextLength <= 0) {
      return '上下文长度必须大于0';
    }

    // 如果启用视觉功能但没有选择模型，给出提示
    if (enableVision && selectedModelId == null) {
      return '启用视觉功能需要选择支持多模态的模型';
    }

    return null;
  }

  /// 创建默认配置
  factory ConversationSettings.createDefault(String conversationId) {
    return ConversationSettings(
      conversationId: conversationId,
      parameters: const ModelParameters(),
      contextLength: 10,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ConversationSettings && other.conversationId == conversationId;
  }

  @override
  int get hashCode => conversationId.hashCode;
}

/// 对话配置预设
class ConversationPreset {
  final String name;
  final String description;
  final ModelParameters parameters;
  final bool enableVision;
  final bool enableTools;
  final int contextLength;

  const ConversationPreset({
    required this.name,
    required this.description,
    required this.parameters,
    this.enableVision = false,
    this.enableTools = false,
    this.contextLength = 10,
  });

  /// 预定义的配置预设
  static const List<ConversationPreset> presets = [
    ConversationPreset(
      name: '平衡模式',
      description: '适合日常对话，平衡创造性和准确性',
      parameters: ModelParameters(
        temperature: 0.7,
        maxTokens: 2048,
        topP: 1.0,
      ),
      contextLength: 10,
    ),
    ConversationPreset(
      name: '精确模式',
      description: '适合代码生成、数学计算等需要精确性的任务',
      parameters: ModelParameters(
        temperature: 0.2,
        maxTokens: 4096,
        topP: 0.9,
      ),
      contextLength: 15,
    ),
    ConversationPreset(
      name: '创造模式',
      description: '适合创意写作、头脑风暴等需要想象力的任务',
      parameters: ModelParameters(
        temperature: 1.2,
        maxTokens: 3072,
        topP: 1.0,
      ),
      contextLength: 8,
    ),
    ConversationPreset(
      name: '长文本模式',
      description: '适合长篇内容生成',
      parameters: ModelParameters(
        temperature: 0.8,
        maxTokens: 8192,
        topP: 1.0,
      ),
      contextLength: 5,
    ),
  ];

  /// 应用预设到对话配置
  ConversationSettings applyTo(ConversationSettings settings) {
    return settings.copyWith(
      parameters: parameters,
      enableVision: enableVision,
      enableTools: enableTools,
      contextLength: contextLength,
    );
  }
}
