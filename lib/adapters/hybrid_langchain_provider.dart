import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:dio/dio.dart';
import 'package:path/path.dart' as path;

import 'ai_provider.dart';
import 'mcp_tool_adapter.dart';
import 'sse/sse_parser.dart';
import 'sse/thinking_extractor.dart';
import 'sse/gemini_parser.dart';
import 'sse/tool_call_extractor.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../models/api_error.dart';
import '../models/mcp/mcp_tool_call.dart';
import '../services/file_content_service.dart';
import '../services/dio_service.dart';

/// 混合 LangChain Provider
/// - 消息转换: LangChainMessageMapper
/// - HTTP 请求: Dio (带 CancelToken)
/// - SSE 解析: SseParser + ThinkingExtractor
/// - MCP 工具调用: McpToolAdapter + ToolCallExtractor
class HybridLangChainProvider extends AIProvider {
  final _dio = DioService().dataPlaneDio;
  CancelToken? _cancelToken;

  /// MCP 工具适配器（可选）
  McpToolAdapter? _mcpAdapter;

  /// 当前模型是否支持工具调用
  /// 需要在调用 sendMessageStream 前设置
  bool modelSupportsTools = false;

  /// 工具调用事件回调
  void Function(ToolCallEvent)? onToolCallEvent;

  /// 工具调用数据回调（用于 UI 更新）
  void Function(ToolCallData)? onToolCallData;

  HybridLangChainProvider(super.config);

  /// 设置 MCP 工具适配器
  /// [adapter] MCP 适配器实例
  /// [supportsTools] 当前模型是否支持工具调用（基于 ModelCapability.tool）
  void setMcpAdapter(McpToolAdapter? adapter, {bool supportsTools = false}) {
    _mcpAdapter = adapter;
    modelSupportsTools = supportsTools;
  }

  /// 检查是否启用了 MCP 工具（适配器存在且模型支持）
  bool get hasMcpTools => _mcpAdapter != null && modelSupportsTools;

  @override
  Map<String, String> buildHeaders() {
    return {
      ...super.buildHeaders(),
      'Authorization': 'Bearer ${config.apiKey}',
    };
  }

  @override
  Future<ProviderTestResult> testConnection() async {
    try {
      final stopwatch = Stopwatch()..start();
      final baseUrl = config.actualApiUrl
          .replaceAll('/chat/completions', '')
          .replaceAll('/messages', '');

      final response = await _dio.get(
        '$baseUrl/models',
        options: Options(
          headers: buildHeaders(),
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
      final baseUrl = config.actualApiUrl
          .replaceAll('/chat/completions', '')
          .replaceAll('/messages', '');

      final response = await _dio.get(
        '$baseUrl/models',
        options: Options(headers: buildHeaders()),
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
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async* {
    _cancelToken?.cancel('新请求开始');
    _cancelToken = DioService().createCancelToken();
    debugPrint(
      '[ROUTE] >>> HybridLangChain | model=$model | url=${config.actualApiUrl}',
    );

    // 工具调用循环：最多执行 5 轮工具调用
    const maxToolRounds = 5;
    var currentMessages = List<ChatMessage>.from(messages);
    var toolRound = 0;

    while (toolRound < maxToolRounds) {
      final requestBody = await _buildRequestBody(
        model: model,
        messages: currentMessages,
        parameters: parameters,
        stream: true,
        files: toolRound == 0 ? files : null, // 只在第一轮发送文件
      );

      if (toolRound == 0) {
        _debugPrintRequest(config.actualApiUrl, requestBody);
      }

      try {
        final response = await _dio.post(
          config.actualApiUrl,
          data: requestBody,
          options: Options(
            headers: buildHeaders(),
            responseType: ResponseType.stream,
          ),
          cancelToken: _cancelToken,
        );

        if (response.statusCode != 200) {
          final responseBody = response.data.toString();
          throw ApiErrorParser.parseFromResponse(
            statusCode: response.statusCode!,
            responseBody: responseBody,
          );
        }

        // 使用 SseParser 解析流
        final responseStream = (response.data as ResponseBody).stream;
        final sseStream = SseParser.parse(responseStream.cast<List<int>>());

        // 根据 provider 类型选择解析器
        final isGemini = config.type == ProviderType.gemini;
        final thinkingExtractor = ThinkingExtractor();
        final geminiParser = GeminiParser();
        final toolCallExtractor = ToolCallExtractor();

        var hasToolCalls = false;
        final assistantContent = StringBuffer();

        // 工具调用轮次中，只在第一轮输出 thinking 内容
        final shouldYieldThinking = toolRound == 0;

        await for (final event in sseStream) {
          switch (event) {
            case SseDataEvent(:final data):
              // 处理 choices 格式
              final choices = data['choices'] as List?;
              if (choices != null && choices.isNotEmpty) {
                final choice = choices[0] as Map<String, dynamic>;
                final delta = choice['delta'] as Map<String, dynamic>?;
                final finishReason = ToolCallExtractor.extractFinishReason(
                  choice,
                );

                if (delta != null) {
                  // 提取工具调用
                  final toolEvents = toolCallExtractor.extract(delta);
                  for (final te in toolEvents) {
                    onToolCallEvent?.call(te);
                    // 工具调用开始时，创建 ToolCallData 通知 UI
                    if (te is ToolCallStarted) {
                      final toolCallData = ToolCallData(
                        callId: te.callId,
                        toolName: te.name,
                        status: ToolCallStatus.pending,
                      );
                      onToolCallData?.call(toolCallData);
                    }
                  }

                  // 提取文本内容
                  // 工具调用后续轮次中，只输出正文，跳过 thinking 内容（避免重复）
                  if (shouldYieldThinking) {
                    for (final chunk in thinkingExtractor.extract(delta)) {
                      yield chunk;
                      assistantContent.write(chunk);
                    }
                  } else {
                    // 后续轮次：只提取正文内容，跳过 thinking
                    final contentField = delta['content'];
                    if (contentField is String && contentField.isNotEmpty) {
                      yield contentField;
                      assistantContent.write(contentField);
                    }
                  }
                }

                // 检查是否需要执行工具调用
                if (ToolCallExtractor.isToolCallFinish(finishReason)) {
                  hasToolCalls = true;
                  final completedCalls = toolCallExtractor.finalize();

                  // 执行工具调用并收集结果
                  final toolResults = await _executeToolCallsAndCollect(
                    completedCalls,
                  );

                  // 添加 assistant 消息（包含 tool_calls）
                  currentMessages.add(
                    ChatMessage(
                      role: 'assistant',
                      content: assistantContent.toString(),
                      toolCalls: completedCalls
                          .map(
                            (c) => {
                              'id': c.callId,
                              'type': 'function',
                              'function': {
                                'name': c.name,
                                'arguments': jsonEncode(c.arguments),
                              },
                            },
                          )
                          .toList(),
                    ),
                  );

                  // 添加 tool 结果消息
                  for (final result in toolResults) {
                    currentMessages.add(
                      ChatMessage(
                        role: 'tool',
                        content: result.content,
                        toolCallId: result.callId,
                      ),
                    );
                  }
                }
              }

              // 处理 candidates 格式 (Gemini)
              final candidates = data['candidates'] as List?;
              if (candidates != null && candidates.isNotEmpty) {
                for (final chunk in geminiParser.extractFromCandidates(
                  candidates,
                  isGemini: isGemini,
                )) {
                  yield chunk;
                  assistantContent.write(chunk);
                }
              }

            case SseErrorEvent(:final type, :final message, :final code):
              throw ApiError(
                statusCode: 200, // SSE 内错误，HTTP 层返回 200
                message: message,
                errorCode: code ?? type,
              );

            case SseDoneEvent():
              break;
          }
        }

        // 关闭 thinking 标签
        final thinkingClosing = thinkingExtractor.getClosingTag();
        if (thinkingClosing != null) yield thinkingClosing;

        final geminiClosing = geminiParser.getClosingTag();
        if (geminiClosing != null) yield geminiClosing;

        // 如果没有工具调用，结束循环
        if (!hasToolCalls) {
          break;
        }

        toolRound++;
        if (kDebugMode) {
          debugPrint('[MCP] Tool round $toolRound completed, continuing...');
          debugPrint('[MCP] Messages count: ${currentMessages.length}');
          // 打印最后两条消息（assistant + tool）
          for (
            var i = currentMessages.length - 2;
            i < currentMessages.length;
            i++
          ) {
            if (i >= 0) {
              final msg = currentMessages[i];
              final preview = msg.content.length > 200
                  ? '${msg.content.substring(0, 200)}...'
                  : msg.content;
              debugPrint(
                '[MCP] Message[$i] role=${msg.role}, toolCallId=${msg.toolCallId}, content=$preview',
              );
            }
          }
        }
      } on DioException catch (e) {
        if (e.type == DioExceptionType.cancel) {
          throw ApiError(
            statusCode: 0,
            message: '请求已取消',
            errorCode: 'cancelled',
          );
        }
        if (e.response != null) {
          // 尝试读取响应体（处理流式响应的情况）
          final responseBody = await _extractResponseBody(e.response!.data);
          throw ApiErrorParser.parseFromResponse(
            statusCode: e.response!.statusCode ?? 500,
            responseBody: responseBody,
          );
        }
        throw ApiError(
          statusCode: 0,
          message: e.message ?? '网络错误',
          errorCode: 'network_error',
        );
      } on ApiError {
        rethrow;
      } catch (e) {
        throw ApiError(
          statusCode: 0,
          message: e.toString(),
          errorCode: 'unknown',
        );
      }
    }

    _cancelToken = null;
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    String? modelId,
  }) async {
    final requestBody = await _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: false,
      files: files,
    );

    _debugPrintRequest(config.actualApiUrl, requestBody);

    try {
      final response = await _dio.post(
        config.actualApiUrl,
        data: requestBody,
        options: Options(headers: buildHeaders()),
      );

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final choices = data['choices'] as List?;
        if (choices != null && choices.isNotEmpty) {
          final message = choices[0]['message'] as Map<String, dynamic>?;
          return message?['content'] as String? ?? '';
        }
        return '';
      } else {
        throw ApiErrorParser.parseFromResponse(
          statusCode: response.statusCode!,
          responseBody: response.data.toString(),
        );
      }
    } on DioException catch (e) {
      if (e.response != null) {
        throw ApiErrorParser.parseFromResponse(
          statusCode: e.response!.statusCode!,
          responseBody: e.response!.data.toString(),
        );
      } else {
        throw ApiError(
          statusCode: 0,
          message: e.message ?? '网络错误',
          errorCode: 'network_error',
        );
      }
    } on ApiError {
      rethrow;
    } catch (e) {
      throw ApiError(
        statusCode: 0,
        message: e.toString(),
        errorCode: 'unknown',
      );
    }
  }

  /// 取消当前请求
  void cancelRequest() {
    if (_cancelToken != null && !_cancelToken!.isCancelled) {
      _cancelToken!.cancel('用户取消');
      if (kDebugMode) {
        debugPrint('✅ [HybridLangChainProvider] 请求已取消');
      }
    }
  }

  /// 构建请求体
  Future<Map<String, dynamic>> _buildRequestBody({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required bool stream,
    List<AttachedFileData>? files,
  }) async {
    final body = <String, dynamic>{
      'model': model,
      'messages': await _convertMessages(messages, files),
      'stream': stream,
      'include_reasoning': true,
    };

    // Gemini 模型特殊处理
    final modelLower = model.toLowerCase();
    if (modelLower.contains('gemini')) {
      body['extra_body'] = {
        'google': {
          'thinking_config': {'include_thoughts': true},
        },
      };
    }

    // 添加 MCP 工具定义（仅当模型支持工具时）
    if (hasMcpTools) {
      final tools = _mcpAdapter!.getToolDefinitions();
      if (tools.isNotEmpty) {
        body['tools'] = tools;
      }
    }

    // 根据 Provider 类型添加参数
    switch (config.type) {
      case ProviderType.openai:
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        _addIfNotDefault(body, 'top_p', parameters.topP, 1.0);
        _addIfNotDefault(
          body,
          'frequency_penalty',
          parameters.frequencyPenalty,
          0.0,
        );
        _addIfNotDefault(
          body,
          'presence_penalty',
          parameters.presencePenalty,
          0.0,
        );
        break;

      case ProviderType.deepseek:
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        _addIfNotDefault(body, 'top_p', parameters.topP, 1.0);
        break;

      case ProviderType.gemini:
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        break;

      case ProviderType.claude:
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        _addIfNotDefault(body, 'top_p', parameters.topP, 1.0);
        break;
    }

    return body;
  }

  void _addIfNotDefault(
    Map<String, dynamic> body,
    String key,
    double value,
    double defaultValue,
  ) {
    if (value != defaultValue) {
      body[key] = value;
    }
  }

  void _addIfNotNull(Map<String, dynamic> body, String key, int? value) {
    if (value != null && value > 0) {
      body[key] = value;
    }
  }

  /// 转换消息格式
  Future<List<Map<String, dynamic>>> _convertMessages(
    List<ChatMessage> messages,
    List<AttachedFileData>? files,
  ) async {
    final converted = messages.map((msg) => msg.toJson()).toList();

    // 过滤空 system 消息
    converted.removeWhere(
      (msg) =>
          msg['role'] == 'system' &&
          (msg['content'] == null || (msg['content'] as String).trim().isEmpty),
    );

    // 处理附件
    if (files != null && files.isNotEmpty && converted.isNotEmpty) {
      final lastMessage = converted.last;
      if (lastMessage['role'] == 'user') {
        final content = <Map<String, dynamic>>[];
        final documentContents = <String>[];
        final imageContents = <Map<String, dynamic>>[];

        for (var file in files) {
          final fileName = path.basename(file.path);
          final extension = path.extension(file.path);

          if (file.mimeType.startsWith('image/')) {
            final imageData = _readFileAsBase64(file.path);
            imageContents.add({
              'type': 'image_url',
              'image_url': {'url': 'data:${file.mimeType};base64,$imageData'},
            });
          } else if (FileContentService.isTextProcessable(
            file.mimeType,
            extension,
          )) {
            try {
              final textContent = await FileContentService.extractTextContent(
                File(file.path),
                file.mimeType,
              );
              documentContents.add(
                FileContentService.generateFilePrompt(
                  fileName,
                  file.mimeType,
                  textContent,
                ),
              );
            } catch (e) {
              documentContents.add('// 文件 $fileName 处理失败: ${e.toString()}');
            }
          } else {
            documentContents.add('// 文件 $fileName (${file.mimeType}) 暂不支持内容提取');
          }
        }

        String textContent = lastMessage['content'] as String? ?? '';
        if (documentContents.isNotEmpty) {
          textContent =
              '${documentContents.join('\n\n')}\n\n---\n\n$textContent';
        }

        content.add({'type': 'text', 'text': textContent});
        content.addAll(imageContents);
        lastMessage['content'] = content;
      }
    }

    return converted;
  }

  String _readFileAsBase64(String filePath) {
    try {
      final file = File(filePath);
      final bytes = file.readAsBytesSync();
      return base64Encode(bytes);
    } catch (e) {
      return '';
    }
  }

  /// 从响应中提取响应体字符串（处理流式和非流式响应）
  Future<String> _extractResponseBody(dynamic data) async {
    if (data == null) return '';
    if (data is String) return data;
    if (data is Map || data is List) {
      try {
        return jsonEncode(data);
      } catch (_) {
        return data.toString();
      }
    }
    if (data is ResponseBody) {
      try {
        final bytes = await data.stream.fold<List<int>>(
          [],
          (prev, chunk) => prev..addAll(chunk),
        );
        return utf8.decode(bytes);
      } catch (_) {
        return '';
      }
    }
    return data.toString();
  }

  void _debugPrintRequest(String url, Map<String, dynamic> requestBody) {
    if (!kDebugMode) return;

    debugPrint(
      '\n╔═══════════════════════════════════════════════════════════════',
    );
    debugPrint('║ 🐛 HybridLangChain API 请求');
    debugPrint(
      '╠═══════════════════════════════════════════════════════════════',
    );
    debugPrint('║ 📍 URL: $url');
    debugPrint(
      '║ 🏢 Provider: ${config.name} (${config.type.toString().split('.').last})',
    );
    debugPrint(
      '║ 🔑 API Key: ${config.apiKey.substring(0, math.min(10, config.apiKey.length))}...****',
    );
    debugPrint(
      '╠═══════════════════════════════════════════════════════════════',
    );

    final displayBody = Map<String, dynamic>.from(requestBody);
    if (displayBody.containsKey('messages')) {
      final messages = displayBody['messages'] as List?;
      if (messages != null && messages.length > 3) {
        final summary = [
          messages[0],
          messages[1],
          {'role': '...', 'content': '(${messages.length - 3}条消息已隐藏)'},
          messages.last,
        ];
        displayBody['messages'] = summary;
      }
    }

    final prettyJson = const JsonEncoder.withIndent('  ').convert(displayBody);
    for (var line in prettyJson.split('\n')) {
      debugPrint('║   $line');
    }

    debugPrint(
      '╚═══════════════════════════════════════════════════════════════\n',
    );
  }

  /// 执行工具调用并收集结果（用于工具调用循环）
  Future<List<({String callId, String content, bool isSuccess})>>
  _executeToolCallsAndCollect(List<ToolCallCompleted> calls) async {
    if (!hasMcpTools || calls.isEmpty) return [];

    final results = <({String callId, String content, bool isSuccess})>[];

    for (final call in calls) {
      // 通知 UI：工具开始执行
      final runningData = ToolCallData(
        callId: call.callId,
        toolName: call.name,
        arguments: call.arguments,
        status: ToolCallStatus.running,
        startTime: DateTime.now(),
      );
      onToolCallData?.call(runningData);

      if (kDebugMode) {
        debugPrint('[MCP] Executing tool: ${call.name} (${call.callId})');
      }

      try {
        final result = await _mcpAdapter!.executeTool(
          name: call.name,
          arguments: call.arguments,
        );

        // 打印工具返回的实际内容（用于调试）
        if (kDebugMode) {
          final preview = result.content.length > 500
              ? '${result.content.substring(0, 500)}...'
              : result.content;
          debugPrint('[MCP] Tool ${call.name} result:\n$preview');
        }

        // 通知 UI：工具执行完成
        final completedData = ToolCallData(
          callId: call.callId,
          toolName: call.name,
          arguments: call.arguments,
          status: result.isSuccess
              ? ToolCallStatus.success
              : ToolCallStatus.error,
          startTime: runningData.startTime,
          endTime: DateTime.now(),
          result: result.isSuccess ? result.content : null,
          errorMessage: result.isSuccess ? null : result.content,
        );
        onToolCallData?.call(completedData);

        if (kDebugMode) {
          debugPrint(
            '[MCP] Tool ${call.name} ${result.isSuccess ? "succeeded" : "failed"}',
          );
        }

        results.add((
          callId: call.callId,
          content: result.content,
          isSuccess: result.isSuccess,
        ));
      } catch (e) {
        // 通知 UI：工具执行错误
        final errorData = ToolCallData(
          callId: call.callId,
          toolName: call.name,
          arguments: call.arguments,
          status: ToolCallStatus.error,
          startTime: runningData.startTime,
          endTime: DateTime.now(),
          errorMessage: e.toString(),
        );
        onToolCallData?.call(errorData);

        if (kDebugMode) {
          debugPrint('[MCP] Tool ${call.name} error: $e');
        }

        results.add((
          callId: call.callId,
          content: 'Error: $e',
          isSuccess: false,
        ));
      }
    }

    return results;
  }
}
