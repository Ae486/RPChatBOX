"""Tests for retrieval maintenance service entrypoints and snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import EmbeddingRecordRecord, KnowledgeChunkRecord
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.retrieval_maintenance_service import RetrievalMaintenanceService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_asset(
    *,
    retrieval_session,
    collection_id: str,
    asset_id: str,
    text: str,
):
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id=asset_id,
            story_id="story-maintenance",
            mode=StoryMode.LONGFORM,
            collection_id=collection_id,
            asset_kind="worldbook",
            source_ref=f"memory://{asset_id}",
            title=asset_id,
            parse_status="queued",
            ingestion_status="queued",
            metadata={
                "seed_sections": [
                    {
                        "section_id": f"{asset_id}:s1",
                        "title": asset_id,
                        "path": f"foundation.world.{asset_id}",
                        "level": 1,
                        "text": text,
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": f"foundation.world.{asset_id}",
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id="story-maintenance",
        asset_id=asset_id,
        collection_id=collection_id,
    )
    retrieval_session.flush()


def test_story_snapshot_collects_counts_and_backfill_candidates(retrieval_session):
    collection_service = RetrievalCollectionService(retrieval_session)
    archival = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="archival",
    )
    recall = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="recall",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-archival",
        text="Archival rule content.",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=recall.collection_id,
        asset_id="asset-recall",
        text="Recall summary content.",
    )

    active_embeddings = retrieval_session.exec(
        select(EmbeddingRecordRecord).where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
    ).all()
    for record in active_embeddings:
        if record.chunk_id:
            chunk = retrieval_session.get(KnowledgeChunkRecord, record.chunk_id)
            if chunk is not None and chunk.asset_id == "asset-archival":
                record.embedding_model = "phase_b_minimal_embedding_stub"
                record.vector_dim = 0
                record.embedding_vector = None
                retrieval_session.add(record)
    retrieval_session.commit()

    snapshot = RetrievalMaintenanceService(retrieval_session).get_story_snapshot(
        story_id="story-maintenance"
    )

    assert snapshot.story_id == "story-maintenance"
    assert snapshot.collection_count == 2
    assert snapshot.asset_count == 2
    assert snapshot.active_chunk_count == 2
    assert snapshot.active_embedding_count == 2
    assert snapshot.backfill_candidate_asset_ids == ["asset-archival"]
    assert {item.collection_id for item in snapshot.collections} == {
        archival.collection_id,
        recall.collection_id,
    }
    archival_snapshot = next(
        item for item in snapshot.collections if item.collection_id == archival.collection_id
    )
    assert archival_snapshot.backfill_candidate_asset_ids == ["asset-archival"]
    assert snapshot.failed_job_count == 0
    assert snapshot.retryable_job_ids == []
    assert snapshot.recent_jobs


def test_reindex_collection_only_targets_collection_assets(retrieval_session):
    collection_service = RetrievalCollectionService(retrieval_session)
    archival = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="archival",
    )
    recall = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="recall",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-archival-a",
        text="Archival asset A.",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-archival-b",
        text="Archival asset B.",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=recall.collection_id,
        asset_id="asset-recall-a",
        text="Recall asset A.",
    )
    retrieval_session.commit()

    jobs = RetrievalMaintenanceService(retrieval_session).reindex_collection(
        collection_id=archival.collection_id
    )

    assert len(jobs) == 2
    assert all(job.job_kind == "reindex" for job in jobs)
    archival_chunk_count = len(
        retrieval_session.exec(
            select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.asset_id == "asset-archival-a")
        ).all()
    )
    recall_chunk_count = len(
        retrieval_session.exec(
            select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.asset_id == "asset-recall-a")
        ).all()
    )
    assert archival_chunk_count > 1
    assert recall_chunk_count == 1


def test_backfill_collection_embeddings_only_targets_collection_assets(retrieval_session):
    collection_service = RetrievalCollectionService(retrieval_session)
    archival = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="archival",
    )
    recall = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="recall",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-archival",
        text="Archival asset.",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=recall.collection_id,
        asset_id="asset-recall",
        text="Recall asset.",
    )
    active_embeddings = retrieval_session.exec(
        select(EmbeddingRecordRecord).where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
    ).all()
    for record in active_embeddings:
        chunk = retrieval_session.get(KnowledgeChunkRecord, record.chunk_id)
        if chunk is not None and chunk.asset_id == "asset-archival":
            record.embedding_model = "phase_b_minimal_embedding_stub"
            record.vector_dim = 0
            record.embedding_vector = None
            retrieval_session.add(record)
    retrieval_session.commit()

    jobs = RetrievalMaintenanceService(retrieval_session).backfill_collection_embeddings(
        collection_id=archival.collection_id
    )

    assert len(jobs) == 1
    assert jobs[0].job_kind == "reindex"
    assert jobs[0].asset_id == "asset-archival"


def test_retry_story_failed_jobs_dedupes_latest_failed_targets(retrieval_session):
    from rp.models.retrieval_records import EmbeddingRecord, KnowledgeChunk
    from rp.retrieval.embedder import Embedder

    class InvalidEmbedder(Embedder):
        def __init__(self) -> None:
            super().__init__(fallback_dim=8)

        def embed(self, chunks: list[KnowledgeChunk]) -> list[EmbeddingRecord]:
            records = super().embed(chunks)
            self.last_warnings = ["forced_invalid_embedding"]
            return [
                record.model_copy(update={"vector_dim": 0, "embedding_vector": None})
                for record in records
            ]

    collection_service = RetrievalCollectionService(retrieval_session)
    archival = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="archival",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-retry-target",
        text="Retry target asset.",
    )
    retrieval_session.commit()

    failed_service = RetrievalIngestionService(retrieval_session, embedder=InvalidEmbedder())
    failed_job_a = failed_service.reindex_asset(
        story_id="story-maintenance",
        asset_id="asset-retry-target",
    )
    retrieval_session.commit()
    failed_job_b = failed_service.reindex_asset(
        story_id="story-maintenance",
        asset_id="asset-retry-target",
    )
    retrieval_session.commit()

    batch = RetrievalMaintenanceService(retrieval_session).retry_story_failed_jobs(
        story_id="story-maintenance"
    )
    snapshot = RetrievalMaintenanceService(retrieval_session).get_story_snapshot(
        story_id="story-maintenance"
    )

    assert failed_job_a.job_state == "failed"
    assert failed_job_b.job_state == "failed"
    assert len(batch.requested_job_ids) == 2
    assert len(batch.deduped_job_ids) == 1
    assert len(batch.retried_jobs) == 1
    assert batch.retried_jobs[0].job_state == "completed"
    assert snapshot.failed_job_count == 2
    assert snapshot.retryable_job_ids == [failed_job_b.job_id]


def test_retry_collection_failed_jobs_respects_limit_and_collection_scope(retrieval_session):
    from rp.models.retrieval_records import EmbeddingRecord, KnowledgeChunk
    from rp.retrieval.embedder import Embedder

    class InvalidEmbedder(Embedder):
        def __init__(self) -> None:
            super().__init__(fallback_dim=8)

        def embed(self, chunks: list[KnowledgeChunk]) -> list[EmbeddingRecord]:
            records = super().embed(chunks)
            self.last_warnings = ["forced_invalid_embedding"]
            return [
                record.model_copy(update={"vector_dim": 0, "embedding_vector": None})
                for record in records
            ]

    collection_service = RetrievalCollectionService(retrieval_session)
    archival = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="archival",
    )
    recall = collection_service.ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="recall",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-archival-a",
        text="Archival asset A",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=archival.collection_id,
        asset_id="asset-archival-b",
        text="Archival asset B",
    )
    _seed_asset(
        retrieval_session=retrieval_session,
        collection_id=recall.collection_id,
        asset_id="asset-recall-a",
        text="Recall asset A",
    )
    retrieval_session.commit()

    failed_service = RetrievalIngestionService(retrieval_session, embedder=InvalidEmbedder())
    failed_service.reindex_asset(story_id="story-maintenance", asset_id="asset-archival-a")
    retrieval_session.commit()
    failed_service.reindex_asset(story_id="story-maintenance", asset_id="asset-archival-b")
    retrieval_session.commit()
    failed_service.reindex_asset(story_id="story-maintenance", asset_id="asset-recall-a")
    retrieval_session.commit()

    batch = RetrievalMaintenanceService(retrieval_session).retry_collection_failed_jobs(
        collection_id=archival.collection_id,
        limit=1,
    )

    assert batch.collection_id == archival.collection_id
    assert len(batch.requested_job_ids) == 2
    assert len(batch.retried_jobs) == 1
    assert len(batch.skipped_job_ids) == 1
    assert batch.retried_jobs[0].asset_id in {"asset-archival-a", "asset-archival-b"}
