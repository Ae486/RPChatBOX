from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlmodel import Session

from config import get_settings
from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.models.proposal.postwrite_runtime_contracts import PostWriteRunKind
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.orchestrator_dispatch import (
    OrchestratorDispatchSelection,
    OrchestratorDispatchToolInput,
    OrchestratorPlanProposal,
)
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
)
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.models.writer.worker_runtime_contracts import (
    WorkerContextPacket,
    WorkerExecutionRequest,
    WorkerPlanSource,
    WorkerResultStatus,
)
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state.authoritative_compatibility_mirror_service import (
    AuthoritativeCompatibilityMirrorService,
)
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.projection.builder_context_service import (
    BuilderProjectionContextService,
)
from rp.services.projection.chapter_workspace_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection.refresh_service import ProjectionRefreshService
from rp.services.projection.state_service import ProjectionStateService
from rp.services.proposal.apply_service import ProposalApplyService
from rp.services.proposal.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal.post_write_governance_service import (
    PostWriteGovernanceService,
)
from rp.services.proposal.post_write_scheduler_service import (
    POST_WRITE_MAINTENANCE_PHASE,
    PostWriteSchedulerService,
)
from rp.services.proposal.repository import ProposalRepository
from rp.services.proposal.workflow_service import ProposalWorkflowService
from rp.services.runtime.maintenance_lock_service import RuntimeMaintenanceLockService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.scheduler_decision_service import SchedulerDecisionService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.services.story.state_apply_service import StoryStateApplyService
from rp.services.story.turn_domain_service import StoryTurnDomainService
from rp.services.writer.memory_maintenance_worker_adapter import (
    MemoryMaintenanceWorkerAdapter,
    S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
    S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
    S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
    ScriptedMemoryMaintenanceStructuredOutputRunner,
)
from rp.services.writer.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WorkerRegistryService,
)
from rp.services.writer.worker_scheduler_service import WorkerSchedulerService
from rp.services.writer.writing_packet_builder import WritingPacketBuilder
from rp.tests.services._helpers.core_state_dual_write_helpers import (
    build_seeded_core_state_dual_write_service_from_story_service,
)
from services.database import create_db_and_tables, get_engine


@pytest.fixture
def retrieval_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATBOX_BACKEND_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "CHATBOX_BACKEND_DATABASE_URL",
        f"sqlite:///{(tmp_path / 'rp-test.db').as_posix()}",
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_db_and_tables()
    with Session(get_engine()) as session:
        yield session
    get_engine.cache_clear()
    get_settings.cache_clear()


class _NoopRegressionService:
    async def run_light_regression(self, **kwargs):
        return kwargs["session"], kwargs["chapter"]

    async def run_heavy_regression(self, **kwargs):
        return kwargs["session"], kwargs["chapter"]


class _FakeOrchestratorDispatchProvider:
    def __init__(self, proposal: OrchestratorPlanProposal) -> None:
        self.proposal = proposal
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
        return self.proposal


class _MemoryAdapterWorkerExecutionService:
    """Executor seam that consumes the selected plan and runs the S3 adapter."""

    def __init__(
        self,
        *,
        db_session,
        adapter: MemoryMaintenanceWorkerAdapter,
    ) -> None:
        self._registry_service = WorkerRegistryService(db_session)
        self._adapter = adapter
        self.calls: list[dict[str, object]] = []
        self.requests: list[WorkerExecutionRequest] = []
        self.context_packets: list[WorkerContextPacket] = []
        self.produced_results = []
        self.selected_worker_ids: list[str] = []

    async def execute_plan(self, **kwargs):
        self.calls.append(kwargs)
        plan = kwargs["plan"]
        story_session = kwargs["session"]
        self.selected_worker_ids = [
            item.worker_id for item in list(plan.selected_workers)
        ]
        results = []
        for item in list(plan.selected_workers):
            registration = self._registry_service.require_worker(
                item.worker_id,
                snapshot_id=plan.identity.runtime_profile_snapshot_id,
            )
            context_packet_ref = (
                f"worker-packet:{plan.identity.turn_id}:{item.worker_id}"
            )
            request = WorkerExecutionRequest(
                request_id=f"worker-request:{plan.plan_id}:{item.worker_id}",
                identity=plan.identity,
                worker_id=item.worker_id,
                phase=plan.phase,
                mode=story_session.mode,
                turn_id=plan.identity.turn_id,
                context_packet_ref=context_packet_ref,
                execution_policy=registration.execution_policy,
                budget_class=item.budget_class,
                reason_codes=list(item.reason_codes),
                scheduler_constraints=dict(item.scheduler_constraints),
            )
            packet = WorkerContextPacket(
                packet_id=context_packet_ref,
                identity=plan.identity,
                worker_id=item.worker_id,
                phase=plan.phase,
                mode=story_session.mode,
                workspace_refs=[context_packet_ref],
                trace_refs=[
                    f"worker_plan:{plan.plan_id}",
                    f"selected_worker:{item.worker_id}",
                ],
            )
            self.requests.append(request)
            self.context_packets.append(packet)
            results.append(
                await self._adapter.execute(
                    request=request,
                    registration=registration,
                    context_packet=packet,
                )
            )
        self.produced_results = results
        return SimpleNamespace(
            plan=plan,
            worker_results=results,
            specialist_bundle=SpecialistResultBundle(),
        )


@pytest.mark.asyncio
async def test_s3f_review_required_path_locks_until_governed_apply(
    retrieval_session,
):
    harness = await _trigger_s3f_path(
        retrieval_session,
        story_id="s3f-review-required",
        structured_output=_candidate_output(governance_route="review_required"),
    )

    result = harness.result
    assert result["run_kind"] == PostWriteRunKind.FULL_SCHEDULE.value
    assert result["settled"] is True
    _assert_selected_longform_worker(harness)
    _assert_scheduler_gate_completed(harness)
    _assert_proposal_job_completed(harness)

    proposals = harness.repository.list_proposals_for_story(harness.session.story_id)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.status == "review_required"
    assert proposal.policy_decision == "review_required"
    assert proposal.operations_json[0]["event_data"]["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )
    assert harness.repository.list_apply_receipts_for_proposal(
        proposal.proposal_id
    ) == []
    assert _active_threads(harness) == []

    locked = harness.lock_service.evaluate(
        story_id=harness.identity.story_id,
        session_id=harness.identity.session_id,
        branch_head_id=harness.identity.branch_head_id,
    )
    assert locked.active is True
    assert locked.causes[0].source_kind == "proposal"
    assert locked.causes[0].status == "review_required"

    apply_receipt = harness.apply_service.apply_proposal(proposal.proposal_id)
    assert apply_receipt.status == "applied"
    assert len(
        harness.repository.list_apply_receipts_for_proposal(proposal.proposal_id)
    ) == 1
    assert _active_threads(harness)[0]["content"] == _CANDIDATE_CONTENT

    unlocked = harness.lock_service.evaluate(
        story_id=harness.identity.story_id,
        session_id=harness.identity.session_id,
        branch_head_id=harness.identity.branch_head_id,
    )
    assert unlocked.active is False


@pytest.mark.asyncio
async def test_s3f_direct_apply_path_mutates_only_through_apply_receipt(
    retrieval_session,
):
    harness = await _trigger_s3f_path(
        retrieval_session,
        story_id="s3f-direct-apply",
        structured_output=_candidate_output(governance_route="direct_apply_allowed"),
    )

    assert harness.result["run_kind"] == PostWriteRunKind.FULL_SCHEDULE.value
    assert harness.result["settled"] is True
    _assert_selected_longform_worker(harness)
    _assert_scheduler_gate_completed(harness)
    _assert_proposal_job_completed(harness)

    proposals = harness.repository.list_proposals_for_story(harness.session.story_id)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.status == "applied"
    assert proposal.policy_decision == "notify_apply"
    receipts = harness.repository.list_apply_receipts_for_proposal(
        proposal.proposal_id
    )
    assert len(receipts) == 1
    assert receipts[0].revision_after_json["plot_thread.active"] == 2
    assert _active_threads(harness)[0]["content"] == _CANDIDATE_CONTENT

    lock_state = harness.lock_service.evaluate(
        story_id=harness.identity.story_id,
        session_id=harness.identity.session_id,
        branch_head_id=harness.identity.branch_head_id,
    )
    assert lock_state.active is False


@pytest.mark.asyncio
async def test_s3f_adapter_failure_emits_no_candidate_or_truth_mutation(
    retrieval_session,
):
    harness = await _trigger_s3f_path(
        retrieval_session,
        story_id="s3f-adapter-failure",
        structured_output={
            "schema_version": S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
            "status": "candidate_batch",
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": POST_WRITE_MAINTENANCE_PHASE,
            "unexpected_field": "must fail closed",
        },
    )

    assert harness.result["run_kind"] == PostWriteRunKind.FULL_SCHEDULE.value
    _assert_selected_longform_worker(harness)
    _assert_scheduler_gate_completed(harness)
    assert harness.runner.call_count == 1
    assert harness.executor.produced_results[0].result_status == (
        WorkerResultStatus.FAILED
    )
    assert harness.executor.produced_results[0].proposal_candidates == []
    assert harness.result["proposal_job_refs"] == []
    assert _proposal_jobs(harness) == []
    assert harness.repository.list_proposals_for_story(harness.session.story_id) == []
    assert harness.repository.list_apply_receipts_for_story(
        harness.session.story_id,
        session_id=harness.session.session_id,
    ) == []
    assert _active_threads(harness) == []
    lock_state = harness.lock_service.evaluate(
        story_id=harness.identity.story_id,
        session_id=harness.identity.session_id,
        branch_head_id=harness.identity.branch_head_id,
    )
    assert lock_state.active is False


@pytest.mark.asyncio
async def test_s3f_governance_handoff_failure_records_failed_job_only(
    retrieval_session,
):
    harness = await _trigger_s3f_path(
        retrieval_session,
        story_id="s3f-governance-failure",
        structured_output=_candidate_output(
            governance_route="review_required",
            base_block_revision_id="revision-one",
        ),
    )

    assert harness.result["run_kind"] == PostWriteRunKind.FULL_SCHEDULE.value
    _assert_selected_longform_worker(harness)
    _assert_scheduler_gate_completed(harness)
    assert harness.executor.produced_results[0].result_status == (
        WorkerResultStatus.COMPLETED
    )
    assert len(harness.result["proposal_job_refs"]) == 1

    proposal_jobs = _proposal_jobs(harness)
    assert len(proposal_jobs) == 1
    failed_job = proposal_jobs[0]
    assert failed_job.status == RuntimeWorkflowJobStatus.FAILED.value
    assert failed_job.failure_reason == "memory_candidate_base_revision_unparseable"
    assert failed_job.last_error_json["code"] == (
        "memory_candidate_base_revision_unparseable"
    )
    assert harness.repository.list_proposals_for_story(harness.session.story_id) == []
    assert harness.repository.list_apply_receipts_for_story(
        harness.session.story_id,
        session_id=harness.session.session_id,
    ) == []
    assert _active_threads(harness) == []

    lock_state = harness.lock_service.evaluate(
        story_id=harness.identity.story_id,
        session_id=harness.identity.session_id,
        branch_head_id=harness.identity.branch_head_id,
    )
    assert lock_state.active is False


async def _trigger_s3f_path(
    retrieval_session,
    *,
    story_id: str,
    structured_output: dict,
):
    ctx = _seed_ready_turn(retrieval_session, story_id=story_id)
    services = _build_real_governance_services(ctx)
    runner = ScriptedMemoryMaintenanceStructuredOutputRunner([structured_output])
    adapter = MemoryMaintenanceWorkerAdapter(structured_output_runner=runner)
    executor = _MemoryAdapterWorkerExecutionService(
        db_session=retrieval_session,
        adapter=adapter,
    )
    proposal = _make_orchestrator_proposal(ctx.identity)
    scheduler = _orchestrator_scheduler(ctx)
    turn_domain_service = _build_turn_domain_service(
        ctx,
        post_write_scheduler_service=scheduler,
        worker_execution_service=executor,
        post_write_governance_service=services.governance_service,
        orchestrator_dispatch_provider=_FakeOrchestratorDispatchProvider(proposal),
    )

    result = await turn_domain_service.trigger_post_write(
        runtime_identity=ctx.identity,
        model_id="model",
    )
    return SimpleNamespace(
        **ctx.__dict__,
        **services.__dict__,
        runner=runner,
        executor=executor,
        result=result,
        lock_service=RuntimeMaintenanceLockService(retrieval_session),
    )


def _seed_ready_turn(retrieval_session, *, story_id: str) -> SimpleNamespace:
    story_session_service = StorySessionService(retrieval_session)
    story_session = story_session_service.create_session(
        story_id=story_id,
        source_workspace_id=f"workspace-{story_id}",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 1,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = story_session_service.create_chapter_workspace(
        session_id=story_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Chapter 1",
        builder_snapshot_json={},
    )
    story_session_service.commit()

    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.s3f.memory_worker_e2e",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    artifact = story_session_service.create_artifact(
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The bridge cutoff becomes visible in the accepted prose.",
        metadata={
            "runtime_turn_id": identity.turn_id,
            "runtime_branch_head_id": identity.branch_head_id,
            "source_ref_kind": "accepted_prose",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        accepted_segment_ids=[artifact.artifact_id],
    )
    turn_record = retrieval_session.get(StoryTurnRecord, identity.turn_id)
    assert turn_record is not None
    turn_record.selected_output_ref = f"artifact:{artifact.artifact_id}"
    turn_record.visible_output_ref = f"artifact:{artifact.artifact_id}"
    retrieval_session.add(turn_record)
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )
    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id=f"retrieval-usage-{story_id}",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.retrieval.usage",
            payload={
                "used_card_material_ids": [f"retrieval-card-{story_id}"],
                "source_artifact_id": artifact.artifact_id,
                "knowledge_gaps": [],
            },
            visibility="runtime_private",
            created_by="test.s3f.memory_worker_e2e",
        )
    )
    return SimpleNamespace(
        db=retrieval_session,
        story_session_service=story_session_service,
        session=story_session_service.get_session(story_session.session_id),
        chapter=story_session_service.get_current_chapter(story_session.session_id),
        snapshot=snapshot,
        identity=identity,
        identity_service=identity_service,
        material_service=material_service,
        workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
    )


def _build_real_governance_services(ctx: SimpleNamespace) -> SimpleNamespace:
    repository = ProposalRepository(ctx.db)
    core_state_store_repository = CoreStateStoreRepository(ctx.db)
    dual_write_service = build_seeded_core_state_dual_write_service_from_story_service(
        ctx.story_session_service,
        session_id=ctx.session.session_id,
    )
    mirror_service = AuthoritativeCompatibilityMirrorService(
        story_session_service=ctx.story_session_service,
    )
    as_of_resolver = CoreStateAsOfResolver(
        session=ctx.db,
        repository=core_state_store_repository,
        mirror_service=mirror_service,
    )
    apply_service = ProposalApplyService(
        story_session_service=ctx.story_session_service,
        proposal_repository=repository,
        story_state_apply_service=StoryStateApplyService(),
        core_state_dual_write_service=dual_write_service,
        authoritative_compatibility_mirror_service=mirror_service,
        runtime_workspace_material_service=ctx.material_service,
        core_state_as_of_resolver=as_of_resolver,
    )
    workflow_service = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=apply_service,
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    governance_service = PostWriteGovernanceService(
        runtime_workflow_job_service=ctx.workflow_job_service,
        projection_refresh_service=ProjectionRefreshService(
            ctx.story_session_service,
            core_state_dual_write_service=dual_write_service,
        ),
        core_state_as_of_resolver=as_of_resolver,
        proposal_workflow_service=workflow_service,
    )
    return SimpleNamespace(
        repository=repository,
        apply_service=apply_service,
        workflow_service=workflow_service,
        governance_service=governance_service,
    )


def _orchestrator_scheduler(ctx: SimpleNamespace) -> PostWriteSchedulerService:
    return PostWriteSchedulerService(
        worker_scheduler_service=WorkerSchedulerService(
            worker_registry_service=WorkerRegistryService(ctx.db)
        ),
        runtime_workspace_material_service=ctx.material_service,
        scheduler_decision_service=SchedulerDecisionService(),
        worker_registry_service=WorkerRegistryService(ctx.db),
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
        story_session_service=ctx.story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(ctx.story_session_service),
    )
    return StoryTurnDomainService(
        story_session_service=ctx.story_session_service,
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


def _make_orchestrator_proposal(identity) -> OrchestratorPlanProposal:
    return OrchestratorPlanProposal(
        identity=identity,
        phase=POST_WRITE_MAINTENANCE_PHASE,
        dispatch_input=OrchestratorDispatchToolInput(
            selections=[
                OrchestratorDispatchSelection(
                    worker_id=LONGFORM_MEMORY_WORKER_ID,
                    source_unit_numbers=[1],
                    reason_codes=["orchestrator_selected"],
                )
            ],
        ),
        source_unit_count=1,
    )


_CANDIDATE_CONTENT = "The bridge cutoff becomes the active thread."


def _candidate_output(
    *,
    governance_route: str,
    base_block_revision_id: str = "block-revision-1",
) -> dict:
    return {
        "schema_version": S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
        "status": "candidate_batch",
        "worker_id": LONGFORM_MEMORY_WORKER_ID,
        "phase": POST_WRITE_MAINTENANCE_PHASE,
        "candidate_batch": {
            "schema_version": S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": POST_WRITE_MAINTENANCE_PHASE,
            "candidates": [
                {
                    "target_domain": "plot_threads",
                    "target_block_id": "plot.active_threads",
                    "base_block_revision_id": base_block_revision_id,
                    "operations": [
                        {
                            "kind": "append_item",
                            "field_id": "facts",
                            "content": _CANDIDATE_CONTENT,
                        }
                    ],
                    "source_refs": [
                        {
                            "source_type": "accepted_prose",
                            "source_id": "segment-s3f-1",
                            "layer": "runtime_workspace",
                        }
                    ],
                    "change_summary": "Track the bridge cutoff as a plot thread.",
                }
            ],
            "metadata": {"governance_route": governance_route},
        },
        "metadata": {"fake_runner": True},
    }


def _assert_selected_longform_worker(harness: SimpleNamespace) -> None:
    assert harness.runner.call_count == 1
    assert harness.executor.selected_worker_ids == [LONGFORM_MEMORY_WORKER_ID]
    assert harness.executor.requests[0].worker_id == LONGFORM_MEMORY_WORKER_ID
    assert harness.executor.requests[0].phase == POST_WRITE_MAINTENANCE_PHASE
    assert harness.executor.requests[0].context_packet_ref == (
        f"worker-packet:{harness.identity.turn_id}:{LONGFORM_MEMORY_WORKER_ID}"
    )
    assert harness.executor.context_packets[0].packet_id == (
        harness.executor.requests[0].context_packet_ref
    )
    worker_plan_dump = harness.result["metadata_json"]["worker_plan"]
    assert worker_plan_dump["plan_source"] == WorkerPlanSource.ORCHESTRATOR.value
    assert [item["worker_id"] for item in worker_plan_dump["selected_workers"]] == [
        LONGFORM_MEMORY_WORKER_ID
    ]


def _assert_scheduler_gate_completed(harness: SimpleNamespace) -> None:
    gates = _scheduler_gate_jobs(harness)
    assert len(gates) == 1
    gate = gates[0]
    assert gate.anchor_turn_id == harness.identity.turn_id
    assert gate.status == RuntimeWorkflowJobStatus.COMPLETED.value


def _assert_proposal_job_completed(harness: SimpleNamespace) -> None:
    proposal_jobs = _proposal_jobs(harness)
    assert len(proposal_jobs) == 1
    job = proposal_jobs[0]
    assert job.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job.completion_reason == "proposal_governance_completed"
    assert harness.result["proposal_job_refs"] == [f"runtime_job:{job.job_id}"]


def _scheduler_gate_jobs(harness: SimpleNamespace) -> list[RuntimeWorkflowJobRecord]:
    return [
        job
        for job in harness.workflow_job_service.list_jobs_for_turn(
            turn_id=harness.identity.turn_id,
        )
        if job.job_kind == RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value
    ]


def _proposal_jobs(harness: SimpleNamespace) -> list[RuntimeWorkflowJobRecord]:
    return [
        job
        for job in harness.workflow_job_service.list_jobs_for_turn(
            turn_id=harness.identity.turn_id,
        )
        if job.job_kind == RuntimeWorkflowJobKind.PROPOSAL_SUBMIT.value
    ]


def _active_threads(harness: SimpleNamespace) -> list[dict]:
    session = harness.story_session_service.get_session(harness.session.session_id)
    assert session is not None
    return list(session.current_state_json.get("active_threads") or [])
