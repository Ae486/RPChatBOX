import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/dio_service.dart';
import 'ai_provider.dart';

/// Provider that routes requests through Python backend proxy.
///
/// This provider sends requests to the local Python backend instead of
/// directly to LLM APIs. The backend handles the actual API calls.
class ProxyOpenAIProvider extends AIProvider {
  static const String defaultProxyUrl = 'http://localhost:8765';

  ProxyOpenAIProvider(super.config);

  String get _proxyBaseUrl => config.proxyApiUrl ?? defaultProxyUrl;

  Map<String, String> _buildProxyHeaders() {
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    // Add proxy-specific headers if configured
    if (config.proxyHeaders != null) {
      headers.addAll(config.proxyHeaders!.cast<String, String>());
    }
    return headers;
  }

  Map<String, dynamic> _buildProviderPayload() {
    return {
      'type': config.type.name,
      'api_key': config.apiKey,
      'api_url': config.actualApiUrl,
      'custom_headers': config.customHeaders,
    };
  }

  Map<String, dynamic> _buildRequestBody({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required bool stream,
    List<AttachedFileData>? files,
  }) {
    final body = <String, dynamic>{
      'model': model,
      'messages': messages.map((m) => m.toJson()).toList(),
      'stream': stream,
      'provider': _buildProviderPayload(),
      'include_reasoning': true,  // 启用 reasoning 输出
    };

    // Add parameters (non-nullable fields, always send non-default values)
    body['temperature'] = parameters.temperature;
    body['max_tokens'] = parameters.maxTokens;
    body['top_p'] = parameters.topP;
    body['frequency_penalty'] = parameters.frequencyPenalty;
    body['presence_penalty'] = parameters.presencePenalty;

    // Gemini 模型特殊处理
    final modelLower = model.toLowerCase();
    if (modelLower.contains('gemini')) {
      body['extra_body'] = {
        'google': {
          'thinking_config': {'include_thoughts': true},
        },
      };
    }

    return body;
  }

  @override
  Future<ProviderTestResult> testConnection() async {
    try {
      final stopwatch = Stopwatch()..start();
      final dio = DioService().dio;

      final response = await dio.get(
        '$_proxyBaseUrl/api/health',
        options: Options(headers: _buildProxyHeaders()),
      );

      stopwatch.stop();

      if (response.statusCode == 200) {
        return ProviderTestResult.success(
          responseTimeMs: stopwatch.elapsedMilliseconds,
        );
      } else {
        return ProviderTestResult.failure('Proxy health check failed');
      }
    } catch (e) {
      return ProviderTestResult.failure('Proxy connection failed: $e');
    }
  }

  @override
  Future<List<String>> listAvailableModels() async {
    try {
      final dio = DioService().dio;

      final response = await dio.post(
        '$_proxyBaseUrl/models',
        data: {'provider': _buildProviderPayload()},
        options: Options(headers: _buildProxyHeaders()),
      );

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final models = data['data'] as List?;
        if (models != null) {
          return models
              .map((m) => (m as Map<String, dynamic>)['id'] as String)
              .toList();
        }
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  @override
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async* {
    final dio = DioService().dio;
    final url = '$_proxyBaseUrl/v1/chat/completions';
    debugPrint('[ROUTE] >>> Python 后端代理 | model=$model | url=$url');

    final body = _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: true,
      files: files,
    );

    final response = await dio.post<ResponseBody>(
      url,
      data: body,
      options: Options(
        headers: _buildProxyHeaders(),
        responseType: ResponseType.stream,
      ),
    );

    final responseStream = response.data!.stream;

    // 思考块状态跟踪（与 OpenAIProvider 保持一致）
    final isGemini = model.toLowerCase().contains('gemini');
    bool geminiReasoningOpen = false;
    bool geminiEmittedBody = false;
    bool reasoningOpen = false;

    await for (final chunk in responseStream
        .cast<List<int>>()
        .transform(utf8.decoder)
        .transform(const LineSplitter())) {
      final line = chunk.trim();
      if (line.isEmpty) continue;

      if (!line.startsWith('data: ')) continue;
      final dataStr = line.substring(6);
      if (dataStr.trim() == '[DONE]') break;

      try {
        final parsed = jsonDecode(dataStr) as Map<String, dynamic>;

        // 检测上游/后端错误响应
        final errorObj = parsed['error'] as Map<String, dynamic>?;
        if (errorObj != null) {
          final errorMsg = errorObj['message'] ?? 'Unknown error';
          final errorType = errorObj['type'] ?? 'error';
          debugPrint('[ERROR_BUBBLE] 检测到上游错误: type=$errorType, msg=$errorMsg');
          throw Exception('[$errorType] $errorMsg');
        }

        final choices = parsed['choices'] as List?;

        if (choices != null && choices.isNotEmpty) {
          final choice = choices[0] as Map<String, dynamic>;
          final delta = choice['delta'] as Map<String, dynamic>?;

          if (delta != null) {
            // 1) 识别 reasoning_content 等思考字段
            for (final key in const ['reasoning', 'reasoning_content', 'internal_thoughts', 'thinking']) {
              final v = delta[key];
              if (v == null) continue;

              final reasoningText = _extractText(v);
              if (reasoningText != null && reasoningText.isNotEmpty) {
                if (!reasoningOpen) {
                  yield '<think>';
                  reasoningOpen = true;
                }
                yield reasoningText;
              }
            }

            // 2) 解析 content
            final contentField = delta['content'];
            if (contentField is String) {
              if (contentField.isNotEmpty) {
                if (reasoningOpen) { yield '</think>'; reasoningOpen = false; }
                yield contentField;
              }
            } else if (contentField is List) {
              if (reasoningOpen && contentField.isNotEmpty) { yield '</think>'; reasoningOpen = false; }
              for (final part in contentField) {
                if (part is Map<String, dynamic>) {
                  final pText = (part['text'] ?? part['content'] ?? '').toString();
                  if (pText.isEmpty) continue;
                  if (_isReasoningType((part['type'] ?? part['role'] ?? '').toString())) {
                    if (!reasoningOpen) { yield '<think>'; reasoningOpen = true; }
                    yield pText;
                  } else {
                    if (reasoningOpen) { yield '</think>'; reasoningOpen = false; }
                    yield pText;
                  }
                } else if (part is String && part.isNotEmpty) {
                  yield part;
                }
              }
            }
          }
        }

        // 3) 兼容 Gemini/OpenRouter 风格：candidates[].content.parts[].text
        final candidates = parsed['candidates'] as List?;
        if (candidates != null && candidates.isNotEmpty) {
          final cand0 = candidates[0] as Map<String, dynamic>;
          final content = cand0['content'] as Map<String, dynamic>?;
          if (content != null) {
            final parts = content['parts'] as List?;
            if (parts != null) {
              for (var i = 0; i < parts.length; i++) {
                final part = parts[i];
                if (part is! Map<String, dynamic>) continue;
                final pText = (part['text'] ?? part['content'] ?? '').toString();
                if (pText.isEmpty) continue;

                if (isGemini) {
                  if (!geminiEmittedBody && i == 0) {
                    if (!geminiReasoningOpen) { yield '<think>'; geminiReasoningOpen = true; }
                    yield pText;
                  } else {
                    if (geminiReasoningOpen) { yield '</think>'; geminiReasoningOpen = false; }
                    geminiEmittedBody = true;
                    yield pText;
                  }
                } else {
                  final pType = (part['type'] ?? part['role'] ?? '').toString();
                  if (_isReasoningType(pType)) {
                    if (!reasoningOpen) { yield '<think>'; reasoningOpen = true; }
                    yield pText;
                  } else {
                    if (reasoningOpen) { yield '</think>'; reasoningOpen = false; }
                    yield pText;
                  }
                }
              }
            } else {
              final cText = (content['text'] ?? '').toString();
              if (cText.isNotEmpty) {
                if (reasoningOpen) { yield '</think>'; reasoningOpen = false; }
                if (isGemini && geminiReasoningOpen) { yield '</think>'; geminiReasoningOpen = false; geminiEmittedBody = true; }
                yield cText;
              }
            }
          } else {
            final cText = (cand0['text'] ?? '').toString();
            if (cText.isNotEmpty) {
              if (reasoningOpen) { yield '</think>'; reasoningOpen = false; }
              if (isGemini && geminiReasoningOpen) { yield '</think>'; geminiReasoningOpen = false; geminiEmittedBody = true; }
              yield cText;
            }
          }
        }
      } catch (e) {
        // 重新抛出检测到的上游错误（格式: [errorType] message）
        final msg = e.toString();
        if (msg.startsWith('Exception: [') && msg.contains('] ')) {
          rethrow;
        }
        // 忽略 JSON 解析错误
        continue;
      }
    }

    // 流结束时补充关闭标签
    if (reasoningOpen) yield '</think>';
    if (isGemini && geminiReasoningOpen) yield '</think>';
  }

  /// 判断类型是否为思考/推理类型
  static bool _isReasoningType(String type) {
    final lower = type.toLowerCase();
    return lower.contains('reason') || lower.contains('think') || lower.contains('thought');
  }

  /// 从不同格式中提取文本
  static String? _extractText(dynamic v) {
    if (v is String) return v;
    if (v is Map<String, dynamic>) return (v['content'] ?? v['text']) as String?;
    if (v is List) {
      return v.map((e) {
        if (e is String) return e;
        if (e is Map<String, dynamic>) return (e['content'] ?? e['text'] ?? '').toString();
        return '';
      }).where((s) => s.isNotEmpty).join('');
    }
    return null;
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async {
    final dio = DioService().dio;
    final url = '$_proxyBaseUrl/v1/chat/completions';

    final body = _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: false,
      files: files,
    );

    final response = await dio.post(
      url,
      data: body,
      options: Options(headers: _buildProxyHeaders()),
    );

    if (response.statusCode == 200) {
      final data = response.data as Map<String, dynamic>;
      final choices = data['choices'] as List?;

      if (choices != null && choices.isNotEmpty) {
        final message =
            (choices[0] as Map<String, dynamic>)['message'] as Map<String, dynamic>?;
        if (message != null) {
          return message['content'] as String? ?? '';
        }
      }
    }

    throw Exception('Invalid response from proxy');
  }
}
