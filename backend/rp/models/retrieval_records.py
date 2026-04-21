"""Setup retrieval ingestion and authoritative retrieval record models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.setup_workspace import StoryMode


class SourceAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    story_id: str
    mode: StoryMode
    collection_id: str | None = None
    asset_kind: str
    source_ref: str
    workspace_id: str | None = None
    step_id: str | None = None
    commit_id: str | None = None
    title: str | None = None
    storage_path: str | None = None
    mime_type: str | None = None
    raw_excerpt: str | None = None
    parse_status: str
    ingestion_status: str
    mapped_targets: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ParsedDocumentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str | None = None
    path: str
    level: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parsed_document_id: str
    asset_id: str
    parser_kind: str
    document_structure: list[ParsedDocumentSection] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    story_id: str
    asset_id: str
    parsed_document_id: str
    collection_id: str | None = None
    chunk_index: int
    domain: str
    domain_path: str | None = None
    title: str | None = None
    text: str
    token_count: int | None = None
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance_refs: list[str] = Field(default_factory=list)
    created_at: datetime


class EmbeddingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_id: str
    chunk_id: str
    embedding_model: str
    provider_id: str | None = None
    vector_dim: int
    status: str
    is_active: bool = True
    embedding_vector: list[float] | None = None
    created_at: datetime
    updated_at: datetime


class IndexJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    story_id: str
    asset_id: str | None = None
    collection_id: str | None = None
    job_kind: Literal["ingest", "reindex", "refresh_projection"]
    job_state: Literal[
        "queued",
        "parsing",
        "chunking",
        "embedding",
        "indexing",
        "completed",
        "failed",
        "cancelled",
    ]
    target_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class KnowledgeCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    story_id: str
    scope: str
    collection_kind: Literal["archival", "recall", "rules", "world", "character", "mixed"]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
