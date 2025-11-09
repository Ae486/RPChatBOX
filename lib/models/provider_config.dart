import '../utils/api_url_helper.dart';

/// AI服务提供商配置模型
/// 支持多种AI服务提供商(OpenAI, Gemini, Claude等)
class ProviderConfig {
  final String id;
  final String name;
  final ProviderType type;
  final String apiUrl;
  final String apiKey;
  final bool isEnabled;
  final DateTime createdAt;
  final DateTime updatedAt;
  final Map<String, dynamic> customHeaders;
  final String? description;

  ProviderConfig({
    required this.id,
    required this.name,
    required this.type,
    required this.apiUrl,
    required this.apiKey,
    this.isEnabled = true,
    DateTime? createdAt,
    DateTime? updatedAt,
    Map<String, dynamic>? customHeaders,
    this.description,
  })  : createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? DateTime.now(),
        customHeaders = customHeaders ?? {};

  /// 从JSON创建实例
  factory ProviderConfig.fromJson(Map<String, dynamic> json) {
    return ProviderConfig(
      id: json['id'] as String,
      name: json['name'] as String,
      type: ProviderType.values.firstWhere(
        (e) => e.name == json['type'],
        orElse: () => ProviderType.openai, // 🔧 修复：custom已移除，使用openai作为默认
      ),
      apiUrl: json['apiUrl'] as String,
      apiKey: json['apiKey'] as String,
      isEnabled: json['isEnabled'] as bool? ?? true,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
      customHeaders: Map<String, dynamic>.from(json['customHeaders'] ?? {}),
      description: json['description'] as String?,
    );
  }

  /// 转换为JSON
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'type': type.name,
      'apiUrl': apiUrl,
      'apiKey': apiKey,
      'isEnabled': isEnabled,
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
      'customHeaders': customHeaders,
      'description': description,
    };
  }

  /// 复制并修改部分字段
  ProviderConfig copyWith({
    String? id,
    String? name,
    ProviderType? type,
    String? apiUrl,
    String? apiKey,
    bool? isEnabled,
    DateTime? createdAt,
    DateTime? updatedAt,
    Map<String, dynamic>? customHeaders,
    String? description,
  }) {
    return ProviderConfig(
      id: id ?? this.id,
      name: name ?? this.name,
      type: type ?? this.type,
      apiUrl: apiUrl ?? this.apiUrl,
      apiKey: apiKey ?? this.apiKey,
      isEnabled: isEnabled ?? this.isEnabled,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? DateTime.now(),
      customHeaders: customHeaders ?? this.customHeaders,
      description: description ?? this.description,
    );
  }

  /// 获取API密钥的脱敏显示
  String get maskedApiKey {
    if (apiKey.length <= 8) return '••••••••';
    return '${apiKey.substring(0, 4)}••••${apiKey.substring(apiKey.length - 4)}';
  }

  /// 🆕 获取实际使用的API地址（应用补全规则）
  String get actualApiUrl {
    return ApiUrlHelper.getActualApiUrl(apiUrl, type);
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ProviderConfig && other.id == id;
  }

  @override
  int get hashCode => id.hashCode;
}

/// 提供商类型枚举
enum ProviderType {
  openai('OpenAI格式', 'https://api.openai.com/v1'),
  gemini('Gemini格式', 'https://generativelanguage.googleapis.com/v1'),
  deepseek('DeepSeek格式', 'https://api.deepseek.com/v1'),
  claude('Claude格式', 'https://api.anthropic.com/v1');
  // 🔧 已移除 custom（自定义）选项

  final String displayName;
  final String defaultApiUrl;

  const ProviderType(this.displayName, this.defaultApiUrl);
}

/// Provider连接测试结果
class ProviderTestResult {
  final bool success;
  final String? errorMessage;
  final int? responseTimeMs;
  final List<String>? availableModels;

  ProviderTestResult({
    required this.success,
    this.errorMessage,
    this.responseTimeMs,
    this.availableModels,
  });

  factory ProviderTestResult.success({
    required int responseTimeMs,
    List<String>? availableModels,
  }) {
    return ProviderTestResult(
      success: true,
      responseTimeMs: responseTimeMs,
      availableModels: availableModels,
    );
  }

  factory ProviderTestResult.failure(String errorMessage) {
    return ProviderTestResult(
      success: false,
      errorMessage: errorMessage,
    );
  }
}
