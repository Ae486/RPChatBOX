import 'attached_file.dart';

/// 消息模型
class Message {
  final String id;
  String content; // 改为可变，支持编辑
  final bool isUser;
  final DateTime timestamp;
  int? inputTokens;  // 输入 token 数量
  int? outputTokens; // 输出 token 数量
  String? modelName; // AI消息的模型名称
  String? providerName; // AI消息的供应商名称
  List<AttachedFileSnapshot>? attachedFiles; // 用户消息的附件快照列表

  Message({
    required this.id,
    required this.content,
    required this.isUser,
    required this.timestamp,
    this.inputTokens,
    this.outputTokens,
    this.modelName,
    this.providerName,
    this.attachedFiles,
  });

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'content': content,
      'isUser': isUser,
      'timestamp': timestamp.toIso8601String(),
      'inputTokens': inputTokens,
      'outputTokens': outputTokens,
      'modelName': modelName,
      'providerName': providerName,
      'attachedFiles': attachedFiles?.map((f) => f.toJson()).toList(),
    };
  }

  factory Message.fromJson(Map<String, dynamic> json) {
    return Message(
      id: json['id'] as String,
      content: json['content'] as String,
      isUser: json['isUser'] as bool,
      timestamp: DateTime.parse(json['timestamp'] as String),
      inputTokens: json['inputTokens'] as int?,
      outputTokens: json['outputTokens'] as int?,
      modelName: json['modelName'] as String?,
      providerName: json['providerName'] as String?,
      attachedFiles: (json['attachedFiles'] as List?)
          ?.map((f) => AttachedFileSnapshot.fromJson(f as Map<String, dynamic>))
          .toList(),
    );
  }
}

