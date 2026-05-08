"""Focused tests for R3 rewrite request and review-overlay packet sidecars."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import RevisionAnchorRef, RewriteRequest
from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformChapterPhase,
    OrchestratorPlan,
    StoryArtifactKind,
    StorySession,
    StorySessionState,
)
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.rewrite_request_builder_service import (
    RewriteRequestBuilderService,
    RewriteRequestBuilderServiceError,
)
from rp.services.writing_packet_builder import WritingPacketBuilder


def test_full_rewrite_comments_only_includes_old_draft_text_in_sidecar(
    retrieval_session,
):
    identity = _identity(turn_id="turn-full-comments")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:full-comments",
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        instruction_text="Make the opening more patient.",
        selected_excerpt=draft.blocks[0].selected_excerpt,
    )
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )

    request = builder.build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction=None,
        comment_refs=[comment.comment_id],
        tracked_change_refs=[],
    )
    sections = builder.build_review_overlay_sections(
        identity=identity,
        rewrite_request=request,
    )
    section_metadata = cast(dict[str, Any], sections[0]["metadata_json"])

    assert request.rewrite_scope == "full"
    assert request.include_full_draft_text is True
    assert request.full_draft_text == _expected_full_draft_text()
    assert request.metadata_json["candidate_output_ref"] is None
    assert request.metadata_json["adopted_output_ref"] is None
    assert request.metadata_json["canonical_truth"] is False
    assert section_metadata["include_full_draft_text"] is True
    assert section_metadata["full_draft_text"] == _expected_full_draft_text()
    assert section_metadata["comments"][0]["comment_id"] == comment.comment_id


def test_full_rewrite_with_global_instruction_excludes_old_draft_text(
    retrieval_session,
):
    identity = _identity(turn_id="turn-full-global")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:full-global",
    )
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )

    request = builder.build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Make the chapter colder and more formal.",
        comment_refs=[],
        tracked_change_refs=[],
    )

    assert request.include_full_draft_text is False
    assert request.full_draft_text is None
    assert request.global_instruction == "Make the chapter colder and more formal."

    with pytest.raises(RewriteRequestBuilderServiceError) as exc:
        builder.build_full_rewrite_request(
            identity=identity,
            draft_ref=draft.draft_ref,
            global_instruction="Make the chapter colder.",
            comment_refs=[],
            tracked_change_refs=[],
            include_full_draft_text=True,
        )
    assert exc.value.code == "revision_full_rewrite_old_text_forbidden"

    with pytest.raises(RewriteRequestBuilderServiceError) as required_exc:
        builder.build_full_rewrite_request(
            identity=identity,
            draft_ref=draft.draft_ref,
            global_instruction=None,
            comment_refs=[],
            tracked_change_refs=[],
            include_full_draft_text=False,
        )
    assert required_exc.value.code == "revision_full_rewrite_old_text_required"


def test_paragraph_rewrite_requires_one_contiguous_target_scope(
    retrieval_session,
):
    identity = _identity(turn_id="turn-paragraph-target")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:paragraph-target",
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[1].block_id),
        instruction_text="Sharpen this paragraph.",
    )
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )

    request = builder.build_paragraph_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        target_block_ids=[draft.blocks[1].block_id],
        comment_refs=[comment.comment_id],
        tracked_change_refs=[],
        global_instruction="Keep the focus local.",
    )

    assert request.rewrite_scope == "paragraph"
    assert request.target_block_ids == [draft.blocks[1].block_id]
    assert request.include_full_draft_text is True
    assert request.full_draft_text == _expected_full_draft_text()
    assert request.metadata_json["expected_writer_output_shape"] == (
        "paragraph_rewrite_patch"
    )
    assert request.metadata_json["replacement_blocks_required"] is True
    assert request.metadata_json["candidate_output_ref"] is None
    assert request.metadata_json["adopted_output_ref"] is None

    with pytest.raises(RewriteRequestBuilderServiceError) as target_exc:
        builder.build_paragraph_rewrite_request(
            identity=identity,
            draft_ref=draft.draft_ref,
            target_block_ids=[],
            comment_refs=[],
            tracked_change_refs=[],
        )
    assert target_exc.value.code == "revision_target_blocks_required"

    with pytest.raises(RewriteRequestBuilderServiceError) as batch_exc:
        builder.build_paragraph_rewrite_request(
            identity=identity,
            draft_ref=draft.draft_ref,
            target_block_ids=[draft.blocks[0].block_id, draft.blocks[2].block_id],
            comment_refs=[],
            tracked_change_refs=[],
        )
    assert batch_exc.value.code == "revision_batch_paragraph_rewrite_unsupported"


def test_paragraph_rewrite_rejects_comment_outside_target_scope(retrieval_session):
    identity = _identity(turn_id="turn-paragraph-comment-scope")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:paragraph-comment-scope",
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[2].block_id),
        instruction_text="This comment is outside the requested paragraph.",
    )
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )

    with pytest.raises(RewriteRequestBuilderServiceError) as exc:
        builder.build_paragraph_rewrite_request(
            identity=identity,
            draft_ref=draft.draft_ref,
            target_block_ids=[draft.blocks[0].block_id],
            comment_refs=[comment.comment_id],
            tracked_change_refs=[],
        )
    assert exc.value.code == "revision_comment_draft_mismatch"


def test_deleted_comment_does_not_enter_future_rewrite_packet(retrieval_session):
    identity = _identity(turn_id="turn-deleted-comment")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:deleted-comment",
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        instruction_text="Delete me before rewrite.",
    )
    overlay_service.delete_comment(identity=identity, comment_id=comment.comment_id)
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )

    with pytest.raises(RewriteRequestBuilderServiceError) as exc:
        builder.build_full_rewrite_request(
            identity=identity,
            draft_ref=draft.draft_ref,
            global_instruction=None,
            comment_refs=[comment.comment_id],
            tracked_change_refs=[],
        )
    assert exc.value.code == "revision_comment_not_active"


def test_review_overlay_sections_map_into_writing_packet_without_top_level_drift(
    retrieval_session,
):
    identity = _identity(turn_id="turn-packet-sidecar")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:packet-sidecar",
    )
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=RevisionAnchorRef(
            anchor_scope="single_block",
            block_ids=[draft.blocks[0].block_id],
            superdoc_anchor_id="superdoc-anchor-1",
        ),
        instruction_text="Make this line more lyrical.",
        selected_excerpt=draft.blocks[0].selected_excerpt,
    )
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )
    request = builder.build_paragraph_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        target_block_ids=[draft.blocks[0].block_id],
        comment_refs=[comment.comment_id],
        tracked_change_refs=[],
    )
    review_sections = builder.build_review_overlay_sections(
        identity=identity,
        rewrite_request=request,
    )

    packet = WritingPacketBuilder().build(
        session=_story_session(identity),
        chapter=_chapter_workspace(identity),
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Rewrite the target paragraph only.",
        ),
        runtime_identity=identity,
        operation_mode="rewrite",
        projection_context_sections=[
            {"label": "core_view", "items": ["Core view summary."]},
        ],
        runtime_writer_hints=[],
        user_instruction="Rewrite the target paragraph only.",
        review_overlay_sections=review_sections,
    )

    assert packet.operation_mode == "rewrite"
    assert len(packet.review_overlay_sections) == 1
    section = packet.review_overlay_sections[0]
    assert section.label == "review_overlay"
    assert section.source_kind == "review_overlay_rewrite_request"
    assert section.metadata_json["rewrite_scope"] == "paragraph"
    assert section.metadata_json["include_full_draft_text"] is True
    assert section.metadata_json["expected_writer_output_shape"] == (
        "paragraph_rewrite_patch"
    )
    assert (
        section.metadata_json["anchor_refs"][0]["superdoc_anchor_id"]
        == "superdoc-anchor-1"
    )
    assert "superdoc-anchor-1" not in section.source_ref_ids
    dumped_packet = packet.model_dump(mode="json")
    assert "rewrite_request" not in dumped_packet
    assert "full_draft_text" not in dumped_packet["metadata"]
    assert dumped_packet["review_overlay_sections"][0]["metadata_json"][
        "full_draft_text"
    ] == _expected_full_draft_text()


def test_review_overlay_sections_reject_cross_branch_request_reuse(
    retrieval_session,
):
    identity = _identity(turn_id="turn-packet-identity")
    other_branch = _identity(
        turn_id="turn-packet-identity",
        branch_head_id="branch-r3-other",
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r3:packet-identity",
    )
    builder = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    )
    request = builder.build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction=None,
        comment_refs=[],
        tracked_change_refs=[],
    )

    with pytest.raises(RewriteRequestBuilderServiceError) as exc:
        builder.build_review_overlay_sections(
            identity=other_branch,
            rewrite_request=request,
        )
    assert exc.value.code == "revision_branch_head_id_mismatch"


def test_rewrite_request_dto_factory_defaults_do_not_share_mutable_state():
    first = RewriteRequest(
        request_id="request-1",
        session_id="session-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        rewrite_scope="full",
        include_full_draft_text=False,
    )
    second = RewriteRequest(
        request_id="request-2",
        session_id="session-1",
        turn_id="turn-1",
        draft_ref="draft-2",
        draft_document_id="doc-2",
        rewrite_scope="full",
        include_full_draft_text=False,
    )

    first.comment_refs.append("comment-1")
    first.metadata_json["marker"] = "first"

    assert second.comment_refs == []
    assert second.metadata_json == {}


def _record_draft(
    service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
):
    draft = DraftMaterializationService().materialize_draft(
        identity=identity,
        draft_ref=draft_ref,
        source_output_ref=f"artifact:{identity.turn_id}",
        output_text=(
            "The storm arrived at dusk.\n\n"
            "Mira kept walking.\n\n"
            "The bell tower answered."
        ),
        source_format="markdown",
    )
    return service.record_draft_document(identity=identity, draft_document=draft)


def _anchor(block_id: str) -> RevisionAnchorRef:
    return RevisionAnchorRef(
        anchor_scope="single_block",
        block_ids=[block_id],
        start_offset=0,
        end_offset=5,
    )


def _expected_full_draft_text() -> str:
    return (
        "The storm arrived at dusk.\n\n"
        "Mira kept walking.\n\n"
        "The bell tower answered."
    )


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-r3"),
        session_id=overrides.get("session_id", "session-r3"),
        branch_head_id=overrides.get("branch_head_id", "branch-r3"),
        turn_id=overrides.get("turn_id", "turn-r3"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-r3",
        ),
    )


def _story_session(identity: MemoryRuntimeIdentity) -> StorySession:
    now = datetime.now(timezone.utc)
    return StorySession(
        session_id=identity.session_id,
        story_id=identity.story_id,
        source_workspace_id="workspace-r3",
        mode="longform",
        session_state=StorySessionState.ACTIVE,
        active_branch_head_id=identity.branch_head_id,
        active_runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
        current_chapter_index=1,
        current_phase=LongformChapterPhase.SEGMENT_DRAFTING,
        writer_contract={"style_rules": ["Precise revisions only."]},
        activated_at=now,
        created_at=now,
        updated_at=now,
    )


def _chapter_workspace(identity: MemoryRuntimeIdentity) -> ChapterWorkspace:
    now = datetime.now(timezone.utc)
    return ChapterWorkspace(
        chapter_workspace_id="chapter-r3",
        session_id=identity.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        created_at=now,
        updated_at=now,
    )
