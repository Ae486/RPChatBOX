"""Typed Runtime Workspace material contracts for current-turn memory work."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)


RUNTIME_WORKSPACE_MATERIAL_LAYER = "runtime_workspace"

RUNTIME_WORKSPACE_BOUNDARY_METADATA: dict[str, Any] = {
    "memory_layer": RUNTIME_WORKSPACE_MATERIAL_LAYER,
    "semantic_layer": "Runtime Workspace",
    "temporary": True,
    "source_of_truth": False,
    "authoritative_mutation": False,
    "core_state_truth": False,
    "recall_truth": False,
    "archival_truth": False,
    "materialized_to_recall": False,
    "materialized_to_archival": False,
}


class RuntimeWorkspaceMaterialKind(StrEnum):
    """Known current-turn material kinds kept in Runtime Workspace."""

    WRITER_INPUT_REF = "writer_input_ref"
    WRITER_OUTPUT_REF = "writer_output_ref"
    RETRIEVAL_CARD = "retrieval_card"
    RETRIEVAL_EXPANDED_CHUNK = "retrieval_expanded_chunk"
    RETRIEVAL_MISS = "retrieval_miss"
    RETRIEVAL_USAGE_RECORD = "retrieval_usage_record"
    RULE_CARD = "rule_card"
    RULE_STATE_CARD = "rule_state_card"
    REVIEW_OVERLAY = "review_overlay"
    WORKER_CANDIDATE = "worker_candidate"
    WORKER_EVIDENCE_BUNDLE = "worker_evidence_bundle"
    POST_WRITE_TRACE = "post_write_trace"
    PACKET_REF = "packet_ref"
    TOKEN_USAGE_METADATA = "token_usage_metadata"


class RuntimeWorkspaceMaterialLifecycle(StrEnum):
    """Lifecycle state for Runtime Workspace turn material."""

    ACTIVE = "active"
    USED = "used"
    UNUSED = "unused"
    EXPANDED = "expanded"
    PROMOTED = "promoted"
    DISCARDED = "discarded"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class RuntimeWorkspaceMaterialVisibility(StrEnum):
    """Initial visibility labels for Runtime Workspace material."""

    RUNTIME_PRIVATE = "runtime_private"
    WORKER_VISIBLE = "worker_visible"
    WRITER_VISIBLE = "writer_visible"
    REVIEW_VISIBLE = "review_visible"


class RuntimeWorkspaceMaterial(BaseModel):
    """Identity-scoped current-turn material that is not durable story truth."""

    model_config = ConfigDict(extra="forbid")

    material_id: str
    material_kind: RuntimeWorkspaceMaterialKind
    identity: MemoryRuntimeIdentity
    domain: str
    domain_path: str | None = None
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    short_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    lifecycle: RuntimeWorkspaceMaterialLifecycle = (
        RuntimeWorkspaceMaterialLifecycle.ACTIVE
    )
    visibility: str
    created_by: str
    expiration_ref: str | None = None
    materialization_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("material_id", "domain", "visibility", "created_by")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("domain_path", "short_id", "expiration_ref", "materialization_ref")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name=info.field_name or "value")

    @model_validator(mode="after")
    def _mark_runtime_workspace_boundary(self) -> "RuntimeWorkspaceMaterial":
        self.metadata = {
            **self.metadata,
            **RUNTIME_WORKSPACE_BOUNDARY_METADATA,
        }
        return self


class RuntimeWorkspaceMaterialQuery(BaseModel):
    """Optional query envelope for callers that need to carry full identity."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    material_kind: RuntimeWorkspaceMaterialKind | None = None
    domain: str | None = None
    lifecycle: RuntimeWorkspaceMaterialLifecycle | None = None

    @field_validator("domain")
    @classmethod
    def _normalize_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _optional_non_blank(value, field_name="domain")


class RuntimeWorkspaceMaterialReceipt(BaseModel):
    """Receipt returned when a material write emits a trace event skeleton."""

    model_config = ConfigDict(extra="forbid")

    material: RuntimeWorkspaceMaterial
    event: MemoryChangeEvent


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
