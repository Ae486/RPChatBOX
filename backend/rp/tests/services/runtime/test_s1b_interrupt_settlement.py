"""Oracle S1b Tier-B: service-level interrupt settlement + receipt (B1-B4).

Service-level oracle (settlement-matrix pattern) over the interrupt-finalize seam:
``RuntimeWorkflowJobService.mark_required_jobs_failed``,
``RuntimeWorkflowJobService.evaluate_turn_settlement`` (exists),
``StoryTurnDomainService.finalize_interrupted_turn`` and
``StoryTurnDomainService.list_interrupt_receipts``. Grounded in
S1b/02-oracle-design.md rev.2 (ratified).

Production surface this oracle pins (the new symbols are absent today -> RED):
- ``RuntimeWorkflowJobService.mark_required_jobs_failed(*, identity, reason)`` ->
  status=FAILED (never DEFERRED). Today only ``mark_required_jobs_deferred`` exists.
- ``StoryTurnDomainService.finalize_interrupted_turn(*, turn_id, reason)`` ->
  turn FAILED(failure_reason) + idempotent interrupt receipt; never accepts.
- ``StoryTurnDomainService.list_interrupt_receipts(*, turn_id)`` -> receipts each
  carrying a ``reason`` field; dedupe key ``turn_id+reason``.
- the shared ``interrupted_by_restart`` reason-code constant (AUTH-012 closed set).

Per-assertion SoT mapping + RED status (all four are GENUINELY RED today because
the finalize/receipt/job-failure wiring does not exist):
- B1 [AUTH-014]    a failed required job lands on status==FAILED (not DEFERRED)
                   AND its dedicated ``failure_reason`` field carries the reason.
- B2 [AUTH-014]    settlement stays blocked because FAILED is NOT a terminal
                   settlement status (FAILED not in _SETTLEMENT_TERMINAL_STATUSES);
                   the DEFERRED-instead-of-FAILED mutation flips this to eligible.
- B3 [idempotency] finalize_interrupted_turn twice == exactly ONE receipt.
- B4 [AUTH-014]    a mid-stream abort with ZERO required jobs yet still finalizes
                   the turn FAILED + emits a receipt, and settlement stays blocked
                   (acceptance is never flipped to accepted).

No assertion may be weakened to green and no ``xfail`` is used.
"""

from __future__ import annotations

from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.story.runtime import LongformTurnCommandKind
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.turn_domain_service import StoryTurnDomainService
from rp.tests.helpers.runtime_seed import seed_runtime_identity
from rp.tests.services.projection.test_projection_builder_services import (
    _build_turn_domain_service,
    _seed_story_runtime,
)


# AUTH-012 closed-set reason code; impl must also export it as a shared constant.
_INTERRUPTED_BY_RESTART = "interrupted_by_restart"

# S1b surfaces, guarded so the file COLLECTS even before S1b lands.
_mark_required_jobs_failed = getattr(
    RuntimeWorkflowJobService, "mark_required_jobs_failed", None
)
_finalize_interrupted_turn = getattr(
    StoryTurnDomainService, "finalize_interrupted_turn", None
)
_list_interrupt_receipts = getattr(
    StoryTurnDomainService, "list_interrupt_receipts", None
)


def _seed_required_obligation(
    service: RuntimeWorkflowJobService, identity
) -> RuntimeWorkflowJobRecord:
    return service.ensure_job(
        identity=identity,
        job_kind=RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
        job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
        creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
        required_for_turn_completion=True,
    )


def _build_interrupt_domain_service(retrieval_session):
    """Seed a story runtime + intake turn and return (domain_service, turn_id)."""

    session, _chapter, story_service = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.s1b.interrupt",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    retrieval_session.commit()
    domain_service = _build_turn_domain_service(
        story_service,
        runtime_identity_service=identity_service,
        runtime_workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
    )
    return domain_service, identity.turn_id


def test_b1_mark_required_jobs_failed_sets_failed_not_deferred(
    retrieval_session,
) -> None:
    identity = seed_runtime_identity(retrieval_session, story_id="s1b-interrupt-b1")
    service = RuntimeWorkflowJobService(retrieval_session)
    job = _seed_required_obligation(service, identity)

    assert _mark_required_jobs_failed is not None, (
        "AUTH-014: RuntimeWorkflowJobService.mark_required_jobs_failed is not "
        "implemented. The interrupt path must fail required jobs (status=FAILED), "
        "not defer them."
    )
    service.mark_required_jobs_failed(
        identity=identity,
        reason=_INTERRUPTED_BY_RESTART,
    )

    reloaded = retrieval_session.get(RuntimeWorkflowJobRecord, job.job_id)
    assert reloaded is not None
    assert reloaded.status == RuntimeWorkflowJobStatus.FAILED.value
    # [P3 TOP-3] the job's dedicated failure_reason field must carry the reason
    # (rp_story_store.py:353); a status-only impl must not false-green.
    assert reloaded.failure_reason == _INTERRUPTED_BY_RESTART


def test_b2_failed_required_job_keeps_settlement_blocked(
    retrieval_session,
) -> None:
    identity = seed_runtime_identity(retrieval_session, story_id="s1b-interrupt-b2")
    service = RuntimeWorkflowJobService(retrieval_session)
    _seed_required_obligation(service, identity)

    assert _mark_required_jobs_failed is not None, (
        "AUTH-014: RuntimeWorkflowJobService.mark_required_jobs_failed is not "
        "implemented (see B1)."
    )
    service.mark_required_jobs_failed(
        identity=identity,
        reason=_INTERRUPTED_BY_RESTART,
    )

    # FAILED is NOT in _SETTLEMENT_TERMINAL_STATUSES, so it must keep the turn
    # blocked. A DEFERRED-instead-of-FAILED mutation would wrongly settle it.
    evaluation = service.evaluate_turn_settlement(turn_id=identity.turn_id)
    assert evaluation.eligible is False
    assert evaluation.blocking_job_ids != ()


def test_b3_finalize_interrupted_turn_receipt_is_idempotent(
    retrieval_session,
) -> None:
    domain_service, turn_id = _build_interrupt_domain_service(retrieval_session)

    assert _finalize_interrupted_turn is not None, (
        "AUTH-014: StoryTurnDomainService.finalize_interrupted_turn is not "
        "implemented."
    )
    assert _list_interrupt_receipts is not None, (
        "AUTH-014: StoryTurnDomainService.list_interrupt_receipts is not "
        "implemented."
    )

    domain_service.finalize_interrupted_turn(
        turn_id=turn_id,
        reason=_INTERRUPTED_BY_RESTART,
    )
    # Second finalize with the same turn_id+reason must dedupe to one receipt.
    domain_service.finalize_interrupted_turn(
        turn_id=turn_id,
        reason=_INTERRUPTED_BY_RESTART,
    )

    receipts = domain_service.list_interrupt_receipts(turn_id=turn_id)
    assert len(receipts) == 1
    assert receipts[0].reason == _INTERRUPTED_BY_RESTART


def test_b4_finalize_with_zero_required_jobs_still_fails_and_blocks(
    retrieval_session,
) -> None:
    domain_service, turn_id = _build_interrupt_domain_service(retrieval_session)

    assert _finalize_interrupted_turn is not None, (
        "AUTH-014: StoryTurnDomainService.finalize_interrupted_turn is not "
        "implemented (see B3)."
    )
    assert _list_interrupt_receipts is not None, (
        "AUTH-014: StoryTurnDomainService.list_interrupt_receipts is not "
        "implemented (see B3)."
    )

    # Mid-stream abort BEFORE any obligation was created: zero required jobs yet.
    assert (
        RuntimeWorkflowJobService(retrieval_session).list_jobs_for_turn(
            turn_id=turn_id
        )
        == []
    )

    domain_service.finalize_interrupted_turn(
        turn_id=turn_id,
        reason=_INTERRUPTED_BY_RESTART,
    )

    retrieval_session.expire_all()
    turn = retrieval_session.get(StoryTurnRecord, turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.FAILED.value
    assert turn.failure_reason == _INTERRUPTED_BY_RESTART

    receipts = domain_service.list_interrupt_receipts(turn_id=turn_id)
    assert len(receipts) == 1

    # Settlement stays blocked: acceptance was never flipped to accepted (and the
    # zero-required-job guard alone would also block it).
    evaluation = RuntimeWorkflowJobService(
        retrieval_session
    ).evaluate_turn_settlement(turn_id=turn_id)
    assert evaluation.eligible is False
