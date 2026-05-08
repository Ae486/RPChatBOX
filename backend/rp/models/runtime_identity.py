"""Runtime identity and compiled profile contracts for boot-bar memory slices."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.post_write_policy import (
    PostWriteMaintenancePolicy,
    build_balanced_policy,
)
from rp.models.retrieval_runtime_config import RetrievalRuntimeConfig


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class BranchHeadStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class BranchVisibilityState(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    DELETED = "deleted"


class BranchControlKind(StrEnum):
    BRANCH_CREATED = "branch_created"
    BRANCH_SWITCHED = "branch_switched"
    BRANCH_DELETED = "branch_deleted"
    ROLLBACK_APPLIED = "rollback_applied"


class StoryTurnStatus(StrEnum):
    STARTED = "started"
    WRITER_COMPLETED = "writer_completed"
    POST_WRITE_PENDING = "post_write_pending"
    POST_WRITE_RUNNING = "post_write_running"
    POST_WRITE_DEFERRED = "post_write_deferred"
    SETTLED = "settled"
    COMPLETED = "completed"
    FAILED = "failed"


class RuntimeProfileSnapshotStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class BranchControlReceipt(BaseModel):
    """Control-plane receipt for branch actions that do not create story turns."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    session_id: str
    story_id: str
    branch_head_id: str
    control_kind: BranchControlKind
    actor: str
    fork_origin_turn_id: str | None = None
    fork_base_turn_id: str | None = None
    from_branch_head_id: str | None = None
    to_branch_head_id: str | None = None
    target_turn_id: str | None = None
    source_ref_ids: list[str] = Field(default_factory=list)
    result_ref_ids: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class RuntimeProfileModeProfile(BaseModel):
    """Pinned mode-level runtime contract frozen into one snapshot."""

    model_config = ConfigDict(extra="forbid")

    mode: str
    registry_version: str
    mode_profile_ref: str | None = None
    mode_profile_version: int | None = None
    model_profile_ref: str | None = None
    worker_profile_ref: str | None = None

    @field_validator("mode", "registry_version")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


class RuntimeWorkerActivation(BaseModel):
    """Minimal worker activation descriptor compiled at snapshot publish time."""

    model_config = ConfigDict(extra="forbid")

    active: bool = True
    profile_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _default_writer_operation_modes() -> list[str]:
    return ["writing", "rewrite", "discussion"]


class RuntimeProfileWriterPolicy(BaseModel):
    """Pinned writer runtime policy derived from writer contract and mode rules."""

    model_config = ConfigDict(extra="forbid")

    supported_operation_modes: list[str] = Field(
        default_factory=_default_writer_operation_modes
    )
    retrieval_mode: str = "bounded_tool_loop"
    rewrite_requires_explicit_selection: bool = False
    discussion_summary_enabled: bool = True
    pov_rules: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    writing_constraints: list[str] = Field(default_factory=list)
    task_writing_rules: list[str] = Field(default_factory=list)


class RuntimeProfileBudgetLatencyPolicy(BaseModel):
    """Pinned budget/latency defaults for one immutable runtime snapshot."""

    model_config = ConfigDict(extra="forbid")

    max_blocking_analysis_workers: int = Field(default=1, ge=0)
    max_writer_workers: int = Field(default=1, ge=1)
    token_usage_source: str = "provider_usage_metadata"
    prewrite_estimation_enabled: bool = True


class RuntimeProfileSnapshotCompiledProfile(BaseModel):
    """Typed top-level compiled profile stored immutably on each snapshot row."""

    model_config = ConfigDict(extra="forbid")

    mode_profile: RuntimeProfileModeProfile
    domain_activation: dict[str, dict[str, Any]] = Field(default_factory=dict)
    block_activation: dict[str, dict[str, Any]] = Field(default_factory=dict)
    worker_activation: dict[str, RuntimeWorkerActivation] = Field(default_factory=dict)
    permission_profile: dict[str, Any] = Field(default_factory=dict)
    retrieval_policy: RetrievalRuntimeConfig = Field(
        default_factory=RetrievalRuntimeConfig
    )
    context_policy: dict[str, Any] = Field(default_factory=dict)
    packet_policy: dict[str, Any] = Field(default_factory=dict)
    writer_policy: RuntimeProfileWriterPolicy = Field(
        default_factory=RuntimeProfileWriterPolicy
    )
    post_write_policy: PostWriteMaintenancePolicy = Field(
        default_factory=build_balanced_policy
    )
    budget_latency_policy: RuntimeProfileBudgetLatencyPolicy = Field(
        default_factory=RuntimeProfileBudgetLatencyPolicy
    )
    writer_model_profile: dict[str, Any] = Field(default_factory=dict)
    worker_model_profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    mode_specific_settings: dict[str, Any] = Field(default_factory=dict)
