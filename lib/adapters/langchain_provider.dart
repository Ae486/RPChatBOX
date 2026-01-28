import 'dart:async';

import 'package:dio/dio.dart';
import 'package:langchain_core/chat_models.dart';
import 'package:langchain_core/prompts.dart';
import 'package:langchain_openai/langchain_openai.dart';
import 'package:langchain_google/langchain_google.dart';

import 'ai_provider.dart' as app;
import 'langchain_message_mapper.dart';
import 'provider_error_mapper.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';

/// LangChain.dart 适配器
///
/// 实现 AIProvider 接口，内部使用 LangChain ChatModel。
/// 支持 OpenAI, Google (Gemini), Anthropic 等多种 Provider。
class LangChainProvider extends app.AIProvider {
  LangChainProvider._(
    super.config,
    this._chatModelFactory,
  );

  /// 创建 ChatModel 的工厂函数
  final BaseChatModel Function({
    required String model,
    required ModelParameters parameters,
  }) _chatModelFactory;

  /// 从配置创建 Provider
  factory LangChainProvider.fromConfig(ProviderConfig config) {
    switch (config.type) {
      case ProviderType.openai:
        return LangChainProvider._(config, ({
          required String model,
          required ModelParameters parameters,
        }) {
          return ChatOpenAI(
            apiKey: config.apiKey,
            baseUrl: _normalizeBaseUrl(config.actualApiUrl),
            defaultOptions: ChatOpenAIOptions(
              model: model,
              temperature: parameters.temperature,
              maxTokens: parameters.maxTokens,
              topP: parameters.topP,
              frequencyPenalty: parameters.frequencyPenalty,
              presencePenalty: parameters.presencePenalty,
            ),
          );
        });

      case ProviderType.gemini:
        return LangChainProvider._(config, ({
          required String model,
          required ModelParameters parameters,
        }) {
          return ChatGoogleGenerativeAI(
            apiKey: config.apiKey,
            defaultOptions: ChatGoogleGenerativeAIOptions(
              model: model,
              temperature: parameters.temperature,
              maxOutputTokens: parameters.maxTokens,
              topP: parameters.topP,
            ),
          );
        });

      case ProviderType.deepseek:
        // DeepSeek 使用 OpenAI 兼容 API
        return LangChainProvider._(config, ({
          required String model,
          required ModelParameters parameters,
        }) {
          return ChatOpenAI(
            apiKey: config.apiKey,
            baseUrl: _normalizeBaseUrl(config.actualApiUrl),
            defaultOptions: ChatOpenAIOptions(
              model: model,
              temperature: parameters.temperature,
              maxTokens: parameters.maxTokens,
              topP: parameters.topP,
              frequencyPenalty: parameters.frequencyPenalty,
              presencePenalty: parameters.presencePenalty,
            ),
          );
        });

      case ProviderType.claude:
        // Claude 暂时使用 OpenAI 兼容模式（通过 OpenRouter 等代理）
        // TODO: 等 langchain_anthropic 包发布后替换
        return LangChainProvider._(config, ({
          required String model,
          required ModelParameters parameters,
        }) {
          return ChatOpenAI(
            apiKey: config.apiKey,
            baseUrl: _normalizeBaseUrl(config.actualApiUrl),
            defaultOptions: ChatOpenAIOptions(
              model: model,
              temperature: parameters.temperature,
              maxTokens: parameters.maxTokens,
              topP: parameters.topP,
            ),
          );
        });
    }
  }

  /// 标准化 baseUrl（移除尾部 /chat/completions，保留 /v1）
  ///
  /// LangChain ChatOpenAI 期望 baseUrl 格式为 `https://api.openai.com/v1`
  /// 而不是 `https://api.openai.com` 或 `https://api.openai.com/v1/chat/completions`
  static String _normalizeBaseUrl(String url) {
    // 移除尾部斜杠
    var normalized = url.endsWith('/') ? url.substring(0, url.length - 1) : url;

    // 迭代移除所有 API 路径后缀（但保留 /v1）
    // 例如: /v1/chat/completions -> /v1
    // 使用循环处理多层后缀的情况
    bool changed;
    do {
      changed = false;
      const suffixes = ['/chat/completions', '/completions', '/messages'];
      for (final suffix in suffixes) {
        if (normalized.endsWith(suffix)) {
          normalized = normalized.substring(0, normalized.length - suffix.length);
          changed = true;
          break;
        }
      }
    } while (changed);

    return normalized;
  }

  @override
  Future<ProviderTestResult> testConnection() async {
    try {
      final stopwatch = Stopwatch()..start();
      final baseUrl = _normalizeBaseUrl(config.actualApiUrl);
      final dio = Dio();

      final response = await dio.get(
        '$baseUrl/models',
        options: Options(
          headers: {
            'Authorization': 'Bearer ${config.apiKey}',
            'Content-Type': 'application/json',
          },
          receiveTimeout: const Duration(seconds: 10),
        ),
      );

      stopwatch.stop();

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final models = (data['data'] as List?)
            ?.map((m) => m['id'] as String)
            .toList();

        return ProviderTestResult.success(
          responseTimeMs: stopwatch.elapsedMilliseconds,
          availableModels: models,
        );
      } else {
        return ProviderTestResult.failure('请求失败: ${response.statusCode}');
      }
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout) {
        return ProviderTestResult.failure('连接超时');
      } else if (e.type == DioExceptionType.connectionError) {
        return ProviderTestResult.failure('网络连接失败');
      } else {
        return ProviderTestResult.failure('测试失败: ${e.message}');
      }
    } catch (e) {
      return ProviderTestResult.failure('测试失败: ${e.toString()}');
    }
  }

  @override
  Future<List<String>> listAvailableModels() async {
    try {
      final baseUrl = _normalizeBaseUrl(config.actualApiUrl);
      final dio = Dio();

      final response = await dio.get(
        '$baseUrl/models',
        options: Options(
          headers: {
            'Authorization': 'Bearer ${config.apiKey}',
            'Content-Type': 'application/json',
          },
          receiveTimeout: const Duration(seconds: 10),
          sendTimeout: const Duration(seconds: 10),
        ),
      );

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        return (data['data'] as List?)
                ?.map((m) => m['id'] as String)
                .toList() ??
            [];
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<app.ChatMessage> messages,
    required ModelParameters parameters,
    List<app.AttachedFileData>? files,
  }) async* {
    try {
      // 创建 ChatModel
      final chatModel = _chatModelFactory(model: model, parameters: parameters);

      // 转换消息格式
      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: config.type,
        files: files,
      );

      // 创建 PromptValue
      final promptValue = PromptValue.chat(lcMessages);

      // 流式调用
      await for (final chunk in chatModel.stream(promptValue)) {
        final content = chunk.output.content;
        if (content.isNotEmpty) {
          yield content;
        }
      }
    } catch (e) {
      throw ProviderErrorMapper.toApiError(e, providerName: config.name);
    }
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<app.ChatMessage> messages,
    required ModelParameters parameters,
    List<app.AttachedFileData>? files,
  }) async {
    try {
      // 创建 ChatModel
      final chatModel = _chatModelFactory(model: model, parameters: parameters);

      // 转换消息格式
      final lcMessages = await LangChainMessageMapper.toLangChainMessages(
        messages: messages,
        providerType: config.type,
        files: files,
      );

      // 创建 PromptValue
      final promptValue = PromptValue.chat(lcMessages);

      // 非流式调用
      final result = await chatModel.invoke(promptValue);
      return result.output.content;
    } catch (e) {
      throw ProviderErrorMapper.toApiError(e, providerName: config.name);
    }
  }
}
