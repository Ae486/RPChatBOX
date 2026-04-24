"""Tests for retrieval-core ingestion and backfill."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from models.rp_retrieval_store import (
    EmbeddingRecordRecord,
    KnowledgeChunkRecord,
    ParsedDocumentRecord,
    SourceAssetRecord,
)
from rp.models.retrieval_records import EmbeddingRecord, KnowledgeChunk
from rp.models.retrieval_records import SourceAsset
from rp.retrieval.embedder import Embedder
from rp.retrieval.parser import Parser
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
            commit_id="commit-ingest",
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
    assert chunks[0].metadata_json["section_id"] == "s-1"
    assert chunks[0].metadata_json["section_part"] == 0
    assert chunks[0].metadata_json["source_ref"] == "memory://asset-1"
    assert chunks[0].metadata_json["commit_id"] == "commit-ingest"
    assert embeddings
    assert all(embedding.vector_dim > 0 for embedding in embeddings)
    assert all(embedding.embedding_vector for embedding in embeddings)


def test_ingest_asset_persists_secondary_chunk_views_for_large_sections(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-ingest-multipass",
        scope="story",
        collection_kind="archival",
    )
    long_text = (
        ("alpha archive rule " * 15)
        + "\n"
        + ("beta archive rule " * 15)
        + "\n"
        + ("gamma archive rule " * 15)
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-multipass",
            story_id="story-ingest-multipass",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-multipass",
            title="Asset Multipass",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "s-multipass",
                        "title": "Rule",
                        "path": "foundation.world.multipass_rule",
                        "level": 1,
                        "text": long_text,
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.multipass_rule",
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
        story_id="story-ingest-multipass",
        asset_id="asset-multipass",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.asset_id == "asset-multipass")
    ).all()
    embeddings = retrieval_session.exec(
        select(EmbeddingRecordRecord)
        .join(KnowledgeChunkRecord, KnowledgeChunkRecord.chunk_id == EmbeddingRecordRecord.chunk_id)
        .where(KnowledgeChunkRecord.asset_id == "asset-multipass")
    ).all()

    assert job.job_state == "completed"
    assert any(chunk.metadata_json["chunk_view"] == "primary" for chunk in chunks)
    assert any(chunk.metadata_json["chunk_view"] == "secondary" for chunk in chunks)
    assert all(chunk.metadata_json["chunk_family_id"] == "s-multipass:0" for chunk in chunks)
    assert all(chunk.metadata_json["char_start"] < chunk.metadata_json["char_end"] for chunk in chunks)
    assert len(embeddings) == len(chunks)


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


def test_ingestion_warnings_use_stable_taxonomy(retrieval_session):
    class StubParser(Parser):
        def parse(self, asset: SourceAsset):
            document = super().parse(asset)
            return document.model_copy(
                update={
                    "parser_kind": "fallback",
                    "parse_warnings": ["raw_file_read_failed:missing_file"],
                }
            )

    class StubEmbedder(Embedder):
        def __init__(self) -> None:
            super().__init__(fallback_dim=8)

        def embed(self, chunks: list[KnowledgeChunk]) -> list[EmbeddingRecord]:
            embeddings = super().embed(chunks)
            self.last_warnings = ["embedding_provider_unconfigured:fallback_local"]
            return embeddings

    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-warning",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-warning",
            story_id="story-warning",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-warning",
            title="Warning Asset",
            parse_status="queued",
            ingestion_status="queued",
            metadata={
                "seed_sections": [
                    {
                        "section_id": "warn-1",
                        "title": "Rule",
                        "path": "foundation.world.warning_rule",
                        "level": 1,
                        "text": "Warnings should be normalized.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.warning_rule",
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()

    job = RetrievalIngestionService(
        retrieval_session,
        parser=StubParser(),
        embedder=StubEmbedder(),
    ).ingest_asset(
        story_id="story-warning",
        asset_id="asset-warning",
        collection_id=collection.collection_id,
    )

    assert job.job_state == "completed"
    assert "ingestion:parsing:parser_kind:fallback" in job.warnings
    assert "ingestion:parsing:raw_file_read_failed:missing_file" in job.warnings
    assert "ingestion:embedding:embedding_provider_unconfigured:fallback_local" in job.warnings


def test_list_backfill_candidates_and_reindex_asset(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-maintenance",
        scope="story",
        collection_kind="archival",
    )
    document_service = RetrievalDocumentService(retrieval_session)
    document_service.upsert_source_asset(
        SourceAsset(
            asset_id="asset-maintenance",
            story_id="story-maintenance",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-maintenance",
            title="Maintenance Asset",
            parse_status="queued",
            ingestion_status="queued",
            metadata={
                "seed_sections": [
                    {
                        "section_id": "m-1",
                        "title": "Rule",
                        "path": "foundation.world.maintenance_rule",
                        "level": 1,
                        "text": "Maintenance backfill should discover me.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.maintenance_rule",
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
    service.ingest_asset(
        story_id="story-maintenance",
        asset_id="asset-maintenance",
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

    candidate_ids = service.list_backfill_candidate_asset_ids(story_id="story-maintenance")
    job = service.reindex_asset(story_id="story-maintenance", asset_id="asset-maintenance")

    assert candidate_ids == ["asset-maintenance"]
    assert job.job_kind == "reindex"
    assert job.job_state == "completed"


def test_reindex_failure_preserves_previous_active_records_and_marks_asset_failed(retrieval_session):
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

    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-failure",
        scope="story",
        collection_kind="archival",
    )
    document_service = RetrievalDocumentService(retrieval_session)
    document_service.upsert_source_asset(
        SourceAsset(
            asset_id="asset-failure",
            story_id="story-failure",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-failure",
            title="Failure Asset",
            parse_status="queued",
            ingestion_status="queued",
            metadata={
                "seed_sections": [
                    {
                        "section_id": "f-1",
                        "title": "Rule",
                        "path": "foundation.world.failure_rule",
                        "level": 1,
                        "text": "Previous active retrieval data must survive failed reindex.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.failure_rule",
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
        story_id="story-failure",
        asset_id="asset-failure",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    active_chunks_before = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
    ).all()
    active_embeddings_before = retrieval_session.exec(
        select(EmbeddingRecordRecord).where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
    ).all()

    failed_job = RetrievalIngestionService(
        retrieval_session,
        embedder=InvalidEmbedder(),
    ).reindex_asset(
        story_id="story-failure",
        asset_id="asset-failure",
    )
    retrieval_session.commit()

    active_chunks_after = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(KnowledgeChunkRecord.is_active == True)  # noqa: E712
    ).all()
    active_embeddings_after = retrieval_session.exec(
        select(EmbeddingRecordRecord).where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
    ).all()
    asset_record = retrieval_session.get(SourceAssetRecord, "asset-failure")

    assert first_job.job_state == "completed"
    assert failed_job.job_state == "failed"
    assert "Invalid embedding output for asset: asset-failure" == failed_job.error_message
    assert "ingestion:embedding:forced_invalid_embedding" in failed_job.warnings
    assert "ingestion:embedding:invalid_embedding_output:asset-failure" in failed_job.warnings
    assert len(active_chunks_after) == len(active_chunks_before)
    assert len(active_embeddings_after) == len(active_embeddings_before)
    assert asset_record is not None
    assert asset_record.parse_status == "parsed"
    assert asset_record.ingestion_status == "failed"


def test_retry_failed_job_resubmits_failed_reindex(retrieval_session):
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

    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-retry",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-retry",
            story_id="story-retry",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-retry",
            title="Retry Asset",
            parse_status="queued",
            ingestion_status="queued",
            metadata={
                "seed_sections": [
                    {
                        "section_id": "r-1",
                        "title": "Rule",
                        "path": "foundation.world.retry_rule",
                        "level": 1,
                        "text": "Retry should resubmit failed reindex jobs.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.retry_rule",
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
    service.ingest_asset(
        story_id="story-retry",
        asset_id="asset-retry",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    failed_job = RetrievalIngestionService(
        retrieval_session,
        embedder=InvalidEmbedder(),
    ).reindex_asset(
        story_id="story-retry",
        asset_id="asset-retry",
    )
    retrieval_session.commit()

    retried_job = RetrievalIngestionService(retrieval_session).retry_failed_job(
        job_id=failed_job.job_id
    )
    retrieval_session.commit()

    assert failed_job.job_state == "failed"
    assert retried_job.job_kind == "reindex"
    assert retried_job.job_state == "completed"
    assert retried_job.job_id != failed_job.job_id
