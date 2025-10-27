/// AI 对话设置模型
class ChatSettings {
  final String apiUrl;
  final String apiKey;
  final String model;
  final String providerName; // 服务商名称
  final double temperature;
  final double topP;
  final int maxTokens;

  ChatSettings({
    this.apiUrl = 'https://api.openai.com/v1/chat/completions',
    this.apiKey = '',
    this.model = 'gpt-3.5-turbo',
    this.providerName = 'OpenAI',
    this.temperature = 0.7,
    this.topP = 1.0,
    this.maxTokens = 2000,
  });

  Map<String, dynamic> toJson() {
    return {
      'apiUrl': apiUrl,
      'apiKey': apiKey,
      'model': model,
      'providerName': providerName,
      'temperature': temperature,
      'topP': topP,
      'maxTokens': maxTokens,
    };
  }

  factory ChatSettings.fromJson(Map<String, dynamic> json) {
    return ChatSettings(
      apiUrl: json['apiUrl'] as String? ?? 'https://api.openai.com/v1/chat/completions',
      apiKey: json['apiKey'] as String? ?? '',
      model: json['model'] as String? ?? 'gpt-3.5-turbo',
      providerName: json['providerName'] as String? ?? 'OpenAI',
      temperature: (json['temperature'] as num?)?.toDouble() ?? 0.7,
      topP: (json['topP'] as num?)?.toDouble() ?? 1.0,
      maxTokens: json['maxTokens'] as int? ?? 2000,
    );
  }

  ChatSettings copyWith({
    String? apiUrl,
    String? apiKey,
    String? model,
    String? providerName,
    double? temperature,
    double? topP,
    int? maxTokens,
  }) {
    return ChatSettings(
      apiUrl: apiUrl ?? this.apiUrl,
      apiKey: apiKey ?? this.apiKey,
      model: model ?? this.model,
      providerName: providerName ?? this.providerName,
      temperature: temperature ?? this.temperature,
      topP: topP ?? this.topP,
      maxTokens: maxTokens ?? this.maxTokens,
    );
  }
}

/// AI 服务商预设
class AIProviderPreset {
  final String name;
  final String apiUrl;
  final String defaultModel;
  final String description;

  const AIProviderPreset({
    required this.name,
    required this.apiUrl,
    required this.defaultModel,
    required this.description,
  });

  static const List<AIProviderPreset> presets = [
    AIProviderPreset(
      name: 'OpenAI',
      apiUrl: 'https://api.openai.com/v1/chat/completions',
      defaultModel: 'gpt-3.5-turbo',
      description: 'OpenAI 官方 API',
    ),
    AIProviderPreset(
      name: 'Azure OpenAI',
      apiUrl: 'https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT/chat/completions?api-version=2024-02-15-preview',
      defaultModel: 'gpt-35-turbo',
      description: 'Microsoft Azure OpenAI 服务',
    ),
    AIProviderPreset(
      name: 'Claude',
      apiUrl: 'https://api.anthropic.com/v1/messages',
      defaultModel: 'claude-3-opus',
      description: 'Anthropic Claude API',
    ),
    AIProviderPreset(
      name: 'Gemini',
      apiUrl: 'https://generativelanguage.googleapis.com/v1/models/',
      defaultModel: 'gemini-pro',
      description: 'Google Gemini API',
    ),
    AIProviderPreset(
      name: '自定义',
      apiUrl: '',
      defaultModel: '',
      description: '其他兼容 OpenAI 格式的服务',
    ),
  ];
}

