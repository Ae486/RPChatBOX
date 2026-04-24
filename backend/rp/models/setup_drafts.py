"""Typed setup draft objects for the SetupAgent MVP."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    notes: str | None = None


class WritingContractDraft(BaseModel):
    """Current writing contract draft for prestory setup."""

    model_config = ConfigDict(extra="forbid")

    pov_rules: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    writing_constraints: list[str] = Field(default_factory=list)
    task_writing_rules: list[str] = Field(default_factory=list)
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
