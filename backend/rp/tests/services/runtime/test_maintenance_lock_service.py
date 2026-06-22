from __future__ import annotations

import pytest

from models.rp_memory_store import MemoryProposalRecord
from rp.models.runtime.reason_codes import SchedulerReasonCode
from rp.models.runtime.workflow_job import RuntimeWorkflowJobStatus
from rp.services.runtime.maintenance_lock_service import (
    RuntimeMaintenanceLockError,
    RuntimeMaintenanceLockService,
    RuntimeMaintenanceOperation,
)
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.tests.helpers.runtime_seed import seed_runtime_identity


def test_review_required_s3_proposal_activates_current_branch_lock(
    retrieval_session,
):
    identity = seed_runtime_identity(retrieval_session, story_id="s3d-proposal-lock")
    _seed_proposal(retrieval_session, identity=identity, status="review_required")

    service = RuntimeMaintenanceLockService(retrieval_session)
    state = service.evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )

    assert state.active is True
    assert state.reason_code == SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value
    assert len(state.causes) == 1
    assert state.causes[0].source_kind == "proposal"
    assert state.causes[0].status == "review_required"
    assert state.causes[0].branch_head_id == identity.branch_head_id

    blocked = service.check_operation(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
        operation=RuntimeMaintenanceOperation.CORE_MEMORY_EDIT,
    )
    assert blocked.allowed is False
    assert blocked.reason_code == SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value
    assert blocked.causes[0].operation == RuntimeMaintenanceOperation.CORE_MEMORY_EDIT

    allowed = service.check_operation(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
        operation=RuntimeMaintenanceOperation.INSPECT_DEBUG,
    )
    assert allowed.allowed is True
    assert allowed.causes == state.causes


@pytest.mark.parametrize(
    "status",
    [
        "applied",
        "rejected",
        "discarded",
        "failed",
        "invalid",
        "superseded",
        "cancelled",
    ],
)
def test_terminal_proposal_statuses_clear_current_branch_lock(
    retrieval_session,
    status: str,
):
    identity = seed_runtime_identity(
        retrieval_session,
        story_id=f"s3d-proposal-terminal-{status}",
    )
    _seed_proposal(retrieval_session, identity=identity, status=status)

    state = RuntimeMaintenanceLockService(retrieval_session).evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )

    assert state.active is False
    assert state.causes == ()


def test_proposal_lock_is_branch_scoped(retrieval_session):
    identity = seed_runtime_identity(retrieval_session, story_id="s3d-branch-scope")
    _seed_proposal(
        retrieval_session,
        identity=identity,
        status="review_required",
        branch_head_id="branch:other",
    )

    state = RuntimeMaintenanceLockService(retrieval_session).evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )

    assert state.active is False
    assert state.causes == ()


def test_malformed_proposal_metadata_does_not_crash_lock_read(retrieval_session):
    identity = seed_runtime_identity(
        retrieval_session,
        story_id="s3d-malformed-proposal-metadata",
    )
    proposal = _seed_proposal(
        retrieval_session,
        identity=identity,
        status="review_required",
    )
    proposal.governance_metadata_json = ["legacy-invalid-metadata"]
    retrieval_session.add(proposal)
    retrieval_session.flush()

    state = RuntimeMaintenanceLockService(retrieval_session).evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )

    assert state.active is False
    assert state.causes == ()


def test_non_terminal_required_scheduler_gate_blocks_current_branch(
    retrieval_session,
):
    identity = seed_runtime_identity(retrieval_session, story_id="s3d-gate-lock")
    RuntimeWorkflowJobService(retrieval_session).ensure_scheduler_maintenance_gate(
        identity=identity,
        scheduler_job_id="scheduler-job-s3d",
        anchor_turn_id=identity.turn_id,
    )

    state = RuntimeMaintenanceLockService(retrieval_session).evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )

    assert state.active is True
    assert len(state.causes) == 1
    assert state.causes[0].source_kind == "runtime_job"
    assert state.causes[0].metadata["job_kind"] == "scheduler_maintenance_gate"


@pytest.mark.parametrize(
    "status",
    [
        RuntimeWorkflowJobStatus.COMPLETED,
        RuntimeWorkflowJobStatus.DEFERRED,
        RuntimeWorkflowJobStatus.FAILED,
        RuntimeWorkflowJobStatus.CANCELLED,
    ],
)
def test_terminal_required_job_statuses_clear_current_branch_lock(
    retrieval_session,
    status: RuntimeWorkflowJobStatus,
):
    identity = seed_runtime_identity(
        retrieval_session,
        story_id=f"s3d-job-terminal-{status.value}",
    )
    workflow_jobs = RuntimeWorkflowJobService(retrieval_session)
    job = workflow_jobs.ensure_scheduler_maintenance_gate(
        identity=identity,
        scheduler_job_id=f"scheduler-job-{status.value}",
        anchor_turn_id=identity.turn_id,
    )
    if status == RuntimeWorkflowJobStatus.COMPLETED:
        workflow_jobs.mark_job_completed(job_id=job.job_id, reason="test")
    elif status == RuntimeWorkflowJobStatus.DEFERRED:
        workflow_jobs.mark_job_deferred(job_id=job.job_id, reason="test")
    elif status == RuntimeWorkflowJobStatus.FAILED:
        workflow_jobs.mark_job_failed(job_id=job.job_id, reason="test")
    else:
        job.status = RuntimeWorkflowJobStatus.CANCELLED.value
        retrieval_session.add(job)
        retrieval_session.flush()

    state = RuntimeMaintenanceLockService(retrieval_session).evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )

    assert state.active is False
    assert state.causes == ()


def test_w5a_lock_operation_matrix(retrieval_session):
    identity = seed_runtime_identity(retrieval_session, story_id="s3d-operation-matrix")
    _seed_proposal(retrieval_session, identity=identity, status="review_required")
    service = RuntimeMaintenanceLockService(retrieval_session)

    blocked_operations = [
        RuntimeMaintenanceOperation.CORE_MEMORY_EDIT,
        RuntimeMaintenanceOperation.PROJECTION_EDIT,
        RuntimeMaintenanceOperation.MANUAL_ACCEPTED_PROSE_EDIT,
        RuntimeMaintenanceOperation.STORY_PROGRESSION,
        RuntimeMaintenanceOperation.ROLLBACK,
        RuntimeMaintenanceOperation.BRANCH_SWITCH,
        RuntimeMaintenanceOperation.BRANCH_CREATE,
        RuntimeMaintenanceOperation.REWRITE,
        RuntimeMaintenanceOperation.REGENERATE,
        RuntimeMaintenanceOperation.CHAPTER_COMPLETE,
        RuntimeMaintenanceOperation.STORY_EVOLUTION_OR_ARCHIVAL_EDIT,
    ]
    for operation in blocked_operations:
        decision = service.check_operation(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            operation=operation,
        )
        assert decision.allowed is False, operation.value
        assert decision.reason_code == SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value

    allowed_operations = [
        RuntimeMaintenanceOperation.INSPECT_DEBUG,
        RuntimeMaintenanceOperation.PROPOSAL_ACCEPT,
        RuntimeMaintenanceOperation.PROPOSAL_REJECT,
        RuntimeMaintenanceOperation.PROPOSAL_DISCARD,
        RuntimeMaintenanceOperation.PROPOSAL_EDIT,
        RuntimeMaintenanceOperation.FAILED_WORKER_RETRY,
        RuntimeMaintenanceOperation.RUNTIME_CONFIG_EDIT,
    ]
    for operation in allowed_operations:
        decision = service.require_allowed(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            operation=operation,
        )
        assert decision.allowed is True, operation.value

    with pytest.raises(RuntimeMaintenanceLockError) as exc_info:
        service.require_allowed(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            operation=RuntimeMaintenanceOperation.STORY_PROGRESSION,
        )
    assert exc_info.value.code == SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value
    assert exc_info.value.operation == RuntimeMaintenanceOperation.STORY_PROGRESSION


def test_unknown_operation_is_rejected_as_input_error(retrieval_session):
    identity = seed_runtime_identity(
        retrieval_session,
        story_id="s3d-unknown-operation",
    )
    service = RuntimeMaintenanceLockService(retrieval_session)

    with pytest.raises(
        ValueError,
        match="runtime_maintenance_operation_unknown:not_a_runtime_operation",
    ):
        service.check_operation(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            operation="not_a_runtime_operation",
        )


def test_failed_stale_base_proposal_status_clears_lock_but_stays_visible(
    retrieval_session,
):
    identity = seed_runtime_identity(retrieval_session, story_id="s3d-stale-clear")
    proposal = _seed_proposal(
        retrieval_session,
        identity=identity,
        status="review_required",
    )
    service = RuntimeMaintenanceLockService(retrieval_session)

    locked = service.evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )
    assert locked.active is True

    proposal.status = "failed"
    proposal.error_message = "phase_e_apply_base_revision_conflict:plot_thread.active"
    retrieval_session.add(proposal)
    retrieval_session.flush()

    unlocked = service.evaluate(
        story_id=identity.story_id,
        session_id=identity.session_id,
        branch_head_id=identity.branch_head_id,
    )
    assert unlocked.active is False
    assert proposal.error_message.startswith("phase_e_apply_base_revision_conflict")


def _seed_proposal(
    retrieval_session,
    *,
    identity,
    status: str,
    branch_head_id: str | None = None,
) -> MemoryProposalRecord:
    proposal = MemoryProposalRecord(
        proposal_id=f"proposal:{identity.story_id}:{status}",
        story_id=identity.story_id,
        session_id=identity.session_id,
        chapter_workspace_id=None,
        mode="longform",
        domain="plot_thread",
        domain_path="plot_thread.active",
        status=status,
        policy_decision="review_required",
        submit_source="post_write_worker|worker=longform_memory_worker",
        operations_json=[],
        base_refs_json=[],
        governance_metadata_json={
            "identity": {
                **identity.model_dump(mode="json"),
                "branch_head_id": branch_head_id or identity.branch_head_id,
            },
            "worker_id": "longform_memory_worker",
            "phase": "post_write_maintenance",
        },
    )
    retrieval_session.add(proposal)
    retrieval_session.flush()
    return proposal
