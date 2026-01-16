/// Roleplay Feature 枚举定义
///
/// 存储策略：使用 index 存储为 int，避免字符串膨胀
/// 例如：RpScope.foundation.index → 0
library;

/// 条目作用域
enum RpScope {
  /// 基底（跨分支共享）
  foundation,
  /// 剧情（分支隔离）
  story,
}

/// 条目状态
enum RpStatus {
  /// 已确认（权威）
  confirmed,
  /// 草稿（待审核）
  draft,
}

/// 提议策略层级
enum RpPolicyTier {
  /// 静默应用
  silent,
  /// 通知后应用
  notifyApply,
  /// 需要审核
  reviewRequired,
}

/// 提议类型
enum RpProposalKind {
  /// 写入 confirmed 条目
  confirmedWrite,
  /// 写入 draft 条目
  draftUpdate,
  /// 伏笔链接更新
  linkUpdate,
  /// 场景切换
  sceneTransition,
  /// 摘要压缩
  compressionUpdate,
  /// 一致性修复建议
  outputFix,
  /// 用户编辑解释
  userEditInterpretation,
}

/// 提议决策
enum RpProposalDecision {
  /// 待处理
  pending,
  /// 已应用
  applied,
  /// 已拒绝
  rejected,
  /// 已被取代
  superseded,
}

/// 变更原因
enum RpChangeReason {
  /// Agent 提议
  agentProposal,
  /// 用户直接操作
  userDirect,
  /// 系统合并
  systemMerge,
  /// 回滚操作
  rollback,
}

/// 枚举工具扩展
extension RpScopeExt on RpScope {
  static RpScope fromIndex(int index) => RpScope.values[index];
}

extension RpStatusExt on RpStatus {
  static RpStatus fromIndex(int index) => RpStatus.values[index];
}

extension RpPolicyTierExt on RpPolicyTier {
  static RpPolicyTier fromIndex(int index) => RpPolicyTier.values[index];
}

extension RpProposalKindExt on RpProposalKind {
  static RpProposalKind fromIndex(int index) => RpProposalKind.values[index];
}

extension RpProposalDecisionExt on RpProposalDecision {
  static RpProposalDecision fromIndex(int index) =>
      RpProposalDecision.values[index];
}

extension RpChangeReasonExt on RpChangeReason {
  static RpChangeReason fromIndex(int index) => RpChangeReason.values[index];
}
