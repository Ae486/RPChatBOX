"""Focused tests for runtime scene lifecycle scaffolding."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import create_engine, text

from models.rp_story_store import ensure_story_store_compatible_schema
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
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_runtime_controller import StoryRuntimeController
from rp.services.story_session_service import StorySessionService
from rp.services.story_turn_domain_service import StoryTurnDomainService
from rp.services.writing_packet_builder import WritingPacketBuilder


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-scene-lifecycle",
        source_workspace_id="workspace-scene-lifecycle",
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
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return session, chapter, service


class _NoopRegressionService:
    async def run_light_regression(
        self, *, session, chapter, accepted_artifact, model_id, provider_id
    ):
        return session, chapter

    async def run_heavy_regression(self, *, session, chapter, model_id, provider_id):
        return session, chapter


def _build_turn_domain_service(service: StorySessionService) -> StoryTurnDomainService:
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
    )


def _build_controller(service: StorySessionService) -> StoryRuntimeController:
    return StoryRuntimeController(
        story_session_service=service,
        story_activation_service=SimpleNamespace(),
        version_history_read_service=SimpleNamespace(),
        provenance_read_service=SimpleNamespace(),
        projection_read_service=SimpleNamespace(),
        memory_inspection_read_service=SimpleNamespace(),
        rp_block_read_service=cast(RpBlockReadService, SimpleNamespace()),
    )


def test_story_session_service_seeds_scene_fields_and_default_scene_refs(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)

    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Outline scaffold",
    )
    segment = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Scene-local segment",
    )
    discussion = service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="Keep the pace taut.",
        linked_artifact_id=segment.artifact_id,
    )

    assert chapter.current_scene_ref == "chapter:1:scene:1"
    assert chapter.next_scene_index == 2
    assert chapter.last_closed_scene_ref is None
    assert chapter.closed_scene_refs == []
    assert outline.scene_ref is None
    assert segment.scene_ref == "chapter:1:scene:1"
    assert discussion.scene_ref == "chapter:1:scene:1"


def test_story_session_service_close_current_scene_rotates_scene_refs(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)

    rotated = service.close_current_scene(session_id=session.session_id)
    rotated_segment = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Second scene segment",
    )
    rotated_discussion = service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Push the next beat harder.",
    )
    advanced = service.close_current_scene(session_id=session.session_id)

    assert rotated.phase == LongformChapterPhase.SEGMENT_DRAFTING
    assert rotated.last_closed_scene_ref == "chapter:1:scene:1"
    assert rotated.closed_scene_refs == ["chapter:1:scene:1"]
    assert rotated.current_scene_ref == "chapter:1:scene:2"
    assert rotated.next_scene_index == 3
    assert rotated_segment.scene_ref == "chapter:1:scene:2"
    assert rotated_discussion.scene_ref == "chapter:1:scene:2"
    assert advanced.last_closed_scene_ref == "chapter:1:scene:2"
    assert advanced.closed_scene_refs == [
        "chapter:1:scene:1",
        "chapter:1:scene:2",
    ]
    assert advanced.current_scene_ref == "chapter:1:scene:3"
    assert advanced.next_scene_index == 4


def test_story_runtime_controller_close_current_scene_returns_snapshot(
    retrieval_session,
):
    session, _chapter, service = _seed_story_runtime(retrieval_session)
    controller = _build_controller(service)

    snapshot = controller.close_current_scene(session_id=session.session_id)

    assert snapshot.session.session_id == session.session_id
    assert snapshot.chapter.last_closed_scene_ref == "chapter:1:scene:1"
    assert snapshot.chapter.closed_scene_refs == ["chapter:1:scene:1"]
    assert snapshot.chapter.current_scene_ref == "chapter:1:scene:2"
    assert snapshot.chapter.next_scene_index == 3


def test_story_store_schema_backfill_keeps_legacy_rows_on_first_scene() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE rp_story_sessions ("
                "session_id VARCHAR PRIMARY KEY, "
                "story_id VARCHAR, "
                "source_workspace_id VARCHAR, "
                "mode VARCHAR, "
                "session_state VARCHAR, "
                "current_chapter_index INTEGER, "
                "current_phase VARCHAR, "
                "runtime_story_config_json JSON NOT NULL, "
                "writer_contract_json JSON NOT NULL, "
                "current_state_json JSON NOT NULL, "
                "activated_at DATETIME, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE rp_chapter_workspaces ("
                "chapter_workspace_id VARCHAR PRIMARY KEY, "
                "session_id VARCHAR, "
                "chapter_index INTEGER, "
                "phase VARCHAR, "
                "chapter_goal VARCHAR, "
                "outline_draft_json JSON, "
                "accepted_outline_json JSON, "
                "builder_snapshot_json JSON NOT NULL, "
                "review_notes_json JSON NOT NULL, "
                "accepted_segment_ids_json JSON NOT NULL, "
                "pending_segment_artifact_id VARCHAR, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE rp_story_artifacts ("
                "artifact_id VARCHAR PRIMARY KEY, "
                "session_id VARCHAR, "
                "chapter_workspace_id VARCHAR, "
                "artifact_kind VARCHAR, "
                "status VARCHAR, "
                "revision INTEGER, "
                "content_text TEXT, "
                "metadata_json JSON NOT NULL, "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE rp_story_discussion_entries ("
                "entry_id VARCHAR PRIMARY KEY, "
                "session_id VARCHAR, "
                "chapter_workspace_id VARCHAR, "
                "role VARCHAR, "
                "content_text TEXT, "
                "linked_artifact_id VARCHAR, "
                "created_at DATETIME"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO rp_story_sessions VALUES ("
                "'session-1', 'story-1', 'workspace-1', 'longform', 'active', "
                "1, 'segment_drafting', '{}', '{}', '{}', "
                "'2026-01-01', '2026-01-01', '2026-01-01'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO rp_chapter_workspaces VALUES ("
                "'chapter-1', 'session-1', 1, 'segment_drafting', 'goal', "
                "NULL, NULL, '{}', '[]', '[]', NULL, "
                "'2026-01-01', '2026-01-01'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO rp_story_artifacts VALUES ("
                "'artifact-1', 'session-1', 'chapter-1', 'story_segment', 'draft', "
                "1, 'Segment text', '{}', '2026-01-01', '2026-01-01'"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO rp_story_discussion_entries VALUES ("
                "'entry-1', 'session-1', 'chapter-1', 'user', 'Hello', NULL, "
                "'2026-01-01'"
                ")"
            )
        )

    ensure_story_store_compatible_schema(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE rp_chapter_workspaces "
                "SET current_scene_ref = 'chapter:1:scene:2' "
                "WHERE chapter_workspace_id = 'chapter-1'"
            )
        )
        connection.execute(
            text(
                "UPDATE rp_story_artifacts "
                "SET scene_ref = NULL "
                "WHERE artifact_id = 'artifact-1'"
            )
        )
        connection.execute(
            text(
                "UPDATE rp_story_discussion_entries "
                "SET scene_ref = NULL "
                "WHERE entry_id = 'entry-1'"
            )
        )

    ensure_story_store_compatible_schema(engine)

    with engine.begin() as connection:
        artifact_scene_ref = connection.execute(
            text(
                "SELECT scene_ref "
                "FROM rp_story_artifacts "
                "WHERE artifact_id = 'artifact-1'"
            )
        ).scalar_one()
        discussion_scene_ref = connection.execute(
            text(
                "SELECT scene_ref "
                "FROM rp_story_discussion_entries "
                "WHERE entry_id = 'entry-1'"
            )
        ).scalar_one()

    assert artifact_scene_ref == "chapter:1:scene:1"
    assert discussion_scene_ref == "chapter:1:scene:1"


@pytest.mark.asyncio
async def test_story_turn_domain_service_complete_chapter_auto_closes_open_scene(
    retrieval_session,
):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    service.close_current_scene(session_id=session.session_id)
    turn_domain_service = _build_turn_domain_service(service)

    response = await turn_domain_service.complete_chapter(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id="model-scene-close",
        )
    )
    completed_chapter = service.get_chapter_by_index(
        session_id=session.session_id,
        chapter_index=1,
    )
    next_chapter = service.get_chapter_by_index(
        session_id=session.session_id,
        chapter_index=2,
    )
    updated_session = service.get_session(session.session_id)

    assert response.current_chapter_index == 2
    assert response.current_phase == LongformChapterPhase.OUTLINE_DRAFTING
    assert completed_chapter is not None
    assert completed_chapter.phase == LongformChapterPhase.CHAPTER_COMPLETED
    assert completed_chapter.current_scene_ref is None
    assert completed_chapter.last_closed_scene_ref == "chapter:1:scene:2"
    assert completed_chapter.closed_scene_refs == [
        "chapter:1:scene:1",
        "chapter:1:scene:2",
    ]
    assert completed_chapter.next_scene_index == 3
    assert next_chapter is not None
    assert next_chapter.current_scene_ref == "chapter:2:scene:1"
    assert next_chapter.next_scene_index == 2
    assert next_chapter.last_closed_scene_ref is None
    assert next_chapter.closed_scene_refs == []
    assert updated_session is not None
    assert updated_session.current_chapter_index == 2
    assert updated_session.current_phase == LongformChapterPhase.OUTLINE_DRAFTING
