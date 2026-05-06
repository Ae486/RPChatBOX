"""Focused tests for Recall lifecycle governance over retrieval-core assets."""

from __future__ import annotations

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_materialization import (
    CHAPTER_SUMMARY_KIND,
    HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
    build_recall_materialization_metadata,
)
from rp.models.story_runtime import LongformChapterPhase
from rp.services.recall_lifecycle_service import RecallLifecycleService
from rp.services.recall_summary_ingestion_service import RecallSummaryIngestionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.story_session_service import StorySessionService


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-recall-lifecycle",
        source_workspace_id="workspace-recall-lifecycle",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.SEGMENT_REVIEW,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        builder_snapshot_json={},
    )
    service.commit()
    return session, chapter


def test_recall_lifecycle_service_preserves_supersede_and_invalidate_audit(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    initial_identity = MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        turn_id="turn-1",
        runtime_profile_snapshot_id="snapshot-1",
    )
    asset_id = RecallSummaryIngestionService(retrieval_session).ingest_chapter_summary(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_text="Lifecycle audit baseline summary.",
        runtime_identity=initial_identity,
        source_refs=[
            MemorySourceRef(
                source_type="story_turn",
                source_id=initial_identity.turn_id,
                layer="runtime_identity",
            )
        ],
    )
    retrieval_session.commit()

    replacement_identity = initial_identity.model_copy(update={"turn_id": "turn-2"})
    replacement_metadata = build_recall_materialization_metadata(
        materialization_kind=CHAPTER_SUMMARY_KIND,
        materialization_event=HEAVY_REGRESSION_CHAPTER_CLOSE_EVENT,
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
        domain_path="recall.chapter.1",
        identity=replacement_identity,
        source_refs=[
            MemorySourceRef(
                source_type="story_turn",
                source_id=replacement_identity.turn_id,
                layer="runtime_identity",
            )
        ],
    )
    lifecycle_service = RecallLifecycleService(retrieval_session)
    lifecycle_service.supersede_material(
        material_refs=[asset_id],
        replacement_metadata=replacement_metadata,
    )
    lifecycle_service.invalidate_material(
        material_refs=[asset_id],
        event_id="evt.rollback.1",
        reason="branch rollback hid the later summary",
    )
    retrieval_session.commit()

    asset = RetrievalDocumentService(retrieval_session).get_source_asset(asset_id)
    assert asset is not None
    assert asset.metadata["lifecycle_state"] == "invalidated"
    assert asset.metadata["superseded_by_runtime_identity"]["turn_id"] == "turn-2"
    assert asset.metadata["invalidated_by_event_ids"] == ["evt.rollback.1"]
    seed_section = asset.metadata["seed_sections"][0]
    assert seed_section["metadata"]["lifecycle_state"] == "invalidated"
    assert seed_section["metadata"]["invalidated_by_event_ids"] == ["evt.rollback.1"]
