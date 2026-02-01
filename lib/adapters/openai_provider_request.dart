/// INPUT: 请求参数
/// OUTPUT: 请求体构建和消息转换方法
/// POS: Adapters / OpenAI Provider - 请求构建 Part

part of 'openai_provider.dart';

/// OpenAI Provider 请求构建扩展
extension _OpenAIProviderRequest on OpenAIProvider {
  /// 构建请求体（根据Provider类型定制参数）
  Future<Map<String, dynamic>> buildRequestBody({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    required bool stream,
    List<AttachedFileData>? files,
  }) async {
    // 基础参数（所有Provider都支持）
    final body = <String, dynamic>{
      'model': model,
      'messages': await convertMessages(messages, files),
      'stream': stream,
      // 启用 reasoning 输出（OpenRouter 等聚合服务需要此参数）
      'include_reasoning': true,
    };

    // Gemini 模型特殊处理：添加 thinking_config
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

    // 根据Provider类型添加支持的参数
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
  Future<List<Map<String, dynamic>>> convertMessages(
    List<ChatMessage> messages,
    List<AttachedFileData>? files,
  ) async {
    final converted = messages.map((msg) => msg.toJson()).toList();

    // 过滤空system消息（很多API不接受空的system消息）
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
            final imageData = readFileAsBase64(file.path);
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
  String readFileAsBase64(String filePath) {
    try {
      final file = File(filePath);
      final bytes = file.readAsBytesSync();
      return base64Encode(bytes);
    } catch (e) {
      return '';
    }
  }
}
