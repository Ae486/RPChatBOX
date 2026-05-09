"""Typed contracts for longform chapter bridge and transition sidecars."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity


class ChapterBridgeMaterial(BaseModel):
    """Branch-scoped bridge sidecar for moving from one chapter to the next."""

    model_config = ConfigDict(extra="forbid")

    bridge_id: str
    session_id: str
    branch_head_id: str
    source_chapter_index: int = Field(ge=1)
    target_chapter_index: int = Field(ge=1)
    adopted_output_ref: str | None = None
    accepted_outline_ref: str | None = None
    chapter_goal_ref: str | None = None
    continuity_refs: list[str] = Field(default_factory=list)
    summary_text: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "bridge_id",
        "session_id",
        "branch_head_id",
        "adopted_output_ref",
        "accepted_outline_ref",
        "chapter_goal_ref",
        "summary_text",
    )
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
            if info.field_name in {"bridge_id", "session_id", "branch_head_id"}:
                raise ValueError(f"{info.field_name} must be non-empty")
            return None
        return normalized

    @field_validator("continuity_refs", "source_refs")
    @classmethod
    def _normalize_ref_list(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            output.append(normalized)
        return output


class LongformChapterTransitionReceipt(BaseModel):
    """Deterministic chapter-transition receipt recorded at complete_chapter."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    identity: MemoryRuntimeIdentity
    from_chapter_index: int = Field(ge=1)
    to_chapter_index: int = Field(ge=1)
    adopted_output_ref: str | None = None
    bridge_material_ref: str | None = None
    status: Literal["prepared", "completed", "blocked"]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("receipt_id", "adopted_output_ref", "bridge_material_ref")
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
            if info.field_name == "receipt_id":
                raise ValueError("receipt_id must be non-empty")
            return None
        return normalized
