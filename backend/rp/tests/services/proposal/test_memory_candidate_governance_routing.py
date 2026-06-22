from __future__ import annotations

import pytest

from rp.models.proposal.core_mutation import CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY
from rp.models.runtime.workflow_job import RuntimeWorkflowJobStatus
from rp.models.story.runtime import LongformChapterPhase
from rp.models.writer.worker_runtime_contracts import (
    WorkerExecutionPlan,
    WorkerPlanSource,
    WorkerResult,
    WorkerResultStatus,
)
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state.authoritative_compatibility_mirror_service import (
    AuthoritativeCompatibilityMirrorService,
)
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.proposal.apply_service import ProposalApplyService
from rp.services.proposal.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal.post_write_governance_service import (
    PostWriteGovernanceService,
)
from rp.services.proposal.repository import ProposalRepository
from rp.services.proposal.workflow_service import ProposalWorkflowService
from rp.services.projection.refresh_service import ProjectionRefreshService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService
from rp.services.story.state_apply_service import StoryStateApplyService
from rp.services.writer.memory_maintenance_worker_adapter import (
    S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
    S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
)
from rp.services.writer.worker_registry_service import LONGFORM_MEMORY_WORKER_ID
from rp.tests.services._helpers.core_state_dual_write_helpers import (
    build_seeded_core_state_dual_write_service_from_story_service,
)


@pytest.mark.asyncio
async def test_s3_review_required_candidate_persists_proposal_without_apply(
    retrieval_session,
):
    session, chapter, identity = _seed_runtime(retrieval_session)
    _, repository, governance_service = _build_services(retrieval_session)

    job_refs = await governance_service._dispatch_proposal_governance(
        identity=identity,
        session=session,
        chapter=chapter,
        worker_plan=_worker_plan(identity),
        worker_results=[
            _worker_result(
                _s3_candidate(governance_route="review_required"),
            )
        ],
    )

    assert len(job_refs) == 1
    proposal_records = repository.list_proposals_for_story(session.story_id)
    assert len(proposal_records) == 1
    proposal = proposal_records[0]
    assert proposal.status == "review_required"
    assert proposal.policy_decision == "review_required"
    assert proposal.submit_source.startswith("post_write_worker|worker=")
    assert proposal.operations_json[0]["kind"] == "append_event"
    assert proposal.operations_json[0]["event_data"]["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )
    assert proposal.base_refs_json == [
        {
            "object_id": "plot_thread.active",
            "layer": "core_state.authoritative",
            "domain": "plot_thread",
            "domain_path": "plot_thread.active",
            "scope": "story",
            "revision": 1,
        }
    ]
    core_mutation = proposal.governance_metadata_json["core_mutation"]
    assert core_mutation["origin_kind"] == CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY
    assert core_mutation["base_refs"][0]["revision"] == 1
    assert "s3_candidate_kind:s3_memory_maintenance_candidate" in (
        core_mutation["trace_refs"]
    )
    assert repository.list_apply_receipts_for_proposal(proposal.proposal_id) == []
    jobs = RuntimeWorkflowJobService(retrieval_session).list_jobs_for_turn(
        turn_id=identity.turn_id,
    )
    assert jobs[0].status == RuntimeWorkflowJobStatus.COMPLETED.value
    assert jobs[0].metadata_json["proposal_count"] == 1


@pytest.mark.asyncio
async def test_s3_direct_apply_candidate_routes_through_proposal_apply_service(
    retrieval_session,
):
    session, chapter, identity = _seed_runtime(retrieval_session)
    story_session_service, repository, governance_service = _build_services(
        retrieval_session
    )

    await governance_service._dispatch_proposal_governance(
        identity=identity,
        session=session,
        chapter=chapter,
        worker_plan=_worker_plan(identity),
        worker_results=[
            _worker_result(
                _s3_candidate(governance_route="direct_apply_allowed"),
            )
        ],
    )

    proposal = repository.list_proposals_for_story(session.story_id)[0]
    assert proposal.status == "applied"
    apply_receipts = repository.list_apply_receipts_for_proposal(proposal.proposal_id)
    assert len(apply_receipts) == 1
    assert apply_receipts[0].revision_after_json["plot_thread.active"] == 2
    assert (
        f"core_mutation:origin_kind={CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY}"
        in apply_receipts[0].warnings_json
    )
    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    active_threads = updated_session.current_state_json["active_threads"]
    assert len(active_threads) == 1
    assert active_threads[0]["content"] == (
        "The bridge cutoff becomes the active thread."
    )
    assert active_threads[0]["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )


@pytest.mark.asyncio
async def test_invalid_s3_handoff_marks_proposal_job_failed(retrieval_session):
    session, chapter, identity = _seed_runtime(retrieval_session)
    _, repository, governance_service = _build_services(retrieval_session)
    candidate = _s3_candidate(governance_route="review_required")
    candidate["payload"]["candidates"][0]["base_block_revision_id"] = "revision-one"

    job_refs = await governance_service._dispatch_proposal_governance(
        identity=identity,
        session=session,
        chapter=chapter,
        worker_plan=_worker_plan(identity),
        worker_results=[_worker_result(candidate)],
    )

    assert len(job_refs) == 1
    assert repository.list_proposals_for_story(session.story_id) == []
    jobs = RuntimeWorkflowJobService(retrieval_session).list_jobs_for_turn(
        turn_id=identity.turn_id,
    )
    assert len(jobs) == 1
    assert jobs[0].status == RuntimeWorkflowJobStatus.FAILED.value
    assert jobs[0].failure_reason == "memory_candidate_base_revision_unparseable"
    assert jobs[0].last_error_json == {
        "code": "memory_candidate_base_revision_unparseable",
        "message": "memory_candidate_base_revision_unparseable:revision-one",
        "stage": "proposal_governance_dispatch",
    }
    assert jobs[0].metadata_json["proposal_governance_failure_reason_code"] == (
        "memory_candidate_base_revision_unparseable"
    )


def _seed_runtime(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-s3c",
        source_workspace_id="workspace-s3c",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={},
    )
    story_session_service.commit()
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.s3c.governance",
    )
    identity = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="write_next_segment",
        actor="s3c_test",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    return session, chapter, identity


def _build_services(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    core_state_store_repository = CoreStateStoreRepository(retrieval_session)
    dual_write_service = build_seeded_core_state_dual_write_service_from_story_service(
        story_session_service,
        story_id="story-s3c",
    )
    authoritative_mirror_service = AuthoritativeCompatibilityMirrorService(
        story_session_service=story_session_service
    )
    apply_service = ProposalApplyService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        story_state_apply_service=StoryStateApplyService(),
        core_state_dual_write_service=dual_write_service,
        authoritative_compatibility_mirror_service=authoritative_mirror_service,
        core_state_as_of_resolver=CoreStateAsOfResolver(
            session=retrieval_session,
            repository=core_state_store_repository,
            mirror_service=authoritative_mirror_service,
        ),
    )
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=apply_service,
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    governance_service = PostWriteGovernanceService(
        runtime_workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
        projection_refresh_service=ProjectionRefreshService(
            story_session_service,
            core_state_dual_write_service=dual_write_service,
        ),
        core_state_as_of_resolver=CoreStateAsOfResolver(
            session=retrieval_session,
            repository=core_state_store_repository,
            mirror_service=authoritative_mirror_service,
        ),
        proposal_workflow_service=workflow,
    )
    return story_session_service, repository, governance_service


def _worker_plan(identity) -> WorkerExecutionPlan:
    return WorkerExecutionPlan(
        plan_id="worker-plan-s3c",
        identity=identity,
        plan_source=WorkerPlanSource.POST_WRITE_REQUIRED,
        phase="post_write_maintenance",
    )


def _worker_result(candidate: dict) -> WorkerResult:
    return WorkerResult(
        worker_id=LONGFORM_MEMORY_WORKER_ID,
        phase="post_write_maintenance",
        result_status=WorkerResultStatus.COMPLETED,
        proposal_candidates=[candidate],
        metadata={
            "source_of_truth": False,
            "authoritative_mutation": False,
            "context_packet_ref": "worker-packet-s3c",
        },
    )


def _s3_candidate(*, governance_route: str) -> dict:
    return {
        "candidate_kind": S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
        "payload": {
            "schema_version": S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": "post_write_maintenance",
            "candidates": [
                {
                    "target_domain": "plot_threads",
                    "target_block_id": "plot.active_threads",
                    "base_block_revision_id": "block-revision-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "field_id": "facts",
                            "content": (
                                "The bridge cutoff becomes the active thread."
                            ),
                        }
                    ],
                    "source_refs": [
                        {
                            "source_type": "accepted_prose",
                            "source_id": "segment-s3c-1",
                            "layer": "runtime_workspace",
                        }
                    ],
                    "change_summary": "Track the bridge cutoff as a plot thread.",
                }
            ],
        },
        "source_of_truth": False,
        "authoritative_mutation": False,
        "metadata": {
            "adapter": "s3_memory_maintenance_worker_adapter",
            "governance_route": governance_route,
        },
    }
