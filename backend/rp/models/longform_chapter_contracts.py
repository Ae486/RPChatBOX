"""Typed contracts for longform outline progress and chapter bridge sidecars."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from rp.models.memory_contract_registry import MemoryRuntimeIdentity

LONGFORM_OUTLINE_SCHEMA_VERSION: Literal["longform_outline_v1"] = (
    "longform_outline_v1"
)


class LongformOutlineBeat(BaseModel):
    """One stable longform outline beat used by packet assembly and progress."""

    model_config = ConfigDict(extra="forbid")

    beat_id: str
    order: int = Field(ge=1)
    title: str
    goal: str
    must_include: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("beat_id", "title", "goal")
    @classmethod
    def _require_text(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must be non-empty")
        return normalized

    @field_validator("must_include", "avoid", "continuity_notes")
    @classmethod
    def _normalize_text_list(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class LongformStructuredOutline(BaseModel):
    """Canonical structured outline used for beat tracking."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["longform_outline_v1"] = LONGFORM_OUTLINE_SCHEMA_VERSION
    chapter_index: int = Field(ge=1)
    chapter_title: str | None = None
    chapter_goal: str
    beats: list[LongformOutlineBeat]
    constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("chapter_title", "chapter_goal")
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
            if info.field_name == "chapter_goal":
                raise ValueError("chapter_goal must be non-empty")
            return None
        return normalized

    @model_validator(mode="after")
    def _validate_beats(self) -> "LongformStructuredOutline":
        if not self.beats:
            raise ValueError("beats must be non-empty")
        beat_ids: set[str] = set()
        orders: set[int] = set()
        ordered = sorted(self.beats, key=lambda beat: (beat.order, beat.beat_id))
        for beat in ordered:
            beat_key = beat.beat_id.casefold()
            if beat_key in beat_ids:
                raise ValueError(f"duplicate beat_id: {beat.beat_id}")
            beat_ids.add(beat_key)
            if beat.order in orders:
                raise ValueError(f"duplicate beat order: {beat.order}")
            orders.add(beat.order)
        self.beats = ordered
        return self

    def beat_by_id(self, beat_id: str | None) -> LongformOutlineBeat | None:
        normalized = str(beat_id or "").strip()
        if not normalized:
            return None
        for beat in self.beats:
            if beat.beat_id == normalized:
                return beat
        return None


class LongformOutlineProgress(BaseModel):
    """Branch-scoped outline progress sidecar for one chapter."""

    model_config = ConfigDict(extra="forbid")

    outline_artifact_id: str
    chapter_index: int = Field(ge=1)
    current_beat_id: str | None = None
    covered_beat_ids: list[str] = Field(default_factory=list)
    segment_by_beat_id: dict[str, str] = Field(default_factory=dict)
    status_by_beat_id: dict[str, str] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("outline_artifact_id", "current_beat_id")
    @classmethod
    def _normalize_progress_text(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            if info.field_name == "outline_artifact_id":
                raise ValueError("outline_artifact_id must be non-empty")
            return None
        return normalized

    @field_validator("covered_beat_ids")
    @classmethod
    def _normalize_covered_beat_ids(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @field_validator("segment_by_beat_id", mode="before")
    @classmethod
    def _normalize_segment_map(
        cls,
        values: dict[str, str] | None,
    ) -> dict[str, str]:
        if not isinstance(values, dict):
            return {}
        normalized: dict[str, str] = {}
        for beat_id, artifact_id in values.items():
            normalized_beat_id = str(beat_id or "").strip()
            normalized_artifact_id = str(artifact_id or "").strip()
            if not normalized_beat_id or not normalized_artifact_id:
                continue
            normalized[normalized_beat_id] = normalized_artifact_id
        return normalized

    @field_validator("status_by_beat_id", mode="before")
    @classmethod
    def _normalize_status_map(
        cls,
        values: dict[str, str] | None,
    ) -> dict[str, str]:
        if not isinstance(values, dict):
            return {}
        normalized: dict[str, str] = {}
        for beat_id, status in values.items():
            normalized_beat_id = str(beat_id or "").strip()
            normalized_status = str(status or "").strip().lower()
            if not normalized_beat_id or not normalized_status:
                continue
            normalized[normalized_beat_id] = normalized_status
        return normalized

    @classmethod
    def initialize(
        cls,
        *,
        outline_artifact_id: str,
        outline: LongformStructuredOutline,
        metadata_json: dict[str, Any] | None = None,
    ) -> "LongformOutlineProgress":
        current_beat_id = outline.beats[0].beat_id if outline.beats else None
        return cls(
            outline_artifact_id=outline_artifact_id,
            chapter_index=outline.chapter_index,
            current_beat_id=current_beat_id,
            covered_beat_ids=[],
            segment_by_beat_id={},
            status_by_beat_id={
                beat.beat_id: ("current" if beat.beat_id == current_beat_id else "pending")
                for beat in outline.beats
            },
            metadata_json=dict(metadata_json or {}),
        )


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
    covered_beat_ids: list[str] = Field(default_factory=list)
    continuity_refs: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
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

    @field_validator(
        "covered_beat_ids",
        "continuity_refs",
        "continuity_notes",
        "open_threads",
        "source_refs",
    )
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


def _normalize_text_list(values: list[str]) -> list[str]:
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
