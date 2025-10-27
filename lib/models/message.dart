/// 消息模型
class Message {
  final String id;
  String content; // 改为可变，支持编辑
  final bool isUser;
  final DateTime timestamp;
  int? inputTokens;  // 输入 token 数量
  int? outputTokens; // 输出 token 数量

  Message({
    required this.id,
    required this.content,
    required this.isUser,
    required this.timestamp,
    this.inputTokens,
    this.outputTokens,
  });

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'content': content,
      'isUser': isUser,
      'timestamp': timestamp.toIso8601String(),
      'inputTokens': inputTokens,
      'outputTokens': outputTokens,
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
    );
  }
}

