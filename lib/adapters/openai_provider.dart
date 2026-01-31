import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/foundation.dart';
import 'package:dio/dio.dart';
import 'package:path/path.dart' as path;
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../models/api_error.dart';
import '../services/file_content_service.dart';
import '../services/dio_service.dart';
import 'ai_provider.dart';

/// OpenAI格式Provider适配器
/// 支持OpenAI官方API和兼容格式的第三方服务
class OpenAIProvider extends AIProvider {
  // Dio 实例和取消令牌
  final _dio = DioService().dio;
  CancelToken? _currentCancelToken;
  
  OpenAIProvider(super.config);

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
      // 🔧 使用actualApiUrl获取实际API地址
      final baseUrl = config.actualApiUrl.replaceAll('/chat/completions', '').replaceAll('/messages', '');

      // 使用 dio 发送请求
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
      // 🔧 使用actualApiUrl获取实际API地址
      final baseUrl = config.actualApiUrl.replaceAll('/chat/completions', '').replaceAll('/messages', '');
      
      // 使用 dio 发送请求
      final response = await _dio.get(
        '$baseUrl/models',
        options: Options(
          headers: buildHeaders(),
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
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async* {
    // 取消之前的请求（如果有）
    _currentCancelToken?.cancel('新请求开始');
    _currentCancelToken = DioService().createCancelToken();
    
    final requestBody = await _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: true,
      files: files,
    );
    
    // 🐛 调试输出：请求详情
    _debugPrintRequest(config.actualApiUrl, requestBody);

    try {
      // 使用 dio 发送流式请求
      final response = await _dio.post(
        config.actualApiUrl,
        data: requestBody,
        options: Options(
          headers: buildHeaders(),
          responseType: ResponseType.stream, // 流式响应
        ),
        cancelToken: _currentCancelToken,
      );

      if (response.statusCode != 200) {
        final responseBody = response.data.toString();
        final apiError = ApiErrorParser.parseFromResponse(
          statusCode: response.statusCode!,
          responseBody: responseBody,
          apiProvider: config.name,
        );
        _debugPrintError(apiError);
        throw apiError;
      }

      // 处理流式响应
      // response.data 是 ResponseBody，需要访问其 stream 属性
      final responseStream = (response.data as ResponseBody).stream;
      // 🧠 Gemini思考块控制（仅在 ProviderType.gemini 时启用）
      final isGemini = config.type == ProviderType.gemini;
      debugPrint('🔍 [Provider] type=${config.type}, isGemini=$isGemini');
      bool geminiReasoningOpen = false;      // 是否已输出 <think>
      bool geminiEmittedBody = false;        // 是否已开始输出正文
      await for (var chunk in responseStream
          .cast<List<int>>()  // Cast to List<int> first
          .transform(utf8.decoder)
          .transform(const LineSplitter())) {
        // 🐛 调试：打印原始 SSE 行
        if (kDebugMode) {
          debugPrint('🔶 [SSE raw] $chunk');
        }

        final line = chunk.trim();
        if (line.isEmpty) continue;
        final data = line.startsWith('data: ') ? line.substring(6) : line;
        if (kDebugMode) {
          debugPrint('🟢 [SSE data] $data');
        }
        if (data == '[DONE]') break;

        try {
          final parsed = json.decode(data) as Map<String, dynamic>;
          if (kDebugMode) {
            // 打印解析后的完整 JSON（逐行，便于阅读）
            final pretty = const JsonEncoder.withIndent('  ').convert(parsed);
            debugPrint('🧾 [SSE parsed]');
            for (final line in pretty.split('\n')) {
              debugPrint('    $line');
            }
          }

          final choices = parsed['choices'] as List?;
          if (choices != null && choices.isNotEmpty) {
            final choice = choices[0] as Map<String, dynamic>;
            final delta = choice['delta'] as Map<String, dynamic>?;

            // 调试：打印完整的 choice 结构
            debugPrint('🔍 [choice keys] ${choice.keys.toList()}');

            if (delta != null) {
              // 调试：打印 delta 的所有 key
              debugPrint('🔍 [delta keys] ${delta.keys.toList()}');

              // 1) 尝试识别不同供应商可能使用的"思考/推理"字段
              final possibleKeys = [
                'reasoning',
                'reasoning_content',
                'internal_thoughts',
                'thinking',
              ];

              for (final key in possibleKeys) {
                final v = delta[key];
                if (v == null) continue;

                String? reasoningText;
                if (v is String) {
                  reasoningText = v;
                } else if (v is Map<String, dynamic>) {
                  // 常见结构：{ content: '...' } / { text: '...' }
                  reasoningText = (v['content'] ?? v['text']) as String?;
                } else if (v is List) {
                  // 如果是数组，拼接其中的文本
                  reasoningText = v.map((e) {
                    if (e is String) return e;
                    if (e is Map<String, dynamic>) {
                      return (e['content'] ?? e['text'] ?? '').toString();
                    }
                    return '';
                  }).where((s) => s.isNotEmpty).join('');
                }

                if (reasoningText != null && reasoningText.isNotEmpty) {
                  final wrapped = '<think>$reasoningText</think>';
                  if (kDebugMode) {
                    debugPrint('💡 [reasoning detected][$key] ${reasoningText.length} chars');
                  }
                  yield wrapped;
                }
              }

              // 2) 解析 content
              final contentField = delta['content'];
              if (contentField is String) {
                if (contentField.isNotEmpty) {
                  if (kDebugMode) {
                    debugPrint('✍️  [content:string] ${contentField.length} chars');
                  }
                  yield contentField;
                }
              } else if (contentField is List) {
                for (final part in contentField) {
                  if (part is Map<String, dynamic>) {
                    final pType = (part['type'] ?? part['role'] ?? '').toString();
                    final pText = (part['text'] ?? part['content'] ?? '').toString();
                    if (pText.isEmpty) continue;
                    if (kDebugMode) {
                      debugPrint('🔹 [content:part] type=$pType len=${pText.length}');
                    }
                    // 常见：type 为 'reasoning' 或自定义标签
                    final lower = pType.toLowerCase();
                    if (lower.contains('reason') || lower.contains('think') || lower.contains('thought')) {
                      yield '<think>$pText</think>';
                    } else {
                      yield pText;
                    }
                  } else if (part is String && part.isNotEmpty) {
                    if (kDebugMode) {
                      debugPrint('🔹 [content:part:string] len=${part.length}');
                    }
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
                  final pType = (part['type'] ?? part['role'] ?? '').toString().toLowerCase();
                  if (pText.isEmpty) continue;
                  if (kDebugMode) {
                    debugPrint('🔹 [candidates:part] idx=$i type=$pType len=${pText.length}');
                  }
                  if (isGemini) {
                    // 规则：在遇到正文前，首个parts作为思考；一旦开始正文，关闭思考块
                    if (!geminiEmittedBody && i == 0) {
                      if (!geminiReasoningOpen) {
                        yield '<think>';
                        geminiReasoningOpen = true;
                        if (kDebugMode) debugPrint('💡 [gemini] open <think>');
                      }
                      yield pText;
                    } else {
                      if (geminiReasoningOpen) {
                        yield '</think>';
                        geminiReasoningOpen = false;
                        if (kDebugMode) debugPrint('💡 [gemini] close </think>');
                      }
                      geminiEmittedBody = true;
                      yield pText;
                    }
                  } else {
                    // 非Gemini：类型含 reasoning/think 视为思考块
                    if (pType.contains('reason') || pType.contains('think') || pType.contains('thought')) {
                      yield '<think>$pText</think>';
                    } else {
                      yield pText;
                    }
                  }
                }
              } else {
                // 一些实现直接将 text 放在 content.text
                final cText = (content['text'] ?? '').toString();
                if (cText.isNotEmpty) {
                  if (kDebugMode) {
                    debugPrint('🔹 [candidates:content.text] len=${cText.length}');
                  }
                  if (isGemini && geminiReasoningOpen) {
                    // content.text 视为正文
                    yield '</think>';
                    geminiReasoningOpen = false;
                    if (kDebugMode) debugPrint('💡 [gemini] close </think> (content.text)');
                    geminiEmittedBody = true;
                  }
                  yield cText;
                }
              }
            } else {
              // 一些实现直接 candidates[].text
              final cText = (cand0['text'] ?? '').toString();
              if (cText.isNotEmpty) {
                if (kDebugMode) {
                  debugPrint('🔹 [candidates:text] len=${cText.length}');
                }
                if (isGemini && geminiReasoningOpen) {
                  yield '</think>';
                  geminiReasoningOpen = false;
                  if (kDebugMode) debugPrint('💡 [gemini] close </think> (candidates.text)');
                  geminiEmittedBody = true;
                }
                yield cText;
              }
            }
          }
        } catch (e) {
          // 🟠 调试：解析失败
          if (kDebugMode) {
            debugPrint('⚠️ [SSE parse error] ${e.toString()}');
          }
          continue;
        }
      }
      // 流结束时，如果Gemini思考块仍未关闭，则补充关闭标签
      if (isGemini && geminiReasoningOpen) {
        yield '</think>';
        if (kDebugMode) debugPrint('💡 [gemini] auto close </think> at stream end');
      }
    } on DioException catch (e) {
      if (e.type == DioExceptionType.cancel) {
        throw Exception('请求已取消');
      } else {
        throw Exception('流式请求失败: ${e.message}');
      }
    } catch (e) {
      throw Exception('流式请求失败: ${e.toString()}');
    } finally {
      _currentCancelToken = null;
    }
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async {
    final requestBody = await _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: false,
      files: files,
    );
    
    // 🐛 调试输出：请求详情
    _debugPrintRequest(config.actualApiUrl, requestBody);

    try {
      // 使用 dio 发送请求
      final response = await _dio.post(
        config.actualApiUrl,
        data: requestBody,
        options: Options(
          headers: buildHeaders(),
        ),
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
        // 🐛 使用新的错误处理系统
        final apiError = ApiErrorParser.parseFromResponse(
          statusCode: response.statusCode!,
          responseBody: response.data.toString(),
          apiProvider: config.name,
        );
        _debugPrintError(apiError);
        throw apiError;
      }
    } on DioException catch (e) {
      if (e.response != null) {
        final apiError = ApiErrorParser.parseFromResponse(
          statusCode: e.response!.statusCode!,
          responseBody: e.response!.data.toString(),
          apiProvider: config.name,
        );
        throw apiError;
      } else {
        throw Exception('请求失败: ${e.message}');
      }
    } catch (e) {
      throw Exception('请求失败: ${e.toString()}');
    }
  }

  /// 取消当前请求
  /// 用于用户点击停止按钮时真正中断网络请求
  void cancelRequest() {
    if (_currentCancelToken != null && !_currentCancelToken!.isCancelled) {
      _currentCancelToken!.cancel('用户取消');
      if (kDebugMode) {
        debugPrint('✅ [OpenAIProvider] 请求已取消');
      }
    }
  }

  /// 构建请求体（根据Provider类型定制参数）
  Future<Map<String, dynamic>> _buildRequestBody({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required bool stream,
    List<AttachedFileData>? files,
  }) async {
    // 🔧 基础参数（所有Provider都支持）
    final body = <String, dynamic>{
      'model': model,
      'messages': await _convertMessages(messages, files),
      'stream': stream,
      // 🆕 启用 reasoning 输出（OpenRouter 等聚合服务需要此参数）
      'include_reasoning': true,
    };

    // 🆕 Gemini 模型特殊处理：添加 thinking_config
    final modelLower = model.toLowerCase();
    if (modelLower.contains('gemini')) {
      body['extra_body'] = {
        'google': {
          'thinking_config': {
            'include_thoughts': true,
          },
        },
      };
    }

    // 🆕 根据Provider类型添加支持的参数
    switch (config.type) {
      case ProviderType.openai:
        // OpenAI官方API - 支持所有参数
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        _addIfNotDefault(body, 'top_p', parameters.topP, 1.0);
        _addIfNotDefault(body, 'frequency_penalty', parameters.frequencyPenalty, 0.0);
        _addIfNotDefault(body, 'presence_penalty', parameters.presencePenalty, 0.0);
        break;

      case ProviderType.deepseek:
        // DeepSeek - 不支持frequency_penalty和presence_penalty
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        _addIfNotDefault(body, 'top_p', parameters.topP, 1.0);
        break;

      case ProviderType.gemini:
        // Gemini - 只支持基础参数
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        break;

      case ProviderType.claude:
        // Claude - 使用max_tokens而不是max_completion_tokens
        _addIfNotDefault(body, 'temperature', parameters.temperature, 1.0);
        _addIfNotNull(body, 'max_tokens', parameters.maxTokens);
        _addIfNotDefault(body, 'top_p', parameters.topP, 1.0);
        break;
    }

    return body;
  }

  /// 添加非默认值的参数
  void _addIfNotDefault(Map<String, dynamic> body, String key, double value, double defaultValue) {
    if (value != defaultValue) {
      body[key] = value;
    }
  }

  /// 添加非null且有效的参数
  void _addIfNotNull(Map<String, dynamic> body, String key, int? value) {
    if (value != null && value > 0) {
      body[key] = value;
    }
  }

  /// 转换消息格式，处理多模态内容
  Future<List<Map<String, dynamic>>> _convertMessages(
    List<ChatMessage> messages,
    List<AttachedFileData>? files,
  ) async {
    final converted = messages.map((msg) => msg.toJson()).toList();

    // 🆕 过滤空system消息（很多API不接受空的system消息）
    converted.removeWhere((msg) => 
      msg['role'] == 'system' && 
      (msg['content'] == null || (msg['content'] as String).trim().isEmpty)
    );

    // 如果有附件且最后一条是用户消息，添加多模态内容
    if (files != null && files.isNotEmpty && converted.isNotEmpty) {
      final lastMessage = converted.last;
      if (lastMessage['role'] == 'user') {
        final content = <Map<String, dynamic>>[];

        // 准备文档内容
        final documentContents = <String>[];
        final imageContents = <Map<String, dynamic>>[];

        // 处理所有文件
        for (var file in files) {
          final fileName = path.basename(file.path);
          final extension = path.extension(file.path);

          if (file.mimeType.startsWith('image/')) {
            // 处理图片文件
            final imageData = _readFileAsBase64(file.path);
            imageContents.add({
              'type': 'image_url',
              'image_url': {
                'url': 'data:${file.mimeType};base64,$imageData',
              },
            });
          } else if (FileContentService.isTextProcessable(file.mimeType, extension)) {
            // 处理文本文件
            try {
              final textContent = await FileContentService.extractTextContent(
                File(file.path),
                file.mimeType,
              );
              documentContents.add(
                FileContentService.generateFilePrompt(fileName, file.mimeType, textContent)
              );
            } catch (e) {
              documentContents.add('// 文件 $fileName 处理失败: ${e.toString()}');
            }
          } else {
            // 其他文件类型
            documentContents.add('// 文件 $fileName (${file.mimeType}) 暂不支持内容提取');
          }
        }

        // 构建文本内容
        String textContent = lastMessage['content'] as String? ?? '';

        // 如果有文档内容，添加到文本前面
        if (documentContents.isNotEmpty) {
          textContent = '${documentContents.join('\n\n')}\n\n---\n\n$textContent';
        }

        content.add({
          'type': 'text',
          'text': textContent,
        });

        // 添加图片内容
        content.addAll(imageContents);

        lastMessage['content'] = content;
      }
    }

    return converted;
  }

  /// 读取文件为Base64
  String _readFileAsBase64(String path) {
    try {
      final file = File(path);
      final bytes = file.readAsBytesSync();
      return base64Encode(bytes);
    } catch (e) {
      return '';
    }
  }

  /// 🐛 调试方法：打印请求内容
  void _debugPrintRequest(String url, Map<String, dynamic> requestBody) {
    // 仅在调试模式启用详细日志
    if (!kDebugMode) return;
    
    debugPrint('\n╔═══════════════════════════════════════════════════════════════');
    debugPrint('║ 🐛 API 请求调试信息');
    debugPrint('╠═══════════════════════════════════════════════════════════════');
    debugPrint('║ 📍 API 地址: $url');
    debugPrint('║ 🏢 Provider: ${config.name} (${config.type.toString().split('.').last})');
    debugPrint('║ 🔑 API Key: ${config.apiKey.substring(0, math.min(10, config.apiKey.length))}...****');
    debugPrint('╠═══════════════════════════════════════════════════════════════');
    debugPrint('║ 📤 完整请求体:');
    debugPrint('║');
    
    // 格式化输出JSON（截断过长的messages）
    final displayBody = Map<String, dynamic>.from(requestBody);
    if (displayBody.containsKey('messages')) {
      final messages = displayBody['messages'] as List?;
      if (messages != null && messages.length > 3) {
        // 只显示前2条和最后1条消息
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
    
    debugPrint('║');
    debugPrint('╠══════════════════════════════════════════════════════════════╗');
    debugPrint('║ 📊 参数摘要:');
    debugPrint('║   • 模型: ${requestBody['model']}');
    debugPrint('║   • 流式模式: ${requestBody['stream']}');
    if (requestBody.containsKey('temperature')) {
      debugPrint('║   • Temperature: ${requestBody['temperature']}');
    }
    if (requestBody.containsKey('max_tokens')) {
      debugPrint('║   • Max Tokens: ${requestBody['max_tokens']}');
    }
    if (requestBody.containsKey('top_p')) {
      debugPrint('║   • Top P: ${requestBody['top_p']}');
    }
    if (requestBody.containsKey('frequency_penalty')) {
      debugPrint('║   • Frequency Penalty: ${requestBody['frequency_penalty']}');
    }
    if (requestBody.containsKey('presence_penalty')) {
      debugPrint('║   • Presence Penalty: ${requestBody['presence_penalty']}');
    }
    final messages = requestBody['messages'] as List?;
    if (messages != null) {
      debugPrint('║   • 消息数: ${messages.length}');
    }
    debugPrint('╚══════════════════════════════════════════════════════════════╗\n');
  }
  
  /// 🐛 调试方法：打印错误信息
  void _debugPrintError(ApiError error) {
    if (!kDebugMode) return;
    
    debugPrint('\n╔══════════════════════════════════════════════════════════════╗');
    debugPrint('║ ${error.title}');
    debugPrint('╠══════════════════════════════════════════════════════════════╗');
    debugPrint('║ 🔴 状态码: ${error.statusCode}');
    debugPrint('║ 📝 消息: ${error.message}');
    if (error.errorCode != null) {
      debugPrint('║ 🎯 错误代码: ${error.errorCode}');
    }
    if (error.details != null) {
      debugPrint('║ ℹ️ 详情: ${error.details}');
    }
    debugPrint('║ 🕒 时间: ${error.timestamp}');
    debugPrint('║ ♾️ 可重试: ${error.isRetryable}');
    if (error.isRetryable) {
      debugPrint('║ ✇️ 建议延迟: ${error.retryDelayMs}ms');
    }
    debugPrint('╚══════════════════════════════════════════════════════════════╗\n');
  }
}
