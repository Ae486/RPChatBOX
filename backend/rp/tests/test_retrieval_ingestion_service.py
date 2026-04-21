"""Tests for retrieval-core ingestion and backfill."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    KnowledgeChunkRecord,
    ParsedDocumentRecord,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_ingest_asset_builds_real_chunks_and_embeddings(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-ingest",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-1",
            story_id="story-ingest",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-1",
            title="Asset 1",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "s-1",
                        "title": "Rule",
                        "path": "foundation.world.rule",
                        "level": 1,
                        "text": "The city seals all gates at dusk.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.rule",
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()

    job = RetrievalIngestionService(retrieval_session).ingest_asset(
        story_id="story-ingest",
        asset_id="asset-1",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    parsed_documents = retrieval_session.exec(select(ParsedDocumentRecord)).all()
    chunks = retrieval_session.exec(select(KnowledgeChunkRecord)).all()
    embeddings = retrieval_session.exec(select(EmbeddingRecordRecord)).all()

    assert job.job_state == "completed"
    assert parsed_documents
    assert chunks
    assert all(chunk.is_active for chunk in chunks)
    assert embeddings
    assert all(embedding.vector_dim > 0 for embedding in embeddings)
    assert all(embedding.embedding_vector for embedding in embeddings)


def test_backfill_stub_embeddings_reindexes_asset(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-backfill",
        scope="story",
        collection_kind="archival",
    )
    document_service = RetrievalDocumentService(retrieval_session)
    document_service.upsert_source_asset(
        SourceAsset(
            asset_id="asset-backfill",
            story_id="story-backfill",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-backfill",
            title="Backfill Asset",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "s-1",
                        "title": "Rule",
                        "path": "foundation.world.rule",
                        "level": 1,
                        "text": "Lantern keepers mark every sealed door.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.rule",
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()

    service = RetrievalIngestionService(retrieval_session)
    first_job = service.ingest_asset(
        story_id="story-backfill",
        asset_id="asset-backfill",
        collection_id=collection.collection_id,
    )
    retrieval_session.flush()

    active_embeddings = retrieval_session.exec(
        select(EmbeddingRecordRecord).where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
    ).all()
    for record in active_embeddings:
        record.embedding_model = "phase_b_minimal_embedding_stub"
        record.vector_dim = 0
        record.embedding_vector = None
        retrieval_session.add(record)
    retrieval_session.commit()

    jobs = service.backfill_stub_embeddings(story_id="story-backfill")
    retrieval_session.commit()

    refreshed_embeddings = retrieval_session.exec(select(EmbeddingRecordRecord)).all()
    new_active = [item for item in refreshed_embeddings if item.is_active]
    old_inactive = [item for item in refreshed_embeddings if not item.is_active]

    assert first_job.job_state == "completed"
    assert jobs
    assert all(job.job_state == "completed" for job in jobs)
    assert old_inactive
    assert new_active
    assert all(item.vector_dim > 0 for item in new_active)
