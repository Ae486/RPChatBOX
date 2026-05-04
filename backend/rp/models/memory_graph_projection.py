"""Shared contracts for RP Memory Graph Projection inspection surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT = "postgres_lightweight"

GRAPH_SOURCE_LAYER_ARCHIVAL = "archival"
GRAPH_SOURCE_LAYER_RECALL = "recall"
GraphSourceLayer = Literal["archival", "recall"]
GRAPH_SOURCE_LAYERS = (GRAPH_SOURCE_LAYER_ARCHIVAL, GRAPH_SOURCE_LAYER_RECALL)

GRAPH_SOURCE_STATUS_SOURCE_REFERENCE = "source_reference"
GRAPH_SOURCE_STATUS_CANON_CONFIRMED = "canon_confirmed"
GRAPH_SOURCE_STATUS_CANDIDATE = "candidate"
GRAPH_SOURCE_STATUS_INVALIDATED = "invalidated"
GraphSourceStatus = Literal[
    "source_reference",
    "canon_confirmed",
    "candidate",
    "invalidated",
]
GRAPH_SOURCE_STATUSES = (
    GRAPH_SOURCE_STATUS_SOURCE_REFERENCE,
    GRAPH_SOURCE_STATUS_CANON_CONFIRMED,
    GRAPH_SOURCE_STATUS_CANDIDATE,
    GRAPH_SOURCE_STATUS_INVALIDATED,
)

GRAPH_CANON_STATUS_SOURCE_REFERENCE = "source_reference"
GRAPH_CANON_STATUS_CANON_CONFIRMED = "canon_confirmed"
GRAPH_CANON_STATUS_NON_CANON = "non_canon"
GRAPH_CANON_STATUS_SUPERSEDED = "superseded"
GRAPH_CANON_STATUS_BRANCH_ONLY = "branch_only"
GraphCanonStatus = Literal[
    "source_reference",
    "canon_confirmed",
    "non_canon",
    "superseded",
    "branch_only",
]
GRAPH_CANON_STATUSES = (
    GRAPH_CANON_STATUS_SOURCE_REFERENCE,
    GRAPH_CANON_STATUS_CANON_CONFIRMED,
    GRAPH_CANON_STATUS_NON_CANON,
    GRAPH_CANON_STATUS_SUPERSEDED,
    GRAPH_CANON_STATUS_BRANCH_ONLY,
)

GRAPH_EDGE_DIRECTION_DIRECTED = "directed"
GRAPH_EDGE_DIRECTION_UNDIRECTED = "undirected"
GraphEdgeDirection = Literal["directed", "undirected"]
GRAPH_EDGE_DIRECTIONS = (
    GRAPH_EDGE_DIRECTION_DIRECTED,
    GRAPH_EDGE_DIRECTION_UNDIRECTED,
)

GRAPH_JOB_STATUS_QUEUED = "queued"
GRAPH_JOB_STATUS_RUNNING = "running"
GRAPH_JOB_STATUS_COMPLETED = "completed"
GRAPH_JOB_STATUS_FAILED = "failed"
GRAPH_JOB_STATUS_SKIPPED = "skipped"
GRAPH_JOB_STATUS_CANCELLED = "cancelled"
GraphJobStatus = Literal[
    "queued", "running", "completed", "failed", "skipped", "cancelled"
]
GRAPH_JOB_STATUSES = (
    GRAPH_JOB_STATUS_QUEUED,
    GRAPH_JOB_STATUS_RUNNING,
    GRAPH_JOB_STATUS_COMPLETED,
    GRAPH_JOB_STATUS_FAILED,
    GRAPH_JOB_STATUS_SKIPPED,
    GRAPH_JOB_STATUS_CANCELLED,
)

GRAPH_JOB_REASON_ARCHIVAL_INGESTED = "archival_ingested"
GRAPH_JOB_REASON_MANUAL_REBUILD = "manual_rebuild"
GRAPH_JOB_REASON_MANUAL_RETRY = "manual_retry"
GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED = "model_config_changed"
GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED = "schema_version_changed"
GraphJobQueuedReason = Literal[
    "archival_ingested",
    "manual_rebuild",
    "manual_retry",
    "model_config_changed",
    "schema_version_changed",
]
GRAPH_JOB_QUEUED_REASONS = (
    GRAPH_JOB_REASON_ARCHIVAL_INGESTED,
    GRAPH_JOB_REASON_MANUAL_REBUILD,
    GRAPH_JOB_REASON_MANUAL_RETRY,
    GRAPH_JOB_REASON_MODEL_CONFIG_CHANGED,
    GRAPH_JOB_REASON_SCHEMA_VERSION_CHANGED,
)

GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE = "unsupported_entity_type"
GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE = "unsupported_relation_type"
GRAPH_WARNING_MAPPED_TO_RELATED_TO = "mapped_to_related_to"
GRAPH_WARNING_LOW_CONFIDENCE = "low_confidence"
GRAPH_WARNING_MISSING_OPTIONAL_EVIDENCE_SPAN = "missing_optional_evidence_span"
GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED = "duplicate_candidate_merged"
GRAPH_WARNING_NEIGHBORHOOD_TRUNCATED = "graph_neighborhood_truncated"
GraphWarningCode = Literal[
    "unsupported_entity_type",
    "unsupported_relation_type",
    "mapped_to_related_to",
    "low_confidence",
    "missing_optional_evidence_span",
    "duplicate_candidate_merged",
]
GRAPH_WARNING_CODES = (
    GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE,
    GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE,
    GRAPH_WARNING_MAPPED_TO_RELATED_TO,
    GRAPH_WARNING_LOW_CONFIDENCE,
    GRAPH_WARNING_MISSING_OPTIONAL_EVIDENCE_SPAN,
    GRAPH_WARNING_DUPLICATE_CANDIDATE_MERGED,
)

GRAPH_ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
GRAPH_ERROR_MODEL_CONFIG_MISSING = "model_config_missing"
GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID = "structured_output_invalid"
GRAPH_ERROR_EXTRACTION_TIMEOUT = "extraction_timeout"
GRAPH_ERROR_SOURCE_CHUNK_MISSING = "source_chunk_missing"
GRAPH_ERROR_EVIDENCE_POINTER_INVALID = "evidence_pointer_invalid"
GRAPH_ERROR_PERSISTENCE_FAILED = "persistence_failed"
GraphErrorCode = Literal[
    "provider_unavailable",
    "model_config_missing",
    "structured_output_invalid",
    "extraction_timeout",
    "source_chunk_missing",
    "evidence_pointer_invalid",
    "persistence_failed",
]
GRAPH_ERROR_CODES = (
    GRAPH_ERROR_PROVIDER_UNAVAILABLE,
    GRAPH_ERROR_MODEL_CONFIG_MISSING,
    GRAPH_ERROR_STRUCTURED_OUTPUT_INVALID,
    GRAPH_ERROR_EXTRACTION_TIMEOUT,
    GRAPH_ERROR_SOURCE_CHUNK_MISSING,
    GRAPH_ERROR_EVIDENCE_POINTER_INVALID,
    GRAPH_ERROR_PERSISTENCE_FAILED,
)

GRAPH_ENTITY_CHARACTER = "character"
GRAPH_ENTITY_PLACE = "place"
GRAPH_ENTITY_FACTION_OR_ORG = "faction_or_org"
GRAPH_ENTITY_RULE = "rule"
GRAPH_ENTITY_OBJECT_OR_ARTIFACT = "object_or_artifact"
GRAPH_ENTITY_TERM_OR_CONCEPT = "term_or_concept"
GraphEntityType = Literal[
    "character",
    "place",
    "faction_or_org",
    "rule",
    "object_or_artifact",
    "term_or_concept",
]
GRAPH_ENTITY_TYPES = (
    GRAPH_ENTITY_CHARACTER,
    GRAPH_ENTITY_PLACE,
    GRAPH_ENTITY_FACTION_OR_ORG,
    GRAPH_ENTITY_RULE,
    GRAPH_ENTITY_OBJECT_OR_ARTIFACT,
    GRAPH_ENTITY_TERM_OR_CONCEPT,
)
GRAPH_ENTITY_SCENE = "scene"
GRAPH_ENTITY_EVENT = "event"
GRAPH_ENTITY_FORESHADOW = "foreshadow"
GRAPH_ENTITY_CHAPTER = "chapter"
GRAPH_ENTITY_TIMELINE_MARKER = "timeline_marker"
GRAPH_RESERVED_ENTITY_TYPES = (
    GRAPH_ENTITY_SCENE,
    GRAPH_ENTITY_EVENT,
    GRAPH_ENTITY_FORESHADOW,
    GRAPH_ENTITY_CHAPTER,
    GRAPH_ENTITY_TIMELINE_MARKER,
)

GRAPH_REL_ALIAS_OF = "alias_of"
GRAPH_REL_PART_OF = "part_of"
GRAPH_REL_LOCATED_IN = "located_in"
GRAPH_REL_MEMBER_OF = "member_of"
GRAPH_REL_AFFILIATED_WITH = "affiliated_with"
GRAPH_REL_HAS_ROLE = "has_role"
GRAPH_REL_OWNS_OR_CONTROLS = "owns_or_controls"
GRAPH_REL_GOVERNED_BY_RULE = "governed_by_rule"
GRAPH_REL_REQUIRES = "requires"
GRAPH_REL_FORBIDS = "forbids"
GRAPH_REL_ENABLES = "enables"
GRAPH_REL_RELATED_TO = "related_to"
GraphRelationType = Literal[
    "alias_of",
    "part_of",
    "located_in",
    "member_of",
    "affiliated_with",
    "has_role",
    "owns_or_controls",
    "governed_by_rule",
    "requires",
    "forbids",
    "enables",
    "related_to",
]
GRAPH_RELATION_TYPES = (
    GRAPH_REL_ALIAS_OF,
    GRAPH_REL_PART_OF,
    GRAPH_REL_LOCATED_IN,
    GRAPH_REL_MEMBER_OF,
    GRAPH_REL_AFFILIATED_WITH,
    GRAPH_REL_HAS_ROLE,
    GRAPH_REL_OWNS_OR_CONTROLS,
    GRAPH_REL_GOVERNED_BY_RULE,
    GRAPH_REL_REQUIRES,
    GRAPH_REL_FORBIDS,
    GRAPH_REL_ENABLES,
    GRAPH_REL_RELATED_TO,
)

GRAPH_RELATION_FAMILY_STABLE_SETUP = "stable_setup"
GRAPH_RELATION_FAMILY_SOCIAL = "social_relation"
GRAPH_RELATION_FAMILY_CONFLICT = "conflict_relation"
GRAPH_RELATION_FAMILY_SECRET = "secret_relation"
GRAPH_RELATION_FAMILY_CAUSAL = "causal_relation"
GRAPH_RELATION_FAMILY_FORESHADOW = "foreshadow_relation"
GRAPH_RELATION_FAMILY_TEMPORAL = "temporal_relation"
GRAPH_RELATION_FAMILY_STATE_CHANGE = "state_change_relation"
GraphRelationFamily = Literal[
    "stable_setup",
    "social_relation",
    "conflict_relation",
    "secret_relation",
    "causal_relation",
    "foreshadow_relation",
    "temporal_relation",
    "state_change_relation",
]
GRAPH_RELATION_FAMILIES = (
    GRAPH_RELATION_FAMILY_STABLE_SETUP,
    GRAPH_RELATION_FAMILY_SOCIAL,
    GRAPH_RELATION_FAMILY_CONFLICT,
    GRAPH_RELATION_FAMILY_SECRET,
    GRAPH_RELATION_FAMILY_CAUSAL,
    GRAPH_RELATION_FAMILY_FORESHADOW,
    GRAPH_RELATION_FAMILY_TEMPORAL,
    GRAPH_RELATION_FAMILY_STATE_CHANGE,
)

GRAPH_ENTITY_SCHEMA_VERSION = "graph_entity_v1"
GRAPH_RELATION_SCHEMA_VERSION = "graph_relation_v1"
GRAPH_EXTRACTION_SCHEMA_VERSION = "graph_extraction_v1"
GRAPH_TAXONOMY_VERSION = "graph_taxonomy_v1"


def validate_graph_constant(
    value: str, *, allowed: tuple[str, ...], field_name: str
) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise ValueError(f"Unsupported graph {field_name}: {value!r}")
    return normalized


def validate_graph_entity_type(value: str) -> str:
    return validate_graph_constant(
        value,
        allowed=GRAPH_ENTITY_TYPES,
        field_name="entity_type",
    )


def normalize_graph_entity_type(
    value: str,
    *,
    fallback_to_term: bool = False,
) -> tuple[str, list[str]]:
    try:
        return validate_graph_entity_type(value), []
    except ValueError:
        if fallback_to_term:
            return GRAPH_ENTITY_TERM_OR_CONCEPT, [GRAPH_WARNING_UNSUPPORTED_ENTITY_TYPE]
        raise


def validate_graph_relation_type(value: str) -> str:
    return validate_graph_constant(
        value,
        allowed=GRAPH_RELATION_TYPES,
        field_name="relation_type",
    )


def normalize_graph_relation_type(
    value: str,
    *,
    fallback_to_related_to: bool = False,
) -> tuple[str, list[str]]:
    try:
        return validate_graph_relation_type(value), []
    except ValueError:
        if fallback_to_related_to:
            return GRAPH_REL_RELATED_TO, [
                GRAPH_WARNING_UNSUPPORTED_RELATION_TYPE,
                GRAPH_WARNING_MAPPED_TO_RELATED_TO,
            ]
        raise


class MemoryGraphNodeUpsert(BaseModel):
    """Seed/extraction DTO for one graph node candidate."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    workspace_id: str | None = None
    session_id: str | None = None
    source_layer: str = GRAPH_SOURCE_LAYER_ARCHIVAL
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    source_status: str = GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
    confidence: float | None = None
    first_seen_source_ref: str | None = None
    entity_schema_version: str = GRAPH_ENTITY_SCHEMA_VERSION
    normalization_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryGraphEdgeUpsert(BaseModel):
    """Seed/extraction DTO for one evidence-backed relation candidate."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    workspace_id: str | None = None
    session_id: str | None = None
    source_node_id: str
    target_node_id: str
    source_entity_name: str | None = None
    target_entity_name: str | None = None
    relation_type: str
    relation_family: str = GRAPH_RELATION_FAMILY_STABLE_SETUP
    relation_schema_version: str = GRAPH_RELATION_SCHEMA_VERSION
    raw_relation_text: str | None = None
    source_layer: str = GRAPH_SOURCE_LAYER_ARCHIVAL
    source_status: str = GRAPH_SOURCE_STATUS_SOURCE_REFERENCE
    confidence: float | None = None
    direction: str = GRAPH_EDGE_DIRECTION_DIRECTED
    valid_from: str | None = None
    valid_to: str | None = None
    branch_id: str | None = None
    canon_status: str = GRAPH_CANON_STATUS_SOURCE_REFERENCE
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryGraphEvidenceUpsert(BaseModel):
    """Seed/extraction DTO that preserves retrieval-core provenance pointers."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    workspace_id: str | None = None
    node_id: str | None = None
    edge_id: str | None = None
    source_layer: str = GRAPH_SOURCE_LAYER_ARCHIVAL
    source_family: str | None = None
    source_type: str | None = None
    import_event: str | None = None
    source_ref: str | None = None
    source_asset_id: str | None = None
    collection_id: str | None = None
    parsed_document_id: str | None = None
    chunk_id: str | None = None
    section_id: str | None = None
    domain: str | None = None
    domain_path: str | None = None
    commit_id: str | None = None
    step_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    evidence_excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryGraphExtractionJobUpsert(BaseModel):
    """Seed/extraction DTO for graph maintenance job rows."""

    model_config = ConfigDict(extra="forbid")

    graph_job_id: str
    workspace_id: str | None = None
    session_id: str | None = None
    commit_id: str | None = None
    source_layer: str = GRAPH_SOURCE_LAYER_ARCHIVAL
    source_asset_id: str | None = None
    chunk_id: str | None = None
    section_id: str | None = None
    input_fingerprint: str
    status: str = GRAPH_JOB_STATUS_QUEUED
    attempt_count: int = 0
    model_config_ref: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    extraction_schema_version: str = GRAPH_EXTRACTION_SCHEMA_VERSION
    taxonomy_version: str = GRAPH_TAXONOMY_VERSION
    token_usage: dict[str, Any] = Field(default_factory=dict)
    warning_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    queued_reason: str | None = None
    retry_after: datetime | None = None
    completed_at: datetime | None = None


class MemoryGraphNodeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    type: str
    story_id: str
    workspace_id: str | None = None
    session_id: str | None = None
    source_layer: str
    source_status: str
    confidence: float | None = None
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    first_seen_source_ref: str | None = None
    entity_schema_version: str
    normalization_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MemoryGraphEdgeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    story_id: str
    workspace_id: str | None = None
    session_id: str | None = None
    source: str
    target: str
    source_entity_name: str | None = None
    target_entity_name: str | None = None
    label: str
    relation_family: str
    relation_schema_version: str
    raw_relation_text: str | None = None
    source_layer: str
    source_status: str
    confidence: float | None = None
    direction: str
    valid_from: str | None = None
    valid_to: str | None = None
    branch_id: str | None = None
    canon_status: str
    evidence_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MemoryGraphEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    story_id: str
    workspace_id: str | None = None
    node_id: str | None = None
    edge_id: str | None = None
    source_layer: str
    source_family: str | None = None
    source_type: str | None = None
    import_event: str | None = None
    source_ref: str | None = None
    source_asset_id: str | None = None
    collection_id: str | None = None
    parsed_document_id: str | None = None
    chunk_id: str | None = None
    section_id: str | None = None
    domain: str | None = None
    domain_path: str | None = None
    commit_id: str | None = None
    step_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MemoryGraphExtractionJobView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_job_id: str
    story_id: str
    workspace_id: str | None = None
    session_id: str | None = None
    commit_id: str | None = None
    source_layer: str
    source_asset_id: str | None = None
    chunk_id: str | None = None
    section_id: str | None = None
    input_fingerprint: str
    status: str
    attempt_count: int
    model_config_ref: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    extraction_schema_version: str
    taxonomy_version: str
    token_usage: dict[str, Any] = Field(default_factory=dict)
    warning_codes: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    queued_reason: str | None = None
    retry_after: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class MemoryGraphMaintenanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    graph_backend: str = GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT
    graph_extraction_enabled: bool = True
    graph_extraction_configured: bool = False
    graph_extraction_model_config_ref: str | None = None
    graph_extraction_provider_id: str | None = None
    graph_extraction_model_id: str | None = None
    maintenance_warnings: list[str] = Field(default_factory=list)
    source_layers: list[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    evidence_count: int = 0
    job_count: int = 0
    queued_job_count: int = 0
    running_job_count: int = 0
    completed_job_count: int = 0
    failed_job_count: int = 0
    skipped_job_count: int = 0
    cancelled_job_count: int = 0
    retryable_job_ids: list[str] = Field(default_factory=list)
    warning_code_counts: dict[str, int] = Field(default_factory=dict)
    error_code_counts: dict[str, int] = Field(default_factory=dict)
    recent_jobs: list[MemoryGraphExtractionJobView] = Field(default_factory=list)


class MemoryGraphNodeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    graph_backend: str = GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT
    source_layer: str | None = None
    object: Literal["list"] = "list"
    data: list[MemoryGraphNodeView] = Field(default_factory=list)


class MemoryGraphEdgeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    graph_backend: str = GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT
    source_layer: str | None = None
    object: Literal["list"] = "list"
    data: list[MemoryGraphEdgeView] = Field(default_factory=list)


class MemoryGraphEvidenceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    graph_backend: str = GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT
    source_layer: str | None = None
    object: Literal["list"] = "list"
    data: list[MemoryGraphEvidenceView] = Field(default_factory=list)


class MemoryGraphNeighborhoodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    graph_backend: str = GRAPH_BACKEND_POSTGRES_LIGHTWEIGHT
    source_layer: str | None = None
    anchor_node_id: str | None = None
    max_depth: int = 1
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    nodes: list[MemoryGraphNodeView] = Field(default_factory=list)
    edges: list[MemoryGraphEdgeView] = Field(default_factory=list)
    evidence: list[MemoryGraphEvidenceView] = Field(default_factory=list)
