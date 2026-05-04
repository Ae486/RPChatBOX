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

class RpMemoryGraphExtractionJob {
  final String graphJobId;
  final String storyId;
  final String? workspaceId;
  final String? sessionId;
  final String? commitId;
  final String sourceLayer;
  final String? sourceAssetId;
  final String? chunkId;
  final String? sectionId;
  final String inputFingerprint;
  final String status;
  final int attemptCount;
  final String? modelConfigRef;
  final String? providerId;
  final String? modelId;
  final String extractionSchemaVersion;
  final String taxonomyVersion;
  final Map<String, dynamic> tokenUsage;
  final List<String> warningCodes;
  final String? errorCode;
  final String? errorMessage;
  final String? queuedReason;
  final DateTime? retryAfter;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? completedAt;

  const RpMemoryGraphExtractionJob({
    required this.graphJobId,
    required this.storyId,
    required this.workspaceId,
    required this.sessionId,
    required this.commitId,
    required this.sourceLayer,
    required this.sourceAssetId,
    required this.chunkId,
    required this.sectionId,
    required this.inputFingerprint,
    required this.status,
    required this.attemptCount,
    required this.modelConfigRef,
    required this.providerId,
    required this.modelId,
    required this.extractionSchemaVersion,
    required this.taxonomyVersion,
    required this.tokenUsage,
    required this.warningCodes,
    required this.errorCode,
    required this.errorMessage,
    required this.queuedReason,
    required this.retryAfter,
    required this.createdAt,
    required this.updatedAt,
    required this.completedAt,
  });

  bool get isFailed => status == 'failed';
  bool get isCompleted => status == 'completed';
  bool get isRunning => status == 'queued' || status == 'running';

  factory RpMemoryGraphExtractionJob.fromJson(Map<String, dynamic> json) {
    return RpMemoryGraphExtractionJob(
      graphJobId: json['graph_job_id'] as String,
      storyId: json['story_id'] as String,
      workspaceId: json['workspace_id'] as String?,
      sessionId: json['session_id'] as String?,
      commitId: json['commit_id'] as String?,
      sourceLayer: json['source_layer'] as String? ?? 'archival',
      sourceAssetId: json['source_asset_id'] as String?,
      chunkId: json['chunk_id'] as String?,
      sectionId: json['section_id'] as String?,
      inputFingerprint: json['input_fingerprint'] as String? ?? '',
      status: json['status'] as String? ?? 'queued',
      attemptCount: (json['attempt_count'] as num?)?.toInt() ?? 0,
      modelConfigRef: json['model_config_ref'] as String?,
      providerId: json['provider_id'] as String?,
      modelId: json['model_id'] as String?,
      extractionSchemaVersion:
          json['extraction_schema_version'] as String? ?? '',
      taxonomyVersion: json['taxonomy_version'] as String? ?? '',
      tokenUsage: _parseMap(json['token_usage']),
      warningCodes: _parseStringList(json['warning_codes']),
      errorCode: json['error_code'] as String?,
      errorMessage: json['error_message'] as String?,
      queuedReason: json['queued_reason'] as String?,
      retryAfter: _parseDateTime(json['retry_after']),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      completedAt: _parseDateTime(json['completed_at']),
    );
  }
}

class RpMemoryGraphMaintenanceSnapshot {
  final String storyId;
  final String graphBackend;
  final bool graphExtractionEnabled;
  final bool graphExtractionConfigured;
  final String? graphExtractionModelConfigRef;
  final String? graphExtractionProviderId;
  final String? graphExtractionModelId;
  final List<String> maintenanceWarnings;
  final List<String> sourceLayers;
  final int nodeCount;
  final int edgeCount;
  final int evidenceCount;
  final int jobCount;
  final int queuedJobCount;
  final int runningJobCount;
  final int completedJobCount;
  final int failedJobCount;
  final int skippedJobCount;
  final int cancelledJobCount;
  final List<String> retryableJobIds;
  final Map<String, int> warningCodeCounts;
  final Map<String, int> errorCodeCounts;
  final List<RpMemoryGraphExtractionJob> recentJobs;

  const RpMemoryGraphMaintenanceSnapshot({
    required this.storyId,
    required this.graphBackend,
    required this.graphExtractionEnabled,
    required this.graphExtractionConfigured,
    required this.graphExtractionModelConfigRef,
    required this.graphExtractionProviderId,
    required this.graphExtractionModelId,
    required this.maintenanceWarnings,
    required this.sourceLayers,
    required this.nodeCount,
    required this.edgeCount,
    required this.evidenceCount,
    required this.jobCount,
    required this.queuedJobCount,
    required this.runningJobCount,
    required this.completedJobCount,
    required this.failedJobCount,
    required this.skippedJobCount,
    required this.cancelledJobCount,
    required this.retryableJobIds,
    required this.warningCodeCounts,
    required this.errorCodeCounts,
    required this.recentJobs,
  });

  factory RpMemoryGraphMaintenanceSnapshot.fromJson(Map<String, dynamic> json) {
    return RpMemoryGraphMaintenanceSnapshot(
      storyId: json['story_id'] as String,
      graphBackend: json['graph_backend'] as String? ?? 'postgres_lightweight',
      graphExtractionEnabled: json['graph_extraction_enabled'] as bool? ?? true,
      graphExtractionConfigured:
          json['graph_extraction_configured'] as bool? ?? false,
      graphExtractionModelConfigRef:
          json['graph_extraction_model_config_ref'] as String?,
      graphExtractionProviderId:
          json['graph_extraction_provider_id'] as String?,
      graphExtractionModelId: json['graph_extraction_model_id'] as String?,
      maintenanceWarnings: _parseStringList(json['maintenance_warnings']),
      sourceLayers: _parseStringList(json['source_layers']),
      nodeCount: (json['node_count'] as num?)?.toInt() ?? 0,
      edgeCount: (json['edge_count'] as num?)?.toInt() ?? 0,
      evidenceCount: (json['evidence_count'] as num?)?.toInt() ?? 0,
      jobCount: (json['job_count'] as num?)?.toInt() ?? 0,
      queuedJobCount: (json['queued_job_count'] as num?)?.toInt() ?? 0,
      runningJobCount: (json['running_job_count'] as num?)?.toInt() ?? 0,
      completedJobCount: (json['completed_job_count'] as num?)?.toInt() ?? 0,
      failedJobCount: (json['failed_job_count'] as num?)?.toInt() ?? 0,
      skippedJobCount: (json['skipped_job_count'] as num?)?.toInt() ?? 0,
      cancelledJobCount: (json['cancelled_job_count'] as num?)?.toInt() ?? 0,
      retryableJobIds: _parseStringList(json['retryable_job_ids']),
      warningCodeCounts: _parseStringIntMap(json['warning_code_counts']),
      errorCodeCounts: _parseStringIntMap(json['error_code_counts']),
      recentJobs: (json['recent_jobs'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) => RpMemoryGraphExtractionJob.fromJson(
              Map<String, dynamic>.from(item),
            ),
          )
          .toList(),
    );
  }
}

class RpMemoryGraphNode {
  final String id;
  final String label;
  final String type;
  final String storyId;
  final String? workspaceId;
  final String? sessionId;
  final String sourceLayer;
  final String sourceStatus;
  final double? confidence;
  final List<String> aliases;
  final String? description;
  final String? firstSeenSourceRef;
  final String entitySchemaVersion;
  final String? normalizationKey;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;
  final DateTime updatedAt;

  const RpMemoryGraphNode({
    required this.id,
    required this.label,
    required this.type,
    required this.storyId,
    required this.workspaceId,
    required this.sessionId,
    required this.sourceLayer,
    required this.sourceStatus,
    required this.confidence,
    required this.aliases,
    required this.description,
    required this.firstSeenSourceRef,
    required this.entitySchemaVersion,
    required this.normalizationKey,
    required this.metadata,
    required this.createdAt,
    required this.updatedAt,
  });

  factory RpMemoryGraphNode.fromJson(Map<String, dynamic> json) {
    return RpMemoryGraphNode(
      id: json['id'] as String,
      label: json['label'] as String? ?? json['id'] as String,
      type: json['type'] as String? ?? 'term_or_concept',
      storyId: json['story_id'] as String,
      workspaceId: json['workspace_id'] as String?,
      sessionId: json['session_id'] as String?,
      sourceLayer: json['source_layer'] as String? ?? 'archival',
      sourceStatus: json['source_status'] as String? ?? 'source_reference',
      confidence: (json['confidence'] as num?)?.toDouble(),
      aliases: _parseStringList(json['aliases']),
      description: json['description'] as String?,
      firstSeenSourceRef: json['first_seen_source_ref'] as String?,
      entitySchemaVersion: json['entity_schema_version'] as String? ?? '',
      normalizationKey: json['normalization_key'] as String?,
      metadata: _parseMap(json['metadata']),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpMemoryGraphEdge {
  final String id;
  final String storyId;
  final String? workspaceId;
  final String? sessionId;
  final String source;
  final String target;
  final String? sourceEntityName;
  final String? targetEntityName;
  final String label;
  final String relationFamily;
  final String relationSchemaVersion;
  final String? rawRelationText;
  final String sourceLayer;
  final String sourceStatus;
  final double? confidence;
  final String direction;
  final String? validFrom;
  final String? validTo;
  final String? branchId;
  final String canonStatus;
  final int evidenceCount;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;
  final DateTime updatedAt;

  const RpMemoryGraphEdge({
    required this.id,
    required this.storyId,
    required this.workspaceId,
    required this.sessionId,
    required this.source,
    required this.target,
    required this.sourceEntityName,
    required this.targetEntityName,
    required this.label,
    required this.relationFamily,
    required this.relationSchemaVersion,
    required this.rawRelationText,
    required this.sourceLayer,
    required this.sourceStatus,
    required this.confidence,
    required this.direction,
    required this.validFrom,
    required this.validTo,
    required this.branchId,
    required this.canonStatus,
    required this.evidenceCount,
    required this.metadata,
    required this.createdAt,
    required this.updatedAt,
  });

  factory RpMemoryGraphEdge.fromJson(Map<String, dynamic> json) {
    return RpMemoryGraphEdge(
      id: json['id'] as String,
      storyId: json['story_id'] as String,
      workspaceId: json['workspace_id'] as String?,
      sessionId: json['session_id'] as String?,
      source: json['source'] as String,
      target: json['target'] as String,
      sourceEntityName: json['source_entity_name'] as String?,
      targetEntityName: json['target_entity_name'] as String?,
      label: json['label'] as String? ?? 'related_to',
      relationFamily: json['relation_family'] as String? ?? 'stable_setup',
      relationSchemaVersion: json['relation_schema_version'] as String? ?? '',
      rawRelationText: json['raw_relation_text'] as String?,
      sourceLayer: json['source_layer'] as String? ?? 'archival',
      sourceStatus: json['source_status'] as String? ?? 'source_reference',
      confidence: (json['confidence'] as num?)?.toDouble(),
      direction: json['direction'] as String? ?? 'directed',
      validFrom: json['valid_from'] as String?,
      validTo: json['valid_to'] as String?,
      branchId: json['branch_id'] as String?,
      canonStatus: json['canon_status'] as String? ?? 'source_reference',
      evidenceCount: (json['evidence_count'] as num?)?.toInt() ?? 0,
      metadata: _parseMap(json['metadata']),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpMemoryGraphEvidence {
  final String id;
  final String storyId;
  final String? workspaceId;
  final String? nodeId;
  final String? edgeId;
  final String sourceLayer;
  final String? sourceFamily;
  final String? sourceType;
  final String? importEvent;
  final String? sourceRef;
  final String? sourceAssetId;
  final String? collectionId;
  final String? parsedDocumentId;
  final String? chunkId;
  final String? sectionId;
  final String? domain;
  final String? domainPath;
  final String? commitId;
  final String? stepId;
  final int? charStart;
  final int? charEnd;
  final String? excerpt;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;
  final DateTime updatedAt;

  const RpMemoryGraphEvidence({
    required this.id,
    required this.storyId,
    required this.workspaceId,
    required this.nodeId,
    required this.edgeId,
    required this.sourceLayer,
    required this.sourceFamily,
    required this.sourceType,
    required this.importEvent,
    required this.sourceRef,
    required this.sourceAssetId,
    required this.collectionId,
    required this.parsedDocumentId,
    required this.chunkId,
    required this.sectionId,
    required this.domain,
    required this.domainPath,
    required this.commitId,
    required this.stepId,
    required this.charStart,
    required this.charEnd,
    required this.excerpt,
    required this.metadata,
    required this.createdAt,
    required this.updatedAt,
  });

  factory RpMemoryGraphEvidence.fromJson(Map<String, dynamic> json) {
    return RpMemoryGraphEvidence(
      id: json['id'] as String,
      storyId: json['story_id'] as String,
      workspaceId: json['workspace_id'] as String?,
      nodeId: json['node_id'] as String?,
      edgeId: json['edge_id'] as String?,
      sourceLayer: json['source_layer'] as String? ?? 'archival',
      sourceFamily: json['source_family'] as String?,
      sourceType: json['source_type'] as String?,
      importEvent: json['import_event'] as String?,
      sourceRef: json['source_ref'] as String?,
      sourceAssetId: json['source_asset_id'] as String?,
      collectionId: json['collection_id'] as String?,
      parsedDocumentId: json['parsed_document_id'] as String?,
      chunkId: json['chunk_id'] as String?,
      sectionId: json['section_id'] as String?,
      domain: json['domain'] as String?,
      domainPath: json['domain_path'] as String?,
      commitId: json['commit_id'] as String?,
      stepId: json['step_id'] as String?,
      charStart: (json['char_start'] as num?)?.toInt(),
      charEnd: (json['char_end'] as num?)?.toInt(),
      excerpt: json['excerpt'] as String?,
      metadata: _parseMap(json['metadata']),
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }
}

class RpMemoryGraphNeighborhoodResponse {
  final String storyId;
  final String graphBackend;
  final String? sourceLayer;
  final String? anchorNodeId;
  final int maxDepth;
  final bool truncated;
  final List<String> warnings;
  final List<RpMemoryGraphNode> nodes;
  final List<RpMemoryGraphEdge> edges;
  final List<RpMemoryGraphEvidence> evidence;

  const RpMemoryGraphNeighborhoodResponse({
    required this.storyId,
    required this.graphBackend,
    required this.sourceLayer,
    required this.anchorNodeId,
    required this.maxDepth,
    required this.truncated,
    required this.warnings,
    required this.nodes,
    required this.edges,
    required this.evidence,
  });

  factory RpMemoryGraphNeighborhoodResponse.fromJson(
    Map<String, dynamic> json,
  ) {
    return RpMemoryGraphNeighborhoodResponse(
      storyId: json['story_id'] as String,
      graphBackend: json['graph_backend'] as String? ?? 'postgres_lightweight',
      sourceLayer: json['source_layer'] as String?,
      anchorNodeId: json['anchor_node_id'] as String?,
      maxDepth: (json['max_depth'] as num?)?.toInt() ?? 1,
      truncated: json['truncated'] as bool? ?? false,
      warnings: _parseStringList(json['warnings']),
      nodes: (json['nodes'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpMemoryGraphNode.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      edges: (json['edges'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpMemoryGraphEdge.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
      evidence: (json['evidence'] as List? ?? const [])
          .whereType<Map>()
          .map(
            (item) =>
                RpMemoryGraphEvidence.fromJson(Map<String, dynamic>.from(item)),
          )
          .toList(),
    );
  }

  List<RpMemoryGraphEvidence> evidenceForNode(String nodeId) {
    return evidence.where((item) => item.nodeId == nodeId).toList();
  }

  List<RpMemoryGraphEvidence> evidenceForEdge(String edgeId) {
    return evidence.where((item) => item.edgeId == edgeId).toList();
  }
}

DateTime? _parseDateTime(dynamic value) {
  if (value is String && value.isNotEmpty) {
    return DateTime.tryParse(value);
  }
  return null;
}

List<String> _parseStringList(dynamic value) {
  return (value as List? ?? const []).map((item) => item.toString()).toList();
}

Map<String, dynamic> _parseMap(dynamic value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

Map<String, int> _parseStringIntMap(dynamic value) {
  if (value is! Map) return const {};
  return value.map(
    (key, rawValue) =>
        MapEntry(key.toString(), (rawValue as num?)?.toInt() ?? 0),
  );
}
