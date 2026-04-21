"""Tests for the DB-backed retrieval broker."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
)
from rp.models.retrieval_records import SourceAsset
from rp.models.setup_workspace import StoryMode
from rp.services.memory_os_service import MemoryOsService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_get_state_returns_stable_items():
    broker = RetrievalBroker()
    result = await broker.get_state(
        MemoryGetStateInput(
            refs=[
                ObjectRef(
                    object_id="scene.current",
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=Domain.SCENE,
                    domain_path="scene.current",
                )
            ]
        )
    )

    assert result.items[0].object_ref.object_id == "scene.current"
    assert result.items[0].data["domain"] == "scene"


@pytest.mark.asyncio
async def test_memory_os_service_is_a_pure_facade(monkeypatch):
    captured = {}

    async def fake_get_summary(input_model):
        captured["input"] = input_model
        return "ok"

    broker = RetrievalBroker()
    monkeypatch.setattr(broker, "get_summary", fake_get_summary)
    service = MemoryOsService(retrieval_broker=broker)
    input_model = MemoryGetSummaryInput(summary_ids=["scene.current"])

    result = await service.get_summary(input_model)

    assert result == "ok"
    assert captured["input"] is input_model


@pytest.mark.asyncio
async def test_search_and_provenance_surfaces_are_stable(retrieval_session):
    collection_service = RetrievalCollectionService(retrieval_session)
    document_service = RetrievalDocumentService(retrieval_session)
    ingestion_service = RetrievalIngestionService(retrieval_session)
    collection = collection_service.ensure_story_collection(
        story_id="story-1",
        scope="story",
        collection_kind="archival",
    )
    document_service.upsert_source_asset(
        SourceAsset(
            asset_id="asset-worldbook",
            story_id="story-1",
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="worldbook",
            source_ref="memory://worldbook",
            title="Worldbook",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["foundation"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "sec-1",
                        "title": "River District",
                        "path": "foundation.world.river_district",
                        "level": 1,
                        "text": "River District forbids open spell rituals after dusk.",
                        "metadata": {
                            "domain": "world_rule",
                            "domain_path": "foundation.world.river_district",
                            "tags": ["district"],
                        },
                    }
                ]
            },
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )
    retrieval_session.flush()
    ingestion_service.ingest_asset(
        story_id="story-1",
        asset_id="asset-worldbook",
        collection_id=collection.collection_id,
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id="story-1")

    recall = await broker.search_recall(
        MemorySearchRecallInput(
            query="market square",
            domains=[Domain.SCENE],
            scope="story",
            top_k=1,
        )
    )
    archival = await broker.search_archival(
        MemorySearchArchivalInput(
            query="spell rituals after dusk",
            domains=[Domain.WORLD_RULE],
            knowledge_collections=[collection.collection_id],
            top_k=1,
        )
    )
    provenance = await broker.read_provenance(
        MemoryReadProvenanceInput(
            target_ref=ObjectRef(
                object_id="scene.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=Domain.SCENE,
            )
        )
    )

    assert recall.hits == []
    assert recall.trace is not None
    assert recall.trace.route.startswith("retrieval.")
    assert archival.hits[0].layer == "archival"
    assert archival.hits[0].query_id == archival.trace.query_id
    assert archival.hits[0].rank == 1
    assert archival.hits[0].knowledge_ref is not None
    assert "forbids open spell rituals" in archival.hits[0].excerpt_text
    assert archival.trace.route.startswith("retrieval.")
    assert provenance.source_refs
