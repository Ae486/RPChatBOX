"""RuntimeWorkflowJobRecord write-authority characterization tests."""

from __future__ import annotations

from models.rp_story_store import StoryTurnRecord
from rp.devtools.check_story_session_write_boundary import (
    DEFAULT_BACKEND_ROOT,
    scan_story_session_write_boundary,
)
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import LongformChapterPhase
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService


def _seed_story_session(retrieval_session, *, story_id: str):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    return StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def _seed_runtime_identity(retrieval_session, *, story_id: str):
    story_session = _seed_story_session(
        retrieval_session,
        story_id=story_id,
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from=f"test.{story_id}.snapshot",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    return identity


def _ensure_projection_refresh_job(
    workflow_job_service: RuntimeWorkflowJobService,
    *,
    identity,
    metadata: dict | None = None,
):
    return workflow_job_service.ensure_job(
        identity=identity,
        job_kind=RuntimeWorkflowJobKind.PROJECTION_REFRESH,
        job_category=RuntimeWorkflowJobCategory.STATE_GOVERNANCE,
        creation_mode=RuntimeWorkflowJobCreationMode.DERIVED,
        required_for_turn_completion=False,
        metadata=metadata,
    )


def test_c1_ensure_job_does_not_mutate_story_turn_record(retrieval_session):
    identity = _seed_runtime_identity(
        retrieval_session,
        story_id="workflow-job-c1-turn-non-mutation",
    )
    workflow_job_service = RuntimeWorkflowJobService(retrieval_session)
    turn_before = retrieval_session.get(StoryTurnRecord, identity.turn_id)
    assert turn_before is not None
    before_dump = turn_before.model_dump()

    _ensure_projection_refresh_job(workflow_job_service, identity=identity)

    retrieval_session.expire_all()
    turn_after = retrieval_session.get(StoryTurnRecord, identity.turn_id)
    assert turn_after is not None
    assert turn_after.model_dump() == before_dump


def test_c2_ensure_job_is_idempotent_for_same_turn_kind_and_mode(retrieval_session):
    identity = _seed_runtime_identity(
        retrieval_session,
        story_id="workflow-job-c2-idempotency",
    )
    workflow_job_service = RuntimeWorkflowJobService(retrieval_session)

    first = _ensure_projection_refresh_job(workflow_job_service, identity=identity)
    second = _ensure_projection_refresh_job(workflow_job_service, identity=identity)
    jobs = [
        job
        for job in workflow_job_service.list_jobs_for_turn(turn_id=identity.turn_id)
        if job.job_kind == RuntimeWorkflowJobKind.PROJECTION_REFRESH.value
    ]

    assert second.job_id == first.job_id
    assert [job.job_id for job in jobs] == [first.job_id]


def test_c3_terminal_job_transitions_are_noops(retrieval_session):
    identity = _seed_runtime_identity(
        retrieval_session,
        story_id="workflow-job-c3-terminal-guard",
    )
    workflow_job_service = RuntimeWorkflowJobService(retrieval_session)
    job = _ensure_projection_refresh_job(workflow_job_service, identity=identity)
    completed = workflow_job_service.mark_job_completed(
        job_id=job.job_id,
        reason="test_complete",
    )
    terminal_dump = completed.model_dump()

    after_running = workflow_job_service.mark_job_running(
        job_id=job.job_id,
        reason="should_not_run",
        metadata={"after_terminal": "running"},
    )
    after_completed = workflow_job_service.mark_job_completed(
        job_id=job.job_id,
        reason="should_not_complete_again",
        metadata={"after_terminal": "completed"},
    )
    after_deferred = workflow_job_service.mark_job_deferred(
        job_id=job.job_id,
        reason="should_not_defer",
        metadata={"after_terminal": "deferred"},
    )

    assert after_running.model_dump() == terminal_dump
    assert after_completed.model_dump() == terminal_dump
    assert after_deferred.model_dump() == terminal_dump
    assert after_deferred.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert after_deferred.attempt_count == 0
    assert after_deferred.completed_at == terminal_dump["completed_at"]


def test_c4_mark_job_completed_merges_metadata_and_sets_completion_state(
    retrieval_session,
):
    identity = _seed_runtime_identity(
        retrieval_session,
        story_id="workflow-job-c4-metadata-merge",
    )
    workflow_job_service = RuntimeWorkflowJobService(retrieval_session)
    job = _ensure_projection_refresh_job(
        workflow_job_service,
        identity=identity,
        metadata={"a": 1},
    )
    created_updated_at = job.updated_at

    completed = workflow_job_service.mark_job_completed(
        job_id=job.job_id,
        reason="test_complete",
        result_ref_ids=["artifact:result"],
        trace_refs=["trace:complete"],
        metadata={"b": 2},
    )

    assert completed.status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert completed.completion_reason == "test_complete"
    assert completed.completed_at is not None
    assert completed.updated_at >= created_updated_at
    assert completed.result_ref_ids_json == ["artifact:result"]
    assert completed.trace_refs_json == ["trace:complete"]
    assert completed.metadata_json == {"a": 1, "b": 2}


def test_c5_runtime_workflow_job_record_construction_is_single_writer():
    result = scan_story_session_write_boundary(DEFAULT_BACKEND_ROOT)
    findings = [
        finding
        for finding in result.allowed_authorized
        if finding.record == "RuntimeWorkflowJobRecord"
    ]

    assert findings
    assert {finding.path for finding in findings} == {
        "rp/services/runtime/workflow_job_service.py"
    }
