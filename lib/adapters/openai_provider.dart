import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/file_content_service.dart';
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
      // 🔧 使用actualApiUrl获取实际API地址
      final baseUrl = config.actualApiUrl.replaceAll('/chat/completions', '').replaceAll('/messages', '');

      final response = await http
          .get(
            Uri.parse('$baseUrl/models'),
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
      // 🔧 使用actualApiUrl获取实际API地址
      final baseUrl = config.actualApiUrl.replaceAll('/chat/completions', '').replaceAll('/messages', '');
      final response = await http.get(
        Uri.parse('$baseUrl/models'),
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
    final requestBody = await _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: true,
      files: files,
    );

    // 🔧 使用actualApiUrl获取实际API地址
    final request = http.Request(
      'POST',
      Uri.parse(config.actualApiUrl),
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
    final requestBody = await _buildRequestBody(
      model: model,
      messages: messages,
      parameters: parameters,
      stream: false,
      files: files,
    );

    try {
      // 🔧 使用actualApiUrl获取实际API地址
      final response = await http.post(
        Uri.parse(config.actualApiUrl),
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
  Future<List<Map<String, dynamic>>> _convertMessages(
    List<ChatMessage> messages,
    List<AttachedFileData>? files,
  ) async {
    final converted = messages.map((msg) => msg.toJson()).toList();

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
