import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/backend_provider_registry_service.dart';
import '../services/dio_service.dart';
import 'ai_provider.dart';

/// Provider that routes requests through Python backend proxy.
///
/// This provider sends requests to the local Python backend instead of
/// directly to LLM APIs. The backend handles the actual API calls.
class ProxyOpenAIProvider extends AIProvider {
  static const String defaultProxyUrl = 'http://localhost:8765';
  static final Map<String, String> _providerRegistrySyncVersions = {};
  static bool _preferTypedStreamEvents = true;
  CancelToken? _currentCancelToken;
  bool _backendToolLoopEnabled = false;

  ProxyOpenAIProvider(super.config);

  void setBackendToolLoopEnabled(bool enabled) {
    _backendToolLoopEnabled = enabled;
  }

  String get _proxyBaseUrl => config.proxyApiUrl ?? defaultProxyUrl;

  Map<String, String> _buildProxyHeaders() {
    final headers = <String, String>{'Content-Type': 'application/json'};
    // Add proxy-specific headers if configured
    if (config.proxyHeaders != null) {
      headers.addAll(config.proxyHeaders!.cast<String, String>());
    }
    return headers;
  }

  @visibleForTesting
  static void debugResetProviderRegistrySyncCache() {
    _providerRegistrySyncVersions.clear();
  }

  @visibleForTesting
  static void debugSetPreferTypedStreamEvents(bool value) {
    _preferTypedStreamEvents = value;
  }

  String get _providerRegistryVersion => config.updatedAt.toIso8601String();

  bool get _providerRegistryNeedsSync =>
      _providerRegistrySyncVersions[config.id] != _providerRegistryVersion;

  Future<void> _ensureProviderRegistered() async {
    if (config.apiKey.trim().isEmpty) {
      return;
    }
    if (!_providerRegistryNeedsSync) {
      return;
    }

    await BackendProviderRegistryService().upsertProvider(config);
    _providerRegistrySyncVersions[config.id] = _providerRegistryVersion;
  }

  List<Map<String, dynamic>> _buildFilesPayload(List<AttachedFileData> files) {
    return files
        .map(
          (file) => {
            'name': file.name,
            'mime_type': file.mimeType,
            if (file.bytes != null) 'data': base64Encode(file.bytes!),
            if (file.path.isNotEmpty) 'path': file.path,
          },
        )
        .toList();
  }

  Map<String, dynamic> _buildRequestBody({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required bool stream,
    List<AttachedFileData>? files,
    String? modelId,
  }) {
    final body = <String, dynamic>{
      'model': model,
      if (modelId != null) 'model_id': modelId,
      'messages': messages.map((m) => m.toJson()).toList(),
      'stream': stream,
      'provider_id': config.id,
      'include_reasoning': true, // 启用 reasoning 输出
      if (stream && _preferTypedStreamEvents) 'stream_event_mode': 'typed',
      if (_backendToolLoopEnabled) 'enable_tools': true,
      if (files != null && files.isNotEmpty) 'files': _buildFilesPayload(files),
    };

    // Add parameters (non-nullable fields, always send non-default values)
    body['temperature'] = parameters.temperature;
    body['max_tokens'] = parameters.maxTokens;
    body['top_p'] = parameters.topP;
    body['frequency_penalty'] = parameters.frequencyPenalty;
    body['presence_penalty'] = parameters.presencePenalty;

    // Gemini 模型特殊处理
    if (config.type == ProviderType.gemini) {
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
      final dio = DioService().controlPlaneDio;

      final response = await dio.get(
        '$_proxyBaseUrl/models',
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
      await _ensureProviderRegistered();
      final dio = DioService().dataPlaneDio;

      for (final path in const ['/models', '/v1/models']) {
        final response = await dio.post(
          '$_proxyBaseUrl$path',
          data: {'provider_id': config.id},
          options: Options(headers: _buildProxyHeaders()),
        );

        if (response.statusCode == 404) {
          continue;
        }

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
    String? modelId,
  }) async* {
    final parser = ProxyStreamChunkParser(
      isGeminiModel: model.toLowerCase().contains('gemini'),
    );

    await for (final parsed in _streamParsedPayloads(
      model: model,
      messages: messages,
      parameters: parameters,
      files: files,
      modelId: modelId,
      debugLabel: 'Python 后端代理',
    )) {
      for (final content in parser.parse(parsed)) {
        yield content;
      }
    }

    for (final content in parser.flush()) {
      yield content;
    }
  }

  @override
  Stream<AIStreamEvent> sendMessageEventStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    final parser = ProxyStreamChunkParser(
      isGeminiModel: model.toLowerCase().contains('gemini'),
    );

    await for (final parsed in _streamParsedPayloads(
      model: model,
      messages: messages,
      parameters: parameters,
      files: files,
      modelId: modelId,
      debugLabel: 'Python 后端代理(event)',
    )) {
      for (final event in parser.parseEvents(parsed)) {
        yield event;
      }
    }

    for (final event in parser.flushEvents()) {
      yield event;
    }
  }

  Stream<Map<String, dynamic>> _streamParsedPayloads({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required String debugLabel,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    await _ensureProviderRegistered();
    final dio = DioService().dataPlaneDio;
    final url = '$_proxyBaseUrl/v1/chat/completions';
    _currentCancelToken?.cancel('新请求开始');
    _currentCancelToken = DioService().createCancelToken();
    debugPrint('[ROUTE] >>> $debugLabel | model=$model | url=$url');

    final body = _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: true,
      files: files,
      modelId: modelId,
    );

    final response = await dio.post<ResponseBody>(
      url,
      data: body,
      cancelToken: _currentCancelToken,
      options: Options(
        headers: _buildProxyHeaders(),
        responseType: ResponseType.stream,
      ),
    );

    final statusCode = response.statusCode ?? 0;
    if (statusCode < 200 || statusCode >= 300) {
      final errorBody = await response.data!.stream
          .cast<List<int>>()
          .transform(utf8.decoder)
          .join();
      throw Exception('Backend returned HTTP $statusCode: $errorBody');
    }

    final responseStream = response.data!.stream;
    await for (final chunk
        in responseStream
            .cast<List<int>>()
            .transform(utf8.decoder)
            .transform(const LineSplitter())) {
      final parsed = _tryParseStreamingPayload(chunk);
      if (parsed != null) {
        yield parsed;
      }
    }
  }

  Map<String, dynamic>? _tryParseStreamingPayload(String rawChunk) {
    final line = rawChunk.trim();
    if (line.isEmpty) return null;
    if (!line.startsWith('data: ')) return null;

    final dataStr = line.substring(6);
    if (dataStr.trim() == '[DONE]') return null;

    try {
      final parsed = jsonDecode(dataStr) as Map<String, dynamic>;
      final errorObj = parsed['error'] as Map<String, dynamic>?;
      if (errorObj != null) {
        final errorMsg = errorObj['message'] ?? 'Unknown error';
        final errorType = errorObj['type'] ?? 'error';
        throw Exception('[$errorType] $errorMsg');
      }
      return parsed;
    } catch (e) {
      final msg = e.toString();
      if (msg.startsWith('Exception: [') && msg.contains('] ')) {
        rethrow;
      }
      return null;
    }
  }

  /// 判断类型是否为思考/推理类型
  static bool _isReasoningType(String type) {
    final lower = type.toLowerCase();
    return lower.contains('reason') ||
        lower.contains('think') ||
        lower.contains('thought');
  }

  /// 从不同格式中提取文本
  static String? _extractText(dynamic v) {
    if (v is String) {
      return v;
    }
    if (v is Map<String, dynamic>) {
      return (v['content'] ?? v['text']) as String?;
    }
    if (v is List) {
      return v
          .map((e) {
            if (e is String) {
              return e;
            }
            if (e is Map<String, dynamic>) {
              return (e['content'] ?? e['text'] ?? '').toString();
            }
            return '';
          })
          .where((s) => s.isNotEmpty)
          .join('');
    }
    return null;
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async {
    await _ensureProviderRegistered();
    final dio = DioService().dataPlaneDio;
    final url = '$_proxyBaseUrl/v1/chat/completions';
    _currentCancelToken?.cancel('新请求开始');
    _currentCancelToken = DioService().createCancelToken();

    final body = _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: false,
      files: files,
      modelId: modelId,
    );

    final response = await dio.post(
      url,
      data: body,
      cancelToken: _currentCancelToken,
      options: Options(headers: _buildProxyHeaders()),
    );

    if (response.statusCode == 200) {
      final data = response.data as Map<String, dynamic>;
      final choices = data['choices'] as List?;

      if (choices != null && choices.isNotEmpty) {
        final message =
            (choices[0] as Map<String, dynamic>)['message']
                as Map<String, dynamic>?;
        if (message != null) {
          return message['content'] as String? ?? '';
        }
      }
    }

    throw Exception('Invalid response from proxy');
  }

  /// 取消当前请求
  /// 用于用户点击停止按钮时真正中断 proxy 网络请求
  void cancelRequest() {
    if (_currentCancelToken != null && !_currentCancelToken!.isCancelled) {
      _currentCancelToken!.cancel('用户取消');
      if (kDebugMode) {
        debugPrint('✅ [ProxyOpenAIProvider] 请求已取消');
      }
    }
  }
}

/// Consumes backend proxy SSE payloads.
///
/// Primary path: trust backend-normalized `choices[].delta.content`.
/// Compatibility path: retain legacy provider-specific extraction for older
/// backend builds that may still emit raw reasoning/candidates payloads.
class ProxyStreamChunkParser {
  final bool isGeminiModel;

  bool _legacyGeminiReasoningOpen = false;
  bool _legacyGeminiEmittedBody = false;
  bool _legacyReasoningOpen = false;
  bool _typedThinkingOpen = false;

  ProxyStreamChunkParser({required this.isGeminiModel});

  Iterable<String> parse(Map<String, dynamic> parsed) sync* {
    final typedPayload = _extractTypedPayload(parsed);
    if (typedPayload != null) {
      yield* typedPayload.legacyChunks;
      return;
    }

    if (_shouldUseLegacyPath(parsed)) {
      yield* _extractLegacyContent(parsed);
    } else {
      final normalizedChunks = _extractNormalizedContent(parsed);
      if (normalizedChunks.isNotEmpty) {
        yield* normalizedChunks;
        return;
      }

      yield* _extractLegacyContent(parsed);
    }
  }

  Iterable<String> flush() sync* {
    yield* _flushLegacyChunks();
  }

  Iterable<AIStreamEvent> parseEvents(Map<String, dynamic> parsed) sync* {
    final typedPayload = _extractTypedPayload(parsed);
    if (typedPayload != null) {
      yield* typedPayload.events;
      return;
    }

    for (final chunk in parse(parsed)) {
      yield AIStreamEvent.text(chunk, isTypedSemantic: false);
    }
  }

  Iterable<AIStreamEvent> flushEvents() sync* {
    for (final chunk in _flushLegacyChunks()) {
      yield AIStreamEvent.text(chunk, isTypedSemantic: false);
    }
  }

  _TypedPayloadParseResult? _extractTypedPayload(Map<String, dynamic> parsed) {
    final type = parsed['type'];
    if (type is! String || type.isEmpty) {
      return null;
    }

    switch (type) {
      case 'thinking_delta':
        final delta = parsed['delta']?.toString() ?? '';
        if (delta.isNotEmpty) {
          final outputs = <String>[];
          if (!_typedThinkingOpen) {
            outputs.add('<think>');
            _typedThinkingOpen = true;
          }
          outputs.add(delta);
          return _TypedPayloadParseResult(
            legacyChunks: outputs,
            events: [AIStreamEvent.thinking(delta)],
          );
        }
        return _TypedPayloadParseResult.empty();
      case 'text_delta':
        final delta = parsed['delta']?.toString() ?? '';
        if (delta.isNotEmpty) {
          final outputs = <String>[];
          if (_typedThinkingOpen) {
            outputs.add('</think>');
            _typedThinkingOpen = false;
          }
          outputs.add(delta);
          return _TypedPayloadParseResult(
            legacyChunks: outputs,
            events: [AIStreamEvent.text(delta, isTypedSemantic: true)],
          );
        }
        return _TypedPayloadParseResult.empty();
      case 'tool_call':
        final rawToolCalls = parsed['tool_calls'] as List?;
        final toolCalls = rawToolCalls
            ?.whereType<Map>()
            .map((call) => Map<String, dynamic>.from(call))
            .toList();
        return _TypedPayloadParseResult(
          legacyChunks: _closeTypedThinkingIfNeeded(),
          events: (toolCalls != null && toolCalls.isNotEmpty)
              ? [AIStreamEvent.toolCall(toolCalls)]
              : const [],
        );
      case 'tool_started':
        final callId = parsed['call_id']?.toString() ?? '';
        if (callId.isEmpty) return _TypedPayloadParseResult.empty();
        return _TypedPayloadParseResult(
          legacyChunks: _closeTypedThinkingIfNeeded(),
          events: [
            AIStreamEvent.toolStarted(
              callId: callId,
              toolName: parsed['tool_name']?.toString(),
            ),
          ],
        );
      case 'tool_result':
        final callId = parsed['call_id']?.toString() ?? '';
        if (callId.isEmpty) return _TypedPayloadParseResult.empty();
        return _TypedPayloadParseResult(
          legacyChunks: _closeTypedThinkingIfNeeded(),
          events: [
            AIStreamEvent.toolResult(
              callId: callId,
              toolName: parsed['tool_name']?.toString(),
              result: parsed['result']?.toString() ?? '',
            ),
          ],
        );
      case 'tool_error':
        final callId = parsed['call_id']?.toString() ?? '';
        if (callId.isEmpty) return _TypedPayloadParseResult.empty();
        return _TypedPayloadParseResult(
          legacyChunks: _closeTypedThinkingIfNeeded(),
          events: [
            AIStreamEvent.toolError(
              callId: callId,
              toolName: parsed['tool_name']?.toString(),
              errorMessage: parsed['error']?.toString() ?? 'Unknown tool error',
            ),
          ],
        );
      case 'usage':
        final promptTokens = (parsed['prompt_tokens'] as num?)?.toInt() ?? 0;
        final completionTokens =
            (parsed['completion_tokens'] as num?)?.toInt() ?? 0;
        final totalTokens = (parsed['total_tokens'] as num?)?.toInt() ?? 0;
        return _TypedPayloadParseResult(
          legacyChunks: const [],
          events: [
            AIStreamEvent.usage(
              promptTokens: promptTokens,
              completionTokens: completionTokens,
              totalTokens: totalTokens,
            ),
          ],
        );
      case 'done':
      case 'raw':
      case 'error':
        return _TypedPayloadParseResult.empty();
      default:
        return null;
    }
  }

  List<String> _closeTypedThinkingIfNeeded() {
    if (_typedThinkingOpen) {
      _typedThinkingOpen = false;
      return const ['</think>'];
    }
    return const [];
  }

  Iterable<String> _flushLegacyChunks() sync* {
    if (_typedThinkingOpen) {
      _typedThinkingOpen = false;
      yield '</think>';
    }
    if (_legacyReasoningOpen) {
      _legacyReasoningOpen = false;
      yield '</think>';
    }
    if (isGeminiModel && _legacyGeminiReasoningOpen) {
      _legacyGeminiReasoningOpen = false;
      yield '</think>';
    }
  }

  bool _shouldUseLegacyPath(Map<String, dynamic> parsed) {
    if (_legacyReasoningOpen || _legacyGeminiReasoningOpen) {
      return true;
    }

    if (parsed['candidates'] is List) {
      return true;
    }

    final choices = parsed['choices'] as List?;
    if (choices == null || choices.isEmpty) {
      return false;
    }

    final choice = choices[0];
    if (choice is! Map<String, dynamic>) return false;

    final delta = choice['delta'];
    if (delta is! Map<String, dynamic>) return false;

    for (final key in const [
      'reasoning',
      'reasoning_content',
      'internal_thoughts',
      'thinking',
    ]) {
      if (delta[key] != null) {
        return true;
      }
    }

    final content = delta['content'];
    if (content is List) {
      for (final part in content) {
        if (part is! Map<String, dynamic>) continue;
        final type = (part['type'] ?? part['role'] ?? '').toString();
        if (ProxyOpenAIProvider._isReasoningType(type)) {
          return true;
        }
      }
    }

    return false;
  }

  List<String> _extractNormalizedContent(Map<String, dynamic> parsed) {
    final choices = parsed['choices'] as List?;
    if (choices == null || choices.isEmpty) return const [];

    final choice = choices[0];
    if (choice is! Map<String, dynamic>) return const [];

    final delta = choice['delta'];
    if (delta is! Map<String, dynamic> || !delta.containsKey('content')) {
      return const [];
    }

    final content = delta['content'];
    if (content is String) {
      return content.isEmpty ? const [] : [content];
    }

    if (content is List) {
      final contents = <String>[];
      for (final part in content) {
        if (part is String && part.isNotEmpty) {
          contents.add(part);
        } else if (part is Map<String, dynamic>) {
          final text = (part['text'] ?? part['content'] ?? '').toString();
          if (text.isNotEmpty) {
            contents.add(text);
          }
        }
      }
      return contents;
    }

    return const [];
  }

  Iterable<String> _extractLegacyContent(Map<String, dynamic> parsed) sync* {
    final choices = parsed['choices'] as List?;
    if (choices != null && choices.isNotEmpty) {
      final choice = choices[0] as Map<String, dynamic>;
      final delta = choice['delta'] as Map<String, dynamic>?;

      if (delta != null) {
        for (final key in const [
          'reasoning',
          'reasoning_content',
          'internal_thoughts',
          'thinking',
        ]) {
          final value = delta[key];
          if (value == null) continue;

          final reasoningText = ProxyOpenAIProvider._extractText(value);
          if (reasoningText != null && reasoningText.isNotEmpty) {
            if (!_legacyReasoningOpen) {
              yield '<think>';
              _legacyReasoningOpen = true;
            }
            yield reasoningText;
          }
        }

        final contentField = delta['content'];
        if (contentField is String) {
          if (contentField.isNotEmpty) {
            if (_legacyReasoningOpen) {
              yield '</think>';
              _legacyReasoningOpen = false;
            }
            yield contentField;
          }
        } else if (contentField is List) {
          if (_legacyReasoningOpen && contentField.isNotEmpty) {
            yield '</think>';
            _legacyReasoningOpen = false;
          }

          for (final part in contentField) {
            if (part is Map<String, dynamic>) {
              final text = (part['text'] ?? part['content'] ?? '').toString();
              if (text.isEmpty) continue;

              if (ProxyOpenAIProvider._isReasoningType(
                (part['type'] ?? part['role'] ?? '').toString(),
              )) {
                if (!_legacyReasoningOpen) {
                  yield '<think>';
                  _legacyReasoningOpen = true;
                }
                yield text;
              } else {
                if (_legacyReasoningOpen) {
                  yield '</think>';
                  _legacyReasoningOpen = false;
                }
                yield text;
              }
            } else if (part is String && part.isNotEmpty) {
              yield part;
            }
          }
        }
      }
    }

    final candidates = parsed['candidates'] as List?;
    if (candidates == null || candidates.isEmpty) return;

    final candidate = candidates[0];
    if (candidate is! Map<String, dynamic>) return;

    final content = candidate['content'] as Map<String, dynamic>?;
    if (content != null) {
      final parts = content['parts'] as List?;
      if (parts != null) {
        for (var i = 0; i < parts.length; i++) {
          final part = parts[i];
          if (part is! Map<String, dynamic>) continue;

          final text = (part['text'] ?? part['content'] ?? '').toString();
          if (text.isEmpty) continue;

          if (isGeminiModel) {
            if (!_legacyGeminiEmittedBody && i == 0) {
              if (!_legacyGeminiReasoningOpen) {
                yield '<think>';
                _legacyGeminiReasoningOpen = true;
              }
              yield text;
            } else {
              if (_legacyGeminiReasoningOpen) {
                yield '</think>';
                _legacyGeminiReasoningOpen = false;
              }
              _legacyGeminiEmittedBody = true;
              yield text;
            }
          } else {
            final partType = (part['type'] ?? part['role'] ?? '').toString();
            if (ProxyOpenAIProvider._isReasoningType(partType)) {
              if (!_legacyReasoningOpen) {
                yield '<think>';
                _legacyReasoningOpen = true;
              }
              yield text;
            } else {
              if (_legacyReasoningOpen) {
                yield '</think>';
                _legacyReasoningOpen = false;
              }
              yield text;
            }
          }
        }
      } else {
        final text = (content['text'] ?? '').toString();
        if (text.isNotEmpty) {
          if (_legacyReasoningOpen) {
            yield '</think>';
            _legacyReasoningOpen = false;
          }
          if (isGeminiModel && _legacyGeminiReasoningOpen) {
            yield '</think>';
            _legacyGeminiReasoningOpen = false;
            _legacyGeminiEmittedBody = true;
          }
          yield text;
        }
      }
      return;
    }

    final candidateText = (candidate['text'] ?? '').toString();
    if (candidateText.isNotEmpty) {
      if (_legacyReasoningOpen) {
        yield '</think>';
        _legacyReasoningOpen = false;
      }
      if (isGeminiModel && _legacyGeminiReasoningOpen) {
        yield '</think>';
        _legacyGeminiReasoningOpen = false;
        _legacyGeminiEmittedBody = true;
      }
      yield candidateText;
    }
  }
}

class _TypedPayloadParseResult {
  final List<String> legacyChunks;
  final List<AIStreamEvent> events;

  const _TypedPayloadParseResult({
    required this.legacyChunks,
    required this.events,
  });

  factory _TypedPayloadParseResult.empty() {
    return const _TypedPayloadParseResult(legacyChunks: [], events: []);
  }
}
