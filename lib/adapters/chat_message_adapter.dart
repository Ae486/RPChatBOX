import 'package:flutter_chat_core/flutter_chat_core.dart' as chat;
import '../models/message.dart' as app;
import '../models/attached_file.dart';

/// 消息适配器
///
/// 将应用内部的 Message 模型转换为 flutter_chat_ui 的 Message 模型
/// 同时支持反向转换，保持数据兼容性
class ChatMessageAdapter {
  static const String _userAuthorId = 'user';
  static const String _assistantAuthorId = 'assistant';

  /// 思考标签列表（按优先级排序）
  static const _thinkingTags = [
    ('<thinking>', '</thinking>'),
    ('<think>', '</think>'),
    ('<thought>', '</thought>'),
    ('<thoughts>', '</thoughts>'),
  ];

  /// 将应用 Message 转换为 flutter_chat_ui Message
  static chat.Message toFlutterChatMessage(app.Message msg) {
    if (msg.isUser) {
      return _convertUserMessage(msg);
    } else {
      return _convertAssistantMessage(msg);
    }
  }

  /// 转换用户消息
  static chat.Message _convertUserMessage(app.Message msg) {
    // 检查是否有附件
    final hasAttachments = msg.attachedFiles != null && msg.attachedFiles!.isNotEmpty;

    if (hasAttachments) {
      // 如果有图片附件，使用 ImageMessage
      final imageFiles = msg.attachedFiles!.where((f) => f.isImage).toList();
      if (imageFiles.isNotEmpty && msg.content.isEmpty) {
        // 纯图片消息
        return chat.ImageMessage(
          id: msg.id,
          authorId: _userAuthorId,
          createdAt: msg.timestamp.toUtc(),
          source: imageFiles.first.path,
          metadata: {
            'inputTokens': msg.inputTokens,
            'attachedFiles': msg.attachedFiles?.map((f) => f.toJson()).toList(),
          },
        );
      }
    }

    // 普通文本消息（可能带附件）
    return chat.TextMessage(
      id: msg.id,
      authorId: _userAuthorId,
      createdAt: msg.timestamp.toUtc(),
      text: msg.content,
      metadata: {
        'inputTokens': msg.inputTokens,
        'attachedFiles': msg.attachedFiles?.map((f) => f.toJson()).toList(),
      },
    );
  }

  /// 转换助手消息
  static chat.Message _convertAssistantMessage(app.Message msg) {
    // 检测是否包含思考内容
    final thinkingResult = _extractThinking(msg.content);

    if (thinkingResult != null) {
      // 包含思考内容，使用 CustomMessage
      return chat.CustomMessage(
        id: msg.id,
        authorId: _assistantAuthorId,
        createdAt: msg.timestamp.toUtc(),
        metadata: {
          'type': 'thinking_message',
          'thinking': thinkingResult.thinking,
          'body': thinkingResult.body,
          'outputTokens': msg.outputTokens,
          'inputTokens': msg.inputTokens,
          'modelName': msg.modelName,
          'providerName': msg.providerName,
          'thinkingDurationSeconds': msg.thinkingDurationSeconds,
        },
      );
    }

    // 普通文本消息
    return chat.TextMessage(
      id: msg.id,
      authorId: _assistantAuthorId,
      createdAt: msg.timestamp.toUtc(),
      text: msg.content,
      metadata: {
        'outputTokens': msg.outputTokens,
        'inputTokens': msg.inputTokens,
        'modelName': msg.modelName,
        'providerName': msg.providerName,
      },
    );
  }

  /// 从 flutter_chat_ui Message 转换回应用 Message
  static app.Message fromFlutterChatMessage(chat.Message msg) {
    final metadata = msg.metadata ?? {};
    final isUser = msg.authorId == _userAuthorId;

    String content;
    if (msg is chat.TextMessage) {
      content = msg.text;
    } else if (msg is chat.CustomMessage) {
      // 重建思考消息内容
      final thinking = metadata['thinking'] as String?;
      final body = metadata['body'] as String?;
      if (thinking != null && thinking.isNotEmpty) {
        content = '<think>$thinking</think>${body ?? ''}';
      } else {
        content = body ?? '';
      }
    } else if (msg is chat.ImageMessage) {
      content = msg.text ?? '';
    } else {
      content = '';
    }

    // 解析附件
    List<AttachedFileSnapshot>? attachedFiles;
    final attachedFilesJson = metadata['attachedFiles'] as List?;
    if (attachedFilesJson != null) {
      attachedFiles = attachedFilesJson
          .map((f) => AttachedFileSnapshot.fromJson(f as Map<String, dynamic>))
          .toList();
    }

    return app.Message(
      id: msg.id,
      content: content,
      isUser: isUser,
      timestamp: msg.createdAt ?? DateTime.now(),
      inputTokens: metadata['inputTokens'] as int?,
      outputTokens: metadata['outputTokens'] as int?,
      modelName: metadata['modelName'] as String?,
      providerName: metadata['providerName'] as String?,
      attachedFiles: attachedFiles,
    );
  }

  /// 提取思考内容
  /// 返回 null 表示没有思考内容
  static ThinkingResult? _extractThinking(String content) {
    for (final (startTag, endTag) in _thinkingTags) {
      final startIdx = content.indexOf(startTag);
      if (startIdx == -1) continue;

      final afterStart = startIdx + startTag.length;
      final endIdx = content.indexOf(endTag, afterStart);

      if (endIdx == -1) continue;

      final thinking = content.substring(afterStart, endIdx);
      final body = content.substring(0, startIdx) + content.substring(endIdx + endTag.length);

      return ThinkingResult(
        thinking: thinking.trim(),
        body: body.trim(),
      );
    }

    return null;
  }

  /// 检查消息是否包含思考内容
  static bool hasThinking(String content) {
    return _extractThinking(content) != null;
  }

  /// 获取消息的显示作者名称
  static String getAuthorDisplayName(chat.Message msg, {String defaultName = 'AI助手'}) {
    final metadata = msg.metadata ?? {};
    final modelName = metadata['modelName'] as String?;
    final providerName = metadata['providerName'] as String?;

    if (modelName != null && providerName != null) {
      return '$modelName|$providerName';
    } else if (modelName != null) {
      return modelName;
    } else if (msg.authorId == _userAuthorId) {
      return '用户';
    }

    return defaultName;
  }
}

/// 思考内容提取结果
class ThinkingResult {
  final String thinking;
  final String body;

  ThinkingResult({
    required this.thinking,
    required this.body,
  });
}
