import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/provider_config.dart';
import '../models/model_config.dart';
import 'ai_provider.dart';

/// OpenAI格式Provider适配器
/// 支持OpenAI官方API和兼容格式的第三方服务
class OpenAIProvider extends AIProvider {
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

      final response = await http
          .get(
            Uri.parse('${config.apiUrl}/models'),
            headers: buildHeaders(),
          )
          .timeout(const Duration(seconds: 10));

      stopwatch.stop();

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        final models = (data['data'] as List?)
            ?.map((m) => m['id'] as String)
            .toList();

        return ProviderTestResult.success(
          responseTimeMs: stopwatch.elapsedMilliseconds,
          availableModels: models,
        );
      } else {
        final error = _parseErrorMessage(response);
        return ProviderTestResult.failure(error);
      }
    } on TimeoutException {
      return ProviderTestResult.failure('连接超时');
    } on SocketException {
      return ProviderTestResult.failure('网络连接失败');
    } catch (e) {
      return ProviderTestResult.failure('测试失败: ${e.toString()}');
    }
  }

  @override
  Future<List<String>> listAvailableModels() async {
    try {
      final response = await http.get(
        Uri.parse('${config.apiUrl}/models'),
        headers: buildHeaders(),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
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
    final requestBody = _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: true,
      files: files,
    );

    final request = http.Request(
      'POST',
      Uri.parse('${config.apiUrl}/chat/completions'),
    );
    request.headers.addAll(buildHeaders());
    request.body = json.encode(requestBody);

    try {
      final streamedResponse = await request.send();

      if (streamedResponse.statusCode != 200) {
        final responseBody = await streamedResponse.stream.bytesToString();
        final error = _parseErrorFromBody(responseBody);
        throw Exception('API错误: $error');
      }

      await for (var chunk in streamedResponse.stream
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
    } catch (e) {
      throw Exception('流式请求失败: ${e.toString()}');
    }
  }

  @override
  Future<String> sendMessage({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  }) async {
    final requestBody = _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: false,
      files: files,
    );

    try {
      final response = await http.post(
        Uri.parse('${config.apiUrl}/chat/completions'),
        headers: buildHeaders(),
        body: json.encode(requestBody),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        final choices = data['choices'] as List?;
        if (choices != null && choices.isNotEmpty) {
          final message = choices[0]['message'] as Map<String, dynamic>?;
          return message?['content'] as String? ?? '';
        }
        return '';
      } else {
        final error = _parseErrorMessage(response);
        throw Exception(error);
      }
    } catch (e) {
      throw Exception('请求失败: ${e.toString()}');
    }
  }

  /// 构建请求体
  Map<String, dynamic> _buildRequestBody({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required bool stream,
    List<AttachedFileData>? files,
  }) {
    final body = <String, dynamic>{
      'model': model,
      'messages': _convertMessages(messages, files),
      'temperature': parameters.temperature,
      'max_tokens': parameters.maxTokens,
      'top_p': parameters.topP,
      'frequency_penalty': parameters.frequencyPenalty,
      'presence_penalty': parameters.presencePenalty,
      'stream': stream,
    };

    return body;
  }

  /// 转换消息格式，处理多模态内容
  List<Map<String, dynamic>> _convertMessages(
    List<ChatMessage> messages,
    List<AttachedFileData>? files,
  ) {
    final converted = messages.map((msg) => msg.toJson()).toList();

    // 如果有附件且最后一条是用户消息，添加多模态内容
    if (files != null && files.isNotEmpty && converted.isNotEmpty) {
      final lastMessage = converted.last;
      if (lastMessage['role'] == 'user') {
        final content = <Map<String, dynamic>>[];

        // 添加文本内容
        if (lastMessage['content'] is String) {
          content.add({
            'type': 'text',
            'text': lastMessage['content'],
          });
        }

        // 添加图片
        for (var file in files) {
          if (file.mimeType.startsWith('image/')) {
            final imageData = _readFileAsBase64(file.path);
            content.add({
              'type': 'image_url',
              'image_url': {
                'url': 'data:${file.mimeType};base64,$imageData',
              },
            });
          }
        }

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

  /// 解析错误消息
  String _parseErrorMessage(http.Response response) {
    try {
      final data = json.decode(response.body) as Map<String, dynamic>;
      final error = data['error'] as Map<String, dynamic>?;
      return error?['message'] as String? ?? '未知错误';
    } catch (e) {
      return '状态码: ${response.statusCode}';
    }
  }

  /// 从响应体解析错误
  String _parseErrorFromBody(String body) {
    try {
      final data = json.decode(body) as Map<String, dynamic>;
      final error = data['error'] as Map<String, dynamic>?;
      return error?['message'] as String? ?? '未知错误';
    } catch (e) {
      return body;
    }
  }
}
