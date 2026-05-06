"""Contracts for governed Archival Knowledge Story Evolution edits."""

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

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef


ARCHIVAL_EVOLUTION_EVENT = "story_evolution.archival_edit"
ARCHIVAL_EVOLUTION_SOURCE_FAMILY = "story_evolution"
ARCHIVAL_LIFECYCLE_ACTIVE = "active"
ARCHIVAL_LIFECYCLE_SUPERSEDED = "superseded"
ARCHIVAL_VISIBILITY_ACTIVE = "active"


class ArchivalEvolutionVisibilityScope(StrEnum):
    """Governed visibility scopes for runtime-authored Archival versions."""

    CURRENT_BRANCH = "current_branch"
    SELECTED_BRANCHES = "selected_branches"
    ALL_EXISTING_BRANCHES = "all_existing_branches"
    STORY_GLOBAL = "story_global"


class ArchivalEvolutionSection(BaseModel):
    """Replacement source section rendered through the existing retrieval parser."""

    model_config = ConfigDict(extra="allow")

    section_id: str | None = None
    title: str | None = None
    path: str | None = None
    level: int = 1
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _require_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must be non-empty")
        return normalized

    @field_validator("section_id", "title", "path")
    @classmethod
    def _normalize_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name or 'value'} must be non-empty")
        return normalized

    @field_validator("level")
    @classmethod
    def _normalize_level(cls, value: int) -> int:
        return max(1, int(value))

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, values: list[str]) -> list[str]:
        return _dedupe_text_values(values)


class ArchivalEvolutionRequest(BaseModel):
    """Request to create a versioned Archival source replacement."""

    model_config = ConfigDict(extra="forbid")

    identity: MemoryRuntimeIdentity
    actor: str
    source_asset_id: str
    expected_source_version: int | None = None
    visibility_scope: ArchivalEvolutionVisibilityScope = (
        ArchivalEvolutionVisibilityScope.CURRENT_BRANCH
    )
    selected_branch_head_ids: list[str] = Field(default_factory=list)
    replacement_sections: list[ArchivalEvolutionSection] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None

    @field_validator("actor", "source_asset_id")
    @classmethod
    def _require_required_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")

    @field_validator("selected_branch_head_ids")
    @classmethod
    def _normalize_selected_branches(cls, values: list[str]) -> list[str]:
        return _dedupe_text_values(values)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, field_name="reason")

    @model_validator(mode="after")
    def _validate_visibility_and_sections(self) -> "ArchivalEvolutionRequest":
        if not self.replacement_sections:
            raise ValueError("replacement_sections must include at least one section")
        if (
            self.visibility_scope == ArchivalEvolutionVisibilityScope.SELECTED_BRANCHES
            and not self.selected_branch_head_ids
        ):
            raise ValueError(
                "selected_branches visibility requires selected_branch_head_ids"
            )
        return self


class ArchivalEvolutionReceipt(BaseModel):
    """Trace receipt linking source version, chunks, reindex jobs, and events."""

    model_config = ConfigDict(extra="forbid")

    evolution_id: str
    source_asset_id: str
    superseded_source_asset_id: str | None = None
    root_source_asset_id: str
    new_source_version: int
    superseded_source_version: int | None = None
    visibility_scope: ArchivalEvolutionVisibilityScope
    selected_branch_head_ids: list[str] = Field(default_factory=list)
    replacement_chunk_ids: list[str] = Field(default_factory=list)
    reindex_job_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("evolution_id", "source_asset_id", "root_source_asset_id")
    @classmethod
    def _require_receipt_text(cls, value: str, info: ValidationInfo) -> str:
        return _require_non_blank(value, field_name=info.field_name or "value")


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _dedupe_text_values(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _require_non_blank(str(value), field_name="value")
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized_values.append(normalized)
    return normalized_values
