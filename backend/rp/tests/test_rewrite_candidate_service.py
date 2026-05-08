"""Focused tests for R4 rewrite candidates and paragraph patch composition."""

from __future__ import annotations

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import (
    ParagraphRewritePatch,
    ReplacementBlock,
    RewriteCandidateRecord,
    RevisionAnchorRef,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.rewrite_candidate_service import (
    RewriteCandidateService,
    RewriteCandidateServiceError,
)
from rp.services.rewrite_request_builder_service import RewriteRequestBuilderService
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService


def test_full_rewrite_candidate_is_saved_without_auto_adoption(retrieval_session):
    identity = _identity(turn_id="turn-r4-full")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:full",
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Rewrite with quieter tension.",
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )

    candidate = candidate_service.create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(
            identity=identity,
            output_text="The rain softened the city into a hush.",
        ),
    )

    assert candidate.rewrite_scope == "full"
    assert candidate.full_output_text == "The rain softened the city into a hush."
    assert candidate.candidate_draft_text == candidate.full_output_text
    assert candidate.selected_output_ref is None
    assert candidate.adopted_output_ref is None
    assert candidate.canonical_truth is False
    assert candidate.metadata_json["canonical_truth"] is False
    assert candidate.metadata_json["story_id"] == identity.story_id
    assert candidate.metadata_json["session_id"] == identity.session_id
    assert candidate.metadata_json["branch_head_id"] == identity.branch_head_id
    assert candidate.metadata_json["turn_id"] == identity.turn_id
    assert (
        candidate.metadata_json["runtime_profile_snapshot_id"]
        == identity.runtime_profile_snapshot_id
    )

    listed = candidate_service.list_candidates(identity=identity)
    assert listed == [candidate]

    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
        domain="chapter",
    )
    assert len(materials) == 1
    assert materials[0].payload["payload_kind"] == "rewrite_candidate"
    assert materials[0].payload["canonical_truth"] is False
    assert materials[0].payload["selected_output_ref"] is None
    assert materials[0].payload["adopted_output_ref"] is None
    assert materials[0].metadata["source_of_truth"] is False


def test_paragraph_rewrite_candidate_requires_patch_and_replaces_target_only(
    retrieval_session,
):
    identity = _identity(turn_id="turn-r4-paragraph")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:paragraph",
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
        instruction_text="Make the second paragraph more vivid.",
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_paragraph_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        target_block_ids=[draft.blocks[1].block_id],
        comment_refs=[comment.comment_id],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )

    with pytest.raises(RewriteCandidateServiceError) as missing_exc:
        candidate_service.create_paragraph_rewrite_candidate(
            identity=identity,
            rewrite_request=request,
            replacement_blocks=[],
        )
    assert missing_exc.value.code == "revision_replacement_blocks_required"

    candidate = candidate_service.create_paragraph_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        replacement_blocks=[
            ReplacementBlock(
                block_id=draft.blocks[1].block_id,
                replacement_text="Mira moved on beneath the bell's iron answer.",
                order=draft.blocks[1].order,
            )
        ],
        writer_result=_writer_result(
            identity=identity,
            output_text="Patch-shaped output is carried in metadata.",
        ),
    )

    assert candidate.rewrite_scope == "paragraph"
    assert candidate.full_output_text is None
    assert candidate.target_block_ids == [draft.blocks[1].block_id]
    assert candidate.paragraph_patch is not None
    assert candidate.paragraph_patch.replacement_blocks[0].replacement_text == (
        "Mira moved on beneath the bell's iron answer."
    )
    assert candidate.candidate_draft_text == (
        "The storm arrived at dusk.\n\n"
        "Mira moved on beneath the bell's iron answer.\n\n"
        "The bell tower answered."
    )
    assert candidate.touched_comment_ids == [comment.comment_id]
    assert candidate.selected_output_ref is None
    assert candidate.adopted_output_ref is None
    assert candidate.canonical_truth is False

    inspection = overlay_service.inspect_overlay(
        identity=identity,
        overlay_id=overlay.overlay_id,
    )
    assert inspection.comments[0].status == "active"


def test_paragraph_rewrite_candidate_rejects_replacements_outside_target(
    retrieval_session,
):
    identity = _identity(turn_id="turn-r4-target-mismatch")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:target-mismatch",
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_paragraph_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        target_block_ids=[draft.blocks[0].block_id],
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )

    with pytest.raises(RewriteCandidateServiceError) as exc:
        candidate_service.create_paragraph_rewrite_candidate(
            identity=identity,
            rewrite_request=request,
            replacement_blocks=[
                ReplacementBlock(
                    block_id=draft.blocks[1].block_id,
                    replacement_text="Wrong target.",
                    order=draft.blocks[1].order,
                )
            ],
        )
    assert exc.value.code == "revision_replacement_block_target_mismatch"


def test_candidate_list_is_isolated_by_full_runtime_identity(retrieval_session):
    identity = _identity(turn_id="turn-r4-isolation")
    other_branch_identity = _identity(
        turn_id="turn-r4-isolation",
        branch_head_id="branch-other",
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:isolation",
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction=None,
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )
    candidate = candidate_service.create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(identity=identity, output_text="Branch A draft."),
    )

    assert candidate_service.list_candidates(identity=identity) == [candidate]
    assert candidate_service.list_candidates(identity=other_branch_identity) == []


def test_candidate_creation_rejects_cross_branch_request_reuse(retrieval_session):
    identity = _identity(turn_id="turn-r4-request-identity")
    other_branch_identity = _identity(
        turn_id="turn-r4-request-identity",
        branch_head_id="branch-r4-other",
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:request-identity",
    )
    _record_draft(
        overlay_service,
        identity=other_branch_identity,
        draft_ref=draft.draft_ref,
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction=None,
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )

    with pytest.raises(RewriteCandidateServiceError) as exc:
        candidate_service.create_full_rewrite_candidate(
            identity=other_branch_identity,
            rewrite_request=request,
            writer_result=_writer_result(
                identity=other_branch_identity,
                output_text="Wrong branch draft.",
            ),
        )
    assert exc.value.code == "revision_branch_head_id_mismatch"


def test_candidate_dtos_use_factory_defaults_not_shared_mutable_state():
    first = RewriteCandidateRecord(
        candidate_id="candidate-1",
        candidate_output_ref="candidate-1",
        session_id="session-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        rewrite_request_id="request-1",
        rewrite_scope="full",
        full_output_text="First.",
        candidate_draft_text="First.",
        created_at=_created_at(),
    )
    second = RewriteCandidateRecord(
        candidate_id="candidate-2",
        candidate_output_ref="candidate-2",
        session_id="session-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        rewrite_request_id="request-2",
        rewrite_scope="full",
        full_output_text="Second.",
        candidate_draft_text="Second.",
        created_at=_created_at(),
    )
    first.touched_comment_ids.append("comment-1")
    first.metadata_json["marker"] = "first"

    assert second.touched_comment_ids == []
    assert second.metadata_json == {}

    first_patch = ParagraphRewritePatch(
        draft_ref="draft-1",
        target_block_ids=["block-1"],
        replacement_blocks=[
            ReplacementBlock(
                block_id="block-1",
                replacement_text="Replacement.",
                order=0,
            )
        ],
    )
    second_patch = ParagraphRewritePatch(
        draft_ref="draft-1",
        target_block_ids=["block-2"],
        replacement_blocks=[
            ReplacementBlock(
                block_id="block-2",
                replacement_text="Other.",
                order=1,
            )
        ],
    )
    first_patch.touched_comment_ids.append("comment-1")
    first_patch.metadata_json["marker"] = "first"

    assert second_patch.touched_comment_ids == []
    assert second_patch.metadata_json == {}


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


def _writer_result(
    *,
    identity: MemoryRuntimeIdentity,
    output_text: str,
) -> WritingWorkerExecutionResult:
    return WritingWorkerExecutionResult(
        request_id=f"writer-request:{identity.turn_id}",
        packet_id=f"packet:{identity.turn_id}",
        turn_id=identity.turn_id,
        operation_mode="rewrite",
        output_text=output_text,
        output_kind="story_segment",
        result_status="completed",
    )


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-r4"),
        session_id=overrides.get("session_id", "session-r4"),
        branch_head_id=overrides.get("branch_head_id", "branch-r4"),
        turn_id=overrides.get("turn_id", "turn-r4"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-r4",
        ),
    )


def _created_at():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
