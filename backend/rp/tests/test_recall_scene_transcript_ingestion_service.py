"""Tests for closed-scene transcript promotion into Recall."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

import pytest

from rp.models.dsl import Domain
from rp.models.memory_crud import MemorySearchRecallInput
from rp.models.retrieval_records import IndexJob
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection_state_service import ProjectionStateService
from rp.services.recall_scene_transcript_ingestion_service import (
    RecallSceneTranscriptIngestionService,
    SceneTranscriptPromotionInput,
)
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_document_service import RetrievalDocumentService
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_runtime_controller import StoryRuntimeController
from rp.services.story_session_service import StorySessionService
from rp.services.story_turn_domain_service import StoryTurnDomainService
from rp.services.writing_packet_builder import WritingPacketBuilder


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


def _seed_story_runtime(
    retrieval_session,
    *,
    story_id: str = "story-scene-transcript",
    workspace_id: str = "workspace-scene-transcript",
):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id=story_id,
        source_workspace_id=workspace_id,
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "segment_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.SEGMENT_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        chapter_goal="Chapter 1",
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


class _NoopRegressionService:
    async def run_light_regression(
        self, *, session, chapter, accepted_artifact, model_id, provider_id
    ):
        return session, chapter

    async def run_heavy_regression(self, *, session, chapter, model_id, provider_id):
        return session, chapter


def _build_controller(
    service: StorySessionService,
    transcript_service: RecallSceneTranscriptIngestionService,
) -> StoryRuntimeController:
    return StoryRuntimeController(
        story_session_service=service,
        story_activation_service=SimpleNamespace(),
        version_history_read_service=SimpleNamespace(),
        provenance_read_service=SimpleNamespace(),
        projection_read_service=SimpleNamespace(),
        memory_inspection_read_service=SimpleNamespace(),
        rp_block_read_service=cast(RpBlockReadService, SimpleNamespace()),
        recall_scene_transcript_ingestion_service=transcript_service,
    )


def _build_turn_domain_service(
    service: StorySessionService,
    transcript_service: RecallSceneTranscriptIngestionService,
) -> StoryTurnDomainService:
    projection_state_service = ProjectionStateService(
        story_session_service=service,
        adapter=ChapterWorkspaceProjectionAdapter(service),
    )
    return StoryTurnDomainService(
        story_session_service=service,
        orchestrator_service=SimpleNamespace(),
        specialist_service=SimpleNamespace(),
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        projection_state_service=projection_state_service,
        writing_packet_builder=WritingPacketBuilder(),
        writing_worker_execution_service=SimpleNamespace(),
        regression_service=_NoopRegressionService(),
        recall_scene_transcript_ingestion_service=transcript_service,
    )


def test_ingest_scene_transcript_filters_and_persists_metadata(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    service = RecallSceneTranscriptIngestionService(retrieval_session)

    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="The silver braid oath must stay visible.",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="system",
        content_text="system text must stay out of transcript recall.",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="   ",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="We should keep the lantern tally marks in the spoken recall.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Draft prose must not enter settled scene transcript recall.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.SUPERSEDED,
        content_text="Superseded prose must not enter settled scene transcript recall.",
    )
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=("The oath-marked lantern clicked open beside the narrow stair."),
        revision=2,
    )
    story_session_service.close_current_scene(session_id=session.session_id)
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Second-scene discussion should not leak backward.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Second-scene accepted prose should not leak backward.",
    )
    story_session_service.commit()

    input_model = service.build_promotion_input(
        session_id=session.session_id,
        story_id=session.story_id,
        chapter_index=chapter.chapter_index,
        scene_ref="chapter:1:scene:1",
        source_workspace_id=session.source_workspace_id,
        discussion_entries=story_session_service.list_discussion_entries(
            chapter_workspace_id=chapter.chapter_workspace_id
        ),
        artifacts=story_session_service.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        ),
    )
    asset_id = service.ingest_scene_transcript(input_model)
    retrieval_session.commit()

    expected_asset_id = RecallSceneTranscriptIngestionService._build_asset_id(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
        scene_ref="chapter:1:scene:1",
    )
    assert asset_id == expected_asset_id
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert [asset.asset_id for asset in assets] == [expected_asset_id]
    asset = assets[0]
    assert asset.asset_kind == "scene_transcript"
    assert asset.metadata["layer"] == "recall"
    assert asset.metadata["source_family"] == "longform_story_runtime"
    assert asset.metadata["materialization_event"] == "scene_close"
    assert asset.metadata["materialization_kind"] == "scene_transcript"
    assert asset.metadata["materialized_to_recall"] is True
    assert asset.metadata["chapter_index"] == 1
    assert asset.metadata["scene_ref"] == "chapter:1:scene:1"
    assert asset.metadata["transcript_source_count"] == 3
    assert asset.metadata["transcript_includes_discussion"] is True
    assert asset.metadata["transcript_includes_accepted_segments"] is True
    transcript_text = asset.metadata["seed_sections"][0]["text"]
    assert "User: The silver braid oath must stay visible." in transcript_text
    assert (
        "Assistant: We should keep the lantern tally marks in the spoken recall."
        in transcript_text
    )
    assert f"Accepted Segment r{accepted_segment.revision}:" in transcript_text
    assert "system text must stay out of transcript recall" not in transcript_text
    assert (
        "Draft prose must not enter settled scene transcript recall"
        not in transcript_text
    )
    assert (
        "Superseded prose must not enter settled scene transcript recall"
        not in transcript_text
    )
    assert "Second-scene discussion should not leak backward" not in transcript_text


def test_ingest_scene_transcript_reuses_asset_id_and_reindexes(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-rerun",
    )
    service = RecallSceneTranscriptIngestionService(retrieval_session)
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Keep the oath-marked lantern in recall.",
    )
    accepted_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="First accepted scene transcript prose.",
        revision=1,
    )
    story_session_service.commit()

    first_asset_id = service.ingest_scene_transcript(
        service.build_promotion_input(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            scene_ref="chapter:1:scene:1",
            source_workspace_id=session.source_workspace_id,
            discussion_entries=story_session_service.list_discussion_entries(
                chapter_workspace_id=chapter.chapter_workspace_id
            ),
            artifacts=story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            ),
        )
    )
    retrieval_session.commit()

    story_session_service.update_artifact(
        artifact_id=accepted_segment.artifact_id,
        content_text="Updated accepted scene transcript prose after rerun.",
        revision=2,
    )
    story_session_service.commit()

    second_asset_id = service.ingest_scene_transcript(
        service.build_promotion_input(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            scene_ref="chapter:1:scene:1",
            source_workspace_id=session.source_workspace_id,
            discussion_entries=story_session_service.list_discussion_entries(
                chapter_workspace_id=chapter.chapter_workspace_id
            ),
            artifacts=story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            ),
        )
    )
    retrieval_session.commit()

    assert second_asset_id == first_asset_id
    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    assert len(assets) == 1
    assert assets[0].asset_id == first_asset_id
    assert (
        "Updated accepted scene transcript prose after rerun."
        in assets[0].metadata["seed_sections"][0]["text"]
    )


def test_ingest_scene_transcript_rejects_mixed_scene_candidates(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-mixed",
    )
    first_entry = story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Scene one discussion line.",
    )
    story_session_service.close_current_scene(session_id=session.session_id)
    second_entry = story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="Scene two discussion line.",
    )
    story_session_service.commit()

    with pytest.raises(
        ValueError, match="scene transcript candidates mixed scene refs"
    ):
        RecallSceneTranscriptIngestionService(
            retrieval_session
        ).ingest_scene_transcript(
            SceneTranscriptPromotionInput(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                scene_ref="chapter:1:scene:1",
                source_workspace_id=session.source_workspace_id,
                discussion_entries=[first_entry, second_entry],
                accepted_segments=[],
            )
        )


def test_build_scene_transcript_input_rejects_missing_scene_ref(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-missing-scene-ref",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="This discussion forgot its scene ref.",
        scene_ref=None,
    )
    story_session_service.commit()

    with pytest.raises(
        ValueError, match="scene transcript candidate missing scene_ref"
    ):
        RecallSceneTranscriptIngestionService(retrieval_session).build_promotion_input(
            session_id=session.session_id,
            story_id=session.story_id,
            chapter_index=chapter.chapter_index,
            scene_ref="chapter:1:scene:1",
            source_workspace_id=session.source_workspace_id,
            discussion_entries=story_session_service.list_discussion_entries(
                chapter_workspace_id=chapter.chapter_workspace_id
            ),
            artifacts=[],
        )


def test_ingest_scene_transcript_rejects_blank_scene_ref_without_builder(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-blank-scene-ref",
    )
    entry = story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Blank scene ref direct input must fail.",
        scene_ref="",
    )
    story_session_service.commit()

    with pytest.raises(
        ValueError, match="scene transcript promotion requires a non-empty scene_ref"
    ):
        RecallSceneTranscriptIngestionService(retrieval_session).ingest_scene_transcript(
            SceneTranscriptPromotionInput(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                scene_ref="",
                source_workspace_id=session.source_workspace_id,
                discussion_entries=[entry],
                accepted_segments=[],
            )
        )


def test_ingest_scene_transcript_surfaces_failed_index_jobs(
    retrieval_session,
    monkeypatch,
):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-failure",
    )
    service = RecallSceneTranscriptIngestionService(retrieval_session)
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Failure path discussion line.",
    )
    story_session_service.commit()

    asset_id = RecallSceneTranscriptIngestionService._build_asset_id(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
        scene_ref="chapter:1:scene:1",
    )
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
        match=(
            "recall_scene_transcript_ingestion_failed:"
            f"{asset_id}:embedding_provider_unavailable"
        ),
    ):
        service.ingest_scene_transcript(
            service.build_promotion_input(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                scene_ref="chapter:1:scene:1",
                source_workspace_id=session.source_workspace_id,
                discussion_entries=story_session_service.list_discussion_entries(
                    chapter_workspace_id=chapter.chapter_workspace_id
                ),
                artifacts=[],
            )
        )


@pytest.mark.asyncio
async def test_close_current_scene_materializes_searchable_transcript(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-close",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="The silver braid oath moved under the stair.",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="Keep the lantern tally marks attached to that oath.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The lantern tally marks clicked once beneath the stair.",
    )
    controller = _build_controller(
        story_session_service,
        RecallSceneTranscriptIngestionService(retrieval_session),
    )

    snapshot = controller.close_current_scene(session_id=session.session_id)

    assert snapshot.chapter.last_closed_scene_ref == "chapter:1:scene:1"
    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="silver braid oath lantern tally stair",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=5,
            filters={"materialization_kinds": ["scene_transcript"]},
        )
    )

    assert result.hits
    assert result.hits[0].metadata["materialization_kind"] == "scene_transcript"
    assert result.hits[0].metadata["scene_ref"] == "chapter:1:scene:1"
    assert result.hits[0].metadata["materialization_event"] == "scene_close"
    assert "silver braid oath" in result.hits[0].excerpt_text.lower()


@pytest.mark.asyncio
async def test_complete_chapter_materializes_last_scene_transcript(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-complete",
    )
    story_session_service.close_current_scene(session_id=session.session_id)
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Second-scene whisper about the harbor bell debt.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The harbor bell debt echoed across the wet market stalls.",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        RecallSceneTranscriptIngestionService(retrieval_session),
    )

    response = await turn_domain_service.complete_chapter(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id="model-scene-transcript-complete",
        )
    )

    assert response.current_chapter_index == 2
    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="harbor bell debt wet market stalls",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=5,
            filters={"materialization_kinds": ["scene_transcript"]},
        )
    )

    assert result.hits
    assert result.hits[0].metadata["scene_ref"] == "chapter:1:scene:2"


@pytest.mark.asyncio
async def test_accept_pending_segment_reruns_closed_scene_transcript(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="story-scene-transcript-rerun-closed-scene",
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Scene one should stay recoverable after later acceptance.",
    )
    pending_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Later-accepted prose belongs back in scene one transcript.",
        revision=1,
    )
    story_session_service.close_current_scene(session_id=session.session_id)
    story_session_service.commit()

    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        RecallSceneTranscriptIngestionService(retrieval_session),
    )

    response = await turn_domain_service.accept_pending_segment(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            model_id="model-scene-transcript-rerun",
            target_artifact_id=pending_segment.artifact_id,
        )
    )

    assert response.artifact_id == pending_segment.artifact_id
    broker = RetrievalBroker(default_story_id=session.story_id)
    result = await broker.search_recall(
        MemorySearchRecallInput(
            query="later accepted prose recoverable scene one transcript",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=5,
            filters={"materialization_kinds": ["scene_transcript"]},
        )
    )

    assert result.hits
    assert result.hits[0].metadata["scene_ref"] == "chapter:1:scene:1"
    assert "later-accepted prose belongs back in scene one transcript" in (
        result.hits[0].excerpt_text.lower()
    )
