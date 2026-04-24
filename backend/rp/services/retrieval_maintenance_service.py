"""Story- and collection-level maintenance service for retrieval-core."""

from __future__ import annotations

from datetime import timezone

from sqlmodel import select

from models.rp_retrieval_store import EmbeddingRecordRecord, KnowledgeChunkRecord
from rp.models.retrieval_maintenance import (
    RetrievalCollectionMaintenanceSnapshot,
    RetrievalRetryBatchResult,
    RetrievalStoryMaintenanceSnapshot,
)
from rp.models.retrieval_records import IndexJob
from .retrieval_collection_service import RetrievalCollectionService
from .retrieval_document_service import RetrievalDocumentService
from .retrieval_index_job_service import RetrievalIndexJobService
from .retrieval_ingestion_service import RetrievalIngestionService


class RetrievalMaintenanceService:
    """Provide structured maintenance views and entrypoints over retrieval-core."""

    _DEFAULT_RETRY_BATCH_LIMIT = 20

    def __init__(
        self,
        session,
        *,
        document_service: RetrievalDocumentService | None = None,
        collection_service: RetrievalCollectionService | None = None,
        index_job_service: RetrievalIndexJobService | None = None,
        ingestion_service: RetrievalIngestionService | None = None,
    ) -> None:
        self._session = session
        self._document_service = document_service or RetrievalDocumentService(session)
        self._collection_service = collection_service or RetrievalCollectionService(session)
        self._index_job_service = index_job_service or RetrievalIndexJobService(session)
        self._ingestion_service = ingestion_service or RetrievalIngestionService(session)

    def get_story_snapshot(self, *, story_id: str) -> RetrievalStoryMaintenanceSnapshot:
        collections = self._collection_service.list_story_collections(story_id)
        assets = self._document_service.list_story_assets(story_id)
        backfill_candidate_ids = self._ingestion_service.list_backfill_candidate_asset_ids(
            story_id=story_id
        )
        failed_jobs = self._list_failed_jobs(story_id=story_id)
        retryable_jobs, _, _, _ = self._plan_retry_batch(failed_jobs, limit=None)
        collection_snapshots = [
            self._build_collection_snapshot(
                collection_id=collection.collection_id,
                story_id=story_id,
                assets=assets,
                backfill_candidate_ids=backfill_candidate_ids,
                failed_jobs=failed_jobs,
            )
            for collection in collections
        ]

        return RetrievalStoryMaintenanceSnapshot(
            story_id=story_id,
            collection_count=len(collections),
            asset_count=len(assets),
            active_chunk_count=self._count_active_story_chunks(story_id=story_id),
            active_embedding_count=self._count_active_story_embeddings(story_id=story_id),
            backfill_candidate_asset_ids=backfill_candidate_ids,
            failed_job_count=len(failed_jobs),
            retryable_job_ids=[job.job_id for job in retryable_jobs],
            collections=collection_snapshots,
            recent_jobs=sorted(
                self._index_job_service.list_story_jobs(story_id),
                key=self._job_updated_at_key,
                reverse=True,
            )[:10],
        )

    def get_collection_snapshot(
        self,
        *,
        collection_id: str,
    ) -> RetrievalCollectionMaintenanceSnapshot | None:
        collection = self._collection_service.get_collection(collection_id)
        if collection is None:
            return None

        assets = self._document_service.list_story_assets(collection.story_id)
        backfill_candidate_ids = self._ingestion_service.list_backfill_candidate_asset_ids(
            story_id=collection.story_id
        )
        failed_jobs = self._list_failed_jobs(story_id=collection.story_id)
        return self._build_collection_snapshot(
            collection_id=collection_id,
            story_id=collection.story_id,
            assets=assets,
            backfill_candidate_ids=backfill_candidate_ids,
            failed_jobs=failed_jobs,
        )

    def reindex_story(
        self,
        *,
        story_id: str,
        collection_id: str | None = None,
        collection_kind: str | None = None,
    ) -> list[IndexJob]:
        assets = self._document_service.list_story_assets(story_id)
        target_assets = [
            asset
            for asset in assets
            if (collection_id is None or asset.collection_id == collection_id)
            and (
                collection_kind is None
                or (
                    asset.collection_id is not None
                    and asset.collection_id == f"{story_id}:{collection_kind}"
                )
            )
        ]
        return [
            self._ingestion_service.reindex_asset(story_id=story_id, asset_id=asset.asset_id)
            for asset in target_assets
        ]

    def reindex_collection(self, *, collection_id: str) -> list[IndexJob]:
        snapshot = self.get_collection_snapshot(collection_id=collection_id)
        if snapshot is None:
            return []
        return [
            self._ingestion_service.reindex_asset(
                story_id=snapshot.story_id,
                asset_id=asset_id,
            )
            for asset_id in snapshot.asset_ids
        ]

    def backfill_story_embeddings(self, *, story_id: str) -> list[IndexJob]:
        return self._ingestion_service.backfill_stub_embeddings(story_id=story_id)

    def backfill_collection_embeddings(self, *, collection_id: str) -> list[IndexJob]:
        snapshot = self.get_collection_snapshot(collection_id=collection_id)
        if snapshot is None:
            return []
        return [
            self._ingestion_service.reindex_asset(
                story_id=snapshot.story_id,
                asset_id=asset_id,
            )
            for asset_id in snapshot.backfill_candidate_asset_ids
        ]

    def retry_story_failed_jobs(
        self,
        *,
        story_id: str,
        collection_id: str | None = None,
        collection_kind: str | None = None,
        limit: int | None = None,
    ) -> RetrievalRetryBatchResult:
        resolved_limit = self._DEFAULT_RETRY_BATCH_LIMIT if limit is None else max(limit, 0)
        assets = self._document_service.list_story_assets(story_id)
        target_asset_ids = self._target_asset_ids(
            story_id=story_id,
            assets=assets,
            collection_id=collection_id,
            collection_kind=collection_kind,
        )
        failed_jobs = self._list_failed_jobs(story_id=story_id)
        selected_jobs, requested_job_ids, deduped_job_ids, skipped_job_ids = self._plan_retry_batch(
            failed_jobs,
            asset_ids=target_asset_ids,
            limit=resolved_limit,
        )
        retried_jobs = [
            self._ingestion_service.retry_failed_job(job_id=job.job_id)
            for job in selected_jobs
        ]
        return RetrievalRetryBatchResult(
            story_id=story_id,
            collection_id=collection_id,
            requested_job_ids=requested_job_ids,
            deduped_job_ids=deduped_job_ids,
            skipped_job_ids=skipped_job_ids,
            retried_jobs=retried_jobs,
            limit_applied=resolved_limit,
        )

    def retry_collection_failed_jobs(
        self,
        *,
        collection_id: str,
        limit: int | None = None,
    ) -> RetrievalRetryBatchResult:
        snapshot = self.get_collection_snapshot(collection_id=collection_id)
        if snapshot is None:
            return RetrievalRetryBatchResult(
                story_id="",
                collection_id=collection_id,
                limit_applied=self._DEFAULT_RETRY_BATCH_LIMIT if limit is None else max(limit, 0),
            )
        return self.retry_story_failed_jobs(
            story_id=snapshot.story_id,
            collection_id=collection_id,
            limit=limit,
        )

    def _build_collection_snapshot(
        self,
        *,
        collection_id: str,
        story_id: str,
        assets,
        backfill_candidate_ids: list[str],
        failed_jobs: list[IndexJob],
    ) -> RetrievalCollectionMaintenanceSnapshot:
        collection = self._collection_service.get_collection(collection_id)
        asset_ids = sorted(
            asset.asset_id for asset in assets if asset.collection_id == collection_id
        )
        retryable_jobs, _, _, _ = self._plan_retry_batch(
            failed_jobs,
            asset_ids=set(asset_ids),
            limit=None,
        )
        return RetrievalCollectionMaintenanceSnapshot(
            collection_id=collection_id,
            story_id=story_id,
            collection_kind=collection.collection_kind if collection is not None else "mixed",
            asset_ids=asset_ids,
            asset_count=len(asset_ids),
            active_chunk_count=self._count_active_collection_chunks(collection_id=collection_id),
            active_embedding_count=self._count_active_collection_embeddings(
                collection_id=collection_id
            ),
            backfill_candidate_asset_ids=[
                asset_id for asset_id in backfill_candidate_ids if asset_id in set(asset_ids)
            ],
            failed_job_count=len(
                [job for job in failed_jobs if self._job_matches_assets(job, asset_ids=set(asset_ids))]
            ),
            retryable_job_ids=[job.job_id for job in retryable_jobs],
        )

    def _list_failed_jobs(self, *, story_id: str) -> list[IndexJob]:
        return sorted(
            self._index_job_service.list_story_jobs(story_id, job_state="failed"),
            key=self._job_updated_at_key,
            reverse=True,
        )

    @staticmethod
    def _job_updated_at_key(job: IndexJob) -> float:
        value = job.updated_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()

    def _plan_retry_batch(
        self,
        jobs: list[IndexJob],
        *,
        asset_ids: set[str] | None = None,
        limit: int | None,
    ) -> tuple[list[IndexJob], list[str], list[str], list[str]]:
        requested_job_ids: list[str] = []
        deduped_job_ids: list[str] = []
        skipped_job_ids: list[str] = []
        selected_jobs: list[IndexJob] = []
        seen_keys: set[tuple[str, ...]] = set()

        for job in jobs:
            if asset_ids is not None and not self._job_matches_assets(job, asset_ids=asset_ids):
                continue
            requested_job_ids.append(job.job_id)
            if not self._is_retryable_job(job):
                skipped_job_ids.append(job.job_id)
                continue
            retry_key = self._job_retry_key(job)
            if retry_key in seen_keys:
                deduped_job_ids.append(job.job_id)
                continue
            if limit is not None and len(selected_jobs) >= limit:
                skipped_job_ids.append(job.job_id)
                continue
            seen_keys.add(retry_key)
            selected_jobs.append(job)

        return selected_jobs, requested_job_ids, deduped_job_ids, skipped_job_ids

    @staticmethod
    def _job_retry_key(job: IndexJob) -> tuple[str, ...]:
        refs = list(dict.fromkeys(job.target_refs or []))
        if refs:
            return tuple(sorted(refs))
        if job.asset_id:
            return (f"asset:{job.asset_id}",)
        return (job.job_id,)

    @staticmethod
    def _is_retryable_job(job: IndexJob) -> bool:
        return job.job_state == "failed" and job.job_kind in {"ingest", "reindex"} and bool(
            job.asset_id or job.target_refs
        )

    @staticmethod
    def _job_matches_assets(job: IndexJob, *, asset_ids: set[str]) -> bool:
        if job.asset_id:
            return job.asset_id in asset_ids
        job_asset_ids = {
            item.split("asset:", 1)[1]
            for item in job.target_refs
            if item.startswith("asset:")
        }
        return bool(job_asset_ids.intersection(asset_ids))

    @staticmethod
    def _target_asset_ids(
        *,
        story_id: str,
        assets,
        collection_id: str | None,
        collection_kind: str | None,
    ) -> set[str] | None:
        if collection_id is None and collection_kind is None:
            return None
        target_assets = {
            asset.asset_id
            for asset in assets
            if (collection_id is None or asset.collection_id == collection_id)
            and (
                collection_kind is None
                or (
                    asset.collection_id is not None
                    and asset.collection_id == f"{story_id}:{collection_kind}"
                )
            )
        }
        return target_assets

    def _count_active_story_chunks(self, *, story_id: str) -> int:
        stmt = (
            select(KnowledgeChunkRecord.chunk_id)
            .where(KnowledgeChunkRecord.story_id == story_id)
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        )
        return len(self._session.exec(stmt).all())

    def _count_active_collection_chunks(self, *, collection_id: str) -> int:
        stmt = (
            select(KnowledgeChunkRecord.chunk_id)
            .where(KnowledgeChunkRecord.collection_id == collection_id)
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        )
        return len(self._session.exec(stmt).all())

    def _count_active_story_embeddings(self, *, story_id: str) -> int:
        stmt = (
            select(EmbeddingRecordRecord.embedding_id)
            .join(KnowledgeChunkRecord, KnowledgeChunkRecord.chunk_id == EmbeddingRecordRecord.chunk_id)
            .where(KnowledgeChunkRecord.story_id == story_id)
            .where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        )
        return len(self._session.exec(stmt).all())

    def _count_active_collection_embeddings(self, *, collection_id: str) -> int:
        stmt = (
            select(EmbeddingRecordRecord.embedding_id)
            .join(KnowledgeChunkRecord, KnowledgeChunkRecord.chunk_id == EmbeddingRecordRecord.chunk_id)
            .where(KnowledgeChunkRecord.collection_id == collection_id)
            .where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
            .where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
        )
        return len(self._session.exec(stmt).all())
