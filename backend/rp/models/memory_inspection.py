"""User-visible memory inspection and governed edit contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity


class RecallReviewAction(StrEnum):
    """Governed Recall actions exposed to user-visible review tools."""

    RECOMPUTE = "recompute"
    INVALIDATE = "invalidate"
    SUPERSEDE = "supersede"


class RecallReviewCommand(BaseModel):
    """Layer-specific Recall review command.

    This model intentionally stays separate from Core direct edit and Archival
    evolution requests so the public memory API cannot collapse all layers into
    a generic CRUD write path.
    """

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    action: RecallReviewAction
    material_refs: list[str]
    reason: str | None = None
    event_id: str | None = None

    @field_validator("actor")
    @classmethod
    def _require_actor(cls, value: str) -> str:
        return _require_non_blank(value, field_name="actor")

    @field_validator("material_refs")
    @classmethod
    def _normalize_material_refs(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            ref = _require_non_blank(value, field_name="material_refs")
            if ref in seen:
                continue
            seen.add(ref)
            normalized.append(ref)
        if not normalized:
            raise ValueError("material_refs must include at least one ref")
        return normalized

    @field_validator("reason", "event_id")
    @classmethod
    def _normalize_optional_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, field_name=info.field_name or "value")


class MemoryInspectionQuery(BaseModel):
    """Shared query envelope for branch-aware visible memory inspection."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    layers: list[str] | None = None
    domains: list[str] | None = None
    include_hidden_audit: bool = False

    @field_validator("layers", "domains")
    @classmethod
    def _normalize_optional_text_list(
        cls,
        values: list[str] | None,
        info: ValidationInfo,
    ) -> list[str] | None:
        if values is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = _require_non_blank(value, field_name=info.field_name or "value")
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)
        return normalized


class MemoryDisplayEntry(BaseModel):
    """Canonical user-visible entry envelope shared by UI and governance trace."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    entry_type: str
    label: str | None = None
    current_value: Any = None
    editable_fields: list[str] = Field(default_factory=list)
    field_validation_rules: dict[str, Any] = Field(default_factory=dict)
    base_revision: int | None = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    user_edit_metadata: dict[str, Any] = Field(default_factory=dict)
    conflict_state: str | None = None
    last_modified_actor: str | None = None
    last_modified_turn_or_event_id: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class MemoryDisplayBlock(BaseModel):
    """Canonical user-visible block envelope for memory inspection surfaces."""

    model_config = ConfigDict(extra="forbid")

    block_id: str
    domain: str
    layer: str
    scope: str | None = None
    visibility: dict[str, Any]
    revision: int | None = None
    permission_level: dict[str, Any] = Field(default_factory=dict)
    lifecycle_state: str | None = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    editable_fields: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    entrypoints: dict[str, Any] = Field(default_factory=dict)
    entries: list[MemoryDisplayEntry] = Field(default_factory=list)


class MemoryInspectionActionReceipt(BaseModel):
    """Small trace receipt for user-visible Recall review routing."""

    model_config = ConfigDict(extra="forbid")

    action: RecallReviewAction
    identity: MemoryRuntimeIdentity
    actor: str
    material_refs: list[str] = Field(default_factory=list)
    touched_material_refs: list[str] = Field(default_factory=list)
    event_id: str | None = None
    routed_through: str
    reason: str | None = None


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
