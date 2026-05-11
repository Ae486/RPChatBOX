"""Focused tests for N1 longform chapter lifecycle provider / adapter."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_identity import StoryTurnStatus
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
from rp.services.chapter_bridge_provider import ChapterBridgeProvider
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
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
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


class _RecordingChapterBridgeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_bridge_material(self, **kwargs):
        from rp.services.chapter_bridge_provider import ChapterBridgeProvider

        self.calls.append({"mode": "sync", **kwargs})
        return ChapterBridgeProvider().build_bridge_material(**kwargs)

    async def build_bridge_material_with_summary(self, **kwargs):
        from rp.services.chapter_bridge_provider import ChapterBridgeProvider

        self.calls.append({"mode": "async", **kwargs})
        bridge = ChapterBridgeProvider().build_bridge_material(
            identity=kwargs["identity"],
            from_chapter_index=kwargs["from_chapter_index"],
            to_chapter_index=kwargs["to_chapter_index"],
            adopted_output_ref=kwargs.get("adopted_output_ref"),
            accepted_outline_ref=kwargs.get("accepted_outline_ref"),
            chapter_goal_ref=kwargs.get("chapter_goal_ref"),
            adopted_output_text=(
                "\n\n".join(list(kwargs.get("accepted_segment_texts") or []))
            ),
            source_refs=list(kwargs.get("source_refs") or []),
            covered_beat_ids=list(kwargs.get("covered_beat_ids") or []),
            metadata_json=dict(kwargs.get("metadata_json") or {}),
        )
        return bridge.model_copy(
            update={
                "summary_text": "Stub chapter summary for next chapter.",
                "metadata_json": {
                    **dict(bridge.metadata_json),
                    "summary_provider": "recording_stub",
                },
            }
        )


class _RecordingSummaryGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def complete_text_with_usage(self, **kwargs):
        self.calls.append(kwargs)
        return (
            '{"summary_text":"LLM bridge summary.",'
            '"continuity_notes":["Carry the debt consequence forward."],'
            '"open_threads":["The ledger remains unsettled."]}',
            {"prompt_tokens": 11, "completion_tokens": 13, "total_tokens": 24},
        )


def test_accept_outline_normalizes_structured_outline_and_initializes_progress(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    outline = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="1. Opening conflict\n2. Decision point",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    identity = _identity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch-main",
        turn_id="turn-accept-outline",
        runtime_profile_snapshot_id="snapshot-outline",
    )

    response = turn_domain_service.accept_outline(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_OUTLINE,
            model_id="test-model",
            provider_id="test-provider",
            target_artifact_id=outline.artifact_id,
        ),
        runtime_identity=identity,
    )

    updated_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    assert updated_chapter is not None
    structured_outline = updated_chapter.accepted_outline_json["structured_outline"]
    assert structured_outline["schema_version"] == "longform_outline_v1"
    assert structured_outline["beats"][0]["beat_id"] == "beat_001"
    assert structured_outline["beats"][1]["beat_id"] == "beat_002"
    assert response.warnings == ["outline_normalized_from_non_json_output"]
    progress_service = turn_domain_service._longform_chapter_runtime_service
    assert progress_service is not None
    progress_record = progress_service.get_latest_outline_progress_for_chapter(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id=identity.branch_head_id,
        chapter_index=chapter.chapter_index,
        identity=identity,
    )
    assert progress_record is not None
    _, progress = progress_record
    assert progress.current_beat_id == "beat_001"
    assert progress.covered_beat_ids == []


def test_prepare_chapter_transition_promotes_adopted_candidate_and_records_bridge(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    pending_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.transition.pending",
        actor="longform.transition.pending",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Original pending draft.",
        metadata=_artifact_runtime_metadata(
            story_id=pending_identity.story_id,
            session_id=pending_identity.session_id,
            branch_head_id=pending_identity.branch_head_id,
            turn_id=pending_identity.turn_id,
            runtime_profile_snapshot_id=pending_identity.runtime_profile_snapshot_id,
        ),
    )
    identity_service.update_turn_status(
        turn_id=pending_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    stale_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.transition.stale",
        actor="longform.transition.stale",
    )
    stale = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Stale alternate pending draft.",
        metadata=_artifact_runtime_metadata(
            story_id=stale_identity.story_id,
            session_id=stale_identity.session_id,
            branch_head_id=stale_identity.branch_head_id,
            turn_id=stale_identity.turn_id,
            runtime_profile_snapshot_id=stale_identity.runtime_profile_snapshot_id,
        ),
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )

    review_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        created_from="longform.transition.review",
        actor="longform.transition.review",
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
    completion_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        created_from="longform.transition.complete",
        actor="longform.transition.complete",
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
        branch_head_id=completion_identity.branch_head_id,
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
    pending_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.transition.unadopted_pending",
        actor="longform.transition.unadopted_pending",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Pending draft without adoption.",
        metadata=_artifact_runtime_metadata(
            story_id=pending_identity.story_id,
            session_id=pending_identity.session_id,
            branch_head_id=pending_identity.branch_head_id,
            turn_id=pending_identity.turn_id,
            runtime_profile_snapshot_id=pending_identity.runtime_profile_snapshot_id,
        ),
    )
    identity_service.update_turn_status(
        turn_id=pending_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
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
    accepted_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.transition.adapter.accepted",
        actor="longform.transition.adapter.accepted",
    )
    accepted = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_identity,
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

    completion_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        created_from="longform.transition.adapter.complete",
        actor="longform.transition.adapter.complete",
    )
    prepared = service.prepare_chapter_transition(
        identity=completion_identity,
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
    accepted_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.bridge.accepted",
        actor="longform.bridge.accepted",
    )
    accepted = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_identity,
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
    completion_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        created_from="longform.bridge.complete",
        actor="longform.bridge.complete",
    )
    chapter_runtime_service.prepare_chapter_transition(
        identity=completion_identity,
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
            branch_head_id=completion_identity.branch_head_id,
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


def test_chapter_transition_ignores_rollback_hidden_pending_pointer_and_adoption(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    target_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.transition.rollback_target",
        actor="longform.transition.rollback_target",
    )
    target = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=target_identity,
        content_text="Visible rollback target segment.",
        target_beat_id="beat_001",
    )
    hidden_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.transition.hidden_pending",
        actor="longform.transition.hidden_pending",
    )
    hidden_pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Rollback-hidden pending must not be adopted.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=hidden_identity.story_id,
                session_id=hidden_identity.session_id,
                branch_head_id=hidden_identity.branch_head_id,
                turn_id=hidden_identity.turn_id,
                runtime_profile_snapshot_id=hidden_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_002",
        },
    )
    identity_service.update_turn_status(
        turn_id=hidden_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
        visible_output_ref=hidden_pending.artifact_id,
        selected_output_ref=hidden_pending.artifact_id,
    )
    raw_chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=hidden_pending.artifact_id,
    )
    review_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        created_from="longform.transition.hidden_review",
        actor="longform.transition.hidden_review",
    )
    hidden_candidate = _create_adopted_candidate(
        retrieval_session,
        identity=review_identity,
        draft_ref=f"artifact:{hidden_pending.artifact_id}",
        output_text="Hidden adoption must not be used.",
    )
    identity_service.rollback_to_turn(
        session_id=session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
    )
    completion_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        created_from="longform.transition.hidden_complete",
        actor="longform.transition.hidden_complete",
    )
    service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    )

    prepared = service.prepare_chapter_transition(
        identity=completion_identity,
        session=session,
        chapter=raw_chapter,
    )

    hidden_after = story_session_service.get_artifact(hidden_pending.artifact_id)
    assert prepared.receipt is not None
    assert prepared.receipt.metadata_json["bridge_source"] == "accepted_segment_adapter"
    assert prepared.receipt.adopted_output_ref == target.artifact_id
    assert prepared.receipt.adopted_output_ref != hidden_candidate.candidate_output_ref
    assert prepared.chapter.pending_segment_artifact_id is None
    assert hidden_after is not None
    assert hidden_after.status == StoryArtifactStatus.DRAFT


@pytest.mark.asyncio
async def test_complete_chapter_ignores_rollback_hidden_pending_pointer(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    target_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.complete.rollback_target",
        actor="longform.complete.rollback_target",
    )
    _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=target_identity,
        content_text="Visible segment before completing chapter.",
        target_beat_id="beat_001",
    )
    hidden_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.complete.hidden_pending",
        actor="longform.complete.hidden_pending",
    )
    hidden_pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Hidden pending should not block complete chapter.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=hidden_identity.story_id,
                session_id=hidden_identity.session_id,
                branch_head_id=hidden_identity.branch_head_id,
                turn_id=hidden_identity.turn_id,
                runtime_profile_snapshot_id=hidden_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_002",
        },
    )
    identity_service.update_turn_status(
        turn_id=hidden_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
        visible_output_ref=hidden_pending.artifact_id,
        selected_output_ref=hidden_pending.artifact_id,
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=hidden_pending.artifact_id,
    )
    identity_service.rollback_to_turn(
        session_id=session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
    )
    complete_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        created_from="longform.complete.after_rollback",
        actor="longform.complete.after_rollback",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    turn_domain_service._longform_chapter_runtime_service = (  # noqa: SLF001
        LongformChapterRuntimeService(
            story_session_service=story_session_service,
            chapter_bridge_provider=cast(
                ChapterBridgeProvider,
                _RecordingChapterBridgeProvider(),
            ),
            session=retrieval_session,
        )
    )

    response = await turn_domain_service.complete_chapter(
        request=LongformTurnRequest(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id="model-longform-chapter",
        ),
        runtime_identity=complete_identity,
    )

    hidden_after = story_session_service.get_artifact(hidden_pending.artifact_id)
    assert response.current_chapter_index == 2
    assert hidden_after is not None
    assert hidden_after.status == StoryArtifactStatus.DRAFT


@pytest.mark.asyncio
async def test_story_turn_domain_service_complete_chapter_rejects_unadopted_pending_draft(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    pending_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.complete.unadopted_pending",
        actor="longform.complete.unadopted_pending",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Still pending.",
        metadata=_artifact_runtime_metadata(
            story_id=pending_identity.story_id,
            session_id=pending_identity.session_id,
            branch_head_id=pending_identity.branch_head_id,
            turn_id=pending_identity.turn_id,
            runtime_profile_snapshot_id=pending_identity.runtime_profile_snapshot_id,
        ),
    )
    identity_service.update_turn_status(
        turn_id=pending_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
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


@pytest.mark.asyncio
async def test_prepare_chapter_transition_with_summary_provider_receives_adopted_segments_and_covered_beats(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted_one_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.summary.accepted_one",
        actor="longform.summary.accepted_one",
    )
    accepted_one = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_one_identity,
        content_text="Beat one accepted.",
        target_beat_id="beat_001",
    )
    accepted_two_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="longform.summary.accepted_two",
        actor="longform.summary.accepted_two",
    )
    accepted_two = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_two_identity,
        content_text="Beat two accepted.",
        target_beat_id="beat_002",
    )
    chapter = story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_segment_ids=[accepted_one.artifact_id, accepted_two.artifact_id],
    )
    provider = _RecordingChapterBridgeProvider()
    service = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        chapter_bridge_provider=cast(ChapterBridgeProvider, provider),
        session=retrieval_session,
    )
    completion_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        created_from="longform.summary.complete",
        actor="longform.summary.complete",
    )
    prepared = await service.prepare_chapter_transition_with_summary(
        identity=completion_identity,
        session=session,
        chapter=chapter,
        model_id="summary-model",
        provider_id="summary-provider",
    )

    assert prepared.bridge is not None
    assert prepared.bridge.summary_text == "Stub chapter summary for next chapter."
    assert prepared.bridge.covered_beat_ids == ["beat_001", "beat_002"]
    assert prepared.bridge.metadata_json["summary_provider"] == "recording_stub"
    assert provider.calls
    call = provider.calls[-1]
    assert call["accepted_segment_texts"] == ["Beat one accepted.", "Beat two accepted."]
    assert call["covered_beat_ids"] == ["beat_001", "beat_002"]


@pytest.mark.asyncio
async def test_chapter_bridge_provider_uses_model_summary_when_provider_id_is_omitted():
    gateway = _RecordingSummaryGateway()
    provider = ChapterBridgeProvider(llm_gateway=gateway)

    bridge = await provider.build_bridge_material_with_summary(
        identity=_identity(),
        from_chapter_index=1,
        to_chapter_index=2,
        adopted_output_ref="artifact:accepted-final",
        accepted_outline_ref="outline-accepted",
        chapter_goal_ref="chapter-goal:1",
        chapter_goal="Carry the chapter consequence forward.",
        adopted_output_text="Fallback accepted chapter ending.",
        accepted_segment_texts=["Accepted chapter ending."],
        covered_beat_ids=["beat_001"],
        covered_beats=[
            {
                "beat_id": "beat_001",
                "title": "Opening debt",
                "goal": "Establish the debt consequence.",
            }
        ],
        source_refs=["artifact:accepted-final"],
        model_id="model-story",
        provider_id=None,
    )

    assert len(gateway.calls) == 1
    assert gateway.calls[0]["model_id"] == "model-story"
    assert gateway.calls[0]["provider_id"] is None
    assert bridge.summary_text == "LLM bridge summary."
    assert bridge.covered_beat_ids == ["beat_001"]
    assert bridge.continuity_notes == ["Carry the debt consequence forward."]
    assert bridge.open_threads == ["The ledger remains unsettled."]
    assert bridge.metadata_json["summary_provider"] == "story_llm_gateway"
    assert bridge.metadata_json["summary_generation_mode"] == "async_llm"
    assert bridge.metadata_json["summary_model_id"] == "model-story"
    assert bridge.metadata_json["summary_provider_id"] is None


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


def _resolve_runtime_identity(
    retrieval_session,
    *,
    session_id: str,
    command_kind: LongformTurnCommandKind,
    created_from: str,
    actor: str,
) -> tuple[MemoryRuntimeIdentity, StoryRuntimeIdentityService]:
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session_id,
        created_from=created_from,
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind=command_kind.value,
        actor=actor,
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    return identity, identity_service


def _create_settled_story_segment(
    service: StorySessionService,
    identity_service: StoryRuntimeIdentityService,
    *,
    session,
    chapter,
    identity: MemoryRuntimeIdentity,
    content_text: str,
    target_beat_id: str | None = None,
):
    metadata = _artifact_runtime_metadata(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
        turn_id=identity.turn_id,
        runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
    )
    if target_beat_id is not None:
        metadata["target_beat_id"] = target_beat_id
    segment = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=content_text,
        metadata=metadata,
    )
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=segment.artifact_id,
        selected_output_ref=segment.artifact_id,
        settlement_reason="test_settled_story_segment",
    )
    return segment


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
            "metadata": {
                **outline.metadata,
                "structured_outline": {
                    "schema_version": "longform_outline_v1",
                    "chapter_index": chapter.chapter_index,
                    "chapter_goal": chapter.chapter_goal,
                    "beats": [
                        {
                            "beat_id": "beat_001",
                            "order": 1,
                            "title": "Opening conflict",
                            "goal": "Set the debt conflict in motion.",
                            "must_include": ["bell tower", "debt"],
                            "avoid": ["future spoiler"],
                            "continuity_notes": ["Starts the chapter."],
                        },
                        {
                            "beat_id": "beat_002",
                            "order": 2,
                            "title": "Decision point",
                            "goal": "Force Mira to choose what to pay.",
                            "must_include": ["choice"],
                            "avoid": [],
                            "continuity_notes": ["Continue from beat one."],
                        },
                    ],
                    "constraints": {},
                },
            },
            "structured_outline": {
                "schema_version": "longform_outline_v1",
                "chapter_index": chapter.chapter_index,
                "chapter_goal": chapter.chapter_goal,
                "beats": [
                    {
                        "beat_id": "beat_001",
                        "order": 1,
                        "title": "Opening conflict",
                        "goal": "Set the debt conflict in motion.",
                        "must_include": ["bell tower", "debt"],
                        "avoid": ["future spoiler"],
                        "continuity_notes": ["Starts the chapter."],
                    },
                    {
                        "beat_id": "beat_002",
                        "order": 2,
                        "title": "Decision point",
                        "goal": "Force Mira to choose what to pay.",
                        "must_include": ["choice"],
                        "avoid": [],
                        "continuity_notes": ["Continue from beat one."],
                    },
                ],
                "constraints": {},
            },
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
        writing_worker_execution_service=cast(Any, SimpleNamespace()),
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
