"""Closed scheduler failure categories and reason codes."""

from __future__ import annotations

from enum import StrEnum


class SchedulerFailureCategory(StrEnum):
    """Scheduler-level failure categories with stable wire values."""

    VALIDATION_ERROR = "validation_error"
    PERMISSION_ERROR = "permission_error"
    SOURCE_ERROR = "source_error"
    ORCHESTRATOR_ERROR = "orchestrator_error"
    WORKER_ERROR = "worker_error"
    RETRIEVAL_ERROR = "retrieval_error"
    GOVERNANCE_ERROR = "governance_error"
    PERSISTENCE_ERROR = "persistence_error"
    UPSTREAM_ERROR = "upstream_error"
    UNKNOWN_ERROR = "unknown_error"


class SchedulerReasonCode(StrEnum):
    """Central scheduler reason-code set with stable wire values."""

    WINDOW_FINGERPRINT_CONFLICT = "window_fingerprint_conflict"
    SOURCE_WINDOW_EMPTY = "source_window_empty"
    SOURCE_REF_NOT_FOUND = "source_ref_not_found"
    PARAGRAPH_NUMBER_OUT_OF_RANGE = "paragraph_number_out_of_range"
    WORKER_NOT_ACTIVE = "worker_not_active"
    WORKER_PERMISSION_DENIED = "worker_permission_denied"
    ORCHESTRATOR_SCHEMA_INVALID = "orchestrator_schema_invalid"
    ORCHESTRATOR_PROVIDER_ERROR = "orchestrator_provider_error"
    WORKER_OUTPUT_SCHEMA_INVALID = "worker_output_schema_invalid"
    WORKER_PROVIDER_ERROR = "worker_provider_error"
    RETRIEVAL_QUERY_FAILED = "retrieval_query_failed"
    GOVERNANCE_REJECTED = "governance_rejected"
    RECEIPT_WRITE_FAILED = "receipt_write_failed"
    UNKNOWN_ERROR = "unknown_error"
    MAINTENANCE_IN_PROGRESS = "maintenance_in_progress"
    TURN_IN_FLIGHT = "turn_in_flight"
    INTERRUPTED_BY_RESTART = "interrupted_by_restart"
    WORKER_DISABLED = "worker_disabled"
