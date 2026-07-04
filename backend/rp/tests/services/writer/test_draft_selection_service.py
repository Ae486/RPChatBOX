"""Focused tests for R5 draft selection and accept-and-continue adoption."""

from __future__ import annotations

from uuid import uuid4

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.core_state.revision_overlay_contracts import (
    LongformDraftSelectionReceipt,
    RewriteRequest,
)
from rp.models.writer.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.writer.draft_selection_service import (
    DraftSelectionService,
    DraftSelectionServiceError,
)
from rp.services.core_state.revision_overlay_service import RevisionOverlayService
from rp.services.writer.rewrite_candidate_service import RewriteCandidateService


def test_unique_candidate_can_be_adopted_without_prior_selection(retrieval_session):
    # 乙套 retired (REV-023): rewrite-candidate adoption has no live v1.2 scenario. A
    # unique candidate no longer authors a receipt here; the single live adoption path
    # is 甲套 ``accept_pending_segment``. REV-017/020 are live-guarded by the O-1 oracle.
    identity = _identity(turn_id="turn-r5-unique")
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:unique",
        output_text="Only candidate text.",
    )
    service = DraftSelectionService(session=retrieval_session)

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=candidate.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


def test_multiple_candidates_require_active_selection_or_explicit_ref(
    retrieval_session,
):
    # 乙套 retired (REV-023): multi-candidate rewrite adoption and REV-022 (selection
    # receipt in adoption source refs) have no live v1.2 scenario -> deferred to V2-02.
    identity = _identity(turn_id="turn-r5-multiple")
    first = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:multiple",
        output_text="First candidate.",
    )
    _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:multiple",
        output_text="Second candidate.",
    )
    service = DraftSelectionService(session=retrieval_session)

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=first.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


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

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=first.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


def test_active_selection_drives_adoption_but_not_before_accept_and_continue(
    retrieval_session,
):
    # Selection layer (REV-003/016) is KEPT and still works; only the 乙套 adoption
    # route is retired (REV-023). REV-022 (selection receipt in adoption source refs)
    # is deferred to V2-02 (no live scenario).
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

    assert selection.selected_output_ref == second.candidate_output_ref

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=first.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


def test_next_continuation_base_ignores_unadopted_revision_candidates(
    retrieval_session,
):
    # REV-020 (an unadopted candidate is not the continuation base) is now live-guarded
    # by the O-1 oracle (assertion 8: unadopted draft excluded from base/K-window,
    # included only after the 甲套 adoption receipt). The 乙套 adoption route is retired.
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

    selection = service.select_candidate(
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

    assert selection.selected_output_ref == adopted.candidate_output_ref

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=first.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


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

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=other_branch,
            turn_id=other_branch.turn_id,
            draft_ref=candidate.draft_ref,
            selected_output_ref=candidate.candidate_output_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


def test_adoption_receipt_is_review_sidecar_not_core_truth(retrieval_session):
    # REV-017 (adoption receipt is a Runtime Workspace review sidecar, not core/accepted
    # truth) is now live-guarded by the O-1 oracle (assertion 7). The 乙套 route here is
    # retired; the live 甲套 receipt is what O-1 asserts stays non-canonical.
    identity = _identity(turn_id="turn-r5-material")
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref="draft:r5:material",
        output_text="Adopted candidate.",
    )
    service = DraftSelectionService(session=retrieval_session)

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=candidate.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"


def test_accept_and_continue_does_not_auto_resolve_comments(retrieval_session):
    # FLAG (REV-007): "rewrite does not auto-resolve/delete comments" is re-expressed in
    # the S6-7 memo (comments degraded to passive memos in v1.2). The 乙套 adoption route
    # that used to carry this guard is retired, so the post-adoption comment state cannot
    # be exercised through it here; REV-007's live guard is deferred to S6-7.
    identity = _identity(turn_id="turn-r5-comments")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_ref="artifact:r5:comments",
        mode="viewing",
    )
    comment = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Keep this comment active after adoption.",
        selected_excerpt="The storm arrived at dusk.",
    )
    candidate = _create_full_candidate(
        retrieval_session,
        identity=identity,
        draft_ref=overlay.draft_ref,
        output_text="Candidate with unresolved comment.",
        comment_refs=[comment.comment_id],
    )
    service = DraftSelectionService(session=retrieval_session)

    with pytest.raises(DraftSelectionServiceError) as retired:
        service.adopt_for_continue(
            identity=identity,
            turn_id=identity.turn_id,
            draft_ref=candidate.draft_ref,
        )
    assert retired.value.code == "revision_adoption_route_retired"

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
    comment_refs: list[str] | None = None,
):
    request = _rewrite_request(
        identity,
        draft_ref=draft_ref,
        comment_refs=comment_refs or [],
    )
    return RewriteCandidateService(
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(
            identity=identity,
            output_text=output_text,
        ),
    )


def _rewrite_request(
    identity: MemoryRuntimeIdentity,
    *,
    draft_ref: str,
    comment_refs: list[str] | None = None,
) -> RewriteRequest:
    # Mirrors writing_assistant_service._record_rewrite_candidate: no materialized
    # draft; the request carries runtime identity metadata for the candidate gate.
    return RewriteRequest(
        request_id=f"rewrite_request_{uuid4().hex[:12]}",
        session_id=identity.session_id,
        turn_id=identity.turn_id,
        draft_ref=draft_ref,
        draft_document_id=f"light_draft:{uuid4().hex[:12]}",
        rewrite_scope="full",
        global_instruction="Rewrite this candidate.",
        comment_refs=comment_refs or [],
        metadata_json={
            "story_id": identity.story_id,
            "session_id": identity.session_id,
            "branch_head_id": identity.branch_head_id,
            "turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
        },
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
