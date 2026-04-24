"""Contract tests for retrieval maintenance API endpoints."""

from __future__ import annotations


def _provider_payload(provider_id: str = "provider-local"):
    return {
        "id": provider_id,
        "name": "Local Provider",
        "type": "local",
        "api_key": "unused",
        "api_url": "local://cross-encoder",
        "custom_headers": {},
        "is_enabled": True,
    }


def _seed_asset_payload(asset_id: str, *, text: str, collection_id: str):
    return {
        "asset_id": asset_id,
        "story_id": "story-api-retrieval",
        "mode": "longform",
        "collection_id": collection_id,
        "asset_kind": "worldbook",
        "source_ref": f"memory://{asset_id}",
        "title": asset_id,
        "parse_status": "queued",
        "ingestion_status": "queued",
        "mapped_targets": ["foundation"],
        "metadata": {
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
    }


def _seed_story_assets(client):
    from sqlmodel import Session

    from models.rp_retrieval_store import SourceAssetRecord
    from rp.services.retrieval_collection_service import RetrievalCollectionService
    from rp.services.retrieval_ingestion_service import RetrievalIngestionService
    from services.database import get_engine

    with Session(get_engine()) as session:
        collection = RetrievalCollectionService(session).ensure_story_collection(
            story_id="story-api-retrieval",
            scope="story",
            collection_kind="archival",
        )
        for payload in (
            _seed_asset_payload(
                "asset-api-a",
                text="Archival asset A text.",
                collection_id=collection.collection_id,
            ),
            _seed_asset_payload(
                "asset-api-b",
                text="Archival asset B text.",
                collection_id=collection.collection_id,
            ),
        ):
            session.add(SourceAssetRecord(**payload))
        session.flush()
        ingestion = RetrievalIngestionService(session)
        ingestion.ingest_asset(
            story_id="story-api-retrieval",
            asset_id="asset-api-a",
            collection_id=collection.collection_id,
        )
        ingestion.ingest_asset(
            story_id="story-api-retrieval",
            asset_id="asset-api-b",
            collection_id=collection.collection_id,
        )
        session.commit()
        return collection.collection_id


def test_get_story_maintenance_snapshot(client):
    collection_id = _seed_story_assets(client)

    response = client.get("/api/rp/retrieval/stories/story-api-retrieval/maintenance")

    assert response.status_code == 200
    data = response.json()
    assert data["story_id"] == "story-api-retrieval"
    assert data["collection_count"] == 1
    assert data["asset_count"] == 2
    assert data["collections"][0]["collection_id"] == collection_id


def test_get_collection_maintenance_returns_404_for_unknown_collection(client):
    response = client.get("/api/rp/retrieval/collections/missing-collection/maintenance")

    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "retrieval_collection_not_found"


def test_retry_failed_story_jobs_and_single_job_retry(client):
    from sqlmodel import Session

    from models.rp_retrieval_store import EmbeddingRecordRecord, KnowledgeChunkRecord
    from rp.models.retrieval_records import EmbeddingRecord, KnowledgeChunk
    from rp.retrieval.embedder import Embedder
    from rp.services.retrieval_ingestion_service import RetrievalIngestionService
    from services.database import get_engine

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

    collection_id = _seed_story_assets(client)
    with Session(get_engine()) as session:
        failed_service = RetrievalIngestionService(session, embedder=InvalidEmbedder())
        failed_job = failed_service.reindex_asset(
            story_id="story-api-retrieval",
            asset_id="asset-api-a",
        )
        session.commit()

    retry_response = client.post(
        "/api/rp/retrieval/stories/story-api-retrieval/retry-failed",
        json={"limit": 1},
    )

    assert retry_response.status_code == 200
    retry_payload = retry_response.json()
    assert retry_payload["story_id"] == "story-api-retrieval"
    assert retry_payload["limit_applied"] == 1
    assert len(retry_payload["retried_jobs"]) == 1
    assert retry_payload["retried_jobs"][0]["job_state"] == "completed"

    single_retry_response = client.post(f"/api/rp/retrieval/jobs/{failed_job.job_id}/retry")
    assert single_retry_response.status_code == 200
    assert single_retry_response.json()["job_kind"] == "reindex"
    assert single_retry_response.json()["job_state"] == "completed"

    collection_retry_response = client.post(
        f"/api/rp/retrieval/collections/{collection_id}/retry-failed",
        json={"limit": 2},
    )
    assert collection_retry_response.status_code == 200
    assert collection_retry_response.json()["collection_id"] == collection_id


def test_backfill_collection_endpoint_returns_job_list(client):
    from sqlmodel import Session, select

    from models.rp_retrieval_store import EmbeddingRecordRecord, KnowledgeChunkRecord
    from services.database import get_engine

    collection_id = _seed_story_assets(client)
    with Session(get_engine()) as session:
        active_embeddings = session.exec(
            select(EmbeddingRecordRecord).where(EmbeddingRecordRecord.is_active == True)  # noqa: E712
        ).all()
        for record in active_embeddings:
            chunk = session.get(KnowledgeChunkRecord, record.chunk_id)
            if chunk is not None and chunk.asset_id == "asset-api-a":
                record.embedding_model = "phase_b_minimal_embedding_stub"
                record.vector_dim = 0
                record.embedding_vector = None
                session.add(record)
        session.commit()

    response = client.post(f"/api/rp/retrieval/collections/{collection_id}/backfill")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["asset_id"] == "asset-api-a"
