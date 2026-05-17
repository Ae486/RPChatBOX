"""Focused S1 backend tests for rewrite constraints and continuation packet wiring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel import select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from rp.graphs.story_graph_nodes import StoryGraphNodes
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_identity import StoryTurnStatus
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.longform_chapter_runtime_service import LongformChapterRuntimeService
from rp.services.longform_chapter_runtime_service import LongformChapterRuntimeServiceError
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.rewrite_request_builder_service import (
    RewriteRequestBuilderServiceError,
)
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.writing_worker_execution_service import (
    WritingWorkerExecutionService,
)
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
from rp.tests.test_longform_chapter_runtime_service import (
    _accept_outline,
    _artifact_runtime_metadata,
    _build_turn_domain_service,
    _seed_story_runtime,
)


def _create_settled_story_segment(
    story_session_service,
    identity_service: StoryRuntimeIdentityService,
    *,
    session,
    chapter,
    identity: MemoryRuntimeIdentity,
    content_text: str,
    target_beat_id: str,
):
    segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=content_text,
        metadata={
            **_artifact_runtime_metadata(
                story_id=identity.story_id,
                session_id=identity.session_id,
                branch_head_id=identity.branch_head_id,
                turn_id=identity.turn_id,
                runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": target_beat_id,
        },
    )
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=segment.artifact_id,
        selected_output_ref=segment.artifact_id,
        settlement_reason=f"test_settled_segment:{target_beat_id}",
    )
    return segment


class _RecordingStoryLlmGateway:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.calls: list[dict[str, Any]] = []

    async def complete_text_with_usage(self, **kwargs):
        self.calls.append(kwargs)
        return self._response_text, {
            "prompt_tokens": 17,
            "completion_tokens": 23,
            "total_tokens": 40,
        }

    def supports_tools(self, **_kwargs) -> bool:
        return False


@pytest.mark.asyncio
async def test_rewrite_pending_segment_real_packet_includes_review_overlay_and_prompt_constraints(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    draft_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.draft",
        actor="s1.writer_constraints.draft",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Original draft before rewrite.",
        metadata=_artifact_runtime_metadata(
            story_id=draft_identity.story_id,
            session_id=draft_identity.session_id,
            branch_head_id=draft_identity.branch_head_id,
            turn_id=draft_identity.turn_id,
            runtime_profile_snapshot_id=draft_identity.runtime_profile_snapshot_id,
        ),
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=draft_identity,
        draft_ref=f"artifact:{pending.artifact_id}",
        source_output_ref=pending.artifact_id,
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=draft_identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=draft_identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        selected_excerpt=draft.blocks[0].selected_excerpt,
        instruction_text="Make the bell-tower debt explicit before continuing.",
    )
    tracked_change = overlay_service.add_tracked_change(
        identity=draft_identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[1].block_id),
        change_kind="replace",
        original_text=draft.blocks[1].selected_excerpt,
        suggested_text="Mira turned back toward the bell tower.",
    )
    rewrite_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        created_from="s1.writer_constraints.rewrite",
        actor="s1.writer_constraints.rewrite",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Rewrite the pending segment.",
        ),
        specialist_bundle=SpecialistResultBundle(
            writer_hints=["Keep the local cause-and-effect explicit."]
        ),
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        runtime_identity=rewrite_identity,
        target_artifact_id=pending.artifact_id,
    )

    assert packet.operation_mode == "rewrite"
    assert packet.metadata["target_artifact_id"] == pending.artifact_id
    assert packet.metadata["rewrite_scope"] == "full"
    assert packet.metadata["revision_constraint_source"] == "active_review_overlay"
    assert packet.metadata["review_overlay_section_count"] == 1
    assert len(packet.review_overlay_sections) == 1
    review_section = packet.review_overlay_sections[0]
    assert review_section.label == "review_overlay"
    assert review_section.source_kind == "review_overlay_rewrite_request"
    assert review_section.metadata_json["comments"][0]["comment_id"] == comment.comment_id
    assert (
        review_section.metadata_json["tracked_changes"][0]["tracked_change_id"]
        == tracked_change.tracked_change_id
    )
    assert any(
        "Make the bell-tower debt explicit before continuing." in item
        for item in review_section.items
    )
    assert any(
        "Mira turned back toward the bell tower." in item
        for item in review_section.items
    )

    gateway = _RecordingStoryLlmGateway("Rewrite completed.")
    writer_service = WritingWorkerExecutionService(llm_gateway=gateway)
    await writer_service.execute(
        request=writer_service.build_request(
            packet=packet,
            model_id="test-model",
            provider_id="test-provider",
            request_id="writer-s1-rewrite",
        )
    )
    user_prompt = gateway.calls[0]["messages"][1].content

    assert "review_overlay:" in user_prompt
    assert "Make the bell-tower debt explicit before continuing." in user_prompt
    assert "Mira turned back toward the bell tower." in user_prompt
    assert "Apply every listed review constraint exactly." in user_prompt


def test_rewrite_pending_segment_fails_closed_when_active_constraints_exist_but_draft_sidecar_is_missing(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    draft_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.missing_draft",
        actor="s1.writer_constraints.missing_draft",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Draft whose materialized document will disappear.",
        metadata=_artifact_runtime_metadata(
            story_id=draft_identity.story_id,
            session_id=draft_identity.session_id,
            branch_head_id=draft_identity.branch_head_id,
            turn_id=draft_identity.turn_id,
            runtime_profile_snapshot_id=draft_identity.runtime_profile_snapshot_id,
        ),
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=draft_identity,
        draft_ref=f"artifact:{pending.artifact_id}",
        source_output_ref=pending.artifact_id,
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=draft_identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    overlay_service.add_comment(
        identity=draft_identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        instruction_text="This active comment must block a generic rewrite fallback.",
        selected_excerpt=draft.blocks[0].selected_excerpt,
    )
    removed = 0
    records = retrieval_session.exec(
        select(RuntimeWorkspaceMaterialRecord).where(
            RuntimeWorkspaceMaterialRecord.story_id == draft_identity.story_id,
            RuntimeWorkspaceMaterialRecord.session_id == draft_identity.session_id,
            RuntimeWorkspaceMaterialRecord.branch_head_id
            == draft_identity.branch_head_id,
            RuntimeWorkspaceMaterialRecord.turn_id == draft_identity.turn_id,
            RuntimeWorkspaceMaterialRecord.runtime_profile_snapshot_id
            == draft_identity.runtime_profile_snapshot_id,
        )
    ).all()
    for record in records:
        payload = record.payload_json
        record_body = payload.get("record")
        if (
            payload.get("payload_kind") == "draft_document"
            and isinstance(record_body, dict)
            and record_body.get("draft_ref") == draft.draft_ref
        ):
            retrieval_session.delete(record)
            removed += 1
    retrieval_session.commit()
    assert removed == 1

    rewrite_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        created_from="s1.writer_constraints.rewrite_fail_closed",
        actor="s1.writer_constraints.rewrite_fail_closed",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    with pytest.raises(RewriteRequestBuilderServiceError) as exc_info:
        turn_domain_service.build_packet(
            session_id=session.session_id,
            plan=OrchestratorPlan(
                output_kind=StoryArtifactKind.STORY_SEGMENT,
                writer_instruction="Rewrite the pending segment.",
            ),
            specialist_bundle=SpecialistResultBundle(writer_hints=["Do not drift."]),
            command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
            runtime_identity=rewrite_identity,
            target_artifact_id=pending.artifact_id,
        )

    assert exc_info.value.code == "revision_draft_not_visible"


@pytest.mark.asyncio
async def test_write_next_segment_real_packet_exposes_chapter_progress_and_prompt_continuity(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.accepted_prior",
        actor="s1.writer_constraints.accepted_prior",
    )
    accepted = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_identity,
        content_text="Accepted prior segment: Mira finally paid the bell-tower debt.",
        target_beat_id="beat_001",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[accepted.artifact_id],
    )
    runtime_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.write_next",
        actor="s1.writer_constraints.write_next",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write the next segment.",
        ),
        specialist_bundle=SpecialistResultBundle(writer_hints=["General hint only."]),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        runtime_identity=runtime_identity,
    )

    chapter_progress = next(
        section
        for section in packet.mode_sidecar_sections
        if section.label == "chapter_progress"
    )
    assert chapter_progress.metadata_json["section_family"] == "mode_sidecar"
    assert any("accepted_segment_count: 1" == item for item in chapter_progress.items)
    assert any("covered_beat_ids: beat_001" == item for item in chapter_progress.items)
    assert any("current_beat_id: beat_002" == item for item in chapter_progress.items)
    assert any("current_beat_order: 2" == item for item in chapter_progress.items)
    assert any("current_beat_title: Decision point" == item for item in chapter_progress.items)
    assert any(
        "current_beat_goal: Force Mira to choose what to pay." == item
        for item in chapter_progress.items
    )
    assert any(
        "latest_accepted_segment_excerpt: Accepted prior segment: Mira finally paid the bell-tower debt."
        == item
        for item in chapter_progress.items
    )
    assert any(
        "accepted_outline_ref: outline-accepted" == item
        for item in chapter_progress.items
    )
    assert any(
        "chapter_goal: Close the bell-tower debt cleanly." == item
        for item in chapter_progress.items
    )
    assert any(
        "next_required_continuity_instruction: Write one segment for the current beat only; continue after the latest accepted segment; stop before later beats."
        == item
        for item in chapter_progress.items
    )
    assert packet.mode_sidecar_sections[-1].label == "writer_hints"
    assert packet.mode_sidecar_sections[-1].items == ["General hint only."]

    gateway = _RecordingStoryLlmGateway("Continued segment.")
    writer_service = WritingWorkerExecutionService(llm_gateway=gateway)
    await writer_service.execute(
        request=writer_service.build_request(
            packet=packet,
            model_id="test-model",
            provider_id="test-provider",
            request_id="writer-s1-write-next",
        )
    )
    user_prompt = gateway.calls[0]["messages"][1].content

    assert "chapter_progress:" in user_prompt
    assert "current_beat_id: beat_002" in user_prompt
    assert "Accepted prior segment: Mira finally paid the bell-tower debt." in user_prompt
    assert (
        "Write one segment for the current beat only; continue after the latest accepted segment; stop before later beats."
        in user_prompt
    )


def test_write_next_segment_chapter_progress_uses_active_branch_visible_segments(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    target_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.rollback_target",
        actor="s1.writer_constraints.rollback_target",
    )
    hidden_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.rollback_hidden",
        actor="s1.writer_constraints.rollback_hidden",
    )
    visible_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Visible accepted segment before rollback.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=target_identity.story_id,
                session_id=target_identity.session_id,
                branch_head_id=target_identity.branch_head_id,
                turn_id=target_identity.turn_id,
                runtime_profile_snapshot_id=target_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_001",
        },
    )
    hidden_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Hidden future accepted segment after rollback.",
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
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[visible_segment.artifact_id, hidden_segment.artifact_id],
    )
    identity_service.update_turn_status(
        turn_id=target_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=visible_segment.artifact_id,
        selected_output_ref=visible_segment.artifact_id,
        settlement_reason="s1_visible_segment_binding",
    )
    identity_service.update_turn_status(
        turn_id=hidden_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=hidden_segment.artifact_id,
        selected_output_ref=hidden_segment.artifact_id,
        settlement_reason="s1_hidden_segment_binding",
    )
    identity_service.rollback_to_turn(
        session_id=session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="s1.writer_constraints.rollback",
    )
    continuation_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.writer_constraints.after_rollback",
        actor="s1.writer_constraints.after_rollback",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    generation_inputs = turn_domain_service.prepare_generation_inputs(
        session_id=session.session_id,
        user_prompt=None,
        target_artifact_id=None,
    )
    assert generation_inputs["accepted_segment_ids"] == [visible_segment.artifact_id]

    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue after rollback.",
        ),
        specialist_bundle=SpecialistResultBundle(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        runtime_identity=continuation_identity,
    )

    chapter_progress = next(
        section
        for section in packet.mode_sidecar_sections
        if section.label == "chapter_progress"
    )
    joined_items = "\n".join(chapter_progress.items)
    assert "accepted_segment_count: 1" in joined_items
    assert "covered_beat_ids: beat_001" in joined_items
    assert "current_beat_id: beat_002" in joined_items
    assert "Visible accepted segment before rollback." in joined_items
    assert "Hidden future accepted segment after rollback." not in joined_items


@pytest.mark.asyncio
async def test_branch_accept_sequence_is_isolated_per_active_branch(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    main_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.branch_accept.main_base",
        actor="s1.branch_accept.main_base",
    )
    base_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Base segment shared by both branches.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=main_identity.story_id,
                session_id=main_identity.session_id,
                branch_head_id=main_identity.branch_head_id,
                turn_id=main_identity.turn_id,
                runtime_profile_snapshot_id=main_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_001",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[base_segment.artifact_id],
    )
    identity_service.update_turn_status(
        turn_id=main_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=base_segment.artifact_id,
        selected_output_ref=base_segment.artifact_id,
        settlement_reason="s1_branch_accept_main_base",
    )
    receipt = identity_service.create_branch_from_turn(
        session_id=session.session_id,
        origin_turn_id=main_identity.turn_id,
        actor="s1.branch_accept.create_branch",
        branch_name="branch-a",
    )
    branch_a_id = str(receipt.to_branch_head_id)
    branch_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.branch_accept.branch_pending",
        actor="s1.branch_accept.branch_pending",
    )
    branch_pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Branch-only accepted segment.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=branch_identity.story_id,
                session_id=branch_identity.session_id,
                branch_head_id=branch_identity.branch_head_id,
                turn_id=branch_identity.turn_id,
                runtime_profile_snapshot_id=branch_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_002",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=branch_pending.artifact_id,
    )
    identity_service.update_turn_status(
        turn_id=branch_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    await turn_domain_service.accept_pending_segment(
        request=_request(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            target_artifact_id=branch_pending.artifact_id,
        ),
        runtime_identity=branch_identity,
    )
    branch_snapshot = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert branch_snapshot.chapter.accepted_segment_ids == [
        base_segment.artifact_id,
        branch_pending.artifact_id,
    ]

    identity_service.switch_branch(
        session_id=session.session_id,
        target_branch_head_id=main_identity.branch_head_id,
        actor="s1.branch_accept.switch_main",
    )
    main_snapshot = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert main_snapshot.chapter.accepted_segment_ids == [base_segment.artifact_id]
    assert branch_pending.artifact_id not in {
        artifact.artifact_id for artifact in main_snapshot.artifacts
    }

    main_followup_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.branch_accept.main_followup",
        actor="s1.branch_accept.main_followup",
    )
    main_pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Main-only accepted segment.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=main_followup_identity.story_id,
                session_id=main_followup_identity.session_id,
                branch_head_id=main_followup_identity.branch_head_id,
                turn_id=main_followup_identity.turn_id,
                runtime_profile_snapshot_id=main_followup_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_002",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=main_pending.artifact_id,
    )
    identity_service.update_turn_status(
        turn_id=main_followup_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    await turn_domain_service.accept_pending_segment(
        request=_request(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            target_artifact_id=main_pending.artifact_id,
        ),
        runtime_identity=main_followup_identity,
    )
    main_snapshot_after_accept = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert main_snapshot_after_accept.chapter.accepted_segment_ids == [
        base_segment.artifact_id,
        main_pending.artifact_id,
    ]
    assert branch_pending.artifact_id not in {
        artifact.artifact_id for artifact in main_snapshot_after_accept.artifacts
    }

    identity_service.switch_branch(
        session_id=session.session_id,
        target_branch_head_id=branch_a_id,
        actor="s1.branch_accept.switch_branch_a",
    )
    branch_snapshot_after_main_accept = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert branch_snapshot_after_main_accept.chapter.accepted_segment_ids == [
        base_segment.artifact_id,
        branch_pending.artifact_id,
    ]
    assert main_pending.artifact_id not in {
        artifact.artifact_id for artifact in branch_snapshot_after_main_accept.artifacts
    }


def test_child_branch_can_write_next_segment_when_main_pending_is_hidden(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    main_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="v1.branch_pending.base_segment",
        actor="v1.branch_pending.base_segment",
    )
    base_segment = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=main_identity,
        content_text="Shared settled segment before branching.",
        target_beat_id="beat_001",
    )
    main_pending_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="v1.branch_pending.main_pending",
        actor="v1.branch_pending.main_pending",
    )
    main_pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Main branch pending draft that child branch must not see.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=main_pending_identity.story_id,
                session_id=main_pending_identity.session_id,
                branch_head_id=main_pending_identity.branch_head_id,
                turn_id=main_pending_identity.turn_id,
                runtime_profile_snapshot_id=(
                    main_pending_identity.runtime_profile_snapshot_id
                ),
            ),
            "target_beat_id": "beat_002",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        accepted_segment_ids=[base_segment.artifact_id],
        pending_segment_artifact_id=main_pending.artifact_id,
    )
    identity_service.update_turn_status(
        turn_id=main_pending_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )

    receipt = identity_service.create_branch_from_turn(
        session_id=session.session_id,
        origin_turn_id=main_identity.turn_id,
        actor="v1.branch_pending.create_child_branch",
        branch_name="child-from-settled",
    )
    assert receipt.to_branch_head_id is not None

    snapshot = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert snapshot.chapter.pending_segment_artifact_id is None
    assert snapshot.chapter.phase == LongformChapterPhase.SEGMENT_DRAFTING
    assert snapshot.session.current_phase == LongformChapterPhase.SEGMENT_DRAFTING
    assert snapshot.chapter.accepted_segment_ids == [base_segment.artifact_id]
    assert main_pending.artifact_id not in {
        artifact.artifact_id for artifact in snapshot.artifacts
    }

    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    active_chapter = turn_domain_service.require_active_branch_current_chapter(
        session.session_id
    )
    assert active_chapter.phase == LongformChapterPhase.SEGMENT_DRAFTING

    graph_nodes = StoryGraphNodes(domain_service=turn_domain_service)
    loaded = graph_nodes.load_session_and_chapter({"session_id": session.session_id})
    validated = graph_nodes.validate_command(
        {
            "session_id": session.session_id,
            "command_kind": LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        }
    )
    generation_inputs = turn_domain_service.prepare_generation_inputs(
        session_id=session.session_id,
        user_prompt=None,
        target_artifact_id=None,
    )

    assert loaded["chapter_phase"] == LongformChapterPhase.SEGMENT_DRAFTING.value
    assert validated["status"] == "command_validated"
    assert generation_inputs["pending_artifact_id"] is None
    assert generation_inputs["accepted_segment_ids"] == [base_segment.artifact_id]


def test_branch_writer_packet_omits_source_future_projection_digest(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    first_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="v1.branch_scope.first",
        actor="v1.branch_scope.first",
    )
    first_segment = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=first_identity,
        content_text="First shared segment before branch.",
        target_beat_id="beat_001",
    )
    second_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="v1.branch_scope.source_future",
        actor="v1.branch_scope.source_future",
    )
    second_segment = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=second_identity,
        content_text="Source branch future segment must not leak.",
        target_beat_id="beat_002",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[first_segment.artifact_id, second_segment.artifact_id],
        builder_snapshot_json={
            **dict(chapter.builder_snapshot_json or {}),
            "recent_segment_digest": ["Source branch future segment must not leak."],
            "current_state_digest": ["State after the source branch future."],
        },
    )
    identity_service.create_branch_from_turn(
        session_id=session.session_id,
        origin_turn_id=first_identity.turn_id,
        actor="v1.branch_scope.create_branch",
        branch_name="from-first",
    )
    branch_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="v1.branch_scope.child_writer",
        actor="v1.branch_scope.child_writer",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue on the child branch.",
        ),
        specialist_bundle=SpecialistResultBundle(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        runtime_identity=branch_identity,
    )

    labels = [section["label"] for section in packet.context_sections]
    assert "recent_segment_digest" not in labels
    assert "current_state_digest" not in labels
    joined_packet = "\n".join(
        item
        for section in packet.context_sections
        for item in section.get("items", [])
    )
    assert "Source branch future segment must not leak." not in joined_packet
    assert "State after the source branch future." not in joined_packet
    omitted = packet.metadata["branch_visibility_omitted_projection_sections"]
    assert {item["label"] for item in omitted} == {
        "recent_segment_digest",
        "current_state_digest",
    }
    manifest = packet.metadata["runtime_read_manifest"]
    assert second_identity.branch_head_id in manifest["active_branch_lineage"]
    assert (
        manifest["branch_scope"]["turn_cutoff_by_branch"][
            second_identity.branch_head_id
        ]
        == first_identity.turn_id
    )


def test_active_branch_story_segments_ignore_legacy_accepted_list_pollution(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    first_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.single_path.first",
        actor="s1.single_path.first",
    )
    second_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.single_path.second",
        actor="s1.single_path.second",
    )
    first_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="First legal lineage segment.",
        metadata=_artifact_runtime_metadata(
            story_id=first_identity.story_id,
            session_id=first_identity.session_id,
            branch_head_id=first_identity.branch_head_id,
            turn_id=first_identity.turn_id,
            runtime_profile_snapshot_id=first_identity.runtime_profile_snapshot_id,
        ),
    )
    second_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Second legal lineage segment.",
        metadata=_artifact_runtime_metadata(
            story_id=second_identity.story_id,
            session_id=second_identity.session_id,
            branch_head_id=second_identity.branch_head_id,
            turn_id=second_identity.turn_id,
            runtime_profile_snapshot_id=second_identity.runtime_profile_snapshot_id,
        ),
    )
    no_turn_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Legacy no-turn segment should not be visible.",
        metadata={},
    )
    mismatch_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Mismatched turn segment should not be visible.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=first_identity.story_id,
                session_id=first_identity.session_id,
                branch_head_id="branch:sibling-not-active",
                turn_id=second_identity.turn_id,
                runtime_profile_snapshot_id=first_identity.runtime_profile_snapshot_id,
            ),
        },
    )
    identity_service.update_turn_status(
        turn_id=first_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=first_segment.artifact_id,
        selected_output_ref=first_segment.artifact_id,
        settlement_reason="s1_single_path_first",
    )
    identity_service.update_turn_status(
        turn_id=second_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=second_segment.artifact_id,
        selected_output_ref=second_segment.artifact_id,
        settlement_reason="s1_single_path_second",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[
            mismatch_segment.artifact_id,
            second_segment.artifact_id,
            no_turn_segment.artifact_id,
            first_segment.artifact_id,
        ],
    )

    snapshot = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert snapshot.chapter.accepted_segment_ids == [
        first_segment.artifact_id,
        second_segment.artifact_id,
    ]
    story_segment_ids = {
        artifact.artifact_id
        for artifact in snapshot.artifacts
        if artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
    }
    assert story_segment_ids == {
        first_segment.artifact_id,
        second_segment.artifact_id,
    }


def test_active_branch_story_segments_do_not_need_legacy_accepted_list(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    first_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.single_path.empty_list_first",
        actor="s1.single_path.empty_list_first",
    )
    second_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.single_path.empty_list_second",
        actor="s1.single_path.empty_list_second",
    )
    first_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="First segment with empty legacy list.",
        metadata=_artifact_runtime_metadata(
            story_id=first_identity.story_id,
            session_id=first_identity.session_id,
            branch_head_id=first_identity.branch_head_id,
            turn_id=first_identity.turn_id,
            runtime_profile_snapshot_id=first_identity.runtime_profile_snapshot_id,
        ),
    )
    second_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Second segment with empty legacy list.",
        metadata=_artifact_runtime_metadata(
            story_id=second_identity.story_id,
            session_id=second_identity.session_id,
            branch_head_id=second_identity.branch_head_id,
            turn_id=second_identity.turn_id,
            runtime_profile_snapshot_id=second_identity.runtime_profile_snapshot_id,
        ),
    )
    identity_service.update_turn_status(
        turn_id=first_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=first_segment.artifact_id,
        selected_output_ref=first_segment.artifact_id,
        settlement_reason="s1_empty_list_first",
    )
    identity_service.update_turn_status(
        turn_id=second_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=second_segment.artifact_id,
        selected_output_ref=second_segment.artifact_id,
        settlement_reason="s1_empty_list_second",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[],
    )

    snapshot = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert snapshot.chapter.accepted_segment_ids == [
        first_segment.artifact_id,
        second_segment.artifact_id,
    ]


@pytest.mark.asyncio
async def test_graph_state_stale_accepted_ids_do_not_pollute_specialist_context(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    legal_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s1.single_path.specialist_legal",
        actor="s1.single_path.specialist_legal",
    )
    legal_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Only legal specialist segment.",
        metadata=_artifact_runtime_metadata(
            story_id=legal_identity.story_id,
            session_id=legal_identity.session_id,
            branch_head_id=legal_identity.branch_head_id,
            turn_id=legal_identity.turn_id,
            runtime_profile_snapshot_id=legal_identity.runtime_profile_snapshot_id,
        ),
    )
    stale_segment = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Stale graph segment should not reach specialist.",
        metadata={},
    )
    identity_service.update_turn_status(
        turn_id=legal_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=legal_segment.artifact_id,
        selected_output_ref=legal_segment.artifact_id,
        settlement_reason="s1_specialist_legal",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[stale_segment.artifact_id],
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    captured: dict[str, Any] = {}

    async def _analyze(**kwargs: Any) -> SpecialistResultBundle:
        captured.update(kwargs)
        return SpecialistResultBundle()

    turn_domain_service._specialist_service = SimpleNamespace(analyze=_analyze)

    await turn_domain_service.specialist_analyze(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="test-model",
        provider_id="test-provider",
        user_prompt=None,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue from legal active branch context.",
        ),
        pending_artifact_id=None,
        accepted_segment_ids=[stale_segment.artifact_id],
        runtime_identity=legal_identity,
    )

    accepted_segments = cast(list[Any], captured["accepted_segments"])
    assert [segment.artifact_id for segment in accepted_segments] == [
        legal_segment.artifact_id
    ]


def test_write_next_segment_persisted_candidate_metadata_records_current_target_beat_id(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="t1.target_beat.persist.accepted",
        actor="t1.target_beat.persist.accepted",
    )
    accepted = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_identity,
        content_text="Beat one accepted.",
        target_beat_id="beat_001",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[accepted.artifact_id],
    )
    runtime_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="t1.target_beat.persist",
        actor="t1.target_beat.persist",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write beat two.",
        ),
        specialist_bundle=SpecialistResultBundle(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        runtime_identity=runtime_identity,
    )
    response = turn_domain_service.persist_generated_artifact(
        request=_request(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        ),
        packet=packet,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Write beat two.",
        ),
        writing_result=_story_segment_result(
            packet_id=packet.packet_id,
            turn_id=runtime_identity.turn_id,
            output_text="Draft candidate for beat two.",
        ),
        specialist_bundle=SpecialistResultBundle(),
        pending_artifact_id=None,
    )
    assert response.artifact_id is not None
    created = story_session_service.get_artifact(response.artifact_id)
    assert created is not None
    assert created.metadata["target_beat_id"] == "beat_002"


@pytest.mark.asyncio
async def test_accept_first_pending_segment_advances_from_beat_one_without_self_mismatch(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    write_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="t1.target_beat.first_write",
        actor="t1.target_beat.first_write",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Beat one pending draft.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=write_identity.story_id,
                session_id=write_identity.session_id,
                branch_head_id=write_identity.branch_head_id,
                turn_id=write_identity.turn_id,
                runtime_profile_snapshot_id=write_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_001",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    StoryRuntimeIdentityService(retrieval_session).update_turn_status(
        turn_id=write_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    accept_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        created_from="t1.target_beat.first_accept",
        actor="t1.target_beat.first_accept",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    response = await turn_domain_service.accept_pending_segment(
        request=_request(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            target_artifact_id=pending.artifact_id,
        ),
        runtime_identity=accept_identity,
    )

    assert response.artifact_id == pending.artifact_id
    updated_artifact = story_session_service.get_artifact(pending.artifact_id)
    assert updated_artifact is not None
    assert updated_artifact.status == StoryArtifactStatus.ACCEPTED
    updated_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    assert updated_chapter is not None
    snapshot = story_session_service.build_chapter_snapshot(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert snapshot.chapter.accepted_segment_ids == [pending.artifact_id]
    progress_service = cast(
        LongformChapterRuntimeService,
        turn_domain_service._longform_chapter_runtime_service,
    )
    progress = progress_service.effective_outline_progress(
        chapter=updated_chapter,
        identity=accept_identity,
    )
    assert progress is not None
    assert progress.covered_beat_ids == ["beat_001"]
    assert progress.current_beat_id == "beat_002"


@pytest.mark.asyncio
async def test_accept_stale_pending_segment_rejects_before_mutating_state(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    write_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="t1.target_beat.stale_write",
        actor="t1.target_beat.stale_write",
    )
    accepted = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=write_identity,
        content_text="Beat one already accepted.",
        target_beat_id="beat_001",
    )
    stale_pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Stale beat one draft.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=write_identity.story_id,
                session_id=write_identity.session_id,
                branch_head_id=write_identity.branch_head_id,
                turn_id=write_identity.turn_id,
                runtime_profile_snapshot_id=write_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_001",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        accepted_segment_ids=[accepted.artifact_id],
        pending_segment_artifact_id=stale_pending.artifact_id,
    )
    accept_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        created_from="t1.target_beat.stale_accept",
        actor="t1.target_beat.stale_accept",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    with pytest.raises(LongformChapterRuntimeServiceError) as exc:
        await turn_domain_service.accept_pending_segment(
            request=_request(
                session_id=session.session_id,
                command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
                target_artifact_id=stale_pending.artifact_id,
            ),
            runtime_identity=accept_identity,
        )

    assert exc.value.code == "longform_outline_progress_target_beat_mismatch"
    assert str(exc.value).endswith("beat_002:beat_001")
    unchanged_pending = story_session_service.get_artifact(stale_pending.artifact_id)
    assert unchanged_pending is not None
    assert unchanged_pending.status == StoryArtifactStatus.DRAFT
    unchanged_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    assert unchanged_chapter is not None
    assert unchanged_chapter.accepted_segment_ids == [accepted.artifact_id]
    assert unchanged_chapter.pending_segment_artifact_id == stale_pending.artifact_id


@pytest.mark.asyncio
async def test_rewrite_and_adoption_progress_only_moves_after_accept_pending_segment(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    accepted_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="t1.target_beat.source_accepted",
        actor="t1.target_beat.source_accepted",
    )
    accepted = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=accepted_identity,
        content_text="Beat one accepted.",
        target_beat_id="beat_001",
    )
    pending_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="t1.target_beat.source_pending",
        actor="t1.target_beat.source_pending",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Beat two pending draft.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=pending_identity.story_id,
                session_id=pending_identity.session_id,
                branch_head_id=pending_identity.branch_head_id,
                turn_id=pending_identity.turn_id,
                runtime_profile_snapshot_id=pending_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_002",
        },
    )
    identity_service.update_turn_status(
        turn_id=pending_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        accepted_segment_ids=[accepted.artifact_id],
        pending_segment_artifact_id=pending.artifact_id,
    )
    rewrite_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        created_from="t1.target_beat.rewrite",
        actor="t1.target_beat.rewrite",
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    progress_service = cast(
        LongformChapterRuntimeService,
        turn_domain_service._longform_chapter_runtime_service,
    )
    before_rewrite = progress_service.effective_outline_progress(
        chapter=story_session_service.get_chapter_workspace(chapter.chapter_workspace_id),
        identity=rewrite_identity,
    )
    assert before_rewrite is not None
    assert before_rewrite.current_beat_id == "beat_002"
    rewrite_packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Rewrite beat two.",
        ),
        specialist_bundle=SpecialistResultBundle(),
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        runtime_identity=rewrite_identity,
        target_artifact_id=pending.artifact_id,
    )
    rewrite_response = turn_domain_service.persist_generated_artifact(
        request=_request(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
            target_artifact_id=pending.artifact_id,
        ),
        packet=rewrite_packet,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Rewrite beat two.",
        ),
        writing_result=_story_segment_result(
            packet_id=rewrite_packet.packet_id,
            turn_id=rewrite_identity.turn_id,
            output_text="Rewrite candidate for beat two.",
            operation_mode="rewrite",
        ),
        specialist_bundle=SpecialistResultBundle(),
        pending_artifact_id=pending.artifact_id,
    )
    assert rewrite_response.artifact_id is not None
    rewrite_artifact = story_session_service.get_artifact(rewrite_response.artifact_id)
    assert rewrite_artifact is not None
    assert rewrite_artifact.metadata["target_beat_id"] == "beat_002"
    after_rewrite = progress_service.effective_outline_progress(
        chapter=story_session_service.get_chapter_workspace(chapter.chapter_workspace_id),
        identity=rewrite_identity,
    )
    assert after_rewrite is not None
    assert after_rewrite.current_beat_id == "beat_002"
    accept_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        created_from="t1.target_beat.accept",
        actor="t1.target_beat.accept",
    )
    await turn_domain_service.accept_pending_segment(
        request=_request(
            session_id=session.session_id,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            target_artifact_id=pending.artifact_id,
        ),
        runtime_identity=accept_identity,
    )
    updated_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    assert updated_chapter is not None
    after_accept = progress_service.effective_outline_progress(
        chapter=updated_chapter,
        identity=accept_identity,
    )
    assert after_accept is not None
    assert after_accept.current_beat_id is None
    assert after_accept.covered_beat_ids == ["beat_001", "beat_002"]


def _record_draft(
    service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    source_output_ref: str,
):
    draft = DraftMaterializationService().materialize_draft(
        identity=identity,
        draft_ref=draft_ref,
        source_output_ref=source_output_ref,
        output_text=(
            "The storm arrived at dusk.\n\n"
            "Mira reached the bell tower.\n\n"
            "The debt was still unpaid."
        ),
        source_format="markdown",
    )
    return service.record_draft_document(identity=identity, draft_document=draft)


def _anchor(block_id: str):
    from rp.models.revision_overlay_contracts import RevisionAnchorRef

    return RevisionAnchorRef(anchor_scope="single_block", block_ids=[block_id])


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


def _request(
    *,
    session_id: str,
    command_kind: LongformTurnCommandKind,
    target_artifact_id: str | None = None,
):
    from rp.models.story_runtime import LongformTurnRequest

    return LongformTurnRequest(
        session_id=session_id,
        command_kind=command_kind,
        model_id="test-model",
        provider_id="test-provider",
        target_artifact_id=target_artifact_id,
    )


def _story_segment_result(
    *,
    packet_id: str,
    turn_id: str,
    output_text: str,
    operation_mode: str = "writing",
) -> WritingWorkerExecutionResult:
    return WritingWorkerExecutionResult(
        request_id=f"writer:{packet_id}",
        packet_id=packet_id,
        turn_id=turn_id,
        operation_mode=operation_mode,
        output_text=output_text,
        output_kind="story_segment",
        result_status="completed",
    )
