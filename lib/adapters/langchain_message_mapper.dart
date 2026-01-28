import 'dart:convert';
import 'dart:io';

import 'package:langchain_core/chat_models.dart' as lc;

import 'ai_provider.dart' as app;
import '../models/provider_config.dart';

/// 将 AIProvider.ChatMessage 转换为 LangChain ChatMessage
///
/// 处理:
/// - 文本消息 (system/user/assistant)
/// - 多模态消息 (图片)
/// - 附件文件
class LangChainMessageMapper {
  const LangChainMessageMapper._();

  /// 转换消息列表
  ///
  /// [messages] - AIProvider 格式的消息
  /// [providerType] - 目标 Provider 类型（影响多模态处理）
  /// [files] - 附件文件（图片等）
  static Future<List<lc.ChatMessage>> toLangChainMessages({
    required List<app.ChatMessage> messages,
    required ProviderType providerType,
    List<app.AttachedFileData>? files,
  }) async {
    final result = <lc.ChatMessage>[];

    for (final msg in messages) {
      final lcMessage = await _convertMessage(msg, providerType, files);
      result.add(lcMessage);
    }

    return result;
  }

  /// 转换单个消息
  static Future<lc.ChatMessage> _convertMessage(
    app.ChatMessage msg,
    ProviderType providerType,
    List<app.AttachedFileData>? files,
  ) async {
    // 处理多模态内容
    if (msg.multimodalContent != null && msg.multimodalContent!.isNotEmpty) {
      return _convertMultimodalMessage(msg, providerType);
    }

    // 处理附件（仅对 user 消息）
    if (files != null && files.isNotEmpty && msg.role == 'user') {
      return _convertMessageWithFiles(msg, files, providerType);
    }

    // 纯文本消息
    return _convertTextMessage(msg);
  }

  /// 转换纯文本消息
  static lc.ChatMessage _convertTextMessage(app.ChatMessage msg) {
    switch (msg.role) {
      case 'system':
        return lc.ChatMessage.system(msg.content);
      case 'user':
        return lc.ChatMessage.humanText(msg.content);
      case 'assistant':
        return lc.ChatMessage.ai(msg.content);
      default:
        // 默认作为 human 消息
        return lc.ChatMessage.humanText(msg.content);
    }
  }

  /// 转换多模态消息
  static lc.ChatMessage _convertMultimodalMessage(
    app.ChatMessage msg,
    ProviderType providerType,
  ) {
    final parts = <lc.ChatMessageContent>[];

    for (final content in msg.multimodalContent!) {
      switch (content.type) {
        case 'text':
          if (content.text != null) {
            parts.add(lc.ChatMessageContent.text(content.text!));
          }
          break;
        case 'image_url':
          if (content.imageUrl != null) {
            final imageUrl = content.imageUrl!.url;
            // 判断是 base64 还是 URL
            if (imageUrl.startsWith('data:')) {
              // Base64 图片
              final mimeType = _extractMimeType(imageUrl);
              final base64Data = _extractBase64Data(imageUrl);
              parts.add(lc.ChatMessageContent.image(
                data: base64Data,
                mimeType: mimeType,
              ));
            } else {
              // URL 图片 - 不同 provider 处理方式不同
              // OpenAI/Anthropic 支持 URL，Google 需要下载后转 base64
              if (providerType == ProviderType.gemini) {
                // Gemini 需要 base64，这里先添加占位，实际需要下载
                parts.add(lc.ChatMessageContent.text('[Image: $imageUrl]'));
              } else {
                parts.add(lc.ChatMessageContent.image(data: imageUrl));
              }
            }
          }
          break;
        case 'file':
          // 文件转换为文本描述（LangChain 不直接支持文件类型）
          if (content.file != null) {
            parts.add(lc.ChatMessageContent.text(
              '[File: ${content.file!.name}]',
            ));
          }
          break;
      }
    }

    switch (msg.role) {
      case 'user':
        return lc.ChatMessage.human(lc.ChatMessageContent.multiModal(parts));
      case 'assistant':
        // AI 消息通常只有文本
        final textContent = parts
            .whereType<lc.ChatMessageContentText>()
            .map((p) => p.text)
            .join('\n');
        return lc.ChatMessage.ai(textContent);
      default:
        return lc.ChatMessage.human(lc.ChatMessageContent.multiModal(parts));
    }
  }

  /// 转换带附件的消息
  static Future<lc.ChatMessage> _convertMessageWithFiles(
    app.ChatMessage msg,
    List<app.AttachedFileData> files,
    ProviderType providerType,
  ) async {
    final parts = <lc.ChatMessageContent>[];

    // 添加文本内容
    if (msg.content.isNotEmpty) {
      parts.add(lc.ChatMessageContent.text(msg.content));
    }

    // 添加图片附件
    for (final file in files) {
      if (_isImageMimeType(file.mimeType)) {
        try {
          final imageFile = File(file.path);
          if (await imageFile.exists()) {
            final bytes = await imageFile.readAsBytes();
            final base64Data = base64Encode(bytes);
            parts.add(lc.ChatMessageContent.image(
              data: base64Data,
              mimeType: file.mimeType,
            ));
          }
        } catch (e) {
          // 文件读取失败，添加占位文本
          parts.add(lc.ChatMessageContent.text('[Image: ${file.name} - load failed]'));
        }
      } else {
        // 非图片文件，添加文本描述
        parts.add(lc.ChatMessageContent.text('[Attached: ${file.name}]'));
      }
    }

    return lc.ChatMessage.human(lc.ChatMessageContent.multiModal(parts));
  }

  /// 从 data URL 提取 MIME 类型
  static String _extractMimeType(String dataUrl) {
    // data:image/png;base64,xxx
    final match = RegExp(r'data:([^;]+);').firstMatch(dataUrl);
    return match?.group(1) ?? 'image/png';
  }

  /// 从 data URL 提取 base64 数据
  static String _extractBase64Data(String dataUrl) {
    final commaIndex = dataUrl.indexOf(',');
    if (commaIndex == -1) return dataUrl;
    return dataUrl.substring(commaIndex + 1);
  }

  /// 判断是否为图片 MIME 类型
  static bool _isImageMimeType(String mimeType) {
    return mimeType.startsWith('image/');
  }
}
