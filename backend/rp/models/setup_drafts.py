"""Typed setup draft objects for the SetupAgent MVP."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rp.models.retrieval_runtime_config import GraphExtractionRetryPolicy
from rp.models.setup_stage import SetupStageId


class StoryConfigDraft(BaseModel):
    """Current story configuration draft held inside SetupWorkspace."""

    model_config = ConfigDict(extra="forbid")

    model_profile_ref: str | None = None
    worker_profile_ref: str | None = None
    post_write_policy_preset: str | None = None
    retrieval_embedding_model_id: str | None = None
    retrieval_embedding_provider_id: str | None = None
    retrieval_rerank_model_id: str | None = None
    retrieval_rerank_provider_id: str | None = None
    graph_extraction_provider_id: str | None = None
    graph_extraction_model_id: str | None = None
    graph_extraction_structured_output_mode: str | None = None
    graph_extraction_temperature: float | None = None
    graph_extraction_max_output_tokens: int | None = None
    graph_extraction_timeout_ms: int | None = None
    graph_extraction_retry_policy: GraphExtractionRetryPolicy | None = None
    graph_extraction_fallback_model_ref: str | None = None
    graph_extraction_enabled: bool | None = None
    notes: str | None = None


class WritingContractDraft(BaseModel):
    """Current writing contract draft for prestory setup."""

    model_config = ConfigDict(extra="forbid")

    pov_rules: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    writing_constraints: list[str] = Field(default_factory=list)
    task_writing_rules: list[str] = Field(default_factory=list)
    notes: str | None = None


class SetupDraftSectionKind(StrEnum):
    """Backend-renderable setup draft section kinds."""

    TEXT = "text"
    LIST = "list"
    KEY_VALUE = "key_value"


class SetupDraftSection(BaseModel):
    """One renderable, retrieval-addressable section inside a setup draft entry."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    kind: SetupDraftSectionKind
    content: dict[str, Any] = Field(default_factory=dict)
    retrieval_role: Literal["summary", "detail", "rule", "relationship", "note"] = "detail"
    tags: list[str] = Field(default_factory=list)

    @field_validator("section_id", "title")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @model_validator(mode="after")
    def _validate_content_shape(self) -> "SetupDraftSection":
        if self.kind == SetupDraftSectionKind.TEXT:
            text = self.content.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("text section requires content.text")
        elif self.kind == SetupDraftSectionKind.LIST:
            items = self.content.get("items")
            if not isinstance(items, list) or not items:
                raise ValueError("list section requires non-empty content.items")
        elif self.kind == SetupDraftSectionKind.KEY_VALUE:
            values = self.content.get("values")
            if not isinstance(values, dict) or not values:
                raise ValueError("key_value section requires non-empty content.values")
        return self


class SetupDraftEntry(BaseModel):
    """Stable setup draft entry grammar with flexible domain content in sections."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    entry_type: str
    semantic_path: str
    title: str
    display_label: str | None = None
    summary: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sections: list[SetupDraftSection] = Field(default_factory=list)

    @field_validator("entry_id", "entry_type", "semantic_path", "title")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text


class SetupStageDraftBlock(BaseModel):
    """Canonical data-driven setup draft block owned by one setup stage."""

    model_config = ConfigDict(extra="forbid")

    stage_id: SetupStageId
    entries: list[SetupDraftEntry] = Field(default_factory=list)
    notes: str | None = None


class FoundationEntry(BaseModel):
    """One structured foundation entry staged during setup."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    domain: Literal["world", "character", "rule"]
    path: str
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    content: dict[str, Any] = Field(default_factory=dict)


class FoundationDraft(BaseModel):
    """Foundation draft block stored inside SetupWorkspace."""

    model_config = ConfigDict(extra="forbid")

    entries: list[FoundationEntry] = Field(default_factory=list)


class ChapterBlueprintEntry(BaseModel):
    """One structured chapter blueprint item."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    title: str | None = None
    purpose: str | None = None
    major_beats: list[str] = Field(default_factory=list)
    setup_payoff_targets: list[str] = Field(default_factory=list)


class LongformBlueprintDraft(BaseModel):
    """Longform blueprint draft used by the SetupAgent MVP."""

    model_config = ConfigDict(extra="forbid")

    premise: str | None = None
    central_conflict: str | None = None
    protagonist_arc: str | None = None
    cast_plan: str | None = None
    chapter_strategy: str | None = None
    section_strategy: str | None = None
    ending_direction: str | None = None
    chapter_blueprints: list[ChapterBlueprintEntry] = Field(default_factory=list)
