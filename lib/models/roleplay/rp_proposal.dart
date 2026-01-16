import 'dart:typed_data';
import 'package:hive/hive.dart';
import 'rp_entry_blob.dart';

part 'rp_proposal.g.dart';

/// 提议
///
/// Agent 生成的变更提议，待用户或系统审核
/// Box: rp_proposals, Key: proposalId
@HiveType(typeId: 58)
class RpProposal {
  @HiveField(0)
  final String proposalId;

  @HiveField(1)
  final String storyId;

  @HiveField(2)
  final String branchId;

  @HiveField(3)
  final int createdAtMs;

  /// RpProposalKind.index
  @HiveField(4)
  final int kindIndex;

  /// 领域标识
  @HiveField(5)
  final String domain;

  /// RpPolicyTier.index
  @HiveField(6)
  final int policyTierIndex;

  /// 目标条目
  @HiveField(7)
  final RpProposalTarget target;

  /// 提议内容 JSON，UTF-8 编码存储
  @HiveField(8)
  final Uint8List payloadJsonUtf8;

  /// 证据引用列表
  @HiveField(9)
  final List<RpEvidenceRef> evidence;

  /// 提议原因说明
  @HiveField(10)
  final String reason;

  /// 关联的对话源版本号
  @HiveField(11)
  final int sourceRev;

  /// 期望的 foundation 版本号
  @HiveField(12)
  final int expectedFoundationRev;

  /// 期望的 story 版本号
  @HiveField(13)
  final int expectedStoryRev;

  /// RpProposalDecision.index（可变）
  @HiveField(14)
  int decisionIndex;

  /// 决策时间戳（可选）
  @HiveField(15)
  int? decidedAtMs;

  /// 决策者（可选）: 'user' | 'system' | agent_id
  @HiveField(16)
  String? decidedBy;

  /// 决策说明（可选）
  @HiveField(17)
  String? decisionNote;

  RpProposal({
    required this.proposalId,
    required this.storyId,
    required this.branchId,
    int? createdAtMs,
    required this.kindIndex,
    required this.domain,
    required this.policyTierIndex,
    required this.target,
    required this.payloadJsonUtf8,
    List<RpEvidenceRef>? evidence,
    required this.reason,
    required this.sourceRev,
    required this.expectedFoundationRev,
    required this.expectedStoryRev,
    this.decisionIndex = 0, // RpProposalDecision.pending
    this.decidedAtMs,
    this.decidedBy,
    this.decisionNote,
  })  : createdAtMs = createdAtMs ?? DateTime.now().millisecondsSinceEpoch,
        evidence = evidence ?? [];

  /// 从 UTF-8 字节解码 JSON 字符串
  String get payloadJson => String.fromCharCodes(payloadJsonUtf8);

  /// 是否待处理
  bool get isPending => decisionIndex == 0;

  /// 是否已应用
  bool get isApplied => decisionIndex == 1;

  /// 是否已拒绝
  bool get isRejected => decisionIndex == 2;

  /// 是否已被取代
  bool get isSuperseded => decisionIndex == 3;

  /// 应用提议
  void apply({String? by, String? note}) {
    decisionIndex = 1; // RpProposalDecision.applied
    decidedAtMs = DateTime.now().millisecondsSinceEpoch;
    decidedBy = by ?? 'system';
    decisionNote = note;
  }

  /// 拒绝提议
  void reject({String? by, String? note}) {
    decisionIndex = 2; // RpProposalDecision.rejected
    decidedAtMs = DateTime.now().millisecondsSinceEpoch;
    decidedBy = by ?? 'user';
    decisionNote = note;
  }

  /// 标记为被取代
  void supersede({String? by, String? note}) {
    decisionIndex = 3; // RpProposalDecision.superseded
    decidedAtMs = DateTime.now().millisecondsSinceEpoch;
    decidedBy = by ?? 'system';
    decisionNote = note;
  }
}

/// 提议目标
///
/// 描述提议要修改的条目位置
@HiveType(typeId: 59)
class RpProposalTarget {
  /// RpScope.index
  @HiveField(0)
  final int scopeIndex;

  @HiveField(1)
  final String branchId;

  /// RpStatus.index
  @HiveField(2)
  final int statusIndex;

  /// 逻辑 ID
  @HiveField(3)
  final String logicalId;

  RpProposalTarget({
    required this.scopeIndex,
    required this.branchId,
    required this.statusIndex,
    required this.logicalId,
  });

  /// 创建 foundation/confirmed 目标
  factory RpProposalTarget.foundationConfirmed(String branchId, String logicalId) {
    return RpProposalTarget(
      scopeIndex: 0, // RpScope.foundation
      branchId: branchId,
      statusIndex: 0, // RpStatus.confirmed
      logicalId: logicalId,
    );
  }

  /// 创建 story/confirmed 目标
  factory RpProposalTarget.storyConfirmed(String branchId, String logicalId) {
    return RpProposalTarget(
      scopeIndex: 1, // RpScope.story
      branchId: branchId,
      statusIndex: 0, // RpStatus.confirmed
      logicalId: logicalId,
    );
  }

  /// 创建 story/draft 目标
  factory RpProposalTarget.storyDraft(String branchId, String logicalId) {
    return RpProposalTarget(
      scopeIndex: 1, // RpScope.story
      branchId: branchId,
      statusIndex: 1, // RpStatus.draft
      logicalId: logicalId,
    );
  }
}
