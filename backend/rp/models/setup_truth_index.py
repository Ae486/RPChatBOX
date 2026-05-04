"""Deterministic direct-read index over accepted setup stage snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.setup_stage import SetupStageId


class SetupTruthIndexFilters(BaseModel):
    """Lexical/path/filter search constraints for committed setup truth."""

    model_config = ConfigDict(extra="forbid")

    stage_ids: list[SetupStageId] = Field(default_factory=list)
    entry_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    semantic_path_prefix: str | None = None
    commit_id: str | None = None


class SetupTruthIndexRow(BaseModel):
    """One rebuildable committed setup truth index row."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["committed_snapshot"] = "committed_snapshot"
    workspace_id: str
    story_id: str
    mode: str
    stage_id: SetupStageId
    commit_id: str
    ref: str
    row_type: Literal["stage", "entry", "section"]
    entry_id: str | None = None
    section_id: str | None = None
    semantic_path: str
    parent_path: str | None = None
    entry_type: str | None = None
    title: str | None = None
    display_label: str | None = None
    summary: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    section_title: str | None = None
    section_kind: str | None = None
    retrieval_role: str | None = None
    preview_text: str | None = None
    content_hash: str
    token_count: int = 0
    created_at: datetime
    search_text: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SetupTruthIndex(BaseModel):
    """Rebuilt view over accepted setup truth rows."""

    model_config = ConfigDict(extra="forbid")

    rows: list[SetupTruthIndexRow] = Field(default_factory=list)


class SetupTruthIndexSearchInput(BaseModel):
    """Tool/service input for committed setup truth lexical search."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str = ""
    filters: SetupTruthIndexFilters = Field(default_factory=SetupTruthIndexFilters)
    limit: int = 20


class SetupTruthIndexSearchItem(BaseModel):
    """Small candidate returned by committed setup truth search."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    source: Literal["committed_snapshot"] = "committed_snapshot"
    stage_id: SetupStageId
    commit_id: str
    row_type: Literal["stage", "entry", "section"]
    title: str | None = None
    summary: str | None = None
    semantic_path: str
    entry_id: str | None = None
    section_id: str | None = None
    entry_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    preview_text: str | None = None
    score: int = 0


class SetupTruthIndexSearchResult(BaseModel):
    """Search result for committed setup truth candidate refs."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    items: list[SetupTruthIndexSearchItem] = Field(default_factory=list)


class SetupTruthIndexReadInput(BaseModel):
    """Tool/service input for exact committed setup truth reads."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    refs: list[str]
    detail: Literal["summary", "full"] = "summary"
    max_chars: int = 4000
    commit_id: str | None = None


class SetupTruthIndexReadItem(BaseModel):
    """One exact committed setup truth read result."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    found: bool
    source: Literal["committed_snapshot"] | None = None
    stage_id: SetupStageId | None = None
    commit_id: str | None = None
    row_type: Literal["stage", "entry", "section"] | None = None
    title: str | None = None
    summary: str | None = None
    semantic_path: str | None = None
    payload: dict[str, Any] | None = None
    truncated: bool = False


class SetupTruthIndexReadResult(BaseModel):
    """Exact committed setup truth read result."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    items: list[SetupTruthIndexReadItem] = Field(default_factory=list)
    missing_refs: list[str] = Field(default_factory=list)
