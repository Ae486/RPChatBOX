"""Focused tests for the bounded runtime retrieval card service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchRecallInput
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.models.retrieval_records import SourceAsset
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_retrieval_card_service import RuntimeRetrievalCardService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return service.get_session(session.session_id)


def _seed_recall_asset(retrieval_session, *, story_id: str):
    collection = RetrievalCollectionService(retrieval_session).ensure_story_collection(
        story_id=story_id,
        scope="story",
        collection_kind="recall",
    )
    RetrievalDocumentService(retrieval_session).upsert_source_asset(
        SourceAsset(
            asset_id="asset-runtime-card-1",
            story_id=story_id,
            mode=StoryMode.LONGFORM,
            collection_id=collection.collection_id,
            asset_kind="accepted_story_segment",
            source_ref="memory://runtime-card-1",
            title="Runtime Retrieval Card",
            parse_status="queued",
            ingestion_status="queued",
            mapped_targets=["recall"],
            metadata={
                "seed_sections": [
                    {
                        "section_id": "seed:runtime-card-1",
                        "title": "Runtime Retrieval Card",
                        "path": "chapter.recall.runtime-card-1",
                        "level": 1,
                        "text": "The silver seal broke during the first storm at dusk.",
                        "metadata": {
                            "domain": Domain.CHAPTER.value,
                            "domain_path": "chapter.recall.runtime-card-1",
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
        story_id=story_id,
        asset_id="asset-runtime-card-1",
        collection_id=collection.collection_id,
    )


@pytest.mark.asyncio
async def test_runtime_retrieval_card_service_materializes_cards_expansion_and_usage(
    retrieval_session,
):
    session = _seed_story_runtime(retrieval_session)
    _seed_recall_asset(retrieval_session, story_id=session.story_id)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.runtime_retrieval_card_service",
    )
    identity = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="write_next_segment",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    service = RuntimeRetrievalCardService(session=retrieval_session)

    result, cards, miss = await service.search_recall_to_cards(
        identity=identity,
        input_model=MemorySearchRecallInput(
            query="storm",
            scope="story",
            domains=[Domain.CHAPTER],
        ),
        actor="worker.specialist",
    )

    assert result.hits
    assert miss is None
    assert len(cards) == 1
    assert cards[0].short_id == "R1"

    expanded = service.expand_cards(
        identity=identity,
        card_material_ids=[cards[0].material_id],
        actor="worker.specialist",
    )

    assert len(expanded) == 1
    assert expanded[0].short_id == "X1"
    assert "first storm" in expanded[0].payload["text"]

    usage = service.record_writer_usage(
        identity=identity,
        used_card_ids=[cards[0].material_id],
        used_expanded_chunk_ids=[expanded[0].material_id],
        actor="worker.writer_packet",
    )

    assert usage.short_id == "U1"
    assert usage.payload["used_card_material_ids"] == [cards[0].material_id]
    assert usage.payload["used_expanded_chunk_material_ids"] == [
        expanded[0].material_id
    ]
    bundle = service.build_source_ref_bundle(identity=identity)
    assert bundle.retrieval_card_material_ids == [cards[0].material_id]
    assert bundle.retrieval_expanded_chunk_material_ids == [expanded[0].material_id]
    assert bundle.retrieval_usage_material_ids == [usage.material_id]
