"""User-visible memory inspection and governed edit contracts."""

from __future__ import annotations

from enum import StrEnum

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
