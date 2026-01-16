import 'dart:typed_data';
import 'package:hive/hive.dart';

part 'rp_entry_blob.g.dart';

/// 条目内容（不可变）
///
/// 存储记忆条目的完整内容，采用 COW 模式
/// Box: rp_entry_blobs, Key: blobId
@HiveType(typeId: 53)
class RpEntryBlob {
  @HiveField(0)
  final String blobId;

  @HiveField(1)
  final String storyId;

  /// 逻辑 ID，格式: `rp:v1:<domainCode>:<entityKey>:<entryType>[:<subKey>]`
  @HiveField(2)
  final String logicalId;

  /// RpScope.index
  @HiveField(3)
  final int scopeIndex;

  @HiveField(4)
  final String branchId;

  /// RpStatus.index
  @HiveField(5)
  final int statusIndex;

  /// 领域标识（scene, character, state, etc.）
  @HiveField(6)
  final String domain;

  /// 条目类型（card.base, state, event, etc.）
  @HiveField(7)
  final String entryType;

  /// 内容 JSON，UTF-8 编码存储
  @HiveField(8)
  final Uint8List contentJsonUtf8;

  /// 预览文本（用于 UI 显示）
  @HiveField(9)
  final String? preview;

  /// 标签列表
  @HiveField(10)
  final List<String> tags;

  /// 证据引用列表
  @HiveField(11)
  final List<RpEvidenceRef> evidence;

  @HiveField(12)
  final int createdAtMs;

  /// 关联的对话源版本号
  @HiveField(13)
  final int sourceRev;

  /// 近似 token 数（用于预算计算）
  @HiveField(14)
  final int? approxTokens;

  RpEntryBlob({
    required this.blobId,
    required this.storyId,
    required this.logicalId,
    required this.scopeIndex,
    required this.branchId,
    required this.statusIndex,
    required this.domain,
    required this.entryType,
    required this.contentJsonUtf8,
    this.preview,
    List<String>? tags,
    List<RpEvidenceRef>? evidence,
    int? createdAtMs,
    required this.sourceRev,
    this.approxTokens,
  })  : tags = tags ?? [],
        evidence = evidence ?? [],
        createdAtMs = createdAtMs ?? DateTime.now().millisecondsSinceEpoch;

  /// 从 UTF-8 字节解码 JSON 字符串
  String get contentJson => String.fromCharCodes(contentJsonUtf8);

  /// 创建带有新内容的副本（COW 模式需要新 blobId）
  RpEntryBlob copyWithContent({
    required String newBlobId,
    required Uint8List newContentJsonUtf8,
    String? newPreview,
    int? newApproxTokens,
    int? newSourceRev,
  }) {
    return RpEntryBlob(
      blobId: newBlobId,
      storyId: storyId,
      logicalId: logicalId,
      scopeIndex: scopeIndex,
      branchId: branchId,
      statusIndex: statusIndex,
      domain: domain,
      entryType: entryType,
      contentJsonUtf8: newContentJsonUtf8,
      preview: newPreview ?? preview,
      tags: List.from(tags),
      evidence: List.from(evidence),
      sourceRev: newSourceRev ?? sourceRev,
      approxTokens: newApproxTokens ?? approxTokens,
    );
  }
}

/// 证据引用
///
/// 记录条目内容的来源依据
@HiveType(typeId: 54)
class RpEvidenceRef {
  /// 引用类型: 'msg' | 'op' | 'user_edit' | 'external'
  @HiveField(0)
  final String type;

  /// 引用 ID（消息 ID、操作 ID 等）
  @HiveField(1)
  final String refId;

  /// 引用内容起始位置（可选）
  @HiveField(2)
  final int? start;

  /// 引用内容结束位置（可选）
  @HiveField(3)
  final int? end;

  /// 备注说明（可选）
  @HiveField(4)
  final String? note;

  RpEvidenceRef({
    required this.type,
    required this.refId,
    this.start,
    this.end,
    this.note,
  });

  /// 创建消息引用
  factory RpEvidenceRef.fromMessage(String messageId, {int? start, int? end, String? note}) {
    return RpEvidenceRef(
      type: 'msg',
      refId: messageId,
      start: start,
      end: end,
      note: note,
    );
  }

  /// 创建操作引用
  factory RpEvidenceRef.fromOperation(String opKey, {String? note}) {
    return RpEvidenceRef(
      type: 'op',
      refId: opKey,
      note: note,
    );
  }

  /// 创建用户编辑引用
  factory RpEvidenceRef.fromUserEdit(String editId, {String? note}) {
    return RpEvidenceRef(
      type: 'user_edit',
      refId: editId,
      note: note,
    );
  }
}
