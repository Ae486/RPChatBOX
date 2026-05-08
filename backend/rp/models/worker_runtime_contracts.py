"""Runtime-centric worker contracts for story-runtime bootstrap and scheduling."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity


class WorkerExecutionClass(StrEnum):
    """Scheduler-facing execution class for one worker."""

    ALWAYS_RUN = "always_run"
    SCHEDULED = "scheduled"
    POST_WRITE_OBSERVER = "post_write_observer"
    MAINTENANCE = "maintenance"


class WorkerPlanSource(StrEnum):
    """Source that produced one runtime worker execution plan."""

    ORCHESTRATOR = "orchestrator"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    POST_WRITE_REQUIRED = "post_write_required"


class WorkerResultStatus(StrEnum):
    """Structured result status returned by one worker executor."""

    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class WorkerDescriptor(BaseModel):
    """Runtime-facing descriptor consumed by registry, scheduler, and tests."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    display_name: str
    owned_domains: list[str] = Field(default_factory=list)
    read_domains: list[str] = Field(default_factory=list)
    allowed_layers: list[str] = Field(default_factory=list)
    tool_allowlist: list[str] = Field(default_factory=list)
    default_execution_policy: str
    supported_phases: list[str] = Field(default_factory=list)
    permission_profile_ref: str | None = None
    provider_defaults: dict[str, Any] = Field(default_factory=dict)
    model_defaults: dict[str, Any] = Field(default_factory=dict)
    context_slot_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema_version: str = "story-runtime.worker-result.v1"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "worker_id",
        "display_name",
        "default_execution_policy",
        "output_schema_version",
    )
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("permission_profile_ref")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="permission_profile_ref")

    @field_validator(
        "owned_domains",
        "read_domains",
        "allowed_layers",
        "tool_allowlist",
        "supported_phases",
    )
    @classmethod
    def _normalize_text_lists(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        return _normalize_unique_text_list(values, field_name=info.field_name or "value")


class WorkerExecutionPolicy(BaseModel):
    """Stable execution defaults resolved from registry into the scheduler layer."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str
    execution_class: WorkerExecutionClass
    blocking_default: bool
    allow_async: bool
    allow_degrade: bool
    must_record_trace: bool
    requires_runtime_workspace: bool
    requires_post_write_job: bool
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("policy_id")
    @classmethod
    def _require_policy_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="policy_id")


class WorkerExecutionRequest(BaseModel):
    """Scheduler-dispatch request for one worker execution."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    identity: MemoryRuntimeIdentity
    worker_id: str
    phase: str
    mode: str
    turn_id: str
    context_packet_ref: str | None = None
    context_packet: dict[str, Any] | None = None
    execution_policy: WorkerExecutionPolicy
    budget_class: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    scheduler_constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id", "worker_id", "phase", "mode", "turn_id")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("context_packet_ref", "budget_class")
    @classmethod
    def _normalize_optional_request_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator("reason_codes")
    @classmethod
    def _normalize_reason_codes(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="reason_codes")


class WorkerExecutionItem(BaseModel):
    """Selected worker after deterministic scheduler validation."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    must_run: bool
    allow_degrade: bool
    blocking: bool
    async_allowed: bool
    budget_class: str | None = None
    context_requirements: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    scheduler_constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("worker_id")
    @classmethod
    def _require_worker_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="worker_id")

    @field_validator("budget_class")
    @classmethod
    def _normalize_optional_budget_class(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="budget_class")

    @field_validator("reason_codes")
    @classmethod
    def _normalize_execution_reason_codes(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="reason_codes")


class WorkerSkipItem(BaseModel):
    """Structured record for a skipped worker candidate."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    skip_reason: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("worker_id", "skip_reason")
    @classmethod
    def _require_skip_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("reason_codes")
    @classmethod
    def _normalize_skip_reason_codes(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="reason_codes")


class WorkerDegradeItem(BaseModel):
    """Structured record for a degraded worker execution path."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    from_execution_class: WorkerExecutionClass
    to_execution_class: WorkerExecutionClass
    degrade_reason: str

    @field_validator("worker_id", "degrade_reason")
    @classmethod
    def _require_degrade_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class WorkerExecutionPlan(BaseModel):
    """Deterministic execution plan produced before any worker runs."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    identity: MemoryRuntimeIdentity
    plan_source: WorkerPlanSource
    phase: str
    selected_workers: list[WorkerExecutionItem] = Field(default_factory=list)
    skipped_workers: list[WorkerSkipItem] = Field(default_factory=list)
    degraded_workers: list[WorkerDegradeItem] = Field(default_factory=list)
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("plan_id", "phase")
    @classmethod
    def _require_plan_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class WorkerContextPacket(BaseModel):
    """Worker-facing input packet built by the context orchestration layer."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str
    identity: MemoryRuntimeIdentity
    worker_id: str
    phase: str
    mode: str
    session_refs: list[str] = Field(default_factory=list)
    recent_turn_refs: list[str] = Field(default_factory=list)
    core_projection_refs: list[str] = Field(default_factory=list)
    sidecar_refs: list[str] = Field(default_factory=list)
    retrieval_refs: list[str] = Field(default_factory=list)
    workspace_refs: list[str] = Field(default_factory=list)
    forbidden_context: list[str] = Field(default_factory=list)
    token_budget: dict[str, Any] = Field(default_factory=dict)
    packet_metadata: dict[str, Any] = Field(default_factory=dict)
    trace_refs: list[str] = Field(default_factory=list)

    @field_validator("packet_id", "worker_id", "phase", "mode")
    @classmethod
    def _require_packet_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "session_refs",
        "recent_turn_refs",
        "core_projection_refs",
        "sidecar_refs",
        "retrieval_refs",
        "workspace_refs",
        "forbidden_context",
        "trace_refs",
    )
    @classmethod
    def _normalize_packet_lists(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        return _normalize_unique_text_list(values, field_name=info.field_name or "value")


class WorkerResult(BaseModel):
    """Structured output returned by one worker executor."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    phase: str
    result_status: WorkerResultStatus
    writer_hints: list[dict[str, Any]] = Field(default_factory=list)
    projection_refresh_requests: list[dict[str, Any]] = Field(default_factory=list)
    proposal_candidates: list[dict[str, Any]] = Field(default_factory=list)
    recall_candidates: list[dict[str, Any]] = Field(default_factory=list)
    archival_candidates: list[dict[str, Any]] = Field(default_factory=list)
    validation_findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("worker_id", "phase")
    @classmethod
    def _require_result_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("evidence_refs")
    @classmethod
    def _normalize_evidence_refs(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text_list(values, field_name="evidence_refs")


class RuntimeWorkerRegistration(BaseModel):
    """Runtime worker registration resolved from snapshot + registry sources."""

    model_config = ConfigDict(extra="forbid")

    descriptor: WorkerDescriptor
    execution_policy: WorkerExecutionPolicy
    active: bool = True
    source_worker_id: str
    source_label: str | None = None
    activation_metadata: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_worker_id")
    @classmethod
    def _require_source_worker_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="source_worker_id")

    @field_validator("source_label")
    @classmethod
    def _normalize_optional_source_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="source_label")


class RuntimeWorkerRegistry(BaseModel):
    """Runtime-centric registry snapshot exposed to the scheduler layer."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str | None = None
    mode: str
    registry_version: str
    workers: list[RuntimeWorkerRegistration] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("snapshot_id")
    @classmethod
    def _normalize_optional_snapshot_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="snapshot_id")

    @field_validator("mode", "registry_version")
    @classmethod
    def _require_registry_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized


def _normalize_unique_text_list(values: list[str], *, field_name: str) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(value, field_name=field_name)
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values
