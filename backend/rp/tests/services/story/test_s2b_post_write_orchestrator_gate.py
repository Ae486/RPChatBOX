"""RED-by-design oracle for slice S2b — consumer-wired scheduler decision +
job/gate/guard lifecycle (WRK-007 / WRK-008 / NUM-016 / AUTH-002/003/004).

This file pins the S2b production surfaces that DO NOT EXIST yet. It must collect
cleanly (no S2b symbol is imported at module top); every S2b surface is exercised
INSIDE a test body, so its absence today is a clean runtime FAILURE:

  * ``OrchestratorPlanProposal.source_unit_count``            -> pydantic ValidationError
  * ``PostWriteSchedulerService(scheduler_decision_service=,
        worker_registry_service=)`` + ``build_worker_plan(proposal=)``
  * ``RuntimeWorkflowJobService.ensure_scheduler_maintenance_gate(...)``
        / ``ensure_job(anchor_turn_id=)`` / ``RuntimeWorkflowJobRecord.anchor_turn_id``
  * ``StoryTurnDomainService(orchestrator_dispatch_provider=)``

When S2b lands per ``02-design.md`` (E1-E5), G1-G11 turn GREEN. No assertion is
weakened, no xfail, no skip.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.models.proposal.postwrite_runtime_contracts import (
    PostWriteGovernanceDispatchResult,
    PostWriteRunKind,
)
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.orchestrator_dispatch import (
    OrchestratorDispatchSelection,
    OrchestratorDispatchToolInput,
    OrchestratorPlanProposal,
)
from rp.models.runtime.reason_codes import SchedulerFailureCategory, SchedulerReasonCode
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
)
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    SpecialistResultBundle,
)
from rp.models.writer.worker_runtime_contracts import (
    WorkerPlanSource,
    WorkerResult,
    WorkerResultStatus,
)
from rp.services.projection.builder_context_service import (
    BuilderProjectionContextService,
)
from rp.services.projection.chapter_workspace_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection.state_service import ProjectionStateService
from rp.services.proposal.post_write_scheduler_service import (
    POST_WRITE_MAINTENANCE_PHASE,
    PostWriteSchedulerService,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.scheduler_decision_service import (
    SchedulerDecisionError,
    SchedulerDecisionService,
)
from rp.services.runtime.workflow_job_service import (
    RuntimeWorkflowJobService,
    RuntimeWorkflowJobServiceError,
)
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.services.story.turn_domain_service import StoryTurnDomainService
from rp.services.writer.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WorkerRegistryService,
)
from rp.services.writer.worker_scheduler_service import WorkerSchedulerService
from rp.services.writer.writing_packet_builder import WritingPacketBuilder


_UNKNOWN_WORKER_ID = "GhostWorker"
_UNKNOWN_WORKER_ID_2 = "PhantomWorker"


# --------------------------------------------------------------------------- #
# Local test doubles (own this file — do not import projection-module privates).
# --------------------------------------------------------------------------- #
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
        self, *, session, chapter, model_id, provider_id, runtime_identity=None
    ):
        return session, chapter


class _FakeOrchestratorDispatchProvider:
    """S2b OrchestratorDispatchProvider seam: yields a configurable proposal."""

    def __init__(self, proposal: OrchestratorPlanProposal | None) -> None:
        self._proposal = proposal
        self.calls: list[dict[str, object]] = []

    def propose(self, *, identity, phase, turn, trigger_context):
        self.calls.append(
            {
                "identity": identity,
                "phase": phase,
                "turn": turn,
                "trigger_context": trigger_context,
            }
        )
        return self._proposal


class _FakeWorkerExecutionService:
    """Faithful executor fake: produces one WorkerResult per *selected* worker."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.received_plan = None
        self.produced_results: list[WorkerResult] = []

    async def execute_plan(self, **kwargs):
        self.calls.append(kwargs)
        plan = kwargs.get("plan")
        self.received_plan = plan
        selected = list(plan.selected_workers) if plan is not None else []
        results = [
            WorkerResult(
                worker_id=item.worker_id,
                phase=plan.phase,
                result_status=WorkerResultStatus.COMPLETED,
            )
            for item in selected
        ]
        self.produced_results = results
        return SimpleNamespace(
            plan=plan,
            worker_results=results,
            specialist_bundle=SpecialistResultBundle(),
        )


class _FakeGovernanceService:
    """Governance fake: returns an empty (but real-typed) dispatch result."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch_worker_results(self, **kwargs):
        self.calls.append(kwargs)
        return PostWriteGovernanceDispatchResult()


class _SnapshotMismatchRegistryService:
    """Returns a deliberately misconstructed registry whose ``snapshot_id`` does
    not match the runtime identity, forcing ``SchedulerDecisionService.decide()``
    to fail closed (the only consumer path that reaches the snapshot guard)."""

    def __init__(self, registry) -> None:
        self._registry = registry

    def build_registry_for_snapshot(self, *, snapshot_id):
        return self._registry


# --------------------------------------------------------------------------- #
# Seeding helpers (real session/snapshot/turn/material — mirrors the projection
# full-schedule harness, trimmed to what the post-write trigger consumes).
# --------------------------------------------------------------------------- #
def _seed_story_runtime(session, *, story_id: str):
    workspace = SetupWorkspaceService(session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    service = StorySessionService(session)
    story_session = service.create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=story_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Chapter 1",
    )
    service.commit()
    return service, story_session, chapter


def _seed_ready_turn(session, *, story_id: str) -> SimpleNamespace:
    service, story_session, chapter = _seed_story_runtime(session, story_id=story_id)
    snapshot_service = RuntimeProfileSnapshotService(session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.s2b.post_write_orchestrator_gate",
    )
    identity_service = StoryRuntimeIdentityService(
        session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    # Move the turn into a post-write-ready status so trigger_post_write proceeds.
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    material_service = RuntimeWorkspaceMaterialService(session=session)
    # Retrieval usage makes should_run_full_schedule() true (full-schedule path).
    material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="retrieval-usage-s2b",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.retrieval.usage",
            payload={
                "used_card_material_ids": ["retrieval-card-s2b"],
                "knowledge_gaps": [],
            },
            visibility="runtime_private",
            created_by="test",
        )
    )
    workflow_job_service = RuntimeWorkflowJobService(session)
    return SimpleNamespace(
        db=session,
        service=service,
        session=story_session,
        chapter=chapter,
        snapshot=snapshot,
        identity=identity,
        identity_service=identity_service,
        material_service=material_service,
        workflow_job_service=workflow_job_service,
    )


def _make_orchestrator_proposal(
    identity,
    *,
    worker_selections: list[OrchestratorDispatchSelection],
    source_unit_count,
) -> OrchestratorPlanProposal:
    # `source_unit_count` is the additive S2b field on OrchestratorPlanProposal.
    # Today the model is `extra="forbid"` -> this raises ValidationError (RED).
    return OrchestratorPlanProposal(
        identity=identity,
        phase=POST_WRITE_MAINTENANCE_PHASE,
        dispatch_input=OrchestratorDispatchToolInput(selections=worker_selections),
        source_unit_count=source_unit_count,
    )


def _orchestrator_scheduler(
    ctx: SimpleNamespace,
    *,
    scheduler_decision_service,
    worker_registry_service,
) -> PostWriteSchedulerService:
    # `scheduler_decision_service` / `worker_registry_service` are the additive S2b
    # __init__ kwargs (absent today -> TypeError when this path is reached).
    return PostWriteSchedulerService(
        worker_scheduler_service=WorkerSchedulerService(
            worker_registry_service=WorkerRegistryService(ctx.db)
        ),
        runtime_workspace_material_service=ctx.material_service,
        scheduler_decision_service=scheduler_decision_service,
        worker_registry_service=worker_registry_service,
    )


def _bootstrap_scheduler(ctx: SimpleNamespace) -> PostWriteSchedulerService:
    return PostWriteSchedulerService(
        worker_scheduler_service=WorkerSchedulerService(
            worker_registry_service=WorkerRegistryService(ctx.db)
        ),
        runtime_workspace_material_service=ctx.material_service,
    )


def _build_turn_domain_service(
    ctx: SimpleNamespace,
    *,
    post_write_scheduler_service,
    worker_execution_service,
    post_write_governance_service,
    orchestrator_dispatch_provider,
) -> StoryTurnDomainService:
    projection_state_service = ProjectionStateService(
        story_session_service=ctx.service,
        adapter=ChapterWorkspaceProjectionAdapter(ctx.service),
    )
    # `orchestrator_dispatch_provider` is the additive S2b __init__ kwarg
    # (absent today -> TypeError on construction).
    return StoryTurnDomainService(
        story_session_service=ctx.service,
        orchestrator_service=SimpleNamespace(),
        specialist_service=SimpleNamespace(),
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        projection_state_service=projection_state_service,
        writing_packet_builder=WritingPacketBuilder(),
        writing_worker_execution_service=SimpleNamespace(),
        regression_service=_NoopRegressionService(),
        runtime_identity_service=ctx.identity_service,
        runtime_workspace_material_service=ctx.material_service,
        runtime_workflow_job_service=ctx.workflow_job_service,
        worker_execution_service=worker_execution_service,
        post_write_scheduler_service=post_write_scheduler_service,
        post_write_governance_service=post_write_governance_service,
        orchestrator_dispatch_provider=orchestrator_dispatch_provider,
    )


def _gate_jobs(ctx: SimpleNamespace) -> list[RuntimeWorkflowJobRecord]:
    return [
        job
        for job in ctx.workflow_job_service.list_jobs_for_turn(
            turn_id=ctx.identity.turn_id
        )
        if job.job_kind == RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value
    ]


def _longform_selection(
    worker_id: str = LONGFORM_MEMORY_WORKER_ID,
) -> OrchestratorDispatchSelection:
    return OrchestratorDispatchSelection(
        worker_id=worker_id,
        source_unit_numbers=[1],
        reason_codes=["orchestrator_selected"],
    )


# --------------------------------------------------------------------------- #
# G1 — (b) valid proposal -> ORCHESTRATOR plan + maintenance gate (WRK-007/008).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g1_valid_proposal_builds_orchestrator_plan_and_gate(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g1")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[_longform_selection()],
        source_unit_count=1,
    )
    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    scheduler = _orchestrator_scheduler(
        ctx,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=WorkerRegistryService(ctx.db),
    )
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    assert result["run_kind"] == PostWriteRunKind.FULL_SCHEDULE.value
    assert result["settled"] is True
    worker_plan_dump = result["metadata_json"]["worker_plan"]
    assert worker_plan_dump["plan_source"] == WorkerPlanSource.ORCHESTRATOR.value
    assert [item["worker_id"] for item in worker_plan_dump["selected_workers"]] == [
        LONGFORM_MEMORY_WORKER_ID
    ]
    # [C2] the validated source-unit selection must be carried into the plan item
    # (decide() range-checks it; it must not be dropped — S3 reads it from here).
    selected_item = worker_plan_dump["selected_workers"][0]
    assert selected_item["scheduler_constraints"]["source_unit_numbers"] == [1]
    gates = _gate_jobs(ctx)
    assert len(gates) == 1
    gate = gates[0]
    assert gate.anchor_turn_id == ctx.identity.turn_id
    # [C3] scheduler_job_id is a STABLE per-turn fingerprint (grill: window/source
    # fingerprint idempotency), NOT the ephemeral uuid4 plan_id; the plan_id is
    # carried separately for trace.
    assert gate.metadata_json["scheduler_job_id"] == (
        f"scheduler_maintenance:{ctx.identity.turn_id}"
    )
    assert gate.metadata_json["worker_plan_id"] == worker_plan_dump["plan_id"]
    assert gate.required_for_turn_completion is True

    retrieval_session.commit()
    reloaded_gate = retrieval_session.get(RuntimeWorkflowJobRecord, gate.job_id)
    assert reloaded_gate.status == RuntimeWorkflowJobStatus.COMPLETED.value
    turn = retrieval_session.get(StoryTurnRecord, ctx.identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.SETTLED.value


# --------------------------------------------------------------------------- #
# G2 — (a) illegal selection -> fail-closed skip with a frozen central code,
#      never dispatched (AUTH-002).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g2_illegal_selection_fails_closed_to_skip(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g2")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[_longform_selection(worker_id=_UNKNOWN_WORKER_ID)],
        source_unit_count=1,
    )
    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    scheduler = _orchestrator_scheduler(
        ctx,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=WorkerRegistryService(ctx.db),
    )
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    worker_plan_dump = result["metadata_json"]["worker_plan"]
    skipped_by_id = {
        item["worker_id"]: item for item in worker_plan_dump["skipped_workers"]
    }
    assert _UNKNOWN_WORKER_ID in skipped_by_id
    central_reason_codes = {code.value for code in SchedulerReasonCode}
    assert skipped_by_id[_UNKNOWN_WORKER_ID]["skip_reason"] in central_reason_codes
    assert skipped_by_id[_UNKNOWN_WORKER_ID]["skip_reason"] == (
        SchedulerReasonCode.ORCHESTRATOR_SCHEMA_INVALID.value
    )
    selected_ids = {item["worker_id"] for item in worker_plan_dump["selected_workers"]}
    assert _UNKNOWN_WORKER_ID not in selected_ids
    assert all(
        result_item.worker_id != _UNKNOWN_WORKER_ID
        for result_item in execution.produced_results
    )
    assert result["selected_worker_result_refs"] == []


# --------------------------------------------------------------------------- #
# G3 — (c) single-active guard: a different scheduler job on the same anchor is
#      rejected with maintenance_in_progress; no second gate row (NUM-016).
# --------------------------------------------------------------------------- #
def test_g3_single_active_gate_rejects_different_scheduler_job(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g3")
    ctx.workflow_job_service.ensure_scheduler_maintenance_gate(
        identity=ctx.identity,
        scheduler_job_id="scheduler-job-A",
        anchor_turn_id=ctx.identity.turn_id,
    )
    with pytest.raises(RuntimeWorkflowJobServiceError) as exc_info:
        ctx.workflow_job_service.ensure_scheduler_maintenance_gate(
            identity=ctx.identity,
            scheduler_job_id="scheduler-job-B",
            anchor_turn_id=ctx.identity.turn_id,
        )
    assert exc_info.value.code == SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value
    assert len(_gate_jobs(ctx)) == 1


# --------------------------------------------------------------------------- #
# G4 — (c) idempotent replay: same scheduler job -> same record, one gate row.
# --------------------------------------------------------------------------- #
def test_g4_idempotent_replay_same_scheduler_job(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g4")
    first = ctx.workflow_job_service.ensure_scheduler_maintenance_gate(
        identity=ctx.identity,
        scheduler_job_id="scheduler-job-A",
        anchor_turn_id=ctx.identity.turn_id,
    )
    second = ctx.workflow_job_service.ensure_scheduler_maintenance_gate(
        identity=ctx.identity,
        scheduler_job_id="scheduler-job-A",
        anchor_turn_id=ctx.identity.turn_id,
    )
    assert first.job_id == second.job_id
    assert len(_gate_jobs(ctx)) == 1


# --------------------------------------------------------------------------- #
# G5 — (d) AUTH-003: a valid orchestrator run materializes the gate ledger row
#      tying cross-role work to the durable ledger.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g5_orchestrator_run_materializes_gate_ledger_row(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g5")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[_longform_selection()],
        source_unit_count=1,
    )
    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    scheduler = _orchestrator_scheduler(
        ctx,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=WorkerRegistryService(ctx.db),
    )
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    retrieval_session.commit()
    gates = _gate_jobs(ctx)
    assert len(gates) == 1
    reloaded_gate = retrieval_session.get(RuntimeWorkflowJobRecord, gates[0].job_id)
    assert reloaded_gate is not None
    assert reloaded_gate.job_kind == (
        RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value
    )
    assert reloaded_gate.turn_id == ctx.identity.turn_id
    assert reloaded_gate.anchor_turn_id == ctx.identity.turn_id


# --------------------------------------------------------------------------- #
# G6 — (WRK-007 unit) ensure_job without anchor_turn_id defaults it to turn_id.
# --------------------------------------------------------------------------- #
def test_g6_ensure_job_defaults_anchor_turn_id_to_turn(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g6")
    job = ctx.workflow_job_service.ensure_job(
        identity=ctx.identity,
        job_kind=RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
        job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
        creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
        required_for_turn_completion=True,
    )
    retrieval_session.commit()
    reloaded = retrieval_session.get(RuntimeWorkflowJobRecord, job.job_id)
    assert reloaded is not None
    assert reloaded.anchor_turn_id == ctx.identity.turn_id


# --------------------------------------------------------------------------- #
# G7 — (backward-compat) no provider -> DETERMINISTIC_FALLBACK bootstrap, no gate.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g7_bootstrap_path_unchanged_without_provider(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g7")
    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=_bootstrap_scheduler(ctx),
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=None,
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    worker_plan_dump = result["metadata_json"]["worker_plan"]
    assert worker_plan_dump["plan_source"] == (
        WorkerPlanSource.DETERMINISTIC_FALLBACK.value
    )
    assert _gate_jobs(ctx) == []


# --------------------------------------------------------------------------- #
# G8 — [FAIL-4] proposal present but decision deps absent -> fail-closed; through
#      the consumer -> minimal/deferred, no dispatch, no gate (AUTH-004).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g8_proposal_without_decision_deps_fails_closed(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g8")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[_longform_selection()],
        source_unit_count=1,
    )
    deps_absent_scheduler = _orchestrator_scheduler(
        ctx,
        scheduler_decision_service=None,
        worker_registry_service=None,
    )
    with pytest.raises(SchedulerDecisionError):
        deps_absent_scheduler.build_worker_plan(
            identity=ctx.identity,
            proposal=proposal,
        )

    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=deps_absent_scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    assert result["run_kind"] == PostWriteRunKind.MINIMAL_ONLY.value
    assert _gate_jobs(ctx) == []
    assert execution.calls == []
    assert governance.calls == []


# --------------------------------------------------------------------------- #
# G9 — [Blocker-2] source_unit_count=None -> precondition error; through the
#      consumer -> minimal/deferred, no skipped-only pseudo-plan, no gate.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g9_missing_source_unit_count_is_precondition_error(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g9")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[_longform_selection()],
        source_unit_count=None,
    )
    scheduler = _orchestrator_scheduler(
        ctx,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=WorkerRegistryService(ctx.db),
    )
    with pytest.raises(SchedulerDecisionError) as exc_info:
        scheduler.build_worker_plan(identity=ctx.identity, proposal=proposal)
    assert exc_info.value.category == SchedulerFailureCategory.VALIDATION_ERROR
    assert exc_info.value.message == "source_unit_count_missing"

    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    assert result["run_kind"] == PostWriteRunKind.MINIMAL_ONLY.value
    assert _gate_jobs(ctx) == []
    assert execution.calls == []
    assert governance.calls == []


# --------------------------------------------------------------------------- #
# G10 — [CONCERN-6] decide() snapshot mismatch reaches the consumer -> caught ->
#       minimal/deferred, no dispatch, no gate (AUTH-004 fail-closed).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g10_decide_snapshot_mismatch_propagates_to_minimal(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g10")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[_longform_selection()],
        source_unit_count=1,
    )
    real_registry = WorkerRegistryService(ctx.db).build_registry_for_snapshot(
        snapshot_id=ctx.identity.runtime_profile_snapshot_id
    )
    mismatched_registry = real_registry.model_copy(
        update={"snapshot_id": f"snapshot:deliberate-mismatch:{ctx.identity.turn_id}"}
    )
    scheduler = PostWriteSchedulerService(
        worker_scheduler_service=WorkerSchedulerService(
            worker_registry_service=WorkerRegistryService(ctx.db)
        ),
        runtime_workspace_material_service=ctx.material_service,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=_SnapshotMismatchRegistryService(mismatched_registry),
    )
    with pytest.raises(SchedulerDecisionError):
        scheduler.build_worker_plan(identity=ctx.identity, proposal=proposal)

    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    assert result["run_kind"] == PostWriteRunKind.MINIMAL_ONLY.value
    assert _gate_jobs(ctx) == []
    assert execution.calls == []
    assert governance.calls == []


# --------------------------------------------------------------------------- #
# G11 — [CONCERN-6] all-illegal proposal still decides: ORCHESTRATOR plan with
#       empty selected_workers, all skipped, gate created+completed, no dispatch.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_g11_all_illegal_proposal_still_decides_with_gate(retrieval_session):
    ctx = _seed_ready_turn(retrieval_session, story_id="s2b-g11")
    proposal = _make_orchestrator_proposal(
        ctx.identity,
        worker_selections=[
            _longform_selection(worker_id=_UNKNOWN_WORKER_ID),
            _longform_selection(worker_id=_UNKNOWN_WORKER_ID_2),
        ],
        source_unit_count=1,
    )
    execution = _FakeWorkerExecutionService()
    governance = _FakeGovernanceService()
    scheduler = _orchestrator_scheduler(
        ctx,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=WorkerRegistryService(ctx.db),
    )
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=execution,
        post_write_governance_service=governance,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )

    worker_plan_dump = result["metadata_json"]["worker_plan"]
    assert worker_plan_dump["plan_source"] == WorkerPlanSource.ORCHESTRATOR.value
    assert worker_plan_dump["selected_workers"] == []
    skipped_ids = {item["worker_id"] for item in worker_plan_dump["skipped_workers"]}
    assert skipped_ids == {_UNKNOWN_WORKER_ID, _UNKNOWN_WORKER_ID_2}
    gates = _gate_jobs(ctx)
    assert len(gates) == 1

    retrieval_session.commit()
    reloaded_gate = retrieval_session.get(RuntimeWorkflowJobRecord, gates[0].job_id)
    assert reloaded_gate.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert execution.produced_results == []
