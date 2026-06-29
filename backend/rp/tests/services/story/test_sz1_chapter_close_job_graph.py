"""S-Z1 oracles — chapter-close job graph (AUTH-013 / TURN-004 / WRK-008 / NUM-012).

Fake-executor driven (HAR-012, no live model): the chapter-summary is produced by a
stubbed WRITER-ROLE worker (``WritingWorkerExecutionService`` surface, S-Z2) and the
tail-flush memory-maintenance spine runs through stubbed scheduler/executor/governance
doubles. These oracles pin the frozen chapter-close contract that
``StoryTurnDomainService.complete_chapter`` rebuilds on the S2/S3 job ledger:

  * D-S5-01  ledger topology A (chapter_summary) ∥ B (tail_flush) + G (gate), all
             ``required_for_turn_completion``; A carries the branch-scoped bridge
             material id (bridge-after-summary); turn SETTLED only after all
             three are terminal.
  * D-S5-03  STRONG falsifiable form — JOB B ingestion failure WHILE A and G
             complete leaves the turn NOT settled (proves it is B's per-job
             failure, not "everything incomplete", that blocks settlement; guards
             the AMENDMENT-1 per-job terminalization against a batch false-green).
  * D-S5-04  (S-Z2) JOB A's summary is EXECUTED BY THE WRITER ROLE and dispatched AS
             JOB A's work — the writer worker is invoked once with a summary packet
             (retrieval OFF) WHILE JOB A is still PENDING (Option II), and the
             persisted bridge summary equals the writer worker's output.
  * D-S5-05  (S-Z2) STRONG falsifiable form — a WRITER-ROLE summary failure fails
             JOB A WHILE B and G complete, blocking settlement (JOB A analog of
             D-S5-03; kills the unconditional-complete facade).
  * NUM-012  chapter close creates NO ``recall_materialization`` job and persists
             NO recall seed asset; the reserved enum slot still exists.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.models.writer.worker_runtime_contracts import WorkerResult, WorkerResultStatus
from rp.services.projection.builder_context_service import (
    BuilderProjectionContextService,
)
from rp.services.projection.chapter_workspace_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection.state_service import ProjectionStateService
from rp.services.proposal.post_write_governance_service import (
    PostWriteGovernanceServiceError,
)
from rp.services.retrieval.document_service import RetrievalDocumentService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.story.chapter_bridge_provider import ChapterBridgeProvider
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.services.story.turn_domain_service import StoryTurnDomainService
from rp.services.writer.longform_chapter_runtime_service import (
    LongformChapterRuntimeService,
)
from rp.services.writer.writing_packet_builder import WritingPacketBuilder
from rp.tests.services._helpers.core_state_dual_write_helpers import (
    build_seeded_core_state_dual_write_service_from_story_service,
)


# --------------------------------------------------------------------------- #
# Test doubles (own this file — no live model, deterministic spine).
# --------------------------------------------------------------------------- #
class _FakeWriterRoleWorker:
    """Writer-role double (``WritingWorkerExecutionService`` surface, S-Z2).

    Returns a fixed structured bridge summary as the *writer-produced* text (no live
    model), or raises to model a writer-role failure. Optionally probes the live JOB A
    status at invocation time to prove the summary is driven WITHIN JOB A's open
    lifecycle (Option II), not by a pre-graph call or a post-hoc label.
    """

    DEFAULT_SUMMARY_JSON = (
        '{"summary_text":"Chapter one closed at the river gate.",'
        '"continuity_notes":[],"open_threads":[]}'
    )

    def __init__(
        self,
        *,
        summary_json: str | None = None,
        error: Exception | None = None,
        job_status_probe=None,
    ) -> None:
        self._summary_json = summary_json or self.DEFAULT_SUMMARY_JSON
        self._error = error
        self._job_status_probe = job_status_probe
        self.calls: list[dict[str, object]] = []
        self.job_a_status_at_call: list[str | None] = []

    async def run(self, *, packet, model_id, provider_id):
        if self._job_status_probe is not None:
            self.job_a_status_at_call.append(self._job_status_probe())
        self.calls.append(
            {"packet": packet, "model_id": model_id, "provider_id": provider_id}
        )
        if self._error is not None:
            raise self._error
        return self._summary_json


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


class _FakeChapterCloseScheduler:
    """Returns a one-worker tail-flush plan; mirrors PostWriteSchedulerService."""

    def build_worker_plan(self, *, identity, proposal=None):
        return SimpleNamespace(
            plan_id=f"chapter-close-plan:{identity.turn_id}",
            phase="post_write_maintenance",
            selected_workers=[SimpleNamespace(worker_id="LongformMemoryWorker")],
            identity=identity,
        )


class _FakeWorkerExecutionService:
    """Faithful executor fake: one WorkerResult per selected worker."""

    def __init__(self, *, result_status: WorkerResultStatus) -> None:
        self._result_status = result_status
        self.calls: list[dict[str, object]] = []

    async def execute_plan(self, **kwargs):
        self.calls.append(kwargs)
        plan = kwargs["plan"]
        results = [
            WorkerResult(
                worker_id=item.worker_id,
                phase=plan.phase,
                result_status=self._result_status,
            )
            for item in plan.selected_workers
        ]
        return SimpleNamespace(
            plan=plan,
            worker_results=results,
            specialist_bundle=SpecialistResultBundle(),
        )


class _FakeGovernanceService:
    """Governance fake: empty dispatch result, or raise an ingestion failure."""

    def __init__(self, *, raise_ingestion_error: bool = False) -> None:
        self._raise = raise_ingestion_error
        self.calls: list[dict[str, object]] = []

    async def dispatch_worker_results(self, **kwargs):
        self.calls.append(kwargs)
        if self._raise:
            raise PostWriteGovernanceServiceError(
                "post_write_worker_result_ingestion_failed",
                "injected_tail_flush_ingestion_failure",
            )
        return SimpleNamespace(
            selected_worker_result_refs=["worker_result:tail_flush"],
            projection_refresh_job_refs=[],
            proposal_job_refs=[],
            materialization_job_refs=[],
            trace_refs=["worker_plan:chapter-close-plan"],
            metadata_json={},
        )


# --------------------------------------------------------------------------- #
# Seeding (real session/chapter/accepted-segment/turn; trimmed to chapter close).
# --------------------------------------------------------------------------- #
def _seed_chapter_close_ctx(retrieval_session, *, story_id: str) -> SimpleNamespace:
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id=story_id,
        source_workspace_id=f"workspace-{story_id}",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "segment_drafting",
                "accepted_segments": 1,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.SEGMENT_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        chapter_goal="Close the bell-tower debt cleanly.",
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": [],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.sz1.chapter_close",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    segment_identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="test.sz1.segment",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    segment = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="The bell-tower debt was settled at the river gate.",
        metadata={
            "runtime_story_id": segment_identity.story_id,
            "runtime_session_id": segment_identity.session_id,
            "runtime_branch_head_id": segment_identity.branch_head_id,
            "runtime_turn_id": segment_identity.turn_id,
            "runtime_profile_snapshot_id": (
                segment_identity.runtime_profile_snapshot_id
            ),
        },
    )
    identity_service.update_turn_status(
        turn_id=segment_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=segment.artifact_id,
        selected_output_ref=segment.artifact_id,
        settlement_reason="test_settled_segment",
    )
    service.commit()
    close_identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER.value,
        actor="test.sz1.close",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    return SimpleNamespace(
        db=retrieval_session,
        service=service,
        session=session,
        chapter=chapter,
        identity_service=identity_service,
        workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
        segment_identity=segment_identity,
        close_identity=close_identity,
        segment=segment,
    )


def _build_turn_domain_service(
    ctx: SimpleNamespace,
    *,
    executor: _FakeWorkerExecutionService,
    governance: _FakeGovernanceService,
    writer_worker: _FakeWriterRoleWorker | None = None,
) -> StoryTurnDomainService:
    writer_worker = writer_worker or _FakeWriterRoleWorker()
    projection_state_service = ProjectionStateService(
        story_session_service=ctx.service,
        adapter=ChapterWorkspaceProjectionAdapter(ctx.service),
        core_state_dual_write_service=(
            build_seeded_core_state_dual_write_service_from_story_service(ctx.service)
        ),
    )
    chapter_runtime_service = LongformChapterRuntimeService(
        story_session_service=ctx.service,
        chapter_bridge_provider=ChapterBridgeProvider(
            writing_worker_execution_service=writer_worker
        ),
        session=ctx.db,
    )
    return StoryTurnDomainService(
        story_session_service=ctx.service,
        orchestrator_service=SimpleNamespace(),
        specialist_service=SimpleNamespace(),
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        projection_state_service=projection_state_service,
        writing_packet_builder=WritingPacketBuilder(),
        writing_worker_execution_service=writer_worker,
        regression_service=_NoopRegressionService(),
        runtime_identity_service=ctx.identity_service,
        runtime_workflow_job_service=ctx.workflow_job_service,
        worker_execution_service=executor,
        post_write_scheduler_service=_FakeChapterCloseScheduler(),
        post_write_governance_service=governance,
        longform_chapter_runtime_service=chapter_runtime_service,
    )


def _jobs_by_kind(ctx: SimpleNamespace) -> dict[str, object]:
    return {
        job.job_kind: job
        for job in ctx.workflow_job_service.list_jobs_for_turn(
            turn_id=ctx.close_identity.turn_id
        )
    }


def _complete_chapter_request(ctx: SimpleNamespace) -> LongformTurnRequest:
    return LongformTurnRequest(
        session_id=ctx.session.session_id,
        command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
        model_id="model-sz1-chapter-close",
    )


# --------------------------------------------------------------------------- #
# D-S5-01 — ledger topology + bridge-after-summary + settle gating.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_d_s5_01_chapter_close_job_graph_topology_and_settle(retrieval_session):
    ctx = _seed_chapter_close_ctx(retrieval_session, story_id="sz1-d-s5-01")
    executor = _FakeWorkerExecutionService(result_status=WorkerResultStatus.COMPLETED)
    governance = _FakeGovernanceService()
    turn_domain_service = _build_turn_domain_service(
        ctx,
        executor=executor,
        governance=governance,
    )

    response = await turn_domain_service.complete_chapter(
        request=_complete_chapter_request(ctx),
        runtime_identity=ctx.close_identity,
    )

    jobs = _jobs_by_kind(ctx)
    job_a = jobs[RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS.value]
    job_b = jobs[RuntimeWorkflowJobKind.RUNTIME_WORKSPACE_FINALIZE.value]
    job_g = jobs[RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value]

    # Topology: A ∥ B + G, all required for turn completion (AUTH-013).
    assert job_a.required_for_turn_completion is True
    assert job_b.required_for_turn_completion is True
    assert job_g.required_for_turn_completion is True
    assert job_a.metadata_json["chapter_close_slot"] == "chapter_summary"
    assert job_b.metadata_json["chapter_close_slot"] == "tail_flush"
    # A and B are parallel — no mutual dependency edge.
    assert job_a.parent_job_id is None
    assert job_b.parent_job_id is None

    # Bridge-after-summary: JOB A's result_ref_ids carry the branch-scoped bridge id.
    assert any(
        ref.startswith(f"chapter-bridge:{ctx.close_identity.turn_id}:")
        for ref in job_a.result_ref_ids_json
    )

    # The executor actually ran the tail-flush memory-maintenance pass.
    assert len(executor.calls) == 1
    assert len(governance.calls) == 1

    # Settle only after A, B, G are all terminal (TURN-004).
    assert job_a.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_b.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_g.status == RuntimeWorkflowJobStatus.COMPLETED.value
    close_turn = ctx.identity_service.get_turn(ctx.close_identity.turn_id)
    assert close_turn is not None
    assert close_turn.status == StoryTurnStatus.SETTLED.value

    # Deterministic product transition still advances the chapter.
    assert response.current_chapter_index == 2
    assert response.current_phase == LongformChapterPhase.OUTLINE_DRAFTING


# --------------------------------------------------------------------------- #
# D-S5-03 (STRONG) — JOB B failure blocks settlement while A and G complete.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_d_s5_03_tail_flush_failure_blocks_settlement(retrieval_session):
    ctx = _seed_chapter_close_ctx(retrieval_session, story_id="sz1-d-s5-03")
    executor = _FakeWorkerExecutionService(result_status=WorkerResultStatus.COMPLETED)
    governance = _FakeGovernanceService(raise_ingestion_error=True)
    turn_domain_service = _build_turn_domain_service(
        ctx,
        executor=executor,
        governance=governance,
    )

    await turn_domain_service.complete_chapter(
        request=_complete_chapter_request(ctx),
        runtime_identity=ctx.close_identity,
    )

    jobs = _jobs_by_kind(ctx)
    job_a = jobs[RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS.value]
    job_b = jobs[RuntimeWorkflowJobKind.RUNTIME_WORKSPACE_FINALIZE.value]
    job_g = jobs[RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value]

    # STRONG form: A and G DO complete; only B fails (per-job terminalization).
    assert job_a.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_g.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_b.status == RuntimeWorkflowJobStatus.FAILED.value
    assert job_b.failure_reason == "post_write_worker_result_ingestion_failed"

    # A failed required job is NOT settlement-terminal -> turn never settles.
    settlement = ctx.workflow_job_service.evaluate_turn_settlement(
        turn_id=ctx.close_identity.turn_id
    )
    assert settlement.eligible is False
    assert job_b.job_id in settlement.blocking_job_ids
    close_turn = ctx.identity_service.get_turn(ctx.close_identity.turn_id)
    assert close_turn is not None
    assert close_turn.status not in {
        StoryTurnStatus.SETTLED.value,
        StoryTurnStatus.COMPLETED.value,
    }


# --------------------------------------------------------------------------- #
# D-S5-04 (S-Z2) — JOB A summary EXECUTED BY THE WRITER ROLE, dispatched AS JOB A.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_d_s5_04_chapter_summary_executed_by_writer_role(retrieval_session):
    ctx = _seed_chapter_close_ctx(retrieval_session, story_id="sz2-d-s5-04")
    executor = _FakeWorkerExecutionService(result_status=WorkerResultStatus.COMPLETED)
    governance = _FakeGovernanceService()

    def _job_a_status_probe() -> str | None:
        jobs = {
            job.job_kind: job
            for job in ctx.workflow_job_service.list_jobs_for_turn(
                turn_id=ctx.close_identity.turn_id
            )
        }
        job_a = jobs.get(RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS.value)
        return job_a.status if job_a is not None else None

    writer_worker = _FakeWriterRoleWorker(job_status_probe=_job_a_status_probe)
    turn_domain_service = _build_turn_domain_service(
        ctx,
        executor=executor,
        governance=governance,
        writer_worker=writer_worker,
    )

    await turn_domain_service.complete_chapter(
        request=_complete_chapter_request(ctx),
        runtime_identity=ctx.close_identity,
    )

    # (1) The summary text was produced BY THE WRITER ROLE — invoked exactly once with
    #     a summary WritingPacket; retrieval is OFF (no opt-in), so the writer worker
    #     uses its plain generation path. The old _FakeSummaryGateway seam is gone.
    assert len(writer_worker.calls) == 1
    packet = writer_worker.calls[0]["packet"]
    assert packet.output_kind == "discussion_message"
    assert packet.operation_mode == "writing"
    assert packet.metadata["summary_kind"] == "chapter_summary"
    assert "writer_retrieval_allowed" not in packet.metadata
    assert packet.session_id == ctx.close_identity.session_id
    assert writer_worker.calls[0]["model_id"] == "model-sz1-chapter-close"

    # (2) Dispatched AS JOB A's work (Option II): at writer-call time JOB A already
    #     existed and was still PENDING — the writer ran INSIDE JOB A's open lifecycle,
    #     not before the graph (Option I) and not skipped (the unconditional label).
    assert writer_worker.job_a_status_at_call == [
        RuntimeWorkflowJobStatus.PENDING.value
    ]

    jobs = _jobs_by_kind(ctx)
    job_a = jobs[RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS.value]
    job_b = jobs[RuntimeWorkflowJobKind.RUNTIME_WORKSPACE_FINALIZE.value]
    job_g = jobs[RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value]

    # (3) JOB A terminalized on the real writer outcome: completed + bridge id
    #     (bridge-after-summary still observable).
    assert job_a.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert any(
        ref.startswith(f"chapter-bridge:{ctx.close_identity.turn_id}:")
        for ref in job_a.result_ref_ids_json
    )

    # (4) The persisted branch bridge summary == the writer worker's output, and the
    #     provenance tags are the writer-role tags (behavioral proof of the producer).
    bridge_reader = LongformChapterRuntimeService(
        story_session_service=ctx.service,
        session=ctx.db,
    )
    bridge = bridge_reader.get_latest_bridge_material_for_branch(
        story_id=ctx.close_identity.story_id,
        session_id=ctx.close_identity.session_id,
        branch_head_id=ctx.close_identity.branch_head_id,
        source_chapter_index=1,
        identity=ctx.close_identity,
    )
    assert bridge is not None
    assert bridge.summary_text == "Chapter one closed at the river gate."
    assert bridge.metadata_json["summary_provider"] == "writer_role_worker"
    assert bridge.metadata_json["summary_generation_mode"] == "writer_role"

    # (5) Still scheduler-required + scheduler-gated (the writer cannot self-gate):
    #     all three jobs required; the turn settles only because B and G also completed.
    assert job_a.required_for_turn_completion is True
    assert job_b.required_for_turn_completion is True
    assert job_g.required_for_turn_completion is True
    assert job_b.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_g.status == RuntimeWorkflowJobStatus.COMPLETED.value
    close_turn = ctx.identity_service.get_turn(ctx.close_identity.turn_id)
    assert close_turn is not None
    assert close_turn.status == StoryTurnStatus.SETTLED.value


# --------------------------------------------------------------------------- #
# D-S5-05 (S-Z2, STRONG) — writer-role summary failure fails JOB A, blocks settle.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_d_s5_05_writer_role_summary_failure_blocks_settlement(retrieval_session):
    ctx = _seed_chapter_close_ctx(retrieval_session, story_id="sz2-d-s5-05")
    executor = _FakeWorkerExecutionService(result_status=WorkerResultStatus.COMPLETED)
    governance = _FakeGovernanceService()
    writer_worker = _FakeWriterRoleWorker(
        error=RuntimeError("injected_writer_role_summary_failure"),
    )
    turn_domain_service = _build_turn_domain_service(
        ctx,
        executor=executor,
        governance=governance,
        writer_worker=writer_worker,
    )

    await turn_domain_service.complete_chapter(
        request=_complete_chapter_request(ctx),
        runtime_identity=ctx.close_identity,
    )

    # The writer role WAS invoked (it is JOB A's transport) and it raised.
    assert len(writer_worker.calls) == 1

    jobs = _jobs_by_kind(ctx)
    job_a = jobs[RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS.value]
    job_b = jobs[RuntimeWorkflowJobKind.RUNTIME_WORKSPACE_FINALIZE.value]
    job_g = jobs[RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE.value]

    # STRONG form (JOB A analog of D-S5-03): B and G DO complete; only A fails because
    # the WRITER ROLE raised — proving JOB A terminalizes on the real writer outcome
    # (kills the unconditional-complete facade), per-job, no batch helper.
    assert job_b.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_g.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert job_a.status == RuntimeWorkflowJobStatus.FAILED.value
    assert job_a.failure_reason == "RuntimeError"
    # No bridge materialized on writer failure (no false-green).
    assert not any(
        ref.startswith("chapter-bridge:") for ref in job_a.result_ref_ids_json
    )

    # A failed required job is NOT settlement-terminal -> turn never settles.
    settlement = ctx.workflow_job_service.evaluate_turn_settlement(
        turn_id=ctx.close_identity.turn_id
    )
    assert settlement.eligible is False
    assert job_a.job_id in settlement.blocking_job_ids
    close_turn = ctx.identity_service.get_turn(ctx.close_identity.turn_id)
    assert close_turn is not None
    assert close_turn.status not in {
        StoryTurnStatus.SETTLED.value,
        StoryTurnStatus.COMPLETED.value,
    }


# --------------------------------------------------------------------------- #
# NUM-012 — chapter close materializes no recall (reserved enum slot kept).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_num_012_chapter_close_creates_no_recall(retrieval_session):
    ctx = _seed_chapter_close_ctx(retrieval_session, story_id="sz1-num-012")
    executor = _FakeWorkerExecutionService(result_status=WorkerResultStatus.COMPLETED)
    governance = _FakeGovernanceService()
    turn_domain_service = _build_turn_domain_service(
        ctx,
        executor=executor,
        governance=governance,
    )

    await turn_domain_service.complete_chapter(
        request=_complete_chapter_request(ctx),
        runtime_identity=ctx.close_identity,
    )

    job_kinds = {
        job.job_kind
        for job in ctx.workflow_job_service.list_jobs_for_turn(
            turn_id=ctx.close_identity.turn_id
        )
    }
    # No recall_materialization job is auto-created at chapter close (NUM-012 defer).
    assert RuntimeWorkflowJobKind.RECALL_MATERIALIZATION.value not in job_kinds
    # The reserved enum slot still exists (contract kept, not deleted).
    assert RuntimeWorkflowJobKind.RECALL_MATERIALIZATION.value == "recall_materialization"

    # No recall seed asset is persisted by the chapter-close path.
    assert (
        RetrievalDocumentService(retrieval_session).list_story_assets(ctx.session.story_id)
        == []
    )
