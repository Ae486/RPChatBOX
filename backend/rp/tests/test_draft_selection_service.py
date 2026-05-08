"""Focused tests for R5 draft selection and accept-and-continue adoption."""

from __future__ import annotations

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import (
    LongformDraftAdoptionReceipt,
    LongformDraftSelectionReceipt,
    ReplacementBlock,
    RevisionAnchorRef,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.draft_selection_service import (
    DraftSelectionService,
    DraftSelectionServiceError,
)
from rp.services.revision_overlay_service import RevisionOverlayService
from rp.services.rewrite_candidate_service import RewriteCandidateService
from rp.services.rewrite_request_builder_service import RewriteRequestBuilderService
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService


def test_unique_candidate_can_be_adopted_without_prior_selection(retrieval_session):
    identity = _identity(turn_id="turn-r5-unique")
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:unique",
        output_text="Only candidate text.",
    )
    service = DraftSelectionService(session=retrieval_session)

    receipt = service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=candidate.draft_ref,
    )

    assert isinstance(receipt, LongformDraftAdoptionReceipt)
    assert receipt.adopted_output_ref == candidate.candidate_output_ref
    assert receipt.selection_receipt_id is None
    assert receipt.metadata_json["accept_and_continue"] is True
    assert receipt.metadata_json["canonical_continuation_base"] is True

    anchor = service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=candidate.draft_ref,
    )
    assert anchor == {
        "turn_id": identity.turn_id,
        "draft_ref": candidate.draft_ref,
        "adopted_output_ref": candidate.candidate_output_ref,
        "adoption_receipt_id": receipt.receipt_id,
        "source_kind": "longform_draft_adoption_receipt",
        "canonical_continuation_base": True,
    }


def test_multiple_candidates_require_active_selection_or_explicit_ref(
    retrieval_session,
):
    identity = _identity(turn_id="turn-r5-multiple")
    first = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:multiple",
        output_text="First candidate.",
    )
    second = _create_paragraph_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:multiple",
        replacement_text="The middle paragraph changed.",
    )
    service = DraftSelectionService(session=retrieval_session)

    with pytest.raises(DraftSelectionServiceError) as missing_selection:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=first.draft_ref,
        )
    assert missing_selection.value.code == "revision_adoption_selection_required"

    explicit = service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
        selected_output_ref=second.candidate_output_ref,
    )
    assert explicit.adopted_output_ref == second.candidate_output_ref
    assert explicit.selection_receipt_id is None


def test_selection_can_change_and_clear_before_adoption(retrieval_session):
    identity = _identity(turn_id="turn-r5-selection")
    first = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:selection",
        output_text="First candidate.",
    )
    second = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:selection",
        output_text="Second candidate.",
    )
    candidate_refs = [first.candidate_output_ref, second.candidate_output_ref]
    service = DraftSelectionService(session=retrieval_session)

    initial = service.select_candidate(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
        candidate_output_refs=candidate_refs,
        selected_output_ref=first.candidate_output_ref,
    )
    changed = service.select_candidate(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
        candidate_output_refs=candidate_refs,
        selected_output_ref=second.candidate_output_ref,
    )

    assert isinstance(initial, LongformDraftSelectionReceipt)
    assert service.get_active_selection(
        identity=identity,
        draft_ref=first.draft_ref,
    ) == changed
    assert service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=first.draft_ref,
    ) is None

    cleared = service.clear_selection(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
    )
    assert cleared is not None
    assert cleared.cleared_at is not None
    assert service.get_active_selection(
        identity=identity,
        draft_ref=first.draft_ref,
    ) is None

    with pytest.raises(DraftSelectionServiceError) as missing_selection:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=first.draft_ref,
        )
    assert missing_selection.value.code == "revision_adoption_selection_required"


def test_active_selection_drives_adoption_but_not_before_accept_and_continue(
    retrieval_session,
):
    identity = _identity(turn_id="turn-r5-active-selection")
    first = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:active-selection",
        output_text="First candidate.",
    )
    second = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:active-selection",
        output_text="Second candidate.",
    )
    service = DraftSelectionService(session=retrieval_session)
    selection = service.select_candidate(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
        candidate_output_refs=[first.candidate_output_ref, second.candidate_output_ref],
        selected_output_ref=second.candidate_output_ref,
    )

    assert service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=first.draft_ref,
    ) is None

    adoption = service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
    )

    assert adoption.adopted_output_ref == second.candidate_output_ref
    assert adoption.selection_receipt_id == selection.receipt_id
    adopted_anchor = service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=first.draft_ref,
    )
    assert adopted_anchor is not None
    assert adopted_anchor["adopted_output_ref"] == second.candidate_output_ref
    adoption_materials = [
        material
        for material in RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ).list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            domain="chapter",
        )
        if material.payload.get("record_id") == adoption.receipt_id
    ]
    assert len(adoption_materials) == 1
    assert any(
        ref.source_type == "draft_selection_receipt"
        and ref.source_id == selection.receipt_id
        for ref in adoption_materials[0].source_refs
    )


def test_next_continuation_base_ignores_unadopted_revision_candidates(
    retrieval_session,
):
    identity = _identity(turn_id="turn-r5-continuation-base")
    first = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5-continuation-base",
        output_text="First candidate should stay unadopted.",
    )
    adopted = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5-continuation-base",
        output_text="Adopted continuation text.",
    )
    later_unadopted = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5-continuation-base",
        output_text="Later unadopted candidate.",
    )
    service = DraftSelectionService(session=retrieval_session)

    service.select_candidate(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
        candidate_output_refs=[
            first.candidate_output_ref,
            adopted.candidate_output_ref,
            later_unadopted.candidate_output_ref,
        ],
        selected_output_ref=adopted.candidate_output_ref,
    )

    assert service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=first.draft_ref,
    ) is None

    receipt = service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=first.draft_ref,
    )
    anchor = service.adopted_output_anchor_for_next_turn(
        identity=identity,
        draft_ref=first.draft_ref,
    )

    assert receipt.adopted_output_ref == adopted.candidate_output_ref
    assert anchor is not None
    assert anchor["adopted_output_ref"] == adopted.candidate_output_ref
    assert anchor["adopted_output_ref"] != first.candidate_output_ref
    assert anchor["adopted_output_ref"] != later_unadopted.candidate_output_ref
    assert anchor["canonical_continuation_base"] is True


def test_selected_output_must_be_visible_candidate_for_current_identity_and_draft(
    retrieval_session,
):
    identity = _identity(turn_id="turn-r5-visible")
    other_branch = _identity(
        turn_id="turn-r5-visible",
        branch_head_id="branch-r5-other",
    )
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:visible",
        output_text="Visible candidate.",
    )
    service = DraftSelectionService(session=retrieval_session)

    with pytest.raises(DraftSelectionServiceError) as wrong_ref:
        service.select_candidate(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=candidate.draft_ref,
            candidate_output_refs=[candidate.candidate_output_ref],
            selected_output_ref="not-a-candidate",
        )
    assert wrong_ref.value.code == "revision_selected_output_not_candidate"

    with pytest.raises(DraftSelectionServiceError) as wrong_branch:
        service.adopt_for_continue(
            identity=other_branch,
            turn_id=other_branch.turn_id,
            draft_ref=candidate.draft_ref,
            selected_output_ref=candidate.candidate_output_ref,
        )
    assert wrong_branch.value.code == "revision_candidate_not_found"


def test_adoption_receipt_is_review_sidecar_not_core_truth(retrieval_session):
    identity = _identity(turn_id="turn-r5-material")
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:material",
        output_text="Adopted candidate.",
    )
    service = DraftSelectionService(session=retrieval_session)

    service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=candidate.draft_ref,
    )

    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
        domain="chapter",
    )
    adoption_materials = [
        material
        for material in materials
        if material.payload.get("payload_kind") == "draft_adoption_receipt"
    ]
    assert len(adoption_materials) == 1
    assert adoption_materials[0].payload["canonical_truth"] is False
    assert adoption_materials[0].metadata["source_of_truth"] is False
    assert adoption_materials[0].metadata["canonical_continuation_base"] is True


def test_accept_and_continue_does_not_auto_resolve_comments(retrieval_session):
    identity = _identity(turn_id="turn-r5-comments")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r5:comments",
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
        instruction_text="Keep this comment active after adoption.",
    )
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref=draft.draft_ref,
        output_text="Candidate with unresolved comment.",
        overlay_service=overlay_service,
        comment_refs=[comment.comment_id],
    )
    service = DraftSelectionService(session=retrieval_session)

    service.adopt_for_continue(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=candidate.draft_ref,
    )

    inspection = overlay_service.inspect_overlay(
        identity=identity,
        overlay_id=overlay.overlay_id,
    )
    assert inspection.comments[0].status == "active"


def _create_full_candidate(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    output_text: str,
    overlay_service: RevisionOverlayService | None = None,
    comment_refs: list[str] | None = None,
):
    resolved_overlay_service = overlay_service or RevisionOverlayService(
        session=retrieval_session
    )
    draft = _ensure_draft(
        resolved_overlay_service,
        identity=identity,
        draft_ref=draft_ref,
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=resolved_overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Rewrite this candidate.",
        comment_refs=comment_refs or [],
        tracked_change_refs=[],
    )
    return RewriteCandidateService(
        revision_overlay_service=resolved_overlay_service,
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(
            identity=identity,
            output_text=output_text,
        ),
    )


def _create_paragraph_candidate(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    replacement_text: str,
):
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _ensure_draft(overlay_service, identity=identity, draft_ref=draft_ref)
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_paragraph_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        target_block_ids=[draft.blocks[1].block_id],
        comment_refs=[],
        tracked_change_refs=[],
    )
    return RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    ).create_paragraph_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        replacement_blocks=[
            ReplacementBlock(
                block_id=draft.blocks[1].block_id,
                replacement_text=replacement_text,
                order=draft.blocks[1].order,
            )
        ],
        writer_result=_writer_result(
            identity=identity,
            output_text="Patch-shaped writer result.",
        ),
    )


def _ensure_draft(
    service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
):
    existing = service.find_draft_document_by_ref(
        identity=identity,
        draft_ref=draft_ref,
    )
    if existing is not None:
        return existing
    return _record_draft(service, identity=identity, draft_ref=draft_ref)


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
        story_id=overrides.get("story_id", "story-r5"),
        session_id=overrides.get("session_id", "session-r5"),
        branch_head_id=overrides.get("branch_head_id", "branch-r5"),
        turn_id=overrides.get("turn_id", "turn-r5"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-r5",
        ),
    )
