"""Tests for persisted proposal/apply workflow and regression integration."""

from __future__ import annotations

import pytest

from rp.models.proposal.core_mutation import (
    CORE_MUTATION_ORIGIN_DETERMINISTIC_SYSTEM_REFRESH,
    CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY,
)
from rp.models.shared.dsl import Domain, Layer
from rp.models.memory.contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory.crud import ProposalSubmitInput
from rp.models.proposal.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story.runtime import (
    LongformChapterPhase,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.core_state.legacy_state_patch_proposal_builder import (
    LegacyStatePatchProposalBuilder,
)
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state.authoritative_compatibility_mirror_service import (
    AuthoritativeCompatibilityMirrorService,
)
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.writer.longform_regression_service import LongformRegressionService
from rp.services.memory.change_event_service import MemoryChangeEventService
from rp.services.proposal.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal.apply_service import ProposalApplyService
from rp.services.proposal.repository import ProposalRepository
from rp.services.proposal.workflow_service import ProposalWorkflowService
from rp.services.projection.refresh_service import ProjectionRefreshService
from rp.services.recall.continuity_note_ingestion_service import (
    RecallContinuityNoteIngestionService,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.session_service import StorySessionService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.state_apply_service import StoryStateApplyService
from rp.tests.services._helpers.core_state_dual_write_helpers import (
    build_seeded_core_state_dual_write_service_from_story_service,
)
from rp.models.writer.worker_memory import WorkerProposalGovernanceMetadata


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
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
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return service.get_session(session.session_id), service.get_chapter_by_index(
        session_id=session.session_id,
        chapter_index=1,
    )


def _build_workflow(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    core_state_store_repository = CoreStateStoreRepository(retrieval_session)
    dual_write_service = build_seeded_core_state_dual_write_service_from_story_service(
        story_session_service,
        story_id="story-1",
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
    return story_session_service, repository, workflow


def _build_projection_refresh_service(
    retrieval_session,
    story_session_service: StorySessionService,
) -> ProjectionRefreshService:
    return ProjectionRefreshService(
        story_session_service,
        core_state_dual_write_service=(
            build_seeded_core_state_dual_write_service_from_story_service(
                story_session_service,
                story_id="story-1",
            )
        ),
    )


def _build_runtime_identity(retrieval_session, *, session_id: str):
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session_id,
        created_from="test.proposal_workflow.worker_core_mutation",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    return identity_service.resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind="write_next_segment",
        actor="worker_core_mutation_test",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


class _StaticPlanOrchestrator:
    async def plan(self, **kwargs):
        return OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue the chapter.",
        )


class _CapturingSpecialist:
    def __init__(self) -> None:
        self.accepted_segment_ids: list[str] = []

    async def analyze(self, **kwargs):
        self.accepted_segment_ids = [
            item.artifact_id for item in kwargs["accepted_segments"]
        ]
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=segment_drafting"],
            writer_hints=["Runtime Only Hint"],
            summary_updates=["Light regression continuity note must stay transient."],
        )


class _FailIfContinuityNoteIngestionRuns(RecallContinuityNoteIngestionService):
    def __init__(self) -> None:
        pass

    def ingest_continuity_notes(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        summary_updates: list[str],
    ) -> list[str]:
        raise AssertionError("light regression must not materialize continuity notes")


class _FailingCoreStateDualWriteService:
    def ensure_authoritative_targets_seed(self, **kwargs):
        return None

    def materialize_authoritative_snapshot(self, **kwargs):
        return dict(kwargs.get("fallback_snapshot") or {})

    def current_authoritative_revision(self, **kwargs):
        return 0

    def apply_authoritative_mutation(self, **kwargs):
        raise RuntimeError("phase_e_core_shadow_write_failed")


@pytest.mark.asyncio
async def test_proposal_workflow_applies_and_persists_receipt(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Updated Chapter"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="tool",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )

    assert receipt.status == "applied"
    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"]
        == "Updated Chapter"
    )
    proposal_record = repository.get_proposal_record(receipt.proposal_id)
    assert proposal_record is not None
    assert proposal_record.status == "applied"
    apply_receipts = repository.list_apply_receipts_for_proposal(receipt.proposal_id)
    assert len(apply_receipts) == 1
    assert apply_receipts[0].revision_after_json["chapter.current"] == 2


@pytest.mark.asyncio
async def test_proposal_workflow_applies_matching_base_ref(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Base Matched Chapter"},
                }
            ],
            base_refs=[
                {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE,
                    "domain": Domain.CHAPTER,
                    "domain_path": "chapter.current",
                    "scope": "story",
                    "revision": 1,
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="tool",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )

    assert receipt.status == "applied"
    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"]
        == "Base Matched Chapter"
    )
    apply_receipts = repository.list_apply_receipts_for_proposal(receipt.proposal_id)
    assert len(apply_receipts) == 1
    assert apply_receipts[0].revision_after_json["chapter.current"] == 2


@pytest.mark.asyncio
async def test_proposal_workflow_rejects_stale_base_ref_before_mutation(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    fresh_receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Fresh Chapter"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="tool",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )

    with pytest.raises(ValueError, match="phase_e_apply_base_revision_conflict"):
        await workflow.submit_and_route(
            ProposalSubmitInput(
                story_id="story-1",
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "chapter.current",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.current",
                        },
                        "field_patch": {"title": "Stale Chapter"},
                    }
                ],
                base_refs=[
                    {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                        "scope": "story",
                        "revision": 1,
                    }
                ],
            ),
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            submit_source="tool",
            policy=PostWriteMaintenancePolicy(
                preset_id="test",
                fallback_decision=PolicyDecision.NOTIFY_APPLY,
            ),
        )

    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"] == "Fresh Chapter"
    )
    proposal_records = repository.list_proposals_for_story("story-1")
    stale_record = proposal_records[-1]
    assert stale_record.status == "failed"
    assert stale_record.error_message is not None
    assert stale_record.error_message.startswith("phase_e_apply_base_revision_conflict")
    assert repository.list_apply_receipts_for_proposal(stale_record.proposal_id) == []
    assert (
        len(repository.list_apply_receipts_for_proposal(fresh_receipt.proposal_id)) == 1
    )
    assert (
        len(
            repository.list_apply_receipts_for_story(
                "story-1",
                session_id=session.session_id,
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_proposal_workflow_rejects_base_ref_without_revision(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    with pytest.raises(ValueError, match="phase_e_apply_base_revision_missing"):
        await workflow.submit_and_route(
            ProposalSubmitInput(
                story_id="story-1",
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "chapter.current",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.current",
                        },
                        "field_patch": {"title": "Missing Revision Chapter"},
                    }
                ],
                base_refs=[
                    {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                        "scope": "story",
                    }
                ],
            ),
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            submit_source="tool",
            policy=PostWriteMaintenancePolicy(
                preset_id="test",
                fallback_decision=PolicyDecision.NOTIFY_APPLY,
            ),
        )

    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"] == "Chapter One"
    )
    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].status == "failed"
    assert proposal_records[0].error_message is not None
    assert proposal_records[0].error_message.startswith(
        "phase_e_apply_base_revision_missing"
    )
    assert (
        repository.list_apply_receipts_for_proposal(proposal_records[0].proposal_id)
        == []
    )


@pytest.mark.asyncio
async def test_apply_service_does_not_reapply_applied_proposal(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.TIMELINE,
            domain_path="timeline.event_spine",
            operations=[
                {
                    "kind": "append_event",
                    "target_ref": {
                        "object_id": "timeline.event_spine",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.TIMELINE,
                        "domain_path": "timeline.event_spine",
                    },
                    "event_data": {"event": "first-event"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="tool",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )

    replay_receipt = ProposalApplyService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        story_state_apply_service=StoryStateApplyService(),
        core_state_dual_write_service=(
            build_seeded_core_state_dual_write_service_from_story_service(
                story_session_service,
                story_id="story-1",
            )
        ),
    ).apply_proposal(receipt.proposal_id)

    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert updated_session.current_state_json["timeline_spine"] == [
        {"event": "first-event"}
    ]
    assert replay_receipt.proposal_id == receipt.proposal_id
    assert len(repository.list_apply_receipts_for_proposal(receipt.proposal_id)) == 1


@pytest.mark.asyncio
async def test_proposal_workflow_keeps_review_required_pending(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Pending Chapter"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="tool",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.REVIEW_REQUIRED,
        ),
    )

    assert receipt.status == "review_required"
    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"] == "Chapter One"
    )
    assert repository.list_apply_receipts_for_proposal(receipt.proposal_id) == []


@pytest.mark.asyncio
async def test_proposal_workflow_persists_worker_core_mutation_metadata(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    _, repository, workflow = _build_workflow(retrieval_session)

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Worker Proposed Chapter"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="worker_memory:specialist",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.REVIEW_REQUIRED,
        ),
        governance_metadata=WorkerProposalGovernanceMetadata(
            identity=MemoryRuntimeIdentity(
                story_id=session.story_id,
                session_id=session.session_id,
                branch_head_id="branch:test:worker",
                turn_id="turn:test:worker",
                runtime_profile_snapshot_id="snapshot:test:worker",
            ),
            worker_id="specialist",
            phase="outline_drafting",
            runtime_profile_snapshot_id="snapshot:test:worker",
            permission_decision="allowed",
            permission_reason_codes=["allowed"],
            source_refs=[
                MemorySourceRef(
                    source_type="runtime_workspace_material",
                    source_id="mat-worker-candidate",
                    layer="runtime_workspace",
                    domain=Domain.CHAPTER.value,
                    block_id="chapter.current",
                )
            ],
            trace_refs=["trace:worker:test"],
        ),
    )

    record = repository.get_proposal_record(receipt.proposal_id)

    assert receipt.status == "review_required"
    assert record is not None
    assert record.governance_metadata_json["worker_id"] == "specialist"
    assert record.governance_metadata_json["core_mutation"]["origin_kind"] == (
        CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY
    )
    assert record.governance_metadata_json["core_mutation"]["actor"] == (
        "worker.specialist"
    )
    assert record.governance_metadata_json["core_mutation"]["trace_refs"] == [
        "trace:worker:test"
    ]
    assert (
        record.governance_metadata_json["core_mutation"]["source_refs"][0]["source_id"]
        == "mat-worker-candidate"
    )


@pytest.mark.asyncio
async def test_worker_core_mutation_apply_records_shared_outcomes(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    _, repository, workflow = _build_workflow(retrieval_session)
    identity = _build_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
    )

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Worker Applied Chapter"},
                }
            ],
            base_refs=[
                {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE,
                    "domain": Domain.CHAPTER,
                    "domain_path": "chapter.current",
                    "scope": "story",
                    "revision": 1,
                }
            ],
            reason="worker governed apply",
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="worker_memory:specialist",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
        governance_metadata=WorkerProposalGovernanceMetadata(
            identity=identity,
            worker_id="specialist",
            phase="outline_drafting",
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
            permission_decision="allowed",
            permission_reason_codes=["allowed", "writer_visible"],
            source_refs=[
                MemorySourceRef(
                    source_type="runtime_workspace_material",
                    source_id="mat-worker-applied-candidate",
                    layer="runtime_workspace",
                    domain=Domain.CHAPTER.value,
                    block_id="chapter.current",
                )
            ],
            trace_refs=["trace:worker:applied"],
        ),
    )

    apply_receipts = repository.list_apply_receipts_for_proposal(receipt.proposal_id)
    events = MemoryChangeEventService(session=retrieval_session).list_events(
        identity=identity
    )
    core_events = [
        event
        for event in events
        if event.event_kind == "core_authoritative_mutation_applied"
    ]

    assert receipt.status == "applied"
    assert len(apply_receipts) == 1
    assert (
        f"core_mutation:origin_kind={CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY}"
        in apply_receipts[0].warnings_json
    )
    assert "core_mutation:projection_dirty=chapter.current" in (
        apply_receipts[0].warnings_json
    )
    assert len(core_events) == 1
    core_event = core_events[0]
    assert core_event.metadata["origin_kind"] == (
        CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY
    )
    assert core_event.metadata["worker_id"] == "specialist"
    assert core_event.metadata["permission_decision"] == "allowed"
    assert core_event.metadata["projection_refresh"] == "stale_mark_only"
    assert any(
        ref.source_type == "runtime_workspace_material"
        and ref.source_id == "mat-worker-applied-candidate"
        for ref in core_event.source_refs
    )
    dirty_targets_by_kind = {
        target.target_kind: target for target in core_event.dirty_targets
    }
    assert "core_authoritative_block" in dirty_targets_by_kind
    assert "projection_refresh_pending" in dirty_targets_by_kind
    assert (
        dirty_targets_by_kind["projection_refresh_pending"].metadata["refresh_state"]
        == "stale_mark_only"
    )


@pytest.mark.asyncio
async def test_proposal_workflow_marks_failed_for_non_authoritative_target(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    _, repository, workflow = _build_workflow(retrieval_session)

    with pytest.raises(ValueError, match="phase_e_apply_non_authoritative_target"):
        await workflow.submit_and_route(
            ProposalSubmitInput(
                story_id="story-1",
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="projection.current_outline_digest",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "projection.current_outline_digest",
                            "layer": Layer.CORE_STATE_PROJECTION,
                            "domain": Domain.CHAPTER,
                            "domain_path": "projection.current_outline_digest",
                        },
                        "field_patch": {"title": "Bad Target"},
                    }
                ],
            ),
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            submit_source="tool",
            policy=PostWriteMaintenancePolicy(
                preset_id="test",
                fallback_decision=PolicyDecision.NOTIFY_APPLY,
            ),
        )

    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].status == "failed"


@pytest.mark.asyncio
async def test_proposal_workflow_rejects_unimplemented_operation_kinds_before_persist(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    _, repository, workflow = _build_workflow(retrieval_session)

    with pytest.raises(
        ValueError, match="phase_e_operation_not_supported:remove_record"
    ):
        await workflow.submit_and_route(
            ProposalSubmitInput(
                story_id="story-1",
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                operations=[
                    {
                        "kind": "remove_record",
                        "target_ref": {
                            "object_id": "chapter.current",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.current",
                        },
                    }
                ],
            ),
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            submit_source="tool",
            policy=PostWriteMaintenancePolicy(
                preset_id="test",
                fallback_decision=PolicyDecision.NOTIFY_APPLY,
            ),
        )

    assert repository.list_proposals_for_story("story-1") == []


@pytest.mark.asyncio
async def test_proposal_workflow_rolls_back_state_when_receipt_write_fails(
    retrieval_session, monkeypatch
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)

    def fail_create_apply_receipt(**kwargs):
        raise RuntimeError("phase_e_apply_receipt_write_failed")

    monkeypatch.setattr(repository, "create_apply_receipt", fail_create_apply_receipt)

    with pytest.raises(RuntimeError, match="phase_e_apply_receipt_write_failed"):
        await workflow.submit_and_route(
            ProposalSubmitInput(
                story_id="story-1",
                mode="longform",
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                operations=[
                    {
                        "kind": "patch_fields",
                        "target_ref": {
                            "object_id": "chapter.current",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.CHAPTER,
                            "domain_path": "chapter.current",
                        },
                        "field_patch": {"title": "Should Roll Back"},
                    }
                ],
            ),
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            submit_source="tool",
            policy=PostWriteMaintenancePolicy(
                preset_id="test",
                fallback_decision=PolicyDecision.NOTIFY_APPLY,
            ),
        )

    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert (
        updated_session.current_state_json["chapter_digest"]["title"] == "Chapter One"
    )
    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].status == "failed"
    assert (
        repository.list_apply_receipts_for_proposal(proposal_records[0].proposal_id)
        == []
    )


@pytest.mark.asyncio
async def test_proposal_workflow_rolls_back_mirror_when_core_shadow_write_fails(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
            core_state_dual_write_service=_FailingCoreStateDualWriteService(),
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )

    with pytest.raises(RuntimeError, match="phase_e_core_shadow_write_failed"):
        await workflow.submit_and_route(
            ProposalSubmitInput(
                story_id="story-1",
                mode="longform",
                domain=Domain.TIMELINE,
                domain_path="timeline.event_spine",
                operations=[
                    {
                        "kind": "append_event",
                        "target_ref": {
                            "object_id": "timeline.event_spine",
                            "layer": Layer.CORE_STATE_AUTHORITATIVE,
                            "domain": Domain.TIMELINE,
                            "domain_path": "timeline.event_spine",
                        },
                        "event_data": {"event": "should-roll-back"},
                    }
                ],
            ),
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            submit_source="tool",
            policy=PostWriteMaintenancePolicy(
                preset_id="test",
                fallback_decision=PolicyDecision.NOTIFY_APPLY,
            ),
        )

    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert updated_session.current_state_json["timeline_spine"] == []
    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].status == "failed"
    assert (
        repository.list_apply_receipts_for_proposal(proposal_records[0].proposal_id)
        == []
    )


@pytest.mark.asyncio
async def test_longform_regression_routes_authoritative_patch_through_workflow(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)
    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=object(),
        specialist_service=object(),
        proposal_workflow_service=workflow,
        legacy_state_patch_proposal_builder=LegacyStatePatchProposalBuilder(),
        projection_refresh_service=_build_projection_refresh_service(
            retrieval_session,
            story_session_service,
        ),
    )

    updated_session, updated_chapter = await regression_service._apply_bundle(
        session=session,
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=outline_drafting"],
            writer_hints=["Hint Updated"],
            state_patch_proposals={
                "narrative_progress": {
                    "accepted_segments": 1,
                    "chapter_summary": "Accepted chapter summary",
                }
            },
        ),
    )

    assert (
        updated_session.current_state_json["narrative_progress"]["accepted_segments"]
        == 1
    )
    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].submit_source == "post_write_regression"
    assert (
        proposal_records[0].governance_metadata_json["core_mutation"]["origin_kind"]
        == CORE_MUTATION_ORIGIN_DETERMINISTIC_SYSTEM_REFRESH
    )
    assert proposal_records[0].status == "applied"
    apply_receipts = repository.list_apply_receipts_for_proposal(
        proposal_records[0].proposal_id
    )
    assert len(apply_receipts) == 1
    assert (
        f"core_mutation:origin_kind={CORE_MUTATION_ORIGIN_DETERMINISTIC_SYSTEM_REFRESH}"
        in apply_receipts[0].warnings_json
    )
    assert updated_chapter.builder_snapshot_json["foundation_digest"] == [
        "Found Updated"
    ]
    assert "writer_hints" not in updated_chapter.builder_snapshot_json


@pytest.mark.asyncio
async def test_longform_regression_light_path_deduplicates_newly_accepted_segment(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, _, workflow = _build_workflow(retrieval_session)
    accepted_artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted segment text.",
    )
    story_session_service.commit()

    specialist_service = _CapturingSpecialist()
    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=specialist_service,
        proposal_workflow_service=workflow,
        legacy_state_patch_proposal_builder=LegacyStatePatchProposalBuilder(),
        projection_refresh_service=_build_projection_refresh_service(
            retrieval_session,
            story_session_service,
        ),
        recall_continuity_note_ingestion_service=(_FailIfContinuityNoteIngestionRuns()),
    )

    session = story_session_service.get_session(session.session_id)
    chapter = story_session_service.get_chapter_by_index(
        session_id=accepted_artifact.session_id,
        chapter_index=1,
    )
    assert session is not None
    assert chapter is not None

    await regression_service.run_light_regression(
        session=session,
        chapter=chapter,
        accepted_artifact=accepted_artifact,
        model_id="model-1",
        provider_id=None,
    )

    assert specialist_service.accepted_segment_ids == [accepted_artifact.artifact_id]
