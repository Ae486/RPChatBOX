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
      await for (var chunk in responseStream
          .cast<List<int>>()  // Cast to List<int> first
          .transform(utf8.decoder)
          .transform(const LineSplitter())) {
        if (chunk.isEmpty || !chunk.startsWith('data: ')) continue;

        final data = chunk.substring(6); // Remove 'data: ' prefix
        if (data == '[DONE]') break;

        try {
          final parsed = json.decode(data) as Map<String, dynamic>;
          final choices = parsed['choices'] as List?;
          if (choices != null && choices.isNotEmpty) {
            final delta = choices[0]['delta'] as Map<String, dynamic>?;
            final content = delta?['content'] as String?;
            if (content != null) {
              yield content;
            }
          }
        } catch (e) {
          // Skip malformed chunks
          continue;
        }
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
    };

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
