"""Tests for persisted proposal/apply workflow and regression integration."""

from __future__ import annotations

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import (
    LongformChapterPhase,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.legacy_state_patch_proposal_builder import LegacyStatePatchProposalBuilder
from rp.services.longform_regression_service import LongformRegressionService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService


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
            "narrative_progress": {"current_phase": "outline_drafting", "accepted_segments": 0},
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
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
    apply_service = ProposalApplyService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        story_state_apply_service=StoryStateApplyService(),
    )
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=apply_service,
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    return story_session_service, repository, workflow


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
        self.accepted_segment_ids = [item.artifact_id for item in kwargs["accepted_segments"]]
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=segment_drafting"],
            writer_hints=["Runtime Only Hint"],
        )


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
    assert updated_session.current_state_json["chapter_digest"]["title"] == "Updated Chapter"
    proposal_record = repository.get_proposal_record(receipt.proposal_id)
    assert proposal_record is not None
    assert proposal_record.status == "applied"
    apply_receipts = repository.list_apply_receipts_for_proposal(receipt.proposal_id)
    assert len(apply_receipts) == 1
    assert apply_receipts[0].revision_after_json["chapter.current"] == 2


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
    ).apply_proposal(receipt.proposal_id)

    updated_session = story_session_service.get_session(session.session_id)
    assert updated_session is not None
    assert updated_session.current_state_json["timeline_spine"] == [{"event": "first-event"}]
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
    assert updated_session.current_state_json["chapter_digest"]["title"] == "Chapter One"
    assert repository.list_apply_receipts_for_proposal(receipt.proposal_id) == []


@pytest.mark.asyncio
async def test_proposal_workflow_marks_failed_for_non_authoritative_target(retrieval_session):
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
async def test_proposal_workflow_rejects_unimplemented_operation_kinds_before_persist(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    _, repository, workflow = _build_workflow(retrieval_session)

    with pytest.raises(ValueError, match="phase_e_operation_not_supported:remove_record"):
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
async def test_proposal_workflow_rolls_back_state_when_receipt_write_fails(retrieval_session, monkeypatch):
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
    assert updated_session.current_state_json["chapter_digest"]["title"] == "Chapter One"
    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].status == "failed"
    assert repository.list_apply_receipts_for_proposal(proposal_records[0].proposal_id) == []


@pytest.mark.asyncio
async def test_longform_regression_routes_authoritative_patch_through_workflow(retrieval_session):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, repository, workflow = _build_workflow(retrieval_session)
    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=object(),
        specialist_service=object(),
        proposal_workflow_service=workflow,
        legacy_state_patch_proposal_builder=LegacyStatePatchProposalBuilder(),
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

    assert updated_session.current_state_json["narrative_progress"]["accepted_segments"] == 1
    proposal_records = repository.list_proposals_for_story("story-1")
    assert len(proposal_records) == 1
    assert proposal_records[0].submit_source == "post_write_regression"
    assert proposal_records[0].status == "applied"
    apply_receipts = repository.list_apply_receipts_for_proposal(proposal_records[0].proposal_id)
    assert len(apply_receipts) == 1
    assert updated_chapter.builder_snapshot_json["foundation_digest"] == ["Found Updated"]
    assert "writer_hints" not in updated_chapter.builder_snapshot_json


@pytest.mark.asyncio
async def test_longform_regression_light_path_deduplicates_newly_accepted_segment(retrieval_session):
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
