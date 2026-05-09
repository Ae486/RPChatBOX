"""Story Evolution contracts over governed Memory OS layer services."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.archival_evolution import ArchivalEvolutionVisibilityScope
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef


class StoryEvolutionTargetLayer(StrEnum):
    CORE = "core"
    RECALL = "recall"
    ARCHIVAL = "archival"


class StoryEvolutionOperation(StrEnum):
    EDIT = "edit"
    IMPORT = "import"
    INVALIDATE = "invalidate"
    RECOMPUTE = "recompute"
    PROMOTE_VISIBILITY = "promote_visibility"


class StoryEvolutionStatus(StrEnum):
    ACCEPTED = "accepted"
    PENDING_REINDEX = "pending_reindex"
    FAILED = "failed"


class StoryEvolutionRequest(BaseModel):
    """Layer-neutral Story Evolution command facade.

    M1 only routes Archival edit/import through the governed archival evolution
    service. Core and Recall remain on their existing governed edit/review paths.
    """

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor_id: str | None = None
    target_layer: StoryEvolutionTargetLayer
    operation: StoryEvolutionOperation
    visibility_scope: ArchivalEvolutionVisibilityScope = (
        ArchivalEvolutionVisibilityScope.CURRENT_BRANCH
    )
    selected_branch_head_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None

    @field_validator("actor_id", "reason")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name or 'value'} must be non-empty")
        return normalized

    @field_validator("selected_branch_head_ids")
    @classmethod
    def _normalize_selected_branch_ids(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized:
                raise ValueError("selected_branch_head_ids must be non-empty")
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized_values.append(normalized)
        return normalized_values


class StoryEvolutionReceipt(BaseModel):
    """Receipt returned by the story-level evolution facade."""

    model_config = ConfigDict(extra="forbid")

    evolution_id: str
    identity: MemoryRuntimeIdentity
    target_layer: StoryEvolutionTargetLayer
    operation: StoryEvolutionOperation
    visibility_scope: ArchivalEvolutionVisibilityScope
    affected_refs: list[MemorySourceRef] = Field(default_factory=list)
    reindex_job_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    status: StoryEvolutionStatus
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evolution_id")
    @classmethod
    def _require_evolution_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("evolution_id must be non-empty")
        return normalized
