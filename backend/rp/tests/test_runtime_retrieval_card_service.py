"""Focused tests for the bounded runtime retrieval card service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchRecallInput, RetrievalSearchResult
from rp.models.retrieval_runtime_contracts import RetrievalKnowledgeGapItem
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.models.retrieval_records import SourceAsset
from rp.services.retrieval_collection_service import RetrievalCollectionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.retrieval_ingestion_service import RetrievalIngestionService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_retrieval_card_service import (
    RuntimeRetrievalCardService,
    RuntimeRetrievalCardServiceError,
)
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterialVisibility,
)


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
    assert cards[0].payload["query_text"] == "storm"
    assert cards[0].metadata["attempt_index"] == 1

    expanded = service.expand_cards(
        identity=identity,
        card_material_ids=[cards[0].material_id],
        actor="worker.specialist",
    )

    assert len(expanded) == 1
    assert expanded[0].short_id == "X1"
    assert "first storm" in expanded[0].payload["text"]
    assert expanded[0].payload["card_short_id"] == "R1"

    usage = service.record_writer_usage(
        identity=identity,
        used_card_ids=["R1"],
        used_expanded_chunk_ids=["X1"],
        actor="worker.writer_packet",
        knowledge_gaps=[
            RetrievalKnowledgeGapItem(
                query="storm aftermath",
                status="insufficient_detail",
                impact="need to avoid naming the exact ruin",
                mode_policy_resolution="continue_conservatively",
            )
        ],
    )

    assert usage.short_id == "U1"
    assert usage.payload["used_card_short_ids"] == ["R1"]
    assert usage.payload["expanded_card_short_ids"] == ["R1"]
    assert usage.payload["unused_card_short_ids"] == []
    assert usage.payload["used_card_material_ids"] == [cards[0].material_id]
    assert usage.payload["used_expanded_chunk_material_ids"] == [
        expanded[0].material_id
    ]
    assert usage.payload["unused_card_material_ids"] == []
    assert usage.payload["missed_query_short_ids"] == []
    assert usage.payload["missed_query_material_ids"] == []
    assert usage.payload["knowledge_gaps"] == [
        {
            "gap_id": "G1",
            "query_text": "storm aftermath",
            "gap_kind": "insufficient_detail",
            "mode_policy_resolution": "continue_conservatively",
            "notes": "need to avoid naming the exact ruin",
        }
    ]
    bundle = service.build_source_ref_bundle(identity=identity)
    assert bundle.retrieval_card_material_ids == [cards[0].material_id]
    assert bundle.retrieval_expanded_chunk_material_ids == [expanded[0].material_id]
    assert bundle.retrieval_usage_material_ids == [usage.material_id]


@pytest.mark.asyncio
async def test_runtime_retrieval_card_service_usage_derives_unused_and_missed_fields(
    retrieval_session,
):
    session = _seed_story_runtime(retrieval_session)
    _seed_recall_asset(retrieval_session, story_id=session.story_id)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.runtime_retrieval_card_service.usage_derivation",
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

    _, cards, _ = await service.search_recall_to_cards(
        identity=identity,
        input_model=MemorySearchRecallInput(
            query="storm",
            scope="story",
            domains=[Domain.CHAPTER],
        ),
        actor="writer.retrieval",
    )
    duplicated_card = cards[0].model_copy(
        update={
            "material_id": "retrieval_card_manual_r2",
            "short_id": "R2",
            "payload": {
                **cards[0].payload,
                "hit_id": "manual-hit-2",
                "query_id": "manual-query-2",
                "summary": "A second retrieval card exists but is not used.",
                "excerpt": "A second retrieval card exists but is not used.",
                "title": "Unused Recall",
            },
            "source_refs": [
                cards[0].source_refs[0].model_copy(
                    update={"source_id": "manual-hit-2"}
                )
            ],
            "metadata": {
                **cards[0].metadata,
                "query_id": "manual-query-2",
                "query_text": "unused recall",
            },
        }
    )
    service._workspace().record_material(duplicated_card)

    _, no_hit_cards, miss = service.materialize_search_result(
        identity=identity,
        result=RetrievalSearchResult(
            query="unknown tavern",
            hits=[],
            warnings=["no match"],
        ),
        actor="writer.retrieval",
        query_text="unknown tavern",
        search_kind="recall",
        attempt_index=2,
    )

    assert no_hit_cards == []
    assert miss is not None
    assert miss.short_id == "M1"
    assert miss.payload["attempt_index"] == 2
    assert miss.payload["miss_reason"] == "search_no_hit"
    assert miss.payload["query_text"] == "unknown tavern"

    usage = service.record_writer_usage(
        identity=identity,
        used_card_ids=["R1"],
        used_expanded_chunk_ids=[],
        missed_query_ids=["M1"],
        actor="writer.retrieval",
        knowledge_gaps=[
            {
                "query": "unknown tavern",
                "status": "miss",
                "impact": "cannot name the tavern",
            }
        ],
    )

    assert usage.payload["used_card_short_ids"] == ["R1"]
    assert usage.payload["expanded_card_short_ids"] == []
    assert usage.payload["unused_card_short_ids"] == ["R2"]
    assert usage.payload["unused_card_material_ids"] == ["retrieval_card_manual_r2"]
    assert usage.payload["missed_query_short_ids"] == ["M1"]
    assert usage.payload["missed_query_material_ids"] == [miss.material_id]
    assert usage.payload["knowledge_gaps"] == [
        {
            "gap_id": "G1",
            "query_text": "unknown tavern",
            "gap_kind": "miss",
            "mode_policy_resolution": None,
            "notes": "cannot name the tavern",
        }
    ]


@pytest.mark.asyncio
async def test_runtime_retrieval_card_service_usage_rejects_wrong_kind_and_missing_refs(
    retrieval_session,
):
    session = _seed_story_runtime(retrieval_session)
    _seed_recall_asset(retrieval_session, story_id=session.story_id)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.runtime_retrieval_card_service.fail_closed",
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
    _, cards, _ = await service.search_recall_to_cards(
        identity=identity,
        input_model=MemorySearchRecallInput(
            query="storm",
            scope="story",
            domains=[Domain.CHAPTER],
        ),
        actor="writer.retrieval",
    )
    expanded = service.expand_cards(
        identity=identity,
        card_material_ids=[cards[0].material_id],
        actor="writer.retrieval",
    )

    with pytest.raises(RuntimeRetrievalCardServiceError) as missing_exc:
        service.record_writer_usage(
            identity=identity,
            used_card_ids=["R999"],
            used_expanded_chunk_ids=[],
            actor="writer.retrieval",
        )
    assert missing_exc.value.code == "runtime_retrieval_material_reference_not_found"

    with pytest.raises(RuntimeRetrievalCardServiceError) as wrong_kind_exc:
        service.record_writer_usage(
            identity=identity,
            used_card_ids=[expanded[0].material_id],
            used_expanded_chunk_ids=[],
            actor="writer.retrieval",
        )
    assert wrong_kind_exc.value.code == "runtime_retrieval_material_kind_mismatch"

    broken_expanded = expanded[0].model_copy(
        update={
            "material_id": "retrieval_expanded_broken_x2",
            "short_id": "X2",
            "payload": {
                **expanded[0].payload,
                "card_material_id": "",
                "card_short_id": None,
            },
            "visibility": RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
        }
    )
    service._workspace().record_material(broken_expanded)

    with pytest.raises(RuntimeRetrievalCardServiceError) as broken_parent_exc:
        service.record_writer_usage(
            identity=identity,
            used_card_ids=["R1"],
            used_expanded_chunk_ids=["X2"],
            actor="writer.retrieval",
        )
    assert (
        broken_parent_exc.value.code
        == "runtime_retrieval_expanded_chunk_card_missing"
    )
