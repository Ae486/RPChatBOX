"""Runtime workflow job ledger contracts for turn finalization."""

from __future__ import annotations

from enum import StrEnum


class RuntimeWorkflowJobKind(StrEnum):
    REQUIRED_POST_WRITE_ANALYSIS = "required_post_write_analysis"
    RUNTIME_WORKSPACE_FINALIZE = "runtime_workspace_finalize"
    PROJECTION_REFRESH = "projection_refresh"
    PROPOSAL_SUBMIT = "proposal_submit"
    PROPOSAL_APPLY = "proposal_apply"
    RETRIEVAL_USAGE_PERSIST = "retrieval_usage_persist"
    RECALL_MATERIALIZATION = "recall_materialization"
    ARCHIVAL_MATERIALIZATION = "archival_materialization"
    ARCHIVAL_REINDEX = "archival_reindex"
    REPAIR_RETRY = "repair_retry"
    REPAIR_RECOMPUTE = "repair_recompute"
    CLEANUP_EXPIRE_WORKSPACE = "cleanup_expire_workspace"
    CLEANUP_INVALIDATE_CANDIDATES = "cleanup_invalidate_candidates"


class RuntimeWorkflowJobCategory(StrEnum):
    TURN_FINALIZATION = "turn-finalization"
    STATE_GOVERNANCE = "state-governance"
    MEMORY_MATERIALIZATION = "memory-materialization"
    MAINTENANCE_AND_REPAIR = "maintenance-and-repair"


class RuntimeWorkflowJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"


class RuntimeWorkflowJobCreationMode(StrEnum):
    CREATION_TIME_OBLIGATION = "creation_time_obligation"
    DERIVED = "derived"
