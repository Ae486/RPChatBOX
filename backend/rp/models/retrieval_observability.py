"""Structured observability views for retrieval-core query execution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetrievalWarningBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    count: int = 0
    warnings: list[str] = Field(default_factory=list)


class RetrievalObservabilityHitView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_id: str
    rank: int
    score: float
    domain: str
    domain_path: str | None = None
    asset_id: str | None = None
    collection_id: str | None = None
    title: str | None = None
    page_no: int | None = None
    page_label: str | None = None
    page_ref: str | None = None
    image_caption: str | None = None
    contextual_text_version: str | None = None
    excerpt_preview: str


class RetrievalObservabilityMaintenanceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    collection_count: int = 0
    asset_count: int = 0
    active_chunk_count: int = 0
    active_embedding_count: int = 0
    backfill_candidate_asset_ids: list[str] = Field(default_factory=list)
    failed_job_count: int = 0
    retryable_job_ids: list[str] = Field(default_factory=list)
    recent_job_count: int = 0


class RetrievalObservabilityView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    story_id: str
    query_kind: str
    text_query: str | None = None
    top_k: int = 0
    route: str | None = None
    result_kind: str | None = None
    retriever_routes: list[str] = Field(default_factory=list)
    pipeline_stages: list[str] = Field(default_factory=list)
    reranker_name: str | None = None
    candidate_count: int = 0
    returned_count: int = 0
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    warning_buckets: list[RetrievalWarningBucket] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    top_hits: list[RetrievalObservabilityHitView] = Field(default_factory=list)
    maintenance: RetrievalObservabilityMaintenanceView | None = None
