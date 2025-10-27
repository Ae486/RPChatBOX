import 'dart:io';
import 'package:path_provider/path_provider.dart';
import '../models/conversation.dart';
import '../models/message.dart';

/// 对话导出服务
class ExportService {
  /// 导出单条消息为 Markdown
  static String exportSingleMessageToMarkdown(Message message) {
    final buffer = StringBuffer();
    
    final sender = message.isUser ? '👤 用户' : '🤖 AI';
    final time = _formatDateTime(message.timestamp);
    
    buffer.writeln('### $sender');
    buffer.writeln('*$time*');
    buffer.writeln();
    buffer.writeln(message.content);
    
    return buffer.toString();
  }

  /// 导出单条消息为纯文本
  static String exportSingleMessageToText(Message message) {
    final buffer = StringBuffer();
    
    final sender = message.isUser ? '[用户]' : '[AI]';
    final time = _formatDateTime(message.timestamp);
    
    buffer.writeln('$sender $time');
    buffer.writeln(message.content);
    
    return buffer.toString();
  }

  /// 导出多条消息为 Markdown
  static String exportMessagesToMarkdown(List<Message> messages, String title) {
    final buffer = StringBuffer();

    // 标题
    buffer.writeln('# $title');
    buffer.writeln();
    buffer.writeln('**导出时间**: ${_formatDateTime(DateTime.now())}  ');
    buffer.writeln('**消息数量**: ${messages.length}');
    buffer.writeln();
    buffer.writeln('---');
    buffer.writeln();

    // 消息内容
    for (var message in messages) {
      buffer.writeln(_formatMessageMarkdown(message));
      buffer.writeln();
    }

    return buffer.toString();
  }

  /// 导出多条消息为纯文本
  static String exportMessagesToText(List<Message> messages, String title) {
    final buffer = StringBuffer();

    // 标题
    buffer.writeln('=' * 60);
    buffer.writeln(title);
    buffer.writeln('=' * 60);
    buffer.writeln();
    buffer.writeln('导出时间: ${_formatDateTime(DateTime.now())}');
    buffer.writeln('消息数量: ${messages.length}');
    buffer.writeln();
    buffer.writeln('-' * 60);
    buffer.writeln();

    // 消息内容
    for (var message in messages) {
      buffer.writeln(_formatMessageText(message));
      buffer.writeln();
    }

    return buffer.toString();
  }

  /// 导出完整会话为 Markdown
  static String exportToMarkdown(Conversation conversation) {
    final buffer = StringBuffer();

    // 标题
    buffer.writeln('# ${conversation.title}');
    buffer.writeln();

    // 元数据
    buffer.writeln('**创建时间**: ${_formatDateTime(conversation.createdAt)}  ');
    buffer.writeln('**最后更新**: ${_formatDateTime(conversation.updatedAt)}  ');
    buffer.writeln('**消息数量**: ${conversation.messages.length}');
    
    if (conversation.systemPrompt != null) {
      buffer.writeln('**角色设定**: ${conversation.systemPrompt}');
    }
    
    buffer.writeln();
    buffer.writeln('---');
    buffer.writeln();

    // 消息内容
    for (var message in conversation.messages) {
      buffer.writeln(_formatMessageMarkdown(message));
      buffer.writeln();
    }

    return buffer.toString();
  }

  /// 导出完整会话为纯文本
  static String exportToText(Conversation conversation) {
    final buffer = StringBuffer();

    // 标题
    buffer.writeln('=' * 60);
    buffer.writeln(conversation.title);
    buffer.writeln('=' * 60);
    buffer.writeln();

    // 元数据
    buffer.writeln('创建时间: ${_formatDateTime(conversation.createdAt)}');
    buffer.writeln('最后更新: ${_formatDateTime(conversation.updatedAt)}');
    buffer.writeln('消息数量: ${conversation.messages.length}');
    
    if (conversation.systemPrompt != null) {
      buffer.writeln('角色设定: ${conversation.systemPrompt}');
    }
    
    buffer.writeln();
    buffer.writeln('-' * 60);
    buffer.writeln();

    // 消息内容
    for (var message in conversation.messages) {
      buffer.writeln(_formatMessageText(message));
      buffer.writeln();
    }

    return buffer.toString();
  }

  /// 格式化消息为 Markdown
  static String _formatMessageMarkdown(Message message) {
    final buffer = StringBuffer();
    
    final sender = message.isUser ? '👤 **用户**' : '🤖 **AI**';
    final time = _formatDateTime(message.timestamp);
    
    buffer.writeln('### $sender');
    buffer.writeln('*$time*');
    buffer.writeln();
    buffer.writeln(message.content);
    buffer.writeln();
    buffer.writeln('---');
    
    return buffer.toString();
  }

  /// 格式化消息为纯文本
  static String _formatMessageText(Message message) {
    final buffer = StringBuffer();
    
    final sender = message.isUser ? '[用户]' : '[AI]';
    final time = _formatDateTime(message.timestamp);
    
    buffer.writeln('$sender $time');
    buffer.writeln(message.content);
    buffer.writeln('-' * 60);
    
    return buffer.toString();
  }

  /// 格式化日期时间
  static String _formatDateTime(DateTime dt) {
    return '${dt.year}-${_pad(dt.month)}-${_pad(dt.day)} '
        '${_pad(dt.hour)}:${_pad(dt.minute)}:${_pad(dt.second)}';
  }

  /// 补零
  static String _pad(int n) => n.toString().padLeft(2, '0');

  /// 保存文件到设备
  static Future<String> saveToFile(
    String content,
    String fileName,
  ) async {
    try {
      // 获取下载目录（Android）
      Directory? directory;
      
      if (Platform.isAndroid) {
        directory = await getExternalStorageDirectory();
      } else {
        directory = await getApplicationDocumentsDirectory();
      }

      if (directory == null) {
        throw Exception('无法访问存储目录');
      }

      // 创建 ChatBox 子目录
      final chatBoxDir = Directory('${directory.path}/ChatBox');
      if (!await chatBoxDir.exists()) {
        await chatBoxDir.create(recursive: true);
      }

      // 保存文件
      final file = File('${chatBoxDir.path}/$fileName');
      await file.writeAsString(content, flush: true);

      return file.path;
    } catch (e) {
      throw Exception('保存文件失败: $e');
    }
  }

  /// 生成文件名
  static String generateFileName(String baseName, String extension) {
    final sanitized = baseName.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    return '${sanitized}_$timestamp.$extension';
  }

  /// 生成单条消息文件名
  static String generateSingleMessageFileName(String extension) {
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    return '消息_$timestamp.$extension';
  }

  /// 生成多条消息文件名
  static String generateMultiMessageFileName(String title, int count, String extension) {
    final sanitized = title.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    if (count == 1) {
      return '${sanitized}_单条_$timestamp.$extension';
    }
    return '${sanitized}_$count条_$timestamp.$extension';
  }
}
