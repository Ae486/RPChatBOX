"""Focused tests for N1 longform chapter lifecycle provider / adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
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
from rp.services.context_orchestration_service import (
    ContextOrchestrationService,
)
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.draft_selection_service import DraftSelectionService
from rp.services.longform_chapter_runtime_service import (
    LongformChapterRuntimeService,
    LongformChapterRuntimeServiceError,
)
from rp.services.projection_state_service import ProjectionStateService
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.rewrite_candidate_service import RewriteCandidateService
from rp.services.rewrite_request_builder_service import RewriteRequestBuilderService
from rp.services.story_session_service import StorySessionService
from rp.services.story_turn_domain_service import StoryTurnDomainService
from rp.services.writing_packet_builder import WritingPacketBuilder


class _NoopRegressionService:
    async def run_light_regression(
        self,
        *,
        session,
        chapter,
        accepted_artifact,
        model_id,
        provider_id,
        runtime_identity=None,
    ):
        return session, chapter

    async def run_heavy_regression(
        self,
        *,
        session,
        chapter,
        model_id,
        provider_id,
        runtime_identity=None,
    ):
        return session, chapter


def test_prepare_chapter_transition_promotes_adopted_candidate_and_records_bridge(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Original pending draft.",
        metadata=_artifact_runtime_metadata(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-write",
            runtime_profile_snapshot_id="snapshot-write",
        ),
    )
    stale = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Stale alternate pending draft.",
        metadata=_artifact_runtime_metadata(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-write-alt",
            runtime_profile_snapshot_id="snapshot-write",
        ),
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )

    review_identity = _identity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        turn_id="turn-review",
        runtime_profile_snapshot_id="snapshot-review",
    )
    candidate = _create_adopted_candidate(
        retrieval_session,
        identity=review_identity,
        draft_ref=f"artifact:{pending.artifact_id}",
        output_text="Adopted rewritten chapter ending.",
    )

    service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )
    completion_identity = _identity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        turn_id="turn-complete",
        runtime_profile_snapshot_id="snapshot-complete",
    )

    prepared = service.prepare_chapter_transition(
        identity=completion_identity,
        session=session,
        chapter=chapter,
    )

    updated_pending = story_session_service.get_artifact(pending.artifact_id)
    updated_stale = story_session_service.get_artifact(stale.artifact_id)
    assert updated_pending is not None
    assert updated_pending.status == StoryArtifactStatus.ACCEPTED
    assert updated_pending.content_text == "Adopted rewritten chapter ending."
    assert updated_stale is not None
    assert updated_stale.status == StoryArtifactStatus.SUPERSEDED
    assert prepared.chapter.pending_segment_artifact_id is None
    assert pending.artifact_id in prepared.chapter.accepted_segment_ids
    assert prepared.receipt is not None
    assert prepared.receipt.adopted_output_ref == candidate.candidate_output_ref
    assert prepared.receipt.metadata_json["bridge_source"] == "draft_adoption_receipt"

    bridge = service.get_latest_bridge_material_for_branch(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        source_chapter_index=1,
    )
    assert bridge is not None
    assert bridge.adopted_output_ref == candidate.candidate_output_ref
    assert bridge.accepted_outline_ref == "outline-accepted"
    assert bridge.chapter_goal_ref == f"chapter_goal:{chapter.chapter_workspace_id}"
    assert bridge.summary_text == "Adopted rewritten chapter ending."
    assert service.get_latest_bridge_material_for_branch(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-other",
        source_chapter_index=1,
    ) is None


def test_prepare_chapter_transition_blocks_unadopted_pending_draft(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Pending draft without adoption.",
        metadata=_artifact_runtime_metadata(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-write",
            runtime_profile_snapshot_id="snapshot-write",
        ),
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )

    with pytest.raises(LongformChapterRuntimeServiceError) as exc:
        service.prepare_chapter_transition(
            identity=_identity(
                story_id=session.story_id,
                session_id=session.session_id,
                branch_head_id="branch-main",
                turn_id="turn-complete",
                runtime_profile_snapshot_id="snapshot-complete",
            ),
            session=session,
            chapter=chapter,
        )

    assert exc.value.code == "longform_chapter_adoption_required"


def test_prepare_chapter_transition_uses_accepted_segment_adapter_without_pending_draft(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Already accepted segment.",
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_segment_ids=[accepted.artifact_id],
    )
    service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )

    prepared = service.prepare_chapter_transition(
        identity=_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-complete",
            runtime_profile_snapshot_id="snapshot-complete",
        ),
        session=session,
        chapter=chapter,
    )

    assert prepared.receipt is not None
    assert prepared.receipt.adopted_output_ref == accepted.artifact_id
    assert prepared.receipt.metadata_json["bridge_source"] == "accepted_segment_adapter"


def test_context_orchestration_injects_branch_scoped_chapter_bridge_into_next_writer_packet(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted chapter ending for bridge injection.",
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_segment_ids=[accepted.artifact_id],
    )
    chapter_runtime_service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )
    chapter_runtime_service.prepare_chapter_transition(
        identity=_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-complete",
            runtime_profile_snapshot_id="snapshot-complete",
        ),
        session=session,
        chapter=chapter,
    )
    next_chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Open chapter two with consequences.",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": [],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    story_session_service.update_session(
        session_id=session.session_id,
        current_chapter_index=2,
        current_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    story_session_service.commit()
    orchestration = _build_context_orchestration_service(
        story_session_service,
        retrieval_session,
        chapter_runtime_service=chapter_runtime_service,
    )

    packet = orchestration.build_writing_packet(
        session=session,
        chapter=next_chapter,
        plan=_segment_plan(),
        specialist_bundle=_specialist_bundle(),
        runtime_identity=_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-next-write",
            runtime_profile_snapshot_id="snapshot-next-write",
        ),
    )

    assert [section.label for section in packet.mode_sidecar_sections] == [
        "chapter_bridge_material",
        "writer_hints",
    ]
    bridge_section = packet.mode_sidecar_sections[0]
    assert bridge_section.items[0] == (
        "Prior chapter bridge summary: Accepted chapter ending for bridge injection."
    )
    assert bridge_section.metadata_json["section_family"] == "mode_sidecar"
    assert bridge_section.items[1] == (
        "Current chapter goal: Close the bell-tower debt cleanly."
    )
    assert bridge_section.items[2] == "Accepted outline ref: outline-accepted"
    assert packet.metadata["chapter_bridge_material_ref"].startswith("chapter-bridge:")


def test_context_orchestration_does_not_leak_other_branch_chapter_bridge(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Main branch accepted segment.",
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_segment_ids=[accepted.artifact_id],
    )
    chapter_runtime_service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )
    chapter_runtime_service.prepare_chapter_transition(
        identity=_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-complete-main",
            runtime_profile_snapshot_id="snapshot-main",
        ),
        session=session,
        chapter=chapter,
    )
    next_chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": [],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    orchestration = _build_context_orchestration_service(
        story_session_service,
        retrieval_session,
        chapter_runtime_service=chapter_runtime_service,
    )

    packet = orchestration.build_writing_packet(
        session=session,
        chapter=next_chapter,
        plan=_segment_plan(),
        specialist_bundle=_specialist_bundle(),
        runtime_identity=_identity(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-other",
            turn_id="turn-next-write-other",
            runtime_profile_snapshot_id="snapshot-other",
        ),
    )

    assert [section.label for section in packet.mode_sidecar_sections] == [
        "writer_hints"
    ]
    assert "chapter_bridge_material_ref" not in packet.metadata


@pytest.mark.asyncio
async def test_story_turn_domain_service_complete_chapter_rejects_unadopted_pending_draft(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Still pending.",
        metadata=_artifact_runtime_metadata(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id="branch-main",
            turn_id="turn-write",
            runtime_profile_snapshot_id="snapshot-write",
        ),
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    with pytest.raises(LongformChapterRuntimeServiceError) as exc:
        await turn_domain_service.complete_chapter(
            request=LongformTurnRequest(
                session_id=session.session_id,
                command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
                model_id="model-longform-chapter",
            ),
            runtime_identity=_identity(
                story_id=session.story_id,
                session_id=session.session_id,
                branch_head_id="branch-main",
                turn_id="turn-complete",
                runtime_profile_snapshot_id="snapshot-complete",
            ),
        )

    assert exc.value.code == "longform_chapter_adoption_required"


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-longform-chapter",
        source_workspace_id="workspace-longform-chapter",
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
        chapter_goal="Close the bell-tower debt cleanly.",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return service, session, chapter


def _accept_outline(
    service: StorySessionService,
    session,
    chapter,
) -> None:
    outline = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Outline accepted.",
    )
    service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_outline_json={
            "artifact_id": "outline-accepted",
            "content_text": outline.content_text,
            "metadata": outline.metadata,
        },
    )
    service.commit()


def _create_adopted_candidate(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    output_text: str,
):
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref=draft_ref,
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Rewrite this ending decisively.",
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(identity=identity, output_text=output_text),
    )
    DraftSelectionService(session=retrieval_session).adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=draft.draft_ref,
    )
    return candidate


def _record_draft(
    service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
):
    draft = DraftMaterializationService().materialize_draft(
        identity=identity,
        draft_ref=draft_ref,
        source_output_ref=draft_ref.replace("artifact:", ""),
        output_text=(
            "The storm arrived at dusk.\n\n"
            "Mira reached the bell tower.\n\n"
            "The debt was still unpaid."
        ),
        source_format="markdown",
    )
    return service.record_draft_document(identity=identity, draft_document=draft)


def _writer_result(
    *,
    identity: MemoryRuntimeIdentity,
    output_text: str,
):
    from rp.models.writing_worker_contracts import WritingWorkerExecutionResult

    return WritingWorkerExecutionResult(
        request_id=f"writer-request:{identity.turn_id}",
        packet_id=f"packet:{identity.turn_id}",
        turn_id=identity.turn_id,
        operation_mode="rewrite",
        output_text=output_text,
        output_kind="story_segment",
        result_status="completed",
    )


def _build_turn_domain_service(
    service: StorySessionService,
    retrieval_session,
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
        longform_chapter_runtime_service=LongformChapterRuntimeService(
            story_session_service=service,
            session=retrieval_session,
        ),
    )


def _build_context_orchestration_service(
    service: StorySessionService,
    retrieval_session,
    *,
    chapter_runtime_service: LongformChapterRuntimeService,
):
    projection_state_service = ProjectionStateService(
        story_session_service=service,
        adapter=ChapterWorkspaceProjectionAdapter(service),
    )
    return ContextOrchestrationService(
        story_session_service=service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        writing_packet_builder=WritingPacketBuilder(),
        longform_chapter_runtime_service=chapter_runtime_service,
    )


def _segment_plan():
    from rp.models.story_runtime import OrchestratorPlan

    return OrchestratorPlan(
        output_kind=StoryArtifactKind.STORY_SEGMENT,
        writer_instruction="Write the next segment.",
    )


def _specialist_bundle():
    from rp.models.story_runtime import SpecialistResultBundle

    return SpecialistResultBundle(writer_hints=["Runtime Hint"])


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-longform-chapter"),
        session_id=overrides.get("session_id", "session-longform-chapter"),
        branch_head_id=overrides.get("branch_head_id", "branch-main"),
        turn_id=overrides.get("turn_id", "turn-longform-chapter"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-longform-chapter",
        ),
    )


def _artifact_runtime_metadata(
    *,
    story_id: str,
    session_id: str,
    branch_head_id: str,
    turn_id: str,
    runtime_profile_snapshot_id: str,
) -> dict[str, str]:
    return {
        "runtime_story_id": story_id,
        "runtime_session_id": session_id,
        "runtime_branch_head_id": branch_head_id,
        "runtime_turn_id": turn_id,
        "runtime_profile_snapshot_id": runtime_profile_snapshot_id,
    }
