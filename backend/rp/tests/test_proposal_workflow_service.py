"""Tests for persisted proposal/apply workflow and regression integration."""

from __future__ import annotations

import pytest

from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import MemorySearchRecallInput, ProposalSubmitInput
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import (
    LongformChapterPhase,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.legacy_state_patch_proposal_builder import (
    LegacyStatePatchProposalBuilder,
)
from rp.services.longform_regression_service import LongformRegressionService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.recall_continuity_note_ingestion_service import (
    RecallContinuityNoteIngestionService,
)
from rp.services.recall_detail_ingestion_service import RecallDetailIngestionService
from rp.services.recall_summary_ingestion_service import RecallSummaryIngestionService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.retrieval_document_service import RetrievalDocumentService
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
        self.accepted_segment_ids = [
            item.artifact_id for item in kwargs["accepted_segments"]
        ]
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=segment_drafting"],
            writer_hints=["Runtime Only Hint"],
            summary_updates=["Light regression continuity note must stay transient."],
        )


class _HeavyRegressionRecallSpecialist:
    async def analyze(self, **kwargs):
        return SpecialistResultBundle(
            foundation_digest=["Found Updated"],
            current_state_digest=["phase=chapter_completed"],
            summary_updates=[
                "The masked envoy now knows the seal phrase.",
                "The masked envoy now knows the seal phrase.",
                "The bell tower debt should stay visible next chapter.",
            ],
            recall_summary_text="Chapter one settled into a tense marketplace truce.",
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
    assert proposal_records[0].status == "applied"
    apply_receipts = repository.list_apply_receipts_for_proposal(
        proposal_records[0].proposal_id
    )
    assert len(apply_receipts) == 1
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


@pytest.mark.asyncio
async def test_longform_regression_heavy_path_ingests_recall_summary_and_detail(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(retrieval_session)
    story_session_service, _, workflow = _build_workflow(retrieval_session)
    accepted_primary = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text=(
            "The silver braid oath was hidden beneath the market stair,"
            " beside a lantern scored with nine tally marks."
        ),
    )
    accepted_secondary = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="A second accepted segment described the watch rotation at dusk.",
    )
    draft_artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Draft prose must not enter settled recall.",
    )
    superseded_artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.SUPERSEDED,
        content_text="Superseded prose must not enter settled recall.",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted outline belongs to a different retention slice.",
    )
    discussion_entry = story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="This is a runtime planning discussion, not settled scene prose.",
        linked_artifact_id=draft_artifact.artifact_id,
    )
    story_session_service.commit()

    specialist_service = _HeavyRegressionRecallSpecialist()
    regression_service = LongformRegressionService(
        story_session_service=story_session_service,
        orchestrator_service=_StaticPlanOrchestrator(),
        specialist_service=specialist_service,
        proposal_workflow_service=workflow,
        legacy_state_patch_proposal_builder=LegacyStatePatchProposalBuilder(),
        recall_summary_ingestion_service=RecallSummaryIngestionService(
            retrieval_session
        ),
        recall_detail_ingestion_service=RecallDetailIngestionService(retrieval_session),
        recall_continuity_note_ingestion_service=(
            RecallContinuityNoteIngestionService(retrieval_session)
        ),
    )

    session = story_session_service.get_session(session.session_id)
    chapter = story_session_service.get_chapter_by_index(
        session_id=accepted_primary.session_id,
        chapter_index=1,
    )
    assert session is not None
    assert chapter is not None

    await regression_service.run_heavy_regression(
        session=session,
        chapter=chapter,
        model_id="model-1",
        provider_id=None,
    )
    retrieval_session.commit()

    assets = RetrievalDocumentService(retrieval_session).list_story_assets(
        session.story_id
    )
    summary_assets = [
        asset for asset in assets if asset.asset_kind == "chapter_summary"
    ]
    detail_assets = [
        asset for asset in assets if asset.asset_kind == "accepted_story_segment"
    ]
    continuity_note_assets = [
        asset for asset in assets if asset.asset_kind == "continuity_note"
    ]

    assert len(summary_assets) == 1
    assert len(detail_assets) == 2
    assert len(continuity_note_assets) == 2
    assert {asset.asset_kind for asset in assets} == {
        "chapter_summary",
        "accepted_story_segment",
        "continuity_note",
    }
    summary_asset = summary_assets[0]
    assert summary_asset.metadata["layer"] == "recall"
    assert summary_asset.metadata["source_family"] == "longform_story_runtime"
    assert summary_asset.metadata["materialization_event"] == (
        "heavy_regression.chapter_close"
    )
    assert summary_asset.metadata["materialization_kind"] == "chapter_summary"
    assert summary_asset.metadata["materialized_to_recall"] is True
    summary_seed = summary_asset.metadata["seed_sections"][0]
    assert summary_seed["metadata"]["materialization_kind"] == "chapter_summary"
    assert summary_seed["metadata"]["materialized_to_recall"] is True
    assert {asset.metadata["artifact_id"] for asset in detail_assets} == {
        accepted_primary.artifact_id,
        accepted_secondary.artifact_id,
    }
    assert all(
        asset.metadata.get("materialization_event") == "heavy_regression.chapter_close"
        for asset in detail_assets
    )
    assert all(
        asset.metadata.get("materialized_to_recall") is True for asset in detail_assets
    )
    assert {
        asset.metadata.get("materialization_kind") for asset in continuity_note_assets
    } == {"continuity_note"}
    assert all(
        asset.metadata.get("source_type") == "continuity_note"
        for asset in continuity_note_assets
    )
    assert all(
        asset.metadata.get("materialization_event") == "heavy_regression.chapter_close"
        for asset in continuity_note_assets
    )
    assert all(
        asset.metadata.get("materialized_to_recall") is True
        for asset in continuity_note_assets
    )
    continuity_text = "\n".join(
        asset.raw_excerpt or "" for asset in continuity_note_assets
    )
    assert "masked envoy now knows the seal phrase" in continuity_text
    assert "bell tower debt" in continuity_text
    assert "Draft prose must not enter settled recall" not in continuity_text
    assert "Superseded prose must not enter settled recall" not in continuity_text
    assert "runtime planning discussion" not in continuity_text
    assert draft_artifact.artifact_id not in {
        asset.metadata.get("artifact_id") for asset in detail_assets
    }
    assert superseded_artifact.artifact_id not in {
        asset.metadata.get("artifact_id") for asset in detail_assets
    }
    assert discussion_entry.entry_id not in {
        asset.metadata.get("discussion_entry_id") for asset in assets
    }

    broker = RetrievalBroker(default_story_id=session.story_id)
    recall_result = await broker.search_recall(
        MemorySearchRecallInput(
            query="silver braid lantern tally marks",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=3,
        )
    )

    returned_asset_ids = {hit.metadata.get("asset_id") for hit in recall_result.hits}
    assert f"recall_detail_{accepted_primary.artifact_id}" in returned_asset_ids
    returned_text = "\n".join(hit.excerpt_text for hit in recall_result.hits)
    assert "Draft prose must not enter settled recall" not in returned_text
    assert "runtime planning discussion" not in returned_text
    assert all(
        hit.metadata.get("discussion_entry_id") != discussion_entry.entry_id
        for hit in recall_result.hits
    )

    continuity_result = await broker.search_recall(
        MemorySearchRecallInput(
            query="masked envoy seal phrase bell tower debt",
            domains=[Domain.CHAPTER],
            scope="story",
            top_k=5,
        )
    )
    continuity_hits = [
        hit
        for hit in continuity_result.hits
        if hit.metadata.get("materialization_kind") == "continuity_note"
    ]
    assert continuity_hits
    assert {hit.metadata.get("asset_kind") for hit in continuity_hits} == {
        "continuity_note"
    }
