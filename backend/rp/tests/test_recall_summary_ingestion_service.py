"""Tests for chapter-summary recall ingestion."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.retrieval_records import IndexJob
from rp.models.story_runtime import LongformChapterPhase
from rp.services.recall_summary_ingestion_service import RecallSummaryIngestionService
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.story_session_service import StorySessionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _failed_job(*, story_id: str, asset_id: str) -> IndexJob:
    now = _utcnow()
    return IndexJob(
        job_id=f"failed_{asset_id}",
        story_id=story_id,
        asset_id=asset_id,
        collection_id=None,
        job_kind="ingest",
        job_state="failed",
        target_refs=[f"asset:{asset_id}"],
        warnings=[],
        error_message="embedding_provider_unavailable",
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-recall-summary",
        source_workspace_id="workspace-recall-summary",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "chapter_completed",
                "accepted_segments": 2,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
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


def test_ingest_chapter_summary_persists_recall_metadata(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    runtime_identity = MemoryRuntimeIdentity(
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
        summary_text="Chapter one settled into a tense marketplace truce.",
        runtime_identity=runtime_identity,
        source_refs=[
            MemorySourceRef(
                source_type="story_turn",
                source_id="turn-1",
                layer="runtime_identity",
            )
        ],
    )
    retrieval_session.commit()

    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert [asset.asset_id for asset in assets] == [asset_id]
    asset = assets[0]
    assert asset.asset_kind == "chapter_summary"
    assert asset.metadata["layer"] == "recall"
    assert asset.metadata["source_family"] == "longform_story_runtime"
    assert asset.metadata["materialization_event"] == ("heavy_regression.chapter_close")
    assert asset.metadata["materialization_kind"] == "chapter_summary"
    assert asset.metadata["materialized_to_recall"] is True
    assert asset.metadata["source_type"] == "chapter_summary"
    assert asset.metadata["domain"] == "chapter"
    assert asset.metadata["domain_path"] == f"recall.chapter.{chapter.chapter_index}"
    assert asset.metadata["session_id"] == session.session_id
    assert asset.metadata["chapter_index"] == chapter.chapter_index
    assert asset.metadata["runtime_identity"]["turn_id"] == "turn-1"
    assert asset.metadata["owning_branch_head_id"] == "branch-main"
    assert asset.metadata["lifecycle_state"] == "active"
    assert asset.metadata["source_refs"][0]["source_type"] == "story_turn"
    seed_section = asset.metadata["seed_sections"][0]
    assert seed_section["metadata"]["source_type"] == "chapter_summary"
    assert seed_section["metadata"]["materialized_to_recall"] is True


def test_ingest_chapter_summary_recomputes_existing_asset(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallSummaryIngestionService(retrieval_session)
    runtime_identity = MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        turn_id="turn-1",
        runtime_profile_snapshot_id="snapshot-1",
    )
    asset_id = service.ingest_chapter_summary(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_text="First summary.",
        runtime_identity=runtime_identity,
    )
    retrieval_session.commit()

    recomputed_identity = runtime_identity.model_copy(update={"turn_id": "turn-2"})
    second_asset_id = service.ingest_chapter_summary(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_text="Second summary after recompute.",
        runtime_identity=recomputed_identity,
        source_refs=[
            MemorySourceRef(
                source_type="story_turn",
                source_id="turn-2",
                layer="runtime_identity",
            )
        ],
    )
    retrieval_session.commit()

    assert second_asset_id == asset_id
    asset = RetrievalDocumentService(retrieval_session).get_source_asset(asset_id)
    assert asset is not None
    assert asset.raw_excerpt == "Second summary after recompute."
    assert asset.metadata["lifecycle_state"] == "recomputed"
    assert asset.metadata["visibility_state"] == "active"
    assert asset.metadata["runtime_identity"]["turn_id"] == "turn-2"
    assert "story_turn:turn-1" in asset.metadata["supersedes_refs"]


def test_ingest_chapter_summary_surfaces_failed_index_jobs(
    retrieval_session,
    monkeypatch,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallSummaryIngestionService(retrieval_session)

    monkeypatch.setattr(
        service._ingestion_service,
        "ingest_asset",
        lambda **kwargs: _failed_job(
            story_id=kwargs["story_id"],
            asset_id=kwargs["asset_id"],
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="recall_summary_ingestion_failed:.*:embedding_provider_unavailable",
    ):
        service.ingest_chapter_summary(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            source_workspace_id=session.source_workspace_id,
            summary_text="Chapter one settled into a tense marketplace truce.",
        )
