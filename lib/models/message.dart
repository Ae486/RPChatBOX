/// INPUT: User/assistant message content + metadata (tokens, provider, attachments)
/// OUTPUT: Message model for persistence and UI adapters
/// POS: Models / Base Chat / Message
import 'package:hive/hive.dart';
import 'attached_file.dart';

part 'message.g.dart';

/// 消息模型
@HiveType(typeId: 1)
class Message {
  @HiveField(0)
  final String id;
  @HiveField(1)
  String content; // 改为可变，支持编辑
  @HiveField(2)
  final bool isUser;
  @HiveField(3)
  final DateTime timestamp;
  @HiveField(4)
  int? inputTokens;  // 输入 token 数量
  @HiveField(5)
  int? outputTokens; // 输出 token 数量
  @HiveField(6)
  String? modelName; // AI消息的模型名称
  @HiveField(7)
  String? providerName; // AI消息的供应商名称
  @HiveField(8)
  List<AttachedFileSnapshot>? attachedFiles; // 用户消息的附件快照列表
  @HiveField(9)
  String? parentId; // 树结构父节点（可空，兼容旧数据）
  @HiveField(10)
  DateTime? editedAt; // 编辑时间（可空，兼容旧数据）
  @HiveField(11)
  int? thinkingDurationSeconds; // 思考耗时（秒），用于 UI 显示

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
    this.parentId,
    this.editedAt,
    this.thinkingDurationSeconds,
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
      'parentId': parentId,
      'editedAt': editedAt?.toIso8601String(),
      'thinkingDurationSeconds': thinkingDurationSeconds,
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
          ?.whereType<Map<String, dynamic>>()
          .map((f) => AttachedFileSnapshot.fromJson(f))
          .toList(),
      parentId: json['parentId'] as String?,
      editedAt: json['editedAt'] != null
          ? DateTime.tryParse(json['editedAt'] as String)
          : null,
      thinkingDurationSeconds: json['thinkingDurationSeconds'] as int?,
    );
  }
}

