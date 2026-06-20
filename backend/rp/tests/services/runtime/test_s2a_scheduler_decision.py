"""Oracle S2a: deterministic scheduler decision / validation (D1-D10).

Standalone unit oracle over ``SchedulerDecisionService.decide`` — the propose->decide
front-half of S2 (AUTH-002/003/004). It pins that a deterministic scheduler validates
an ``OrchestratorDispatchToolInput`` against snapshot-pinned ``RuntimeWorkerRegistry``
truth and emits a fail-closed ``WorkerExecutionPlan(plan_source=ORCHESTRATOR)``: every
illegal selection lands in ``skipped_workers`` with a FROZEN central reason code and is
NEVER dispatched. Grounded in S2a/02-design.md rev.2 (codex-P3-ratified).

S2b is the real consumer gate (propose->decide->job->ingest end-to-end through
trigger_post_write); this file is the unit gate for the deterministic validator.

Production surface pinned (ALL absent today -> RED-by-design; leader-verified grep:
zero OrchestratorDispatch*/SchedulerDecision* classes):
- rp.models.runtime.orchestrator_dispatch.{OrchestratorDispatchSelection,
  OrchestratorDispatchToolInput, OrchestratorPlanProposal}
- rp.models.runtime.reason_codes.{SchedulerReasonCode, SchedulerFailureCategory}
- rp.services.runtime.scheduler_decision_service.{SchedulerDecisionService,
  SchedulerDecisionError}

No assertion may be weakened to green; no xfail. Imports are ImportError-guarded so the
file COLLECTS before S2a lands; the symbol-presence asserts fail cleanly (not collection
errors) until the implementation exists.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.writer.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    RuntimeWorkerRegistry,
    WorkerDescriptor,
    WorkerExecutionClass,
    WorkerExecutionPolicy,
    WorkerPlanSource,
)

try:  # S2a surfaces, guarded so the file COLLECTS even before S2a lands.
    from rp.models.runtime.orchestrator_dispatch import (
        OrchestratorDispatchSelection,
        OrchestratorDispatchToolInput,
    )
except ImportError:  # pragma: no cover - RED-by-design until S2a lands
    OrchestratorDispatchSelection = None  # type: ignore[assignment]
    OrchestratorDispatchToolInput = None  # type: ignore[assignment]

try:
    from rp.models.runtime.reason_codes import (
        SchedulerFailureCategory,
        SchedulerReasonCode,
    )
except ImportError:  # pragma: no cover
    SchedulerFailureCategory = None  # type: ignore[assignment]
    SchedulerReasonCode = None  # type: ignore[assignment]

try:
    from rp.services.runtime.scheduler_decision_service import (
        SchedulerDecisionError,
        SchedulerDecisionService,
    )
except ImportError:  # pragma: no cover
    SchedulerDecisionError = None  # type: ignore[assignment]
    SchedulerDecisionService = None  # type: ignore[assignment]


_SNAPSHOT = "snap-s2a"
_PHASE = "post_write_maintenance"


def _identity(snapshot_id: str = _SNAPSHOT) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id="story-s2a",
        session_id="session-s2a",
        branch_head_id="branch-s2a",
        turn_id="turn-s2a",
        runtime_profile_snapshot_id=snapshot_id,
    )


def _policy() -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id="policy-s2a",
        execution_class=WorkerExecutionClass.SCHEDULED,
        blocking_default=True,
        allow_async=False,
        allow_degrade=True,
        must_record_trace=True,
        requires_runtime_workspace=False,
        requires_post_write_job=True,
    )


def _registration(
    worker_id: str,
    *,
    active: bool = True,
    supported_phases: list[str] | None = None,
) -> RuntimeWorkerRegistration:
    return RuntimeWorkerRegistration(
        descriptor=WorkerDescriptor(
            worker_id=worker_id,
            display_name=worker_id,
            default_execution_policy="policy-s2a",
            supported_phases=supported_phases or [_PHASE],
        ),
        execution_policy=_policy(),
        active=active,
        source_worker_id=worker_id,
    )


def _registry(
    *workers: RuntimeWorkerRegistration,
    snapshot_id: str | None = _SNAPSHOT,
) -> RuntimeWorkerRegistry:
    return RuntimeWorkerRegistry(
        snapshot_id=snapshot_id,
        mode="longform",
        registry_version="v1",
        workers=list(workers),
    )


def _require_impl() -> None:
    assert SchedulerDecisionService is not None, (
        "AUTH-002/004: rp.services.runtime.scheduler_decision_service."
        "SchedulerDecisionService is not implemented (S2a)."
    )
    assert OrchestratorDispatchToolInput is not None, (
        "AUTH-002: rp.models.runtime.orchestrator_dispatch.OrchestratorDispatchToolInput "
        "is not implemented (S2a)."
    )
    assert SchedulerReasonCode is not None, (
        "AUTH-012: rp.models.runtime.reason_codes.SchedulerReasonCode is not "
        "implemented (S2a)."
    )


def _decide(dispatch_input, registry, *, source_unit_count: int = 4):
    return SchedulerDecisionService().decide(
        identity=_identity(),
        phase=_PHASE,
        dispatch_input=dispatch_input,
        registry=registry,
        source_unit_count=source_unit_count,
    )


def _sel(worker_id: str, *, source_unit_numbers=None, reason_codes=None):
    return OrchestratorDispatchSelection(
        worker_id=worker_id,
        source_unit_numbers=source_unit_numbers if source_unit_numbers is not None else [1, 2],
        reason_codes=reason_codes or [],
    )


def test_d1_unknown_worker_skipped_not_selected() -> None:
    """D1 [AUTH-004/002]: unknown worker_id -> skipped ORCHESTRATOR_SCHEMA_INVALID."""
    _require_impl()
    plan = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("ghost_worker")]),
        _registry(_registration("w_real")),
    )
    assert [item.worker_id for item in plan.selected_workers] == []
    skips = {s.worker_id: s for s in plan.skipped_workers}
    assert "ghost_worker" in skips
    assert SchedulerReasonCode.ORCHESTRATOR_SCHEMA_INVALID.value in skips["ghost_worker"].reason_codes


def test_d2_inactive_worker_skipped_disabled() -> None:
    """D2 [AUTH-002]: inactive-in-snapshot worker -> skipped WORKER_DISABLED."""
    _require_impl()
    plan = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("w_off")]),
        _registry(_registration("w_off", active=False)),
    )
    assert plan.selected_workers == []
    skips = {s.worker_id: s for s in plan.skipped_workers}
    assert SchedulerReasonCode.WORKER_DISABLED.value in skips["w_off"].reason_codes


def test_d3_phase_not_supported_skipped_not_active() -> None:
    """D3 [AUTH-004]: phase not in supported_phases -> skipped WORKER_NOT_ACTIVE."""
    _require_impl()
    plan = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("w_other_phase")]),
        _registry(_registration("w_other_phase", supported_phases=["pre_write_context"])),
    )
    assert plan.selected_workers == []
    skips = {s.worker_id: s for s in plan.skipped_workers}
    assert SchedulerReasonCode.WORKER_NOT_ACTIVE.value in skips["w_other_phase"].reason_codes


def test_d4_source_units_empty_and_out_of_range() -> None:
    """D4 [AUTH-004]: empty -> SOURCE_WINDOW_EMPTY; out-of-range -> PARAGRAPH_NUMBER_OUT_OF_RANGE."""
    _require_impl()
    empty = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("w_real", source_unit_numbers=[])]),
        _registry(_registration("w_real")),
    )
    assert SchedulerReasonCode.SOURCE_WINDOW_EMPTY.value in (
        {s.worker_id: s for s in empty.skipped_workers}["w_real"].reason_codes
    )
    out = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("w_real", source_unit_numbers=[99])]),
        _registry(_registration("w_real")),
        source_unit_count=4,
    )
    assert SchedulerReasonCode.PARAGRAPH_NUMBER_OUT_OF_RANGE.value in (
        {s.worker_id: s for s in out.skipped_workers}["w_real"].reason_codes
    )


def test_d5_valid_selection_materializes_orchestrator_request() -> None:
    """D5 [AUTH-002/003]: valid selection -> selected; plan is the scheduler-visible request."""
    _require_impl()
    plan = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("w_real")]),
        _registry(_registration("w_real")),
    )
    assert plan.plan_source == WorkerPlanSource.ORCHESTRATOR
    selected = {item.worker_id: item for item in plan.selected_workers}
    assert "w_real" in selected
    # policy fields derived from the registration (AUTH-004 deterministic), not the proposal.
    assert selected["w_real"].blocking is True
    assert selected["w_real"].async_allowed is False


def test_d6_mixed_proposal_fail_closed() -> None:
    """D6 [fail-closed]: 1 valid + 1 illegal -> illegal NEVER selected."""
    _require_impl()
    plan = _decide(
        OrchestratorDispatchToolInput(selections=[_sel("w_real"), _sel("ghost")]),
        _registry(_registration("w_real")),
    )
    assert [i.worker_id for i in plan.selected_workers] == ["w_real"]
    assert "ghost" in {s.worker_id for s in plan.skipped_workers}


def test_d7_dispatch_schema_forbids_extra_fields() -> None:
    """D7 [AUTH-002]: extra="forbid" blocks smuggling non-routing payload (selection + tool-input)."""
    assert OrchestratorDispatchSelection is not None, (
        "AUTH-002: OrchestratorDispatchSelection is not implemented (S2a)."
    )
    assert OrchestratorDispatchToolInput is not None, (
        "AUTH-002: OrchestratorDispatchToolInput is not implemented (S2a)."
    )
    with pytest.raises(ValidationError):
        OrchestratorDispatchSelection(
            worker_id="w_real",
            source_unit_numbers=[1],
            field_path="core.character.name",  # forbidden non-routing payload
            new_value="x",
        )
    # the tool-input envelope itself must also reject smuggled top-level payload.
    with pytest.raises(ValidationError):
        OrchestratorDispatchToolInput(
            selections=[_sel("w_real")],
            rewritten_text="smuggled candidate content",  # forbidden at envelope level
        )


def test_d8_orchestrator_reason_codes_not_in_central_channel() -> None:
    """D8 [central reason-code closure]: orchestrator codes never reach item.reason_codes."""
    _require_impl()
    plan = _decide(
        OrchestratorDispatchToolInput(
            selections=[_sel("w_real", reason_codes=["my_local_alias"])]
        ),
        _registry(_registration("w_real")),
    )
    item = {i.worker_id: i for i in plan.selected_workers}["w_real"]
    assert "my_local_alias" not in item.reason_codes
    # advisory orchestrator hints are namespaced, NOT the central reason-code channel.
    assert "my_local_alias" in item.scheduler_constraints.get("orchestrator_reason_codes", [])


def test_d9_snapshot_mismatch_fails_closed_before_any_plan() -> None:
    """D9 [AUTH-004]: registry/identity snapshot mismatch -> raise (VALIDATION_ERROR) before any dispatch."""
    assert SchedulerDecisionError is not None, (
        "AUTH-004: SchedulerDecisionError is not implemented (S2a)."
    )
    assert SchedulerFailureCategory is not None, (
        "AUTH-004: SchedulerFailureCategory is not implemented (S2a)."
    )
    with pytest.raises(SchedulerDecisionError) as exc_info:
        SchedulerDecisionService().decide(
            identity=_identity(snapshot_id="snap-A"),
            phase=_PHASE,
            dispatch_input=OrchestratorDispatchToolInput(selections=[_sel("w_real")]),
            registry=_registry(_registration("w_real"), snapshot_id="snap-B"),
            source_unit_count=4,
        )
    assert exc_info.value.category == SchedulerFailureCategory.VALIDATION_ERROR


def test_d10_missing_snapshot_fails_closed_before_any_plan() -> None:
    """D10 [AUTH-004]: an unpinned registry (snapshot_id=None) cannot validate -> fail closed."""
    assert SchedulerDecisionError is not None, (
        "AUTH-004: SchedulerDecisionError is not implemented (S2a)."
    )
    assert SchedulerFailureCategory is not None, (
        "AUTH-004: SchedulerFailureCategory is not implemented (S2a)."
    )
    with pytest.raises(SchedulerDecisionError) as exc_info:
        SchedulerDecisionService().decide(
            identity=_identity(),
            phase=_PHASE,
            dispatch_input=OrchestratorDispatchToolInput(selections=[_sel("w_real")]),
            registry=_registry(_registration("w_real"), snapshot_id=None),
            source_unit_count=4,
        )
    assert exc_info.value.category == SchedulerFailureCategory.VALIDATION_ERROR
