import 'dart:async';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import 'openai_provider.dart';

/// AI服务提供商抽象接口
/// 定义所有Provider适配器必须实现的方法
abstract class AIProvider {
  final ProviderConfig config;

  AIProvider(this.config);

  /// 测试连接
  Future<ProviderTestResult> testConnection();

  /// 测试指定模型（发送实际测试请求）
  Future<ProviderTestResult> testModel(String modelName) async {
    // 默认实现：发送简单的测试消息
    try {
      final stopwatch = Stopwatch()..start();
      
      final testMessage = ChatMessage(
        role: 'user',
        content: 'Hi',
      );
      
      await sendMessage(
        model: modelName,
        messages: [testMessage],
        parameters: const ModelParameters(
          temperature: 0.7,
          maxTokens: 10,
        ),
      );
      
      stopwatch.stop();
      
      return ProviderTestResult.success(
        responseTimeMs: stopwatch.elapsedMilliseconds,
      );
    } catch (e) {
      return ProviderTestResult.failure('模型测试失败: ${e.toString()}');
    }
  }

  /// 获取可用模型列表
  Future<List<String>> listAvailableModels();

  /// 发送聊天消息（流式）
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  });

  /// 发送聊天消息（非流式）
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  });

  /// 获取Provider显示名称
  String get displayName => config.name;

  /// 获取Provider类型
  ProviderType get type => config.type;

  /// 验证配置有效性
  String? validateConfig() {
    if (config.apiUrl.isEmpty) return 'API地址不能为空';
    if (config.apiKey.isEmpty) return 'API密钥不能为空';
    if (!Uri.tryParse(config.apiUrl)!.isAbsolute) return 'API地址格式不正确';
    return null;
  }

  /// 构建请求头
  Map<String, String> buildHeaders() {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      ...config.customHeaders,
    };
    return headers;
  }
}

/// 聊天消息数据类
class ChatMessage {
  final String role; // 'system', 'user', 'assistant'
  final String content;
  final List<MessageContent>? multimodalContent;

  ChatMessage({
    required this.role,
    required this.content,
    this.multimodalContent,
  });

  Map<String, dynamic> toJson() {
    if (multimodalContent != null && multimodalContent!.isNotEmpty) {
      return {
        'role': role,
        'content': multimodalContent!.map((c) => c.toJson()).toList(),
      };
    }
    return {
      'role': role,
      'content': content,
    };
  }
}

/// 多模态消息内容
class MessageContent {
  final String type; // 'text', 'image_url', 'file'
  final String? text;
  final ImageUrl? imageUrl;
  final FileData? file;

  MessageContent.text(this.text)
      : type = 'text',
        imageUrl = null,
        file = null;

  MessageContent.image(this.imageUrl)
      : type = 'image_url',
        text = null,
        file = null;

  MessageContent.file(this.file)
      : type = 'file',
        text = null,
        imageUrl = null;

  Map<String, dynamic> toJson() {
    switch (type) {
      case 'text':
        return {'type': 'text', 'text': text};
      case 'image_url':
        return {'type': 'image_url', 'image_url': imageUrl!.toJson()};
      case 'file':
        return {'type': 'file', 'file': file!.toJson()};
      default:
        return {};
    }
  }
}

/// 图片URL数据
class ImageUrl {
  final String url;
  final String? detail; // 'auto', 'low', 'high'

  ImageUrl({required this.url, this.detail});

  Map<String, dynamic> toJson() {
    return {
      'url': url,
      if (detail != null) 'detail': detail,
    };
  }
}

/// 文件数据
class FileData {
  final String name;
  final String mimeType;
  final String data; // base64编码

  FileData({
    required this.name,
    required this.mimeType,
    required this.data,
  });

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'mime_type': mimeType,
      'data': data,
    };
  }
}

/// 附件文件数据
class AttachedFileData {
  final String path;
  final String mimeType;
  final String name;

  AttachedFileData({
    required this.path,
    required this.mimeType,
    required this.name,
  });
}
/// Provider工厂
class ProviderFactory {
  /// 创建 Provider实例
  static AIProvider createProvider(ProviderConfig config) {
    switch (config.type) {
      case ProviderType.openai:
        return OpenAIProvider(config);
      case ProviderType.gemini:
        return GeminiProvider(config);
      case ProviderType.deepseek:
        return DeepSeekProvider(config);
      case ProviderType.claude:
        return ClaudeProvider(config);
      // 🔧 修复：已移除 custom 选项
    }
  }
}

class GeminiProvider extends AIProvider {
  GeminiProvider(super.config);

  @override
  Future<ProviderTestResult> testConnection() {
    throw UnimplementedError();
  }

  @override
  Future<List<String>> listAvailableModels() {
    throw UnimplementedError();
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) {
    throw UnimplementedError();
  }
}

class DeepSeekProvider extends AIProvider {
  DeepSeekProvider(super.config);

  @override
  Future<ProviderTestResult> testConnection() {
    throw UnimplementedError();
  }

  @override
  Future<List<String>> listAvailableModels() {
    throw UnimplementedError();
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) {
    throw UnimplementedError();
  }
}

class ClaudeProvider extends AIProvider {
  ClaudeProvider(super.config);

  @override
  Future<ProviderTestResult> testConnection() {
    throw UnimplementedError();
  }

  @override
  Future<List<String>> listAvailableModels() {
    throw UnimplementedError();
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) {
    throw UnimplementedError();
  }
}

// 🔧 修复：已移除 CustomProvider 类
