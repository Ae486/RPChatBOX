"""Structured post-write runtime contracts for worker maintenance."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef


class PostWriteRunKind(StrEnum):
    MINIMAL_ONLY = "minimal_only"
    FULL_SCHEDULE = "full_schedule"
    SKIPPED = "skipped"


class PostWriteTriggerContext(BaseModel):
    """Deterministic trigger facts used before worker scheduling."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    turn_id: str
    mode: str
    turn_kind: str
    command_kind: str
    retrieval_occurred: bool = False
    manual_core_edit_occurred: bool = False
    rule_card_present: bool = False
    scene_switch_detected: bool = False
    chapter_transition_detected: bool = False
    dirty_domains: list[str] = Field(default_factory=list)
    pending_threshold_reached: bool = False
    full_schedule_due_by_frequency: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id", "mode", "turn_kind", "command_kind")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("dirty_domains")
    @classmethod
    def _normalize_dirty_domains(cls, values: list[str]) -> list[str]:
        return _unique_non_blank(values, field_name="dirty_domains")


class WorkerProposalGovernanceEnvelope(BaseModel):
    """Traceable governance envelope derived from one structured WorkerResult."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    phase: str
    identity: MemoryRuntimeIdentity
    permission_decision: str
    permission_reason_codes: list[str] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    base_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("worker_id", "phase", "permission_decision")
    @classmethod
    def _require_governance_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("permission_reason_codes", "trace_refs")
    @classmethod
    def _normalize_text_lists(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        return _unique_non_blank(values, field_name=info.field_name or "values")


class PostWriteGovernanceDispatchResult(BaseModel):
    """Result refs produced by post-write governance dispatch."""

    model_config = ConfigDict(extra="forbid")

    selected_worker_result_refs: list[str] = Field(default_factory=list)
    projection_refresh_job_refs: list[str] = Field(default_factory=list)
    proposal_job_refs: list[str] = Field(default_factory=list)
    materialization_job_refs: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "selected_worker_result_refs",
        "projection_refresh_job_refs",
        "proposal_job_refs",
        "materialization_job_refs",
        "trace_refs",
    )
    @classmethod
    def _normalize_ref_lists(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        return _unique_non_blank(values, field_name=info.field_name or "refs")


class PostWriteExecutionEnvelope(BaseModel):
    """Graph-visible, structured envelope for one post-write run."""

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    identity: MemoryRuntimeIdentity
    run_kind: PostWriteRunKind
    worker_plan_ref: str | None = None
    selected_worker_result_refs: list[str] = Field(default_factory=list)
    projection_refresh_job_refs: list[str] = Field(default_factory=list)
    proposal_job_refs: list[str] = Field(default_factory=list)
    materialization_job_refs: list[str] = Field(default_factory=list)
    repair_job_refs: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    settled: bool = False
    settlement_reason: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id")
    @classmethod
    def _require_turn_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="turn_id")

    @field_validator("worker_plan_ref", "settlement_reason")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @field_validator(
        "selected_worker_result_refs",
        "projection_refresh_job_refs",
        "proposal_job_refs",
        "materialization_job_refs",
        "repair_job_refs",
        "trace_refs",
    )
    @classmethod
    def _normalize_envelope_refs(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        return _unique_non_blank(values, field_name=info.field_name or "refs")


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional_non_blank(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty when provided")
    return normalized


def _unique_non_blank(values: list[str], *, field_name: str) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(value, field_name=field_name)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values
