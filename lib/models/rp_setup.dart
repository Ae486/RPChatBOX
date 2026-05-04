class SetupDialogueMessage {
  final String role;
  final String content;

  const SetupDialogueMessage({required this.role, required this.content});

  Map<String, dynamic> toJson() => {'role': role, 'content': content};
}

class RpSetupStepState {
  final String stepId;
  final String state;
  final int discussionRound;
  final int reviewRound;
  final String? lastProposalId;
  final String? lastCommitId;
  final DateTime updatedAt;

  const RpSetupStepState({
    required this.stepId,
    required this.state,
    required this.discussionRound,
    required this.reviewRound,
    required this.lastProposalId,
    required this.lastCommitId,
    required this.updatedAt,
  });

  factory RpSetupStepState.fromJson(Map<String, dynamic> json) {
    return RpSetupStepState(
      stepId: json['step_id'] as String,
      state: json['state'] as String,
      discussionRound: json['discussion_round'] as int? ?? 0,
      reviewRound: json['review_round'] as int? ?? 0,
      lastProposalId: json['last_proposal_id'] as String?,
      lastCommitId: json['last_commit_id'] as String?,
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpSetupStageState {
  final String stageId;
  final String state;
  final int discussionRound;
  final int reviewRound;
  final String? lastProposalId;
  final String? lastCommitId;
  final DateTime updatedAt;

  const RpSetupStageState({
    required this.stageId,
    required this.state,
    required this.discussionRound,
    required this.reviewRound,
    required this.lastProposalId,
    required this.lastCommitId,
    required this.updatedAt,
  });

  factory RpSetupStageState.fromJson(Map<String, dynamic> json) {
    return RpSetupStageState(
      stageId: json['stage_id'] as String,
      state: json['state'] as String,
      discussionRound: json['discussion_round'] as int? ?? 0,
      reviewRound: json['review_round'] as int? ?? 0,
      lastProposalId: json['last_proposal_id'] as String?,
      lastCommitId: json['last_commit_id'] as String?,
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpSetupDraftSection {
  final String sectionId;
  final String title;
  final String kind;
  final Map<String, dynamic> content;
  final String retrievalRole;
  final List<String> tags;

  const RpSetupDraftSection({
    required this.sectionId,
    required this.title,
    required this.kind,
    required this.content,
    required this.retrievalRole,
    required this.tags,
  });

  factory RpSetupDraftSection.fromJson(Map<String, dynamic> json) {
    return RpSetupDraftSection(
      sectionId: json['section_id'] as String,
      title: json['title'] as String,
      kind: json['kind'] as String,
      content: json['content'] is Map
          ? Map<String, dynamic>.from(json['content'] as Map)
          : const <String, dynamic>{},
      retrievalRole: json['retrieval_role'] as String? ?? 'detail',
      tags: (json['tags'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class RpSetupDraftEntry {
  final String entryId;
  final String entryType;
  final String semanticPath;
  final String title;
  final String? displayLabel;
  final String? summary;
  final List<String> aliases;
  final List<String> tags;
  final List<RpSetupDraftSection> sections;

  const RpSetupDraftEntry({
    required this.entryId,
    required this.entryType,
    required this.semanticPath,
    required this.title,
    required this.displayLabel,
    required this.summary,
    required this.aliases,
    required this.tags,
    required this.sections,
  });

  factory RpSetupDraftEntry.fromJson(Map<String, dynamic> json) {
    return RpSetupDraftEntry(
      entryId: json['entry_id'] as String,
      entryType: json['entry_type'] as String,
      semanticPath: json['semantic_path'] as String,
      title: json['title'] as String,
      displayLabel: json['display_label'] as String?,
      summary: json['summary'] as String?,
      aliases: (json['aliases'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      tags: (json['tags'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      sections: (json['sections'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpSetupDraftSection.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
    );
  }
}

class RpSetupStageDraftBlock {
  final String stageId;
  final List<RpSetupDraftEntry> entries;
  final String? notes;

  const RpSetupStageDraftBlock({
    required this.stageId,
    required this.entries,
    required this.notes,
  });

  factory RpSetupStageDraftBlock.fromJson(Map<String, dynamic> json) {
    return RpSetupStageDraftBlock(
      stageId: json['stage_id'] as String,
      entries: (json['entries'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpSetupDraftEntry.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      notes: json['notes'] as String?,
    );
  }
}

class RpSetupCommitProposal {
  final String proposalId;
  final String stepId;
  final String status;
  final List<String> targetBlockTypes;
  final List<String> targetDraftRefs;
  final String reviewMessage;
  final String? reason;
  final List<String> unresolvedWarnings;
  final List<String> suggestedIngestionTargets;
  final DateTime createdAt;

  const RpSetupCommitProposal({
    required this.proposalId,
    required this.stepId,
    required this.status,
    required this.targetBlockTypes,
    required this.targetDraftRefs,
    required this.reviewMessage,
    required this.reason,
    required this.unresolvedWarnings,
    required this.suggestedIngestionTargets,
    required this.createdAt,
  });

  bool get isPendingReview => status == 'pending_review';

  factory RpSetupCommitProposal.fromJson(Map<String, dynamic> json) {
    return RpSetupCommitProposal(
      proposalId: json['proposal_id'] as String,
      stepId: json['step_id'] as String,
      status: json['status'] as String,
      targetBlockTypes: (json['target_block_types'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      targetDraftRefs: (json['target_draft_refs'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      reviewMessage: json['review_message'] as String? ?? '',
      reason: json['reason'] as String?,
      unresolvedWarnings: (json['unresolved_warnings'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      suggestedIngestionTargets:
          (json['suggested_ingestion_targets'] as List? ?? const [])
              .map((item) => item.toString())
              .toList(),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class RpSetupAcceptedCommit {
  final String commitId;
  final String stepId;
  final String? summaryTier0;
  final String? summaryTier1;
  final List<String> spotlights;
  final DateTime createdAt;

  const RpSetupAcceptedCommit({
    required this.commitId,
    required this.stepId,
    required this.summaryTier0,
    required this.summaryTier1,
    required this.spotlights,
    required this.createdAt,
  });

  factory RpSetupAcceptedCommit.fromJson(Map<String, dynamic> json) {
    return RpSetupAcceptedCommit(
      commitId: json['commit_id'] as String,
      stepId: json['step_id'] as String,
      summaryTier0: json['summary_tier_0'] as String?,
      summaryTier1: json['summary_tier_1'] as String?,
      spotlights: (json['spotlights'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class RpSetupIngestionJob {
  final String jobId;
  final String commitId;
  final String stepId;
  final String targetType;
  final String targetRef;
  final String state;
  final List<String> warnings;
  final String? errorMessage;
  final DateTime createdAt;

  const RpSetupIngestionJob({
    required this.jobId,
    required this.commitId,
    required this.stepId,
    required this.targetType,
    required this.targetRef,
    required this.state,
    required this.warnings,
    required this.errorMessage,
    required this.createdAt,
  });

  factory RpSetupIngestionJob.fromJson(Map<String, dynamic> json) {
    return RpSetupIngestionJob(
      jobId: json['job_id'] as String,
      commitId: json['commit_id'] as String,
      stepId: json['step_id'] as String,
      targetType: json['target_type'] as String,
      targetRef: json['target_ref'] as String,
      state: json['state'] as String,
      warnings: (json['warnings'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      errorMessage: json['error_message'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class RpReadinessStatus {
  final Map<String, String> stepReadiness;
  final List<String> blockingIssues;
  final List<String> warnings;

  const RpReadinessStatus({
    required this.stepReadiness,
    required this.blockingIssues,
    required this.warnings,
  });

  factory RpReadinessStatus.fromJson(Map<String, dynamic> json) {
    return RpReadinessStatus(
      stepReadiness: (json['step_readiness'] as Map? ?? const {}).map(
        (key, value) => MapEntry(key.toString(), value.toString()),
      ),
      blockingIssues: (json['blocking_issues'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      warnings: (json['warnings'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class RpActivationHandoff {
  final String handoffId;
  final String workspaceId;
  final String storyId;
  final String mode;
  final List<String> foundationCommitRefs;
  final String? blueprintCommitRef;
  final List<String> archivalReadyRefs;

  const RpActivationHandoff({
    required this.handoffId,
    required this.workspaceId,
    required this.storyId,
    required this.mode,
    required this.foundationCommitRefs,
    required this.blueprintCommitRef,
    required this.archivalReadyRefs,
  });

  factory RpActivationHandoff.fromJson(Map<String, dynamic> json) {
    return RpActivationHandoff(
      handoffId: json['handoff_id'] as String,
      workspaceId: json['workspace_id'] as String,
      storyId: json['story_id'] as String,
      mode: json['mode'] as String,
      foundationCommitRefs:
          (json['foundation_commit_refs'] as List? ?? const [])
              .map((item) => item.toString())
              .toList(),
      blueprintCommitRef: json['blueprint_commit_ref'] as String?,
      archivalReadyRefs: (json['archival_ready_refs'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class RpActivationCheckResult {
  final String workspaceId;
  final bool ready;
  final List<String> blockingIssues;
  final List<String> warnings;
  final RpActivationHandoff? handoff;

  const RpActivationCheckResult({
    required this.workspaceId,
    required this.ready,
    required this.blockingIssues,
    required this.warnings,
    required this.handoff,
  });

  factory RpActivationCheckResult.fromJson(Map<String, dynamic> json) {
    return RpActivationCheckResult(
      workspaceId: json['workspace_id'] as String,
      ready: json['ready'] as bool? ?? false,
      blockingIssues: (json['blocking_issues'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      warnings: (json['warnings'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      handoff: json['handoff'] is Map<String, dynamic>
          ? RpActivationHandoff.fromJson(
              json['handoff'] as Map<String, dynamic>,
            )
          : null,
    );
  }
}

class RpSetupWorkspace {
  final String workspaceId;
  final String storyId;
  final String mode;
  final String workspaceState;
  final String currentStep;
  final String? currentStage;
  final List<String> stagePlan;
  final List<RpSetupStepState> stepStates;
  final List<RpSetupStageState> stageStates;
  final Map<String, RpSetupStageDraftBlock> stageDraftBlocks;
  final Map<String, dynamic>? storyConfigDraft;
  final Map<String, dynamic>? writingContractDraft;
  final Map<String, dynamic>? foundationDraft;
  final Map<String, dynamic>? longformBlueprintDraft;
  final List<Map<String, dynamic>> importedAssets;
  final List<RpSetupCommitProposal> commitProposals;
  final List<RpSetupAcceptedCommit> acceptedCommits;
  final List<RpSetupIngestionJob> retrievalIngestionJobs;
  final RpReadinessStatus readinessStatus;
  final String? activatedStorySessionId;
  final int version;
  final DateTime updatedAt;

  const RpSetupWorkspace({
    required this.workspaceId,
    required this.storyId,
    required this.mode,
    required this.workspaceState,
    required this.currentStep,
    required this.currentStage,
    required this.stagePlan,
    required this.stepStates,
    required this.stageStates,
    required this.stageDraftBlocks,
    required this.storyConfigDraft,
    required this.writingContractDraft,
    required this.foundationDraft,
    required this.longformBlueprintDraft,
    required this.importedAssets,
    required this.commitProposals,
    required this.acceptedCommits,
    required this.retrievalIngestionJobs,
    required this.readinessStatus,
    required this.activatedStorySessionId,
    required this.version,
    required this.updatedAt,
  });

  List<RpSetupCommitProposal> get pendingCommitProposals =>
      commitProposals.where((proposal) => proposal.isPendingReview).toList();

  RpSetupStageDraftBlock? stageBlock(String stageId) =>
      stageDraftBlocks[stageId];

  factory RpSetupWorkspace.fromJson(Map<String, dynamic> json) {
    return RpSetupWorkspace(
      workspaceId: json['workspace_id'] as String,
      storyId: json['story_id'] as String,
      mode: json['mode'] as String,
      workspaceState: json['workspace_state'] as String,
      currentStep: json['current_step'] as String,
      currentStage: json['current_stage'] as String?,
      stagePlan: (json['stage_plan'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      stepStates: (json['step_states'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpSetupStepState.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      stageStates: (json['stage_states'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpSetupStageState.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      stageDraftBlocks: (json['draft_blocks'] as Map? ?? const {}).map(
        (key, value) => MapEntry(
          key.toString(),
          RpSetupStageDraftBlock.fromJson(
            Map<String, dynamic>.from(value as Map),
          ),
        ),
      ),
      storyConfigDraft: json['story_config_draft'] is Map
          ? Map<String, dynamic>.from(json['story_config_draft'] as Map)
          : null,
      writingContractDraft: json['writing_contract_draft'] is Map
          ? Map<String, dynamic>.from(json['writing_contract_draft'] as Map)
          : null,
      foundationDraft: json['foundation_draft'] is Map
          ? Map<String, dynamic>.from(json['foundation_draft'] as Map)
          : null,
      longformBlueprintDraft: json['longform_blueprint_draft'] is Map
          ? Map<String, dynamic>.from(json['longform_blueprint_draft'] as Map)
          : null,
      importedAssets: (json['imported_assets'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(),
      commitProposals: (json['commit_proposals'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpSetupCommitProposal.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      acceptedCommits: (json['accepted_commits'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpSetupAcceptedCommit.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      retrievalIngestionJobs:
          (json['retrieval_ingestion_jobs'] as List? ?? const [])
              .whereType<Map>()
              .map(
                (item) => RpSetupIngestionJob.fromJson(
                  Map<String, dynamic>.from(item),
                ),
              )
              .toList(),
      readinessStatus: RpReadinessStatus.fromJson(
        Map<String, dynamic>.from(json['readiness_status'] as Map? ?? const {}),
      ),
      activatedStorySessionId: json['activated_story_session_id'] as String?,
      version: json['version'] as int? ?? 1,
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}
