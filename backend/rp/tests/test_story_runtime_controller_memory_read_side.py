"""Controller-level tests for story runtime memory read side."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import LongformChapterPhase
from rp.services.builder_projection_context_service import BuilderProjectionContextService
from rp.services.chapter_workspace_projection_adapter import ChapterWorkspaceProjectionAdapter
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.story_runtime_controller import StoryRuntimeController
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.version_history_read_service import VersionHistoryReadService


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
    return service.get_session(session.session_id), chapter, service


async def _apply_authoritative_patch(retrieval_session):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )
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
                    "field_patch": {"title": "Chapter Two"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="test",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )
    story_session_service.commit()
    return story_session_service, repository, session.session_id


def _build_controller(story_session_service: StorySessionService, repository: ProposalRepository):
    core_state_adapter = StorySessionCoreStateAdapter(story_session_service)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
    )
    version_history_read_service = VersionHistoryReadService(
        adapter=core_state_adapter,
        proposal_repository=repository,
    )
    provenance_read_service = ProvenanceReadService(
        adapter=core_state_adapter,
        proposal_repository=repository,
    )
    memory_inspection_read_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        proposal_repository=repository,
        version_history_read_service=version_history_read_service,
    )
    return StoryRuntimeController(
        story_session_service=story_session_service,
        story_activation_service=SimpleNamespace(),
        version_history_read_service=version_history_read_service,
        provenance_read_service=provenance_read_service,
        memory_inspection_read_service=memory_inspection_read_service,
    )


@pytest.mark.asyncio
async def test_story_runtime_controller_exposes_memory_read_side(retrieval_session):
    story_session_service, repository, session_id = await _apply_authoritative_patch(
        retrieval_session
    )
    controller = _build_controller(story_session_service, repository)

    authoritative_items = controller.list_memory_authoritative(session_id=session_id)
    projection_items = controller.list_memory_projection(session_id=session_id)
    proposal_items = controller.list_memory_proposals(session_id=session_id, status="applied")
    versions = controller.read_memory_versions(
        session_id=session_id,
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )
    provenance = controller.read_memory_provenance(
        session_id=session_id,
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    chapter_item = next(
        item for item in authoritative_items if item["object_ref"]["object_id"] == "chapter.current"
    )
    assert chapter_item["data"]["title"] == "Chapter Two"
    assert any(item["slot_name"] == "current_outline_digest" for item in projection_items)
    assert proposal_items
    assert versions.current_ref == "chapter.current@2"
    assert provenance.proposal_refs


@pytest.mark.asyncio
async def test_story_runtime_controller_memory_reads_stay_session_scoped(retrieval_session):
    story_session_service, repository, session_id = await _apply_authoritative_patch(
        retrieval_session
    )
    story_session_service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-2",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Fresh Session"},
            "narrative_progress": {"current_phase": "outline_drafting", "accepted_segments": 0},
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    story_session_service.commit()
    controller = _build_controller(story_session_service, repository)

    versions = controller.read_memory_versions(
        session_id=session_id,
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    assert versions.current_ref == "chapter.current@2"
