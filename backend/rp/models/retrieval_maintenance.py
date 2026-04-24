"""Structured maintenance snapshots for retrieval-core."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from rp.models.retrieval_records import IndexJob


class RetrievalCollectionMaintenanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection_id: str
    story_id: str
    collection_kind: str
    asset_ids: list[str] = Field(default_factory=list)
    asset_count: int = 0
    active_chunk_count: int = 0
    active_embedding_count: int = 0
    backfill_candidate_asset_ids: list[str] = Field(default_factory=list)
    failed_job_count: int = 0
    retryable_job_ids: list[str] = Field(default_factory=list)


class RetrievalStoryMaintenanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    collection_count: int = 0
    asset_count: int = 0
    active_chunk_count: int = 0
    active_embedding_count: int = 0
    backfill_candidate_asset_ids: list[str] = Field(default_factory=list)
    failed_job_count: int = 0
    retryable_job_ids: list[str] = Field(default_factory=list)
    collections: list[RetrievalCollectionMaintenanceSnapshot] = Field(default_factory=list)
    recent_jobs: list[IndexJob] = Field(default_factory=list)


class RetrievalRetryBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    collection_id: str | None = None
    requested_job_ids: list[str] = Field(default_factory=list)
    deduped_job_ids: list[str] = Field(default_factory=list)
    skipped_job_ids: list[str] = Field(default_factory=list)
    retried_jobs: list[IndexJob] = Field(default_factory=list)
    limit_applied: int | None = None
