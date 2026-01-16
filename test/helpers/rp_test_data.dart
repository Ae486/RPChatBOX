import 'dart:convert';
import 'dart:typed_data';
import 'package:chatboxapp/models/roleplay/rp_story_meta.dart';
import 'package:chatboxapp/models/roleplay/rp_entry_blob.dart';
import 'package:chatboxapp/models/roleplay/rp_operation.dart';
import 'package:chatboxapp/models/roleplay/rp_snapshot.dart';
import 'package:chatboxapp/models/roleplay/rp_proposal.dart';

/// Roleplay 测试数据工厂
class RpTestData {
  static const String defaultStoryId = 'story-test-001';
  static const String defaultBranchId = 'main';

  /// 创建测试 StoryMeta
  static RpStoryMeta createStoryMeta({
    String? storyId,
    String? activeBranchId,
    List<RpHead>? heads,
    List<RpModuleState>? modules,
  }) {
    return RpStoryMeta(
      storyId: storyId ?? defaultStoryId,
      schemaVersion: 1,
      activeBranchId: activeBranchId ?? defaultBranchId,
      heads: heads ??
          [
            RpHead(
              scopeIndex: 0,
              branchId: defaultBranchId,
              rev: 0,
              lastSnapshotRev: 0,
            ),
            RpHead(
              scopeIndex: 1,
              branchId: defaultBranchId,
              rev: 0,
              lastSnapshotRev: 0,
            ),
          ],
      modules: modules ??
          [
            RpModuleState(moduleId: 'scene', enabled: true),
            RpModuleState(moduleId: 'character', enabled: true),
            RpModuleState(moduleId: 'state', enabled: true),
          ],
    );
  }

  /// 创建测试 EntryBlob
  static RpEntryBlob createBlob({
    String? blobId,
    String? storyId,
    String? logicalId,
    int scopeIndex = 1,
    String? branchId,
    int statusIndex = 0,
    String domain = 'scene',
    String entryType = 'state',
    Map<String, dynamic>? content,
    String? preview,
    int sourceRev = 1,
  }) {
    final jsonContent = content ?? {'name': 'Test Scene', 'desc': 'Test'};
    return RpEntryBlob(
      blobId: blobId ?? 'blob-${DateTime.now().microsecondsSinceEpoch}',
      storyId: storyId ?? defaultStoryId,
      logicalId: logicalId ?? 'rp:v1:scene:main:state',
      scopeIndex: scopeIndex,
      branchId: branchId ?? defaultBranchId,
      statusIndex: statusIndex,
      domain: domain,
      entryType: entryType,
      contentJsonUtf8: Uint8List.fromList(utf8.encode(jsonEncode(jsonContent))),
      preview: preview ?? 'Test Scene',
      sourceRev: sourceRev,
      approxTokens: 50,
    );
  }

  /// 创建测试 Operation
  static RpOperation createOperation({
    String? storyId,
    int scopeIndex = 1,
    String? branchId,
    int rev = 1,
    int sourceRev = 1,
    List<RpEntryChange>? changes,
  }) {
    return RpOperation(
      storyId: storyId ?? defaultStoryId,
      scopeIndex: scopeIndex,
      branchId: branchId ?? defaultBranchId,
      rev: rev,
      sourceRev: sourceRev,
      changes: changes ??
          [
            RpEntryChange(
              logicalId: 'rp:v1:scene:main:state',
              domain: 'scene',
              afterBlobId: 'blob-001',
              reasonKindIndex: 0, // RpChangeReason.agentProposal
            ),
          ],
    );
  }

  /// 创建测试 Snapshot
  static RpSnapshot createSnapshot({
    String? storyId,
    int scopeIndex = 1,
    String? branchId,
    int rev = 1,
    int sourceRev = 1,
    Map<String, String>? pointers,
    Map<String, List<String>>? byDomain,
  }) {
    return RpSnapshot(
      storyId: storyId ?? defaultStoryId,
      scopeIndex: scopeIndex,
      branchId: branchId ?? defaultBranchId,
      rev: rev,
      sourceRev: sourceRev,
      pointers: pointers ?? {'rp:v1:scene:main:state': 'blob-001'},
      byDomain: byDomain ??
          {
            'scene': ['rp:v1:scene:main:state']
          },
    );
  }

  /// 创建测试 Proposal
  static RpProposal createProposal({
    String? proposalId,
    String? storyId,
    String? branchId,
    int kindIndex = 0,
    String domain = 'scene',
    int policyTierIndex = 0,
    RpProposalTarget? target,
    Map<String, dynamic>? payload,
    String reason = 'Test proposal',
    int sourceRev = 1,
    int expectedFoundationRev = 0,
    int expectedStoryRev = 0,
    int decisionIndex = 0,
  }) {
    final payloadJson = payload ?? {'action': 'update', 'data': {}};
    return RpProposal(
      proposalId: proposalId ?? 'proposal-${DateTime.now().microsecondsSinceEpoch}',
      storyId: storyId ?? defaultStoryId,
      branchId: branchId ?? defaultBranchId,
      kindIndex: kindIndex,
      domain: domain,
      policyTierIndex: policyTierIndex,
      target: target ??
          RpProposalTarget(
            scopeIndex: 1,
            branchId: defaultBranchId,
            statusIndex: 0,
            logicalId: 'rp:v1:scene:main:state',
          ),
      payloadJsonUtf8: Uint8List.fromList(utf8.encode(jsonEncode(payloadJson))),
      reason: reason,
      sourceRev: sourceRev,
      expectedFoundationRev: expectedFoundationRev,
      expectedStoryRev: expectedStoryRev,
      decisionIndex: decisionIndex,
    );
  }
}
