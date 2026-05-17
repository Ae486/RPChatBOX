"""Contracts for SetupAgent session-scoped memory search/open paths."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SetupSessionMemorySourceKind = Literal[
    "editable_draft",
    "accepted_truth",
]
SetupSessionMemoryRefKind = Literal[
    "setup_fact_entry",
    "setup_fact_section",
]


class SetupSessionMemoryFreshness(BaseModel):
    """Small freshness marker for rebuildable session-memory refs."""

    model_config = ConfigDict(extra="forbid")

    workspace_version: int | None = None
    fingerprint: str | None = None
    status: Literal["current", "unknown"] = "current"


class SetupSessionMemoryManifestItem(BaseModel):
    """One searchable ref derived from live setup-session sources."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    title: str | None = None
    summary: str | None = None
    source_kind: SetupSessionMemorySourceKind
    ref_kind: SetupSessionMemoryRefKind
    stage: str | None = None
    block_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    search_text: str = ""
    freshness: SetupSessionMemoryFreshness = Field(
        default_factory=SetupSessionMemoryFreshness
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class SetupSessionMemoryManifest(BaseModel):
    """Rebuildable manifest over one setup workspace/session."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    workspace_version: int | None = None
    items: list[SetupSessionMemoryManifestItem] = Field(default_factory=list)


class SetupSessionMemorySearchFilters(BaseModel):
    """Optional deterministic filters for setup-session memory search."""

    model_config = ConfigDict(extra="forbid")

    source_kinds: list[SetupSessionMemorySourceKind] = Field(default_factory=list)
    ref_kinds: list[SetupSessionMemoryRefKind] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    block_types: list[str] = Field(default_factory=list)


class SetupSessionMemorySearchInput(BaseModel):
    """Tool/service input for small ref discovery."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str = ""
    filters: SetupSessionMemorySearchFilters = Field(
        default_factory=SetupSessionMemorySearchFilters
    )
    limit: int = Field(default=10, ge=1, le=50)


class SetupSessionMemoryHit(BaseModel):
    """Small search hit; never carries full source payload."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    title: str | None = None
    path: str | None = None
    scope: Literal["entry", "section"] = "entry"
    navigation_summary: str | None = None
    message: str = "这是搜索候选，不是事实正文。需要使用该设定时，请 open 此 ref。"


class SetupSessionMemorySearchResult(BaseModel):
    """Deterministic setup-session memory search result."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    items: list[SetupSessionMemoryHit] = Field(default_factory=list)


class SetupSessionMemoryReadInput(BaseModel):
    """Tool/service input for exact bounded readback by refs."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    refs: list[str]
    detail: Literal["summary", "full"] = "summary"
    max_chars: int = Field(default=4000, ge=1, le=20000)


class SetupSessionMemoryReadItem(BaseModel):
    """One exact readback result from the current source."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    found: bool
    source_kind: SetupSessionMemorySourceKind | None = None
    ref_kind: SetupSessionMemoryRefKind | None = None
    title: str | None = None
    summary: str | None = None
    stage: str | None = None
    block_type: str | None = None
    payload: dict[str, Any] | None = None
    truncated: bool = False


class SetupSessionMemoryReadResult(BaseModel):
    """Exact setup-session memory read result."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    items: list[SetupSessionMemoryReadItem] = Field(default_factory=list)
    missing_refs: list[str] = Field(default_factory=list)


class SetupSessionMemoryOpenInput(BaseModel):
    """Tool/service input for opening exactly one setup memory ref."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    ref: str
    max_chars: int = Field(default=4000, ge=1, le=20000)


class SetupSessionMemorySectionIndexItem(BaseModel):
    """Clean level-4 section index item returned by opening a level-3 ref."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    path: str | None = None
    title: str | None = None
    navigation_summary: str | None = None


class SetupSessionMemoryContentBlock(BaseModel):
    """Clean structured content returned by opening a level-4 section ref."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text", "list", "key_value", "truncated", "unknown"]
    title: str | None = None
    text: str | None = None
    items: list[Any] | None = None
    values: dict[str, Any] | None = None
    preview: str | None = None


class SetupSessionMemoryOpenResult(BaseModel):
    """Agent-facing open result for one ref."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    result_type: Literal["index", "content", "error"]
    opened_ref: str
    opened_path: str | None = None
    message: str
    sections: list[SetupSessionMemorySectionIndexItem] | None = None
    content: SetupSessionMemoryContentBlock | None = None
    truncated: bool = False
