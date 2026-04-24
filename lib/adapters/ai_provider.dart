import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/provider_config.dart';
import '../models/model_config.dart';
import 'openai_provider.dart';
import 'langchain_provider.dart';
import 'proxy_openai_provider.dart';
import 'hybrid_langchain_provider.dart';

/// AI服务提供商抽象接口
/// 定义所有Provider适配器必须实现的方法
abstract class AIProvider {
  final ProviderConfig config;

  AIProvider(this.config);

  /// 测试连接
  Future<ProviderTestResult> testConnection();

  /// 测试指定模型（发送实际测试请求）
  Future<ProviderTestResult> testModel(ModelConfig model) async {
    if (model.isEmbeddingModel) {
      return ProviderTestResult.failure('当前测试入口未实现 Embedding 模型测试');
    }
    if (model.isRerankModel) {
      return ProviderTestResult.failure('当前测试入口未实现 Rerank 模型测试');
    }
    // 默认实现：发送简单的测试消息
    try {
      final stopwatch = Stopwatch()..start();

      final testMessage = ChatMessage(role: 'user', content: 'Hi');

      await sendMessage(
        model: model.modelName,
        messages: [testMessage],
        parameters: const ModelParameters(temperature: 0.7, maxTokens: 10),
        modelId: model.id,
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
    String? modelId,
  });

  /// 发送聊天消息（结构化事件流）
  ///
  /// 默认回退到字符串流，仅产生 `text` 事件。
  Stream<AIStreamEvent> sendMessageEventStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    await for (final chunk in sendMessageStream(
      model: model,
      messages: messages,
      parameters: parameters,
      files: files,
      modelId: modelId,
    )) {
      yield AIStreamEvent.text(chunk, isTypedSemantic: false);
    }
  }

  /// 发送聊天消息（非流式）
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  });

  /// 获取Provider显示名称
  String get displayName => config.name;

  /// 获取Provider类型
  ProviderType get type => config.type;

  /// 验证配置有效性
  String? validateConfig() {
    if (config.apiUrl.isEmpty) return 'API地址不能为空';
    if (config.apiKey.isEmpty) return 'API密钥不能为空';
    final uri = Uri.tryParse(config.apiUrl);
    if (uri == null || !uri.isAbsolute) return 'API地址格式不正确';
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

enum AIStreamEventType {
  text,
  thinking,
  toolCall,
  toolStarted,
  toolResult,
  toolError,
  usage,
}

class AIStreamEvent {
  final AIStreamEventType type;
  final String? text;
  final List<Map<String, dynamic>>? toolCalls;
  final String? callId;
  final String? toolName;
  final String? result;
  final String? errorMessage;
  final int? promptTokens;
  final int? completionTokens;
  final int? totalTokens;

  /// `true` 表示该事件来自 typed SSE / 结构化语义流，
  /// `false` 表示只是旧字符串流包装出来的兼容事件。
  final bool isTypedSemantic;

  const AIStreamEvent._({
    required this.type,
    this.text,
    this.toolCalls,
    this.callId,
    this.toolName,
    this.result,
    this.errorMessage,
    this.promptTokens,
    this.completionTokens,
    this.totalTokens,
    required this.isTypedSemantic,
  });

  factory AIStreamEvent.text(String text, {required bool isTypedSemantic}) {
    return AIStreamEvent._(
      type: AIStreamEventType.text,
      text: text,
      isTypedSemantic: isTypedSemantic,
    );
  }

  factory AIStreamEvent.thinking(String text) {
    return AIStreamEvent._(
      type: AIStreamEventType.thinking,
      text: text,
      isTypedSemantic: true,
    );
  }

  factory AIStreamEvent.toolCall(List<Map<String, dynamic>> toolCalls) {
    return AIStreamEvent._(
      type: AIStreamEventType.toolCall,
      toolCalls: toolCalls,
      isTypedSemantic: true,
    );
  }

  factory AIStreamEvent.toolStarted({
    required String callId,
    String? toolName,
  }) {
    return AIStreamEvent._(
      type: AIStreamEventType.toolStarted,
      callId: callId,
      toolName: toolName,
      isTypedSemantic: true,
    );
  }

  factory AIStreamEvent.toolResult({
    required String callId,
    String? toolName,
    required String result,
  }) {
    return AIStreamEvent._(
      type: AIStreamEventType.toolResult,
      callId: callId,
      toolName: toolName,
      result: result,
      isTypedSemantic: true,
    );
  }

  factory AIStreamEvent.toolError({
    required String callId,
    String? toolName,
    required String errorMessage,
  }) {
    return AIStreamEvent._(
      type: AIStreamEventType.toolError,
      callId: callId,
      toolName: toolName,
      errorMessage: errorMessage,
      isTypedSemantic: true,
    );
  }

  factory AIStreamEvent.usage({
    required int promptTokens,
    required int completionTokens,
    required int totalTokens,
  }) {
    return AIStreamEvent._(
      type: AIStreamEventType.usage,
      promptTokens: promptTokens,
      completionTokens: completionTokens,
      totalTokens: totalTokens,
      isTypedSemantic: true,
    );
  }
}

/// 聊天消息数据类
class ChatMessage {
  final String role; // 'system', 'user', 'assistant', 'tool'
  final String content;
  final List<MessageContent>? multimodalContent;

  /// 工具调用列表（assistant 消息）
  final List<Map<String, dynamic>>? toolCalls;

  /// 工具调用 ID（tool 消息）
  final String? toolCallId;

  ChatMessage({
    required this.role,
    required this.content,
    this.multimodalContent,
    this.toolCalls,
    this.toolCallId,
  });

  Map<String, dynamic> toJson() {
    if (multimodalContent != null && multimodalContent!.isNotEmpty) {
      return {
        'role': role,
        'content': multimodalContent!.map((c) => c.toJson()).toList(),
      };
    }

    final json = <String, dynamic>{'role': role, 'content': content};

    // 添加 tool_calls（assistant 消息）
    if (toolCalls != null && toolCalls!.isNotEmpty) {
      json['tool_calls'] = toolCalls;
    }

    // 添加 tool_call_id（tool 消息）
    if (toolCallId != null) {
      json['tool_call_id'] = toolCallId;
    }

    return json;
  }
}

/// 多模态消息内容
class MessageContent {
  final String type; // 'text', 'image_url', 'file'
  final String? text;
  final ImageUrl? imageUrl;
  final FileData? file;

  MessageContent.text(this.text) : type = 'text', imageUrl = null, file = null;

  MessageContent.image(this.imageUrl)
    : type = 'image_url',
      text = null,
      file = null;

  MessageContent.file(this.file) : type = 'file', text = null, imageUrl = null;

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
    return {'url': url, if (detail != null) 'detail': detail};
  }
}

/// 文件数据
class FileData {
  final String name;
  final String mimeType;
  final String data; // base64编码

  FileData({required this.name, required this.mimeType, required this.data});

  Map<String, dynamic> toJson() {
    return {'name': name, 'mime_type': mimeType, 'data': data};
  }
}

/// 附件文件数据
class AttachedFileData {
  final String path;
  final String mimeType;
  final String name;
  final Uint8List? bytes;

  AttachedFileData({
    required this.path,
    required this.mimeType,
    required this.name,
    this.bytes,
  });
}

/// Provider工厂
class ProviderFactory {
  /// 是否使用 LangChain 实现（用于 A/B 测试和回滚）
  static bool useLangChain = false;

  /// 是否使用混合 LangChain 实现（推荐）
  /// - true: 使用 HybridLangChainProvider（LangChain 消息格式 + 自实现 SSE）
  /// - false: 使用原有 OpenAIProvider
  static bool useHybridLangChain = true;

  /// 全局后端开关（设为 false 时强制所有请求走直连）
  static bool pythonBackendEnabled = false;

  /// 创建 Provider实例（原有方法，保持不变）
  static AIProvider createProvider(ProviderConfig config) {
    // 优先使用混合实现
    if (useHybridLangChain) {
      return HybridLangChainProvider(config);
    }

    if (useLangChain) {
      // 使用 LangChain.dart 实现
      return LangChainProvider.fromConfig(config);
    }

    // 回滚：使用原有实现
    switch (config.type) {
      case ProviderType.openai:
        return OpenAIProvider(config);
      case ProviderType.gemini:
        // 临时：使用 OpenAI 兼容实现以支持大多数聚合/代理（如 OpenRouter）的 Gemini 路由
        // 待实现原生 GeminiProvider 后再切换
        return OpenAIProvider(config);
      case ProviderType.deepseek:
        return DeepSeekProvider(config);
      case ProviderType.claude:
        return ClaudeProvider(config);
    }
  }

  /// 创建支持后端路由的 Provider（新增）
  ///
  /// 根据 config.backendMode 选择：
  /// - direct: 直连 LLM API（同 createProvider）
  /// - proxy: 走 Python 后端代理
  /// - auto: 优先代理，失败回退到直连
  static AIProvider createProviderWithRouting(
    ProviderConfig config, {
    bool forceDirect = false,
  }) {
    if (forceDirect) {
      debugPrint('[ROUTE] 强制直连模式 → 保留当前前端能力边界');
      return createProvider(config);
    }

    // 全局开关关闭时强制直连
    if (!pythonBackendEnabled) {
      debugPrint('[ROUTE] 全局开关关闭 → 强制直连模式');
      return createProvider(config);
    }

    // 全局开关开启时，强制使用 proxy 模式（忽略 config.backendMode）
    debugPrint('[ROUTE] 全局开关开启 → 使用 Python 后端代理');
    return ProxyOpenAIProvider(config);
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
    String? modelId,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
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
    String? modelId,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
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
    String? modelId,
  }) {
    throw UnimplementedError();
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) {
    throw UnimplementedError();
  }
}

// 🔧 修复：已移除 CustomProvider 类
