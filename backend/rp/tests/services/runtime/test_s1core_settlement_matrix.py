"""Oracle node-5 Tier-A: settlement decision matrix M1-M5.

Service-level oracle over ``RuntimeWorkflowJobService.evaluate_turn_settlement``
(backend/rp/services/runtime/workflow_job_service.py:332). This is the *pure*
settlement decision: it reads turn acceptance + the turn-scoped required-job
ledger and returns a ``TurnSettlementEvaluation`` (it does NOT flip turn.status;
that belongs to the settle path). The matrix locks the frozen SoT rows:

  M1  all required jobs terminal (COMPLETED/DEFERRED) -> settleable      [TURN-004]
  M2  a required job non-terminal                     -> not settleable  [TURN-004]
  M3  ZERO required jobs (intake->pre-writer window)   -> not settleable  guard :356-362
  M4  a non-required job of any category non-terminal -> does NOT block  [TURN-005]
  M5  scheduler_maintenance_gate required/terminal bridge                [WRK-008]

M4 proves settlement keys on the ``required_for_turn_completion`` flag, NOT on
``job_category`` (workflow_job_service.py:343-347). M5 is RED-by-design: the
``scheduler_maintenance_gate`` job_kind is specced (seams.md:367-372) but NOT yet
present in ``RuntimeWorkflowJobKind``; the kind is resolved via getattr INSIDE the
test body so the file still COLLECTS, then a clean assertion fails on the gap.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.tests.helpers.runtime_seed import seed_runtime_identity


@dataclass(frozen=True)
class _JobSpec:
    """One ledger row to seed for a matrix case.

    ``kind_name`` is resolved against ``RuntimeWorkflowJobKind`` via getattr at
    test time so a missing enum member (M5) yields a clean failing assertion
    instead of a collection error.
    """

    kind_name: str
    category: RuntimeWorkflowJobCategory
    required: bool
    final_status: RuntimeWorkflowJobStatus


@dataclass(frozen=True)
class _MatrixCase:
    job_specs: tuple[_JobSpec, ...]
    expected_eligible: bool
    expected_reason: str | None
    expected_required_count: int
    expected_blocking_count: int


_COMPLETED = RuntimeWorkflowJobStatus.COMPLETED
_DEFERRED = RuntimeWorkflowJobStatus.DEFERRED
_PENDING = RuntimeWorkflowJobStatus.PENDING

# Two real required obligation kinds (creation-time obligations) reused for the
# acceptance-satisfied rows; a derived non-required kind for the M4 isolation row.
_REQUIRED_A = "REQUIRED_POST_WRITE_ANALYSIS"
_REQUIRED_B = "RUNTIME_WORKSPACE_FINALIZE"
_NON_REQUIRED = "PROJECTION_REFRESH"
_GATE = "SCHEDULER_MAINTENANCE_GATE"  # WRK-008 red-gap: not yet in the enum.

_CASES: dict[str, _MatrixCase] = {
    # M1 - every required job is terminal (one COMPLETED + one DEFERRED) -> settle.
    "M1": _MatrixCase(
        job_specs=(
            _JobSpec(_REQUIRED_A, RuntimeWorkflowJobCategory.TURN_FINALIZATION, True, _COMPLETED),
            _JobSpec(_REQUIRED_B, RuntimeWorkflowJobCategory.TURN_FINALIZATION, True, _DEFERRED),
        ),
        expected_eligible=True,
        expected_reason="required_jobs_deferred_by_policy",
        expected_required_count=2,
        expected_blocking_count=0,
    ),
    # M2 - one required job still non-terminal -> blocked even though the other is done.
    "M2": _MatrixCase(
        job_specs=(
            _JobSpec(_REQUIRED_A, RuntimeWorkflowJobCategory.TURN_FINALIZATION, True, _COMPLETED),
            _JobSpec(_REQUIRED_B, RuntimeWorkflowJobCategory.TURN_FINALIZATION, True, _PENDING),
        ),
        expected_eligible=False,
        expected_reason=None,
        expected_required_count=2,
        expected_blocking_count=1,
    ),
    # M3 - intake->pre-writer window: ZERO required jobs -> not settleable (guard).
    "M3": _MatrixCase(
        job_specs=(),
        expected_eligible=False,
        expected_reason=None,
        expected_required_count=0,
        expected_blocking_count=0,
    ),
    # M4 - a non-required job (any category) non-terminal does NOT block settlement.
    "M4": _MatrixCase(
        job_specs=(
            _JobSpec(_REQUIRED_A, RuntimeWorkflowJobCategory.TURN_FINALIZATION, True, _COMPLETED),
            _JobSpec(_NON_REQUIRED, RuntimeWorkflowJobCategory.STATE_GOVERNANCE, False, _PENDING),
        ),
        expected_eligible=True,
        expected_reason="all_required_jobs_completed",
        expected_required_count=1,
        expected_blocking_count=0,
    ),
    # M5a - scheduler_maintenance_gate required + non-terminal -> blocks the turn.
    "M5a": _MatrixCase(
        job_specs=(
            _JobSpec(_GATE, RuntimeWorkflowJobCategory.STATE_GOVERNANCE, True, _PENDING),
        ),
        expected_eligible=False,
        expected_reason=None,
        expected_required_count=1,
        expected_blocking_count=1,
    ),
    # M5b - scheduler_maintenance_gate required + terminal (DEFERRED) -> bridges to settle.
    "M5b": _MatrixCase(
        job_specs=(
            _JobSpec(_GATE, RuntimeWorkflowJobCategory.STATE_GOVERNANCE, True, _DEFERRED),
        ),
        expected_eligible=True,
        expected_reason="required_jobs_deferred_by_policy",
        expected_required_count=1,
        expected_blocking_count=0,
    ),
}


def _apply_final_status(
    service: RuntimeWorkflowJobService,
    *,
    job_id: str,
    final_status: RuntimeWorkflowJobStatus,
) -> None:
    if final_status == _COMPLETED:
        service.mark_job_completed(job_id=job_id, reason="settlement-matrix")
    elif final_status == _DEFERRED:
        service.mark_job_deferred(job_id=job_id, reason="settlement-matrix")
    # PENDING: leave as created (non-terminal).


@pytest.mark.parametrize("case_id", list(_CASES), ids=list(_CASES))
def test_settlement_matrix(retrieval_session, case_id: str) -> None:
    case = _CASES[case_id]
    identity = seed_runtime_identity(
        retrieval_session,
        story_id=f"settlement-matrix-{case_id.lower()}",
    )
    service = RuntimeWorkflowJobService(retrieval_session)

    for spec in case.job_specs:
        kind = getattr(RuntimeWorkflowJobKind, spec.kind_name, None)
        assert kind is not None, (
            f"WRK-008: RuntimeWorkflowJobKind.{spec.kind_name} is not implemented "
            "(scheduler_maintenance_gate seam — seams.md:367-372). This job_kind is "
            "required for the maintenance-gate settlement bridge."
        )
        job = service.ensure_job(
            identity=identity,
            job_kind=kind,
            job_category=spec.category,
            creation_mode=(
                RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION
                if spec.required
                else RuntimeWorkflowJobCreationMode.DERIVED
            ),
            required_for_turn_completion=spec.required,
        )
        _apply_final_status(service, job_id=job.job_id, final_status=spec.final_status)

    evaluation = service.evaluate_turn_settlement(turn_id=identity.turn_id)

    assert evaluation.eligible is case.expected_eligible
    assert evaluation.settlement_reason == case.expected_reason
    assert len(evaluation.required_job_ids) == case.expected_required_count
    assert len(evaluation.blocking_job_ids) == case.expected_blocking_count
