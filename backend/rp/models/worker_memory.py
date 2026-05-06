"""Internal worker memory context and governance contracts."""

from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef


def _require_non_blank(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _normalize_text_list(values: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _require_non_blank(value, field_name=field_name)
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


class WorkerMemoryContext(BaseModel):
    """Pinned runtime context that every internal worker memory call must carry."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    worker_id: str
    phase: str
    domain: str | None = None
    block_id: str | None = None
    runtime_profile_snapshot_id: str
    permission_profile: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)

    @field_validator("worker_id", "phase", "runtime_profile_snapshot_id")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("domain", "block_id")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("trace_refs")
    @classmethod
    def _dedupe_trace_refs(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="trace_refs")

    @model_validator(mode="after")
    def _align_snapshot_id(self) -> "WorkerMemoryContext":
        if (
            self.runtime_profile_snapshot_id
            != self.identity.runtime_profile_snapshot_id
        ):
            raise ValueError(
                "runtime_profile_snapshot_id must match identity.runtime_profile_snapshot_id"
            )
        return self


class WorkerPermissionDecision(BaseModel):
    """Resolved permission decision for one worker memory operation."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    permission_decision: str
    reason_codes: list[str] = Field(default_factory=list)
    runtime_profile_snapshot_id: str
    permission_profile: dict[str, Any] = Field(default_factory=dict)

    @field_validator("permission_decision", "runtime_profile_snapshot_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("reason_codes")
    @classmethod
    def _normalize_reason_codes(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values, field_name="reason_codes")


class WorkerSourceRefBundle(BaseModel):
    """Runtime material ids that can later back governed post-write source refs."""

    model_config = ConfigDict(extra="forbid")

    retrieval_card_material_ids: list[str] = Field(default_factory=list)
    retrieval_expanded_chunk_material_ids: list[str] = Field(default_factory=list)
    retrieval_usage_material_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "retrieval_card_material_ids",
        "retrieval_expanded_chunk_material_ids",
        "retrieval_usage_material_ids",
    )
    @classmethod
    def _normalize_material_ids(
        cls, values: list[str], info: ValidationInfo
    ) -> list[str]:
        return _normalize_text_list(
            values, field_name=info.field_name or "material_ids"
        )

    def is_empty(self) -> bool:
        return not (
            self.retrieval_card_material_ids
            or self.retrieval_expanded_chunk_material_ids
            or self.retrieval_usage_material_ids
        )

    def to_source_refs(self) -> list[MemorySourceRef]:
        refs: list[MemorySourceRef] = []
        for source_type, material_ids in (
            ("retrieval_card_material", self.retrieval_card_material_ids),
            (
                "retrieval_expanded_chunk_material",
                self.retrieval_expanded_chunk_material_ids,
            ),
            ("retrieval_usage_material", self.retrieval_usage_material_ids),
        ):
            refs.extend(
                MemorySourceRef(
                    source_type=source_type,
                    source_id=material_id,
                    layer="runtime_workspace",
                    metadata={"source_of_truth": False},
                )
                for material_id in material_ids
            )
        return refs


class WorkerProposalGovernanceMetadata(BaseModel):
    """Internal governance metadata carried into proposal/apply persistence."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    worker_id: str
    phase: str
    runtime_profile_snapshot_id: str
    permission_decision: str
    permission_reason_codes: list[str] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "worker_id",
        "phase",
        "runtime_profile_snapshot_id",
        "permission_decision",
    )
    @classmethod
    def _require_governance_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("permission_reason_codes", "trace_refs")
    @classmethod
    def _normalize_lists(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _normalize_text_list(values, field_name=info.field_name or "values")
