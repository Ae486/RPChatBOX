class RpRetrievalIndexJob {
  final String jobId;
  final String storyId;
  final String? assetId;
  final String? collectionId;
  final String jobKind;
  final String jobState;
  final List<String> targetRefs;
  final List<String> warnings;
  final String? errorMessage;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? startedAt;
  final DateTime? completedAt;

  const RpRetrievalIndexJob({
    required this.jobId,
    required this.storyId,
    required this.assetId,
    required this.collectionId,
    required this.jobKind,
    required this.jobState,
    required this.targetRefs,
    required this.warnings,
    required this.errorMessage,
    required this.createdAt,
    required this.updatedAt,
    required this.startedAt,
    required this.completedAt,
  });

  bool get isFailed => jobState == 'failed';
  bool get isCompleted => jobState == 'completed';
  bool get isRunning =>
      jobState == 'queued' ||
      jobState == 'parsing' ||
      jobState == 'chunking' ||
      jobState == 'embedding' ||
      jobState == 'indexing';

  factory RpRetrievalIndexJob.fromJson(Map<String, dynamic> json) {
    return RpRetrievalIndexJob(
      jobId: json['job_id'] as String,
      storyId: json['story_id'] as String,
      assetId: json['asset_id'] as String?,
      collectionId: json['collection_id'] as String?,
      jobKind: json['job_kind'] as String? ?? 'ingest',
      jobState: json['job_state'] as String? ?? 'queued',
      targetRefs: (json['target_refs'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      warnings: (json['warnings'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      errorMessage: json['error_message'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      startedAt: _parseDateTime(json['started_at']),
      completedAt: _parseDateTime(json['completed_at']),
    );
  }
}

class RpRetrievalCollectionMaintenanceSnapshot {
  final String collectionId;
  final String storyId;
  final String collectionKind;
  final List<String> assetIds;
  final int assetCount;
  final int activeChunkCount;
  final int activeEmbeddingCount;
  final List<String> backfillCandidateAssetIds;
  final int failedJobCount;
  final List<String> retryableJobIds;

  const RpRetrievalCollectionMaintenanceSnapshot({
    required this.collectionId,
    required this.storyId,
    required this.collectionKind,
    required this.assetIds,
    required this.assetCount,
    required this.activeChunkCount,
    required this.activeEmbeddingCount,
    required this.backfillCandidateAssetIds,
    required this.failedJobCount,
    required this.retryableJobIds,
  });

  factory RpRetrievalCollectionMaintenanceSnapshot.fromJson(
    Map<String, dynamic> json,
  ) {
    return RpRetrievalCollectionMaintenanceSnapshot(
      collectionId: json['collection_id'] as String,
      storyId: json['story_id'] as String,
      collectionKind: json['collection_kind'] as String? ?? 'archival',
      assetIds: (json['asset_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      assetCount: (json['asset_count'] as num?)?.toInt() ?? 0,
      activeChunkCount: (json['active_chunk_count'] as num?)?.toInt() ?? 0,
      activeEmbeddingCount:
          (json['active_embedding_count'] as num?)?.toInt() ?? 0,
      backfillCandidateAssetIds:
          (json['backfill_candidate_asset_ids'] as List? ?? const [])
              .map((item) => item.toString())
              .toList(),
      failedJobCount: (json['failed_job_count'] as num?)?.toInt() ?? 0,
      retryableJobIds: (json['retryable_job_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }
}

class RpRetrievalStoryMaintenanceSnapshot {
  final String storyId;
  final int collectionCount;
  final int assetCount;
  final int activeChunkCount;
  final int activeEmbeddingCount;
  final List<String> backfillCandidateAssetIds;
  final int failedJobCount;
  final List<String> retryableJobIds;
  final List<RpRetrievalCollectionMaintenanceSnapshot> collections;
  final List<RpRetrievalIndexJob> recentJobs;

  const RpRetrievalStoryMaintenanceSnapshot({
    required this.storyId,
    required this.collectionCount,
    required this.assetCount,
    required this.activeChunkCount,
    required this.activeEmbeddingCount,
    required this.backfillCandidateAssetIds,
    required this.failedJobCount,
    required this.retryableJobIds,
    required this.collections,
    required this.recentJobs,
  });

  factory RpRetrievalStoryMaintenanceSnapshot.fromJson(
    Map<String, dynamic> json,
  ) {
    return RpRetrievalStoryMaintenanceSnapshot(
      storyId: json['story_id'] as String,
      collectionCount: (json['collection_count'] as num?)?.toInt() ?? 0,
      assetCount: (json['asset_count'] as num?)?.toInt() ?? 0,
      activeChunkCount: (json['active_chunk_count'] as num?)?.toInt() ?? 0,
      activeEmbeddingCount:
          (json['active_embedding_count'] as num?)?.toInt() ?? 0,
      backfillCandidateAssetIds:
          (json['backfill_candidate_asset_ids'] as List? ?? const [])
              .map((item) => item.toString())
              .toList(),
      failedJobCount: (json['failed_job_count'] as num?)?.toInt() ?? 0,
      retryableJobIds: (json['retryable_job_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      collections: (json['collections'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => RpRetrievalCollectionMaintenanceSnapshot.fromJson(
              Map<String, dynamic>.from(item),
            ),
          )
          .toList(),
      recentJobs: (json['recent_jobs'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpRetrievalIndexJob.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
    );
  }
}

class RpRetrievalRetryBatchResult {
  final String storyId;
  final String? collectionId;
  final List<String> requestedJobIds;
  final List<String> dedupedJobIds;
  final List<String> skippedJobIds;
  final List<RpRetrievalIndexJob> retriedJobs;
  final int? limitApplied;

  const RpRetrievalRetryBatchResult({
    required this.storyId,
    required this.collectionId,
    required this.requestedJobIds,
    required this.dedupedJobIds,
    required this.skippedJobIds,
    required this.retriedJobs,
    required this.limitApplied,
  });

  factory RpRetrievalRetryBatchResult.fromJson(Map<String, dynamic> json) {
    return RpRetrievalRetryBatchResult(
      storyId: json['story_id'] as String,
      collectionId: json['collection_id'] as String?,
      requestedJobIds: (json['requested_job_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      dedupedJobIds: (json['deduped_job_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      skippedJobIds: (json['skipped_job_ids'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(),
      retriedJobs: (json['retried_jobs'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpRetrievalIndexJob.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      limitApplied: (json['limit_applied'] as num?)?.toInt(),
    );
  }
}

DateTime? _parseDateTime(dynamic value) {
  if (value is String && value.isNotEmpty) {
    return DateTime.tryParse(value);
  }
  return null;
}
