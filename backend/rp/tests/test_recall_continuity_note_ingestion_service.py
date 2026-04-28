"""Tests for heavy-regression continuity-note recall ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pytest
from sqlmodel import select

from models.rp_retrieval_store import KnowledgeChunkRecord
from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchRecallInput
from rp.models.retrieval_records import IndexJob
from rp.models.story_runtime import LongformChapterPhase
from rp.services.recall_continuity_note_ingestion_service import (
    RecallContinuityNoteIngestionService,
)
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.story_session_service import StorySessionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _index_job(
    *,
    story_id: str,
    asset_id: str,
    state: Literal["completed", "failed"],
    error_message: str | None = None,
) -> IndexJob:
    now = _utcnow()
    return IndexJob(
        job_id=f"{state}_{asset_id}",
        story_id=story_id,
        asset_id=asset_id,
        collection_id=None,
        job_kind="reindex",
        job_state=state,
        target_refs=[f"asset:{asset_id}"],
        warnings=[],
        error_message=error_message,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-recall-continuity-note",
        source_workspace_id="workspace-recall-continuity-note",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "chapter_completed",
                "accepted_segments": 1,
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
    session = service.get_session(session.session_id)
    chapter = service.get_chapter_by_index(
        session_id=chapter.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert session is not None
    assert chapter is not None
    return session, chapter


def test_ingest_continuity_notes_persists_metadata_and_dedupes(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)

    asset_ids = RecallContinuityNoteIngestionService(
        retrieval_session
    ).ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=[
            "The masked envoy now knows the seal phrase.",
            "   ",
            "The masked envoy now knows the seal phrase.",
            "The bell tower debt should stay visible next chapter.",
        ],
    )
    retrieval_session.commit()

    assert len(asset_ids) == 2
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert {asset.asset_kind for asset in assets} == {"continuity_note"}
    assert {asset.asset_id for asset in assets} == set(asset_ids)
    first_asset = next(
        asset
        for asset in assets
        if asset.raw_excerpt == "The masked envoy now knows the seal phrase."
    )
    assert first_asset.metadata["layer"] == "recall"
    assert first_asset.metadata["source_family"] == "longform_story_runtime"
    assert first_asset.metadata["materialization_event"] == (
        "heavy_regression.chapter_close"
    )
    assert first_asset.metadata["materialization_kind"] == "continuity_note"
    assert first_asset.metadata["materialized_to_recall"] is True
    assert first_asset.metadata["source_type"] == "continuity_note"
    assert first_asset.metadata["chapter_index"] == chapter.chapter_index
    assert first_asset.metadata["note_index"] == 0
    seed_section = first_asset.metadata["seed_sections"][0]
    assert seed_section["metadata"]["domain"] == Domain.CHAPTER.value
    assert seed_section["metadata"]["materialization_kind"] == "continuity_note"
    assert seed_section["metadata"]["source_type"] == "continuity_note"
    assert seed_section["metadata"]["materialized_to_recall"] is True
    chunks = retrieval_session.exec(
        select(KnowledgeChunkRecord).where(
            KnowledgeChunkRecord.asset_id == first_asset.asset_id
        )
    ).all()
    assert chunks
    assert chunks[0].metadata_json["materialization_kind"] == "continuity_note"
    assert chunks[0].metadata_json["source_family"] == "longform_story_runtime"
    assert chunks[0].metadata_json["source_type"] == "continuity_note"
    assert chunks[0].metadata_json["note_index"] == 0


def test_ingest_continuity_notes_skips_blank_notes(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)

    asset_ids = RecallContinuityNoteIngestionService(
        retrieval_session
    ).ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=["", "   ", "\n\t"],
    )
    retrieval_session.commit()

    assert asset_ids == []
    assert (
        RetrievalDocumentService(retrieval_session).list_story_assets(session.story_id)
        == []
    )


def test_ingest_continuity_notes_reuses_and_reindexes_existing_asset(
    retrieval_session,
    monkeypatch,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallContinuityNoteIngestionService(retrieval_session)
    first_asset_ids = service.ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=["The canal bridge remains unsafe after moonrise."],
    )
    retrieval_session.commit()

    reindexed_asset_ids: list[str] = []

    def reindex_asset(**kwargs):
        reindexed_asset_ids.append(kwargs["asset_id"])
        return _index_job(
            story_id=kwargs["story_id"],
            asset_id=kwargs["asset_id"],
            state="completed",
        )

    monkeypatch.setattr(service._ingestion_service, "reindex_asset", reindex_asset)

    second_asset_ids = service.ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=["  The canal bridge remains unsafe after moonrise.  "],
    )
    retrieval_session.commit()

    assert second_asset_ids == first_asset_ids
    assert reindexed_asset_ids == first_asset_ids
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert len(assets) == 1
    assert assets[0].asset_id == first_asset_ids[0]


def test_ingest_continuity_note_identity_ignores_note_index(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallContinuityNoteIngestionService(retrieval_session)

    first_asset_ids = service.ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=["The canal bridge remains unsafe after moonrise."],
    )
    retrieval_session.commit()

    second_asset_ids = service.ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=[
            "A new note should become its own continuity asset.",
            "The canal bridge remains unsafe after moonrise.",
        ],
    )
    retrieval_session.commit()

    assert first_asset_ids[0] in second_asset_ids
    assert len(second_asset_ids) == 2
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    repeated_asset = next(
        asset for asset in assets if asset.asset_id == first_asset_ids[0]
    )
    assert repeated_asset.metadata["note_index"] == 1


def test_ingest_continuity_notes_surfaces_failed_index_jobs(
    retrieval_session,
    monkeypatch,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallContinuityNoteIngestionService(retrieval_session)

    monkeypatch.setattr(
        service._ingestion_service,
        "ingest_asset",
        lambda **kwargs: _index_job(
            story_id=kwargs["story_id"],
            asset_id=kwargs["asset_id"],
            state="failed",
            error_message="embedding_provider_unavailable",
        ),
    )

    asset_id = service._build_asset_id(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
        note_text="The envoy's false seal should be remembered.",
    )
    with pytest.raises(
        RuntimeError,
        match=(
            "recall_continuity_note_ingestion_failed:"
            f"{asset_id}:embedding_provider_unavailable"
        ),
    ):
        service.ingest_continuity_notes(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            source_workspace_id=session.source_workspace_id,
            summary_updates=["The envoy's false seal should be remembered."],
        )


@pytest.mark.asyncio
async def test_ingest_continuity_notes_makes_note_searchable_in_recall(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)

    asset_ids = RecallContinuityNoteIngestionService(
        retrieval_session
    ).ingest_continuity_notes(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        summary_updates=[
            "The masked envoy now knows the seal phrase and the river password.",
        ],
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="masked envoy seal phrase river password",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=3,
        )
    )

    assert result.hits
    assert result.hits[0].metadata["asset_id"] == asset_ids[0]
    assert result.hits[0].metadata["source_family"] == "longform_story_runtime"
    assert result.hits[0].metadata["materialization_event"] == (
        "heavy_regression.chapter_close"
    )
    assert result.hits[0].metadata["materialization_kind"] == "continuity_note"
    assert result.hits[0].metadata["materialized_to_recall"] is True
    assert result.hits[0].metadata["source_type"] == "continuity_note"
    assert result.hits[0].metadata["chapter_index"] == chapter.chapter_index
    assert result.hits[0].metadata["note_index"] == 0
