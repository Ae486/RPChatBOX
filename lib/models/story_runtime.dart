class RpStoryActivationResult {
  final String sessionId;
  final String storyId;
  final String sourceWorkspaceId;
  final int currentChapterIndex;
  final String currentPhase;
  final bool initialOutlineRequired;

  const RpStoryActivationResult({
    required this.sessionId,
    required this.storyId,
    required this.sourceWorkspaceId,
    required this.currentChapterIndex,
    required this.currentPhase,
    required this.initialOutlineRequired,
  });

  factory RpStoryActivationResult.fromJson(Map<String, dynamic> json) {
    return RpStoryActivationResult(
      sessionId: json['session_id'] as String,
      storyId: json['story_id'] as String,
      sourceWorkspaceId: json['source_workspace_id'] as String,
      currentChapterIndex: json['current_chapter_index'] as int? ?? 1,
      currentPhase: json['current_phase'] as String? ?? 'outline_drafting',
      initialOutlineRequired: json['initial_outline_required'] as bool? ?? true,
    );
  }
}

class RpStorySession {
  final String sessionId;
  final String storyId;
  final String sourceWorkspaceId;
  final String mode;
  final String sessionState;
  final int currentChapterIndex;
  final String currentPhase;
  final Map<String, dynamic> runtimeStoryConfig;
  final Map<String, dynamic> writerContract;
  final Map<String, dynamic> currentStateJson;
  final DateTime activatedAt;
  final DateTime updatedAt;

  const RpStorySession({
    required this.sessionId,
    required this.storyId,
    required this.sourceWorkspaceId,
    required this.mode,
    required this.sessionState,
    required this.currentChapterIndex,
    required this.currentPhase,
    required this.runtimeStoryConfig,
    required this.writerContract,
    required this.currentStateJson,
    required this.activatedAt,
    required this.updatedAt,
  });

  factory RpStorySession.fromJson(Map<String, dynamic> json) {
    return RpStorySession(
      sessionId: json['session_id'] as String,
      storyId: json['story_id'] as String,
      sourceWorkspaceId: json['source_workspace_id'] as String,
      mode: json['mode'] as String? ?? 'longform',
      sessionState: json['session_state'] as String? ?? 'active',
      currentChapterIndex: json['current_chapter_index'] as int? ?? 1,
      currentPhase: json['current_phase'] as String? ?? 'outline_drafting',
      runtimeStoryConfig: json['runtime_story_config'] is Map
          ? Map<String, dynamic>.from(json['runtime_story_config'] as Map)
          : const {},
      writerContract: json['writer_contract'] is Map
          ? Map<String, dynamic>.from(json['writer_contract'] as Map)
          : const {},
      currentStateJson: json['current_state_json'] is Map
          ? Map<String, dynamic>.from(json['current_state_json'] as Map)
          : const {},
      activatedAt: DateTime.parse(json['activated_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpChapterWorkspace {
  final String chapterWorkspaceId;
  final String sessionId;
  final int chapterIndex;
  final String phase;
  final String? chapterGoal;
  final Map<String, dynamic>? outlineDraftJson;
  final Map<String, dynamic>? acceptedOutlineJson;
  final Map<String, dynamic> builderSnapshotJson;
  final List<String> reviewNotes;
  final List<String> acceptedSegmentIds;
  final String? pendingSegmentArtifactId;
  final DateTime updatedAt;

  const RpChapterWorkspace({
    required this.chapterWorkspaceId,
    required this.sessionId,
    required this.chapterIndex,
    required this.phase,
    required this.chapterGoal,
    required this.outlineDraftJson,
    required this.acceptedOutlineJson,
    required this.builderSnapshotJson,
    required this.reviewNotes,
    required this.acceptedSegmentIds,
    required this.pendingSegmentArtifactId,
    required this.updatedAt,
  });

  factory RpChapterWorkspace.fromJson(Map<String, dynamic> json) {
    return RpChapterWorkspace(
      chapterWorkspaceId: json['chapter_workspace_id'] as String,
      sessionId: json['session_id'] as String,
      chapterIndex: json['chapter_index'] as int? ?? 1,
      phase: json['phase'] as String? ?? 'outline_drafting',
      chapterGoal: json['chapter_goal'] as String?,
      outlineDraftJson: json['outline_draft_json'] is Map
          ? Map<String, dynamic>.from(json['outline_draft_json'] as Map)
          : null,
      acceptedOutlineJson: json['accepted_outline_json'] is Map
          ? Map<String, dynamic>.from(json['accepted_outline_json'] as Map)
          : null,
      builderSnapshotJson: json['builder_snapshot_json'] is Map
          ? Map<String, dynamic>.from(json['builder_snapshot_json'] as Map)
          : const {},
      reviewNotes: (json['review_notes'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      acceptedSegmentIds: (json['accepted_segment_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      pendingSegmentArtifactId: json['pending_segment_artifact_id'] as String?,
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpStoryArtifact {
  final String artifactId;
  final String sessionId;
  final String chapterWorkspaceId;
  final String artifactKind;
  final String status;
  final int revision;
  final String contentText;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;

  const RpStoryArtifact({
    required this.artifactId,
    required this.sessionId,
    required this.chapterWorkspaceId,
    required this.artifactKind,
    required this.status,
    required this.revision,
    required this.contentText,
    required this.metadata,
    required this.createdAt,
  });

  bool get isAccepted => status == 'accepted';
  bool get isDraft => status == 'draft';
  bool get isPendingSegment =>
      artifactKind == 'story_segment' && status == 'draft';

  factory RpStoryArtifact.fromJson(Map<String, dynamic> json) {
    return RpStoryArtifact(
      artifactId: json['artifact_id'] as String,
      sessionId: json['session_id'] as String,
      chapterWorkspaceId: json['chapter_workspace_id'] as String,
      artifactKind: json['artifact_kind'] as String,
      status: json['status'] as String,
      revision: json['revision'] as int? ?? 1,
      contentText: json['content_text'] as String? ?? '',
      metadata: json['metadata'] is Map
          ? Map<String, dynamic>.from(json['metadata'] as Map)
          : const {},
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class RpStoryDiscussionEntry {
  final String entryId;
  final String sessionId;
  final String chapterWorkspaceId;
  final String role;
  final String contentText;
  final String? linkedArtifactId;
  final DateTime createdAt;

  const RpStoryDiscussionEntry({
    required this.entryId,
    required this.sessionId,
    required this.chapterWorkspaceId,
    required this.role,
    required this.contentText,
    required this.linkedArtifactId,
    required this.createdAt,
  });

  factory RpStoryDiscussionEntry.fromJson(Map<String, dynamic> json) {
    return RpStoryDiscussionEntry(
      entryId: json['entry_id'] as String,
      sessionId: json['session_id'] as String,
      chapterWorkspaceId: json['chapter_workspace_id'] as String,
      role: json['role'] as String? ?? 'assistant',
      contentText: json['content_text'] as String? ?? '',
      linkedArtifactId: json['linked_artifact_id'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}

class RpChapterSnapshot {
  final RpStorySession session;
  final RpChapterWorkspace chapter;
  final List<RpStoryArtifact> artifacts;
  final List<RpStoryDiscussionEntry> discussionEntries;

  const RpChapterSnapshot({
    required this.session,
    required this.chapter,
    required this.artifacts,
    required this.discussionEntries,
  });

  List<RpStoryArtifact> get acceptedOutlineArtifacts => artifacts
      .where(
        (item) => item.artifactKind == 'chapter_outline' && item.isAccepted,
      )
      .toList();

  List<RpStoryArtifact> get acceptedSegmentArtifacts => artifacts
      .where((item) => item.artifactKind == 'story_segment' && item.isAccepted)
      .toList();

  RpStoryArtifact? get latestOutlineDraft {
    final items = artifacts
        .where((item) => item.artifactKind == 'chapter_outline' && item.isDraft)
        .toList();
    return items.isEmpty ? null : items.last;
  }

  RpStoryArtifact? get pendingSegment {
    final targetId = chapter.pendingSegmentArtifactId;
    if (targetId != null) {
      for (final item in artifacts) {
        if (item.artifactId == targetId) return item;
      }
    }
    final items = artifacts.where((item) => item.isPendingSegment).toList();
    return items.isEmpty ? null : items.last;
  }

  List<RpStoryArtifact> get pendingSegmentCandidates =>
      artifacts.where((item) => item.isPendingSegment).toList()
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt));

  factory RpChapterSnapshot.fromJson(Map<String, dynamic> json) {
    return RpChapterSnapshot(
      session: RpStorySession.fromJson(
        Map<String, dynamic>.from(json['session'] as Map? ?? const {}),
      ),
      chapter: RpChapterWorkspace.fromJson(
        Map<String, dynamic>.from(json['chapter'] as Map? ?? const {}),
      ),
      artifacts: (json['artifacts'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => RpStoryArtifact.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      discussionEntries: (json['discussion_entries'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => RpStoryDiscussionEntry.fromJson(
              Map<String, dynamic>.from(item),
            ),
          )
          .toList(),
    );
  }
}

class RpStoryTurnResponse {
  final String sessionId;
  final String chapterWorkspaceId;
  final String commandKind;
  final int currentChapterIndex;
  final String currentPhase;
  final String? assistantText;
  final String? artifactId;
  final String? artifactKind;
  final List<String> warnings;

  const RpStoryTurnResponse({
    required this.sessionId,
    required this.chapterWorkspaceId,
    required this.commandKind,
    required this.currentChapterIndex,
    required this.currentPhase,
    required this.assistantText,
    required this.artifactId,
    required this.artifactKind,
    required this.warnings,
  });

  factory RpStoryTurnResponse.fromJson(Map<String, dynamic> json) {
    return RpStoryTurnResponse(
      sessionId: json['session_id'] as String,
      chapterWorkspaceId: json['chapter_workspace_id'] as String,
      commandKind: json['command_kind'] as String,
      currentChapterIndex: json['current_chapter_index'] as int? ?? 1,
      currentPhase: json['current_phase'] as String? ?? 'outline_drafting',
      assistantText: json['assistant_text'] as String?,
      artifactId: json['artifact_id'] as String?,
      artifactKind: json['artifact_kind'] as String?,
      warnings: (json['warnings'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class RpDraftDocumentBlock {
  final String blockId;
  final int order;
  final String blockKind;
  final String text;
  final String? selectedExcerpt;
  final String? selectedExcerptHash;
  final Map<String, dynamic> metadataJson;

  const RpDraftDocumentBlock({
    required this.blockId,
    required this.order,
    required this.blockKind,
    required this.text,
    required this.selectedExcerpt,
    required this.selectedExcerptHash,
    required this.metadataJson,
  });

  factory RpDraftDocumentBlock.fromJson(Map<String, dynamic> json) {
    return RpDraftDocumentBlock(
      blockId: json['block_id'] as String? ?? '',
      order: json['order'] as int? ?? 0,
      blockKind: json['block_kind'] as String? ?? 'unknown',
      text: json['text'] as String? ?? '',
      selectedExcerpt: json['selected_excerpt'] as String?,
      selectedExcerptHash: json['selected_excerpt_hash'] as String?,
      metadataJson: json['metadata_json'] is Map
          ? Map<String, dynamic>.from(json['metadata_json'] as Map)
          : const {},
    );
  }
}

class RpDraftDocumentRecord {
  final String draftDocumentId;
  final String turnId;
  final String draftRef;
  final String sourceOutputRef;
  final String sourceFormat;
  final List<RpDraftDocumentBlock> blocks;
  final String materializationVersion;
  final Map<String, dynamic> metadataJson;

  const RpDraftDocumentRecord({
    required this.draftDocumentId,
    required this.turnId,
    required this.draftRef,
    required this.sourceOutputRef,
    required this.sourceFormat,
    required this.blocks,
    required this.materializationVersion,
    required this.metadataJson,
  });

  factory RpDraftDocumentRecord.fromJson(Map<String, dynamic> json) {
    return RpDraftDocumentRecord(
      draftDocumentId: json['draft_document_id'] as String? ?? '',
      turnId: json['turn_id'] as String? ?? '',
      draftRef: json['draft_ref'] as String? ?? '',
      sourceOutputRef: json['source_output_ref'] as String? ?? '',
      sourceFormat: json['source_format'] as String? ?? 'markdown',
      blocks: (json['blocks'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpDraftDocumentBlock.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      materializationVersion: json['materialization_version'] as String? ?? '',
      metadataJson: json['metadata_json'] is Map
          ? Map<String, dynamic>.from(json['metadata_json'] as Map)
          : const {},
    );
  }
}

class RpRevisionAnchorRef {
  final String anchorScope;
  final List<String> blockIds;
  final int? startOffset;
  final int? endOffset;
  final String? selectedExcerptHash;
  final String? superdocAnchorId;

  const RpRevisionAnchorRef({
    required this.anchorScope,
    required this.blockIds,
    required this.startOffset,
    required this.endOffset,
    required this.selectedExcerptHash,
    required this.superdocAnchorId,
  });

  factory RpRevisionAnchorRef.fromJson(Map<String, dynamic> json) {
    return RpRevisionAnchorRef(
      anchorScope: json['anchor_scope'] as String? ?? 'single_block',
      blockIds: (json['block_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      startOffset: (json['start_offset'] as num?)?.toInt(),
      endOffset: (json['end_offset'] as num?)?.toInt(),
      selectedExcerptHash: json['selected_excerpt_hash'] as String?,
      superdocAnchorId: json['superdoc_anchor_id'] as String?,
    );
  }
}

class RpRevisionComment {
  final String commentId;
  final String turnId;
  final String draftRef;
  final String overlayId;
  final RpRevisionAnchorRef anchorRef;
  final String? selectedExcerpt;
  final String instructionText;
  final String status;
  final String createdBy;

  const RpRevisionComment({
    required this.commentId,
    required this.turnId,
    required this.draftRef,
    required this.overlayId,
    required this.anchorRef,
    required this.selectedExcerpt,
    required this.instructionText,
    required this.status,
    required this.createdBy,
  });

  bool get isActive => status == 'active';

  factory RpRevisionComment.fromJson(Map<String, dynamic> json) {
    return RpRevisionComment(
      commentId: json['comment_id'] as String? ?? '',
      turnId: json['turn_id'] as String? ?? '',
      draftRef: json['draft_ref'] as String? ?? '',
      overlayId: json['overlay_id'] as String? ?? '',
      anchorRef: RpRevisionAnchorRef.fromJson(
        Map<String, dynamic>.from(json['anchor_ref'] as Map? ?? const {}),
      ),
      selectedExcerpt: json['selected_excerpt'] as String?,
      instructionText: json['instruction_text'] as String? ?? '',
      status: json['status'] as String? ?? 'active',
      createdBy: json['created_by'] as String? ?? 'user',
    );
  }
}

class RpTrackedChange {
  final String trackedChangeId;
  final String turnId;
  final String draftRef;
  final String overlayId;
  final RpRevisionAnchorRef anchorRef;
  final String changeKind;
  final String? originalText;
  final String? suggestedText;
  final String status;

  const RpTrackedChange({
    required this.trackedChangeId,
    required this.turnId,
    required this.draftRef,
    required this.overlayId,
    required this.anchorRef,
    required this.changeKind,
    required this.originalText,
    required this.suggestedText,
    required this.status,
  });

  bool get isActive => status == 'active';

  factory RpTrackedChange.fromJson(Map<String, dynamic> json) {
    return RpTrackedChange(
      trackedChangeId: json['tracked_change_id'] as String? ?? '',
      turnId: json['turn_id'] as String? ?? '',
      draftRef: json['draft_ref'] as String? ?? '',
      overlayId: json['overlay_id'] as String? ?? '',
      anchorRef: RpRevisionAnchorRef.fromJson(
        Map<String, dynamic>.from(json['anchor_ref'] as Map? ?? const {}),
      ),
      changeKind: json['change_kind'] as String? ?? 'replace',
      originalText: json['original_text'] as String?,
      suggestedText: json['suggested_text'] as String?,
      status: json['status'] as String? ?? 'active',
    );
  }
}

class RpRevisionReviewSurface {
  final String sessionId;
  final String artifactId;
  final String draftText;
  final RpDraftDocumentRecord draftDocument;
  final Map<String, dynamic> overlay;
  final List<RpRevisionComment> comments;
  final List<RpTrackedChange> trackedChanges;
  final List<String> activeCommentRefs;
  final List<String> activeTrackedChangeRefs;
  final bool canonicalTruth;

  const RpRevisionReviewSurface({
    required this.sessionId,
    required this.artifactId,
    required this.draftText,
    required this.draftDocument,
    required this.overlay,
    required this.comments,
    required this.trackedChanges,
    required this.activeCommentRefs,
    required this.activeTrackedChangeRefs,
    required this.canonicalTruth,
  });

  factory RpRevisionReviewSurface.fromJson(Map<String, dynamic> json) {
    return RpRevisionReviewSurface(
      sessionId: json['session_id'] as String? ?? '',
      artifactId: json['artifact_id'] as String? ?? '',
      draftText: json['draft_text'] as String? ?? '',
      draftDocument: RpDraftDocumentRecord.fromJson(
        Map<String, dynamic>.from(json['draft_document'] as Map? ?? const {}),
      ),
      overlay: json['overlay'] is Map
          ? Map<String, dynamic>.from(json['overlay'] as Map)
          : const {},
      comments: (json['comments'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpRevisionComment.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      trackedChanges: (json['tracked_changes'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => RpTrackedChange.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      activeCommentRefs: (json['active_comment_refs'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      activeTrackedChangeRefs:
          (json['active_tracked_change_refs'] as List? ?? const [])
              .map((item) => item.toString())
              .toList(),
      canonicalTruth: json['canonical_truth'] as bool? ?? false,
    );
  }
}
