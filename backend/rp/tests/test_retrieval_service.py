"""Tests for retrieval-core search service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import RetrievalQuery
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.retrieval_service import RetrievalService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_search_chunks_and_documents_use_real_store(retrieval_session):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id="story-search",
        scope="story",
        collection_kind="archival",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-search",
            story_id="story-search",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://asset-search",
            title="Archive Ledger",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "rule-1",
                        "title": "Archive Rule",
                        "path": "foundation.world.archive_rule",
                        "level": 1,
                        "text": "Archive keepers seal the ledger room before sunrise.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.archive_rule",
                            "tags": ["archive"],
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
        story_id="story-search",
        asset_id="asset-search",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    service = RetrievalService(retrieval_session)
    query = RetrievalQuery(
        query_id="rq-search",
        query_kind="archival",
        story_id="story-search",
        domains=[Domain.WORLD_RULE],
        text_query="ledger room sunrise",
        filters={"knowledge_collections": [collection.collection_id]},
        top_k=3,
    )

    chunk_result = await service.search_chunks(query)
    document_result = await service.search_documents(query)

    assert chunk_result.hits
    assert chunk_result.trace is not None
    assert chunk_result.trace.route.startswith("retrieval.")
    assert chunk_result.hits[0].metadata["asset_id"] == "asset-search"
    assert document_result.hits
    assert document_result.hits[0].metadata["result_kind"] == "document"
