"""Projection refresh request contract for derived Core State current views."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rp.models.dsl import ObjectRef
from rp.models.memory_contract_registry import (
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)


class ProjectionRefreshServiceError(ValueError):
    """Stable projection refresh error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class ProjectionRefreshRequest(BaseModel):
    """Metadata and freshness contract for one projection refresh operation."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity | None = None
    refresh_actor: str = "system"
    refresh_reason: str = "bundle_refresh"
    refresh_source_kind: str = "bundle_refresh"
    refresh_source_ref: str | None = None
    base_revision: int | None = None
    projection_dirty_state: str = "dirty"
    source_authoritative_refs: list[ObjectRef] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    dirty_targets: list[MemoryDirtyTarget] = Field(default_factory=list)

    @field_validator(
        "refresh_actor",
        "refresh_reason",
        "refresh_source_kind",
        "projection_dirty_state",
    )
    @classmethod
    def _require_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("projection refresh text fields must be non-empty")
        return normalized

    @field_validator("refresh_source_ref")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("refresh_source_ref must be non-empty when provided")
        return normalized

    @field_validator("base_revision")
    @classmethod
    def _validate_base_revision(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("base_revision must be >= 0")
        return value
