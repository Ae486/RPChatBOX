"""Tests for accepted-prose recall detail ingestion."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchRecallInput
from rp.models.retrieval_records import IndexJob
from rp.models.story_runtime import (
    LongformChapterPhase,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.recall_detail_ingestion_service import RecallDetailIngestionService
from rp.services.retrieval_broker import RetrievalBroker
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
        job_kind="reindex",
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
        story_id="story-recall-detail",
        source_workspace_id="workspace-recall-detail",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "segment_review",
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
    return service, session, chapter


def test_ingest_accepted_story_segments_persists_recall_assets_with_metadata(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Silver lantern wax clung to the oath-marked railing.",
        revision=2,
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Draft segment should stay out of recall.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted outline should not be ingested as prose detail.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="   ",
    )
    story_session_service.commit()

    asset_ids = RecallDetailIngestionService(
        retrieval_session
    ).ingest_accepted_story_segments(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        accepted_segments=story_session_service.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        ),
    )
    retrieval_session.commit()

    expected_asset_id = f"recall_detail_{accepted_segment.artifact_id}"
    assert asset_ids == [expected_asset_id]
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert [asset.asset_id for asset in assets] == [expected_asset_id]
    asset = assets[0]
    assert asset.asset_kind == "accepted_story_segment"
    assert asset.source_ref == (
        f"story_session:{session.session_id}:chapter:{chapter.chapter_index}:"
        f"artifact:{accepted_segment.artifact_id}"
    )
    assert asset.metadata["layer"] == "recall"
    assert asset.metadata["source_family"] == "longform_story_runtime"
    assert asset.metadata["materialization_event"] == "heavy_regression.chapter_close"
    assert asset.metadata["materialization_kind"] == "accepted_story_segment"
    assert asset.metadata["materialized_to_recall"] is True
    assert asset.metadata["source_type"] == "accepted_story_segment"
    assert asset.metadata["artifact_id"] == accepted_segment.artifact_id
    assert asset.metadata["artifact_revision"] == 2
    assert asset.metadata["artifact_kind"] == StoryArtifactKind.STORY_SEGMENT.value
    assert asset.metadata["chapter_index"] == chapter.chapter_index
    seed_section = asset.metadata["seed_sections"][0]
    assert seed_section["path"] == (
        f"recall.chapter.{chapter.chapter_index}.accepted_segment."
        f"{accepted_segment.artifact_id}"
    )
    assert seed_section["metadata"]["domain"] == Domain.CHAPTER.value
    assert seed_section["metadata"]["layer"] == "recall"
    assert seed_section["metadata"]["source_family"] == "longform_story_runtime"
    assert seed_section["metadata"]["materialization_event"] == (
        "heavy_regression.chapter_close"
    )
    assert seed_section["metadata"]["materialization_kind"] == (
        "accepted_story_segment"
    )
    assert seed_section["metadata"]["materialized_to_recall"] is True
    assert seed_section["metadata"]["source_type"] == "accepted_story_segment"


def test_ingest_accepted_story_segments_reuses_deterministic_asset_ids(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="First accepted prose detail.",
    )
    story_session_service.commit()

    service = RecallDetailIngestionService(retrieval_session)
    first_asset_ids = service.ingest_accepted_story_segments(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    updated_artifact = story_session_service.update_artifact(
        artifact_id=accepted_segment.artifact_id,
        content_text="Updated accepted prose detail after a second heavy regression.",
        revision=3,
    )
    story_session_service.commit()

    second_asset_ids = service.ingest_accepted_story_segments(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        accepted_segments=[updated_artifact],
    )
    retrieval_session.commit()

    assert second_asset_ids == first_asset_ids
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert len(assets) == 1
    asset = assets[0]
    assert asset.asset_id == first_asset_ids[0]
    assert asset.raw_excerpt == (
        "Updated accepted prose detail after a second heavy regression."
    )
    assert asset.metadata["artifact_revision"] == 3


def test_ingest_accepted_story_segments_surfaces_reindex_failures(
    retrieval_session,
    monkeypatch,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="First accepted prose detail.",
    )
    story_session_service.commit()

    service = RecallDetailIngestionService(retrieval_session)
    service.ingest_accepted_story_segments(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    updated_artifact = story_session_service.update_artifact(
        artifact_id=accepted_segment.artifact_id,
        content_text="Updated accepted prose detail after a second heavy regression.",
        revision=2,
    )
    story_session_service.commit()

    monkeypatch.setattr(
        service._ingestion_service,
        "reindex_asset",
        lambda **kwargs: _failed_job(
            story_id=kwargs["story_id"],
            asset_id=kwargs["asset_id"],
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "recall_detail_ingestion_failed:"
            f"recall_detail_{accepted_segment.artifact_id}:embedding_provider_unavailable"
        ),
    ):
        service.ingest_accepted_story_segments(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            source_workspace_id=session.source_workspace_id,
            accepted_segments=[updated_artifact],
        )


@pytest.mark.asyncio
async def test_ingest_accepted_story_segments_makes_prose_searchable_in_recall(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "The silver braid oath was hidden beneath the market stair,"
            " beside a lantern scored with nine tally marks."
        ),
    )
    story_session_service.commit()

    RecallDetailIngestionService(retrieval_session).ingest_accepted_story_segments(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        source_workspace_id=session.source_workspace_id,
        accepted_segments=[accepted_segment],
    )
    retrieval_session.commit()

    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="silver braid lantern tally marks",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=3,
        )
    )

    assert result.hits
    assert result.hits[0].layer == "recall"
    assert result.hits[0].metadata["asset_id"] == (
        f"recall_detail_{accepted_segment.artifact_id}"
    )
    assert "silver braid oath" in result.hits[0].excerpt_text.lower()
