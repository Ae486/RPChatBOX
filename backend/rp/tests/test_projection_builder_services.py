"""Tests for Phase E3 settled projection refresh and builder context flow."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactStatus,
    StoryArtifactKind,
)
from rp.services.authoritative_state_view_service import AuthoritativeStateViewService
from rp.services.builder_projection_context_service import BuilderProjectionContextService
from rp.services.chapter_workspace_projection_adapter import ChapterWorkspaceProjectionAdapter
from rp.services.longform_orchestrator_service import LongformOrchestratorService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.projection_refresh_service import ProjectionRefreshService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_turn_domain_service import StoryTurnDomainService
from rp.services.writing_packet_builder import WritingPacketBuilder


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
        mode="longform",
        runtime_story_config={},
        writer_contract={"style_rules": ["Lean"]},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {"current_phase": "outline_drafting", "accepted_segments": 0},
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
            "writer_hints": ["Persisted Hint"],
        },
    )
    service.commit()
    return service.get_session(session.session_id), service.get_chapter_by_index(
        session_id=session.session_id,
        chapter_index=1,
    ), service


def _build_boundary_services(service: StorySessionService) -> tuple[
    AuthoritativeStateViewService,
    ProjectionStateService,
]:
    authoritative_state_view_service = AuthoritativeStateViewService(
        adapter=StorySessionCoreStateAdapter(service)
    )
    projection_state_service = ProjectionStateService(
        story_session_service=service,
        adapter=ChapterWorkspaceProjectionAdapter(service),
    )
    return authoritative_state_view_service, projection_state_service


class _NoopRegressionService:
    async def run_light_regression(self, *, session, chapter, accepted_artifact, model_id, provider_id):
        return session, chapter

    async def run_heavy_regression(self, *, session, chapter, model_id, provider_id):
        return session, chapter


def _build_turn_domain_service(service: StorySessionService) -> StoryTurnDomainService:
    authoritative_state_view_service, projection_state_service = _build_boundary_services(service)
    return StoryTurnDomainService(
        story_session_service=service,
        orchestrator_service=SimpleNamespace(),
        specialist_service=SimpleNamespace(),
        builder_projection_context_service=BuilderProjectionContextService(projection_state_service),
        projection_state_service=projection_state_service,
        writing_packet_builder=WritingPacketBuilder(),
        writing_worker_execution_service=SimpleNamespace(),
        regression_service=_NoopRegressionService(),
    )


def test_authoritative_state_view_service_reads_session_scoped_objects(retrieval_session):
    session, _, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, _ = _build_boundary_services(service)

    chapter_digest = authoritative_state_view_service.get_chapter_digest(
        session_id=session.session_id
    )
    narrative_progress = authoritative_state_view_service.get_narrative_progress(
        session_id=session.session_id
    )

    assert chapter_digest == {"current_chapter": 1, "title": "Chapter One"}
    assert narrative_progress["current_phase"] == LongformChapterPhase.OUTLINE_DRAFTING.value


def test_projection_state_service_updates_slots_and_rollover(retrieval_session):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)

    projection_state_service.set_current_outline(
        chapter_workspace_id=chapter.chapter_workspace_id,
        outline_text="Fresh Outline",
    )
    projection_state_service.append_recent_segment(
        chapter_workspace_id=chapter.chapter_workspace_id,
        excerpt="Segment B",
    )
    next_chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Chapter 2",
    )
    projection_state_service.seed_next_chapter(
        previous_chapter_workspace_id=chapter.chapter_workspace_id,
        next_chapter_workspace_id=next_chapter.chapter_workspace_id,
        next_chapter_index=2,
    )

    updated_chapter = service.get_chapter_workspace(chapter.chapter_workspace_id)
    seeded_chapter = service.get_chapter_workspace(next_chapter.chapter_workspace_id)

    assert updated_chapter is not None
    assert seeded_chapter is not None
    assert updated_chapter.builder_snapshot_json["current_outline_digest"] == ["Fresh Outline"]
    assert updated_chapter.builder_snapshot_json["recent_segment_digest"] == [
        "Segment A",
        "Segment B",
    ]
    assert seeded_chapter.builder_snapshot_json["blueprint_digest"] == ["Blueprint A"]
    assert seeded_chapter.builder_snapshot_json["current_outline_digest"] == []
    assert seeded_chapter.builder_snapshot_json["recent_segment_digest"] == []
    assert seeded_chapter.builder_snapshot_json["chapter_index"] == 2


def test_builder_projection_context_service_ignores_writer_hints(retrieval_session):
    session, _, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)
    context_service = BuilderProjectionContextService(projection_state_service)

    context_sections = context_service.build_context_sections(session_id=session.session_id)

    assert [section["label"] for section in context_sections] == [
        "foundation_digest",
        "blueprint_digest",
        "current_outline_digest",
        "recent_segment_digest",
        "current_state_digest",
    ]


def test_writing_packet_builder_uses_projection_sections_and_runtime_hints(retrieval_session):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    _, projection_state_service = _build_boundary_services(service)
    context_service = BuilderProjectionContextService(projection_state_service)
    builder = WritingPacketBuilder()

    packet = builder.build(
        session=session,
        chapter=chapter,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        ),
        projection_context_sections=context_service.build_context_sections(session_id=session.session_id),
        runtime_writer_hints=["Runtime Hint"],
        user_instruction="Write the next segment.",
    )

    assert [section["label"] for section in packet.context_sections] == [
        "foundation_digest",
        "blueprint_digest",
        "current_outline_digest",
        "recent_segment_digest",
        "current_state_digest",
        "writer_hints",
    ]
    assert packet.context_sections[-1]["items"] == ["Runtime Hint"]


def test_projection_refresh_service_updates_settled_slots_only(retrieval_session):
    _, chapter, service = _seed_story_runtime(retrieval_session)
    refresh_service = ProjectionRefreshService(service)

    updated_chapter = refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
    )

    assert updated_chapter.builder_snapshot_json["foundation_digest"] == ["New Found"]
    assert "writer_hints" not in updated_chapter.builder_snapshot_json


def test_orchestrator_fallback_uses_projection_slots_not_writer_hints(retrieval_session):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    authoritative_state_view_service, projection_state_service = _build_boundary_services(service)
    orchestrator_service = LongformOrchestratorService(
        authoritative_state_view_service=authoritative_state_view_service,
        projection_state_service=projection_state_service,
    )
    plan = orchestrator_service._fallback_plan(
        session=session,
        chapter=chapter,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        user_prompt=None,
        projection_snapshot=projection_state_service.build_planner_projection(
            session_id=session.session_id
        ),
    )

    assert "Persisted Hint" not in " ".join(plan.archival_queries)
    assert any("Outline A" in query for query in plan.archival_queries)


def test_story_turn_accept_outline_updates_projection_via_boundary_service(retrieval_session):
    session, chapter, service = _seed_story_runtime(retrieval_session)
    turn_domain_service = _build_turn_domain_service(service)
    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Accepted Outline Text",
    )

    response = turn_domain_service.accept_outline(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE,
            model_id="model",
            target_artifact_id=outline.artifact_id,
        )
    )
    updated_chapter = service.get_current_chapter(session.session_id)

    assert updated_chapter is not None
    assert updated_chapter.builder_snapshot_json["current_outline_digest"] == [
        "Accepted Outline Text"
    ]
    assert response.current_phase == LongformChapterPhase.SEGMENT_DRAFTING
