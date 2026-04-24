"""Tests for authoritative version/provenance and inspection read services."""

from __future__ import annotations

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProposalSubmitInput,
)
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import LongformChapterPhase
from rp.services.chapter_workspace_projection_adapter import ChapterWorkspaceProjectionAdapter
from rp.services.projection_state_service import ProjectionStateService
from rp.services.builder_projection_context_service import BuilderProjectionContextService
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.retrieval_broker import RetrievalBroker
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
            "writer_hints": ["Hint A"],
        },
    )
    service.commit()
    return service.get_session(session.session_id), service.get_chapter_by_index(
        session_id=session.session_id,
        chapter_index=1,
    ), service


async def _apply_chapter_patch(retrieval_session):
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
                    "field_patch": {"title": "Chapter Two"},
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
    # RetrievalBroker opens its own Session, so the persisted proposal/apply lineage
    # must be committed here to exercise the durable read side instead of same-session state.
    story_session_service.commit()
    return receipt, story_session_service, repository


@pytest.mark.asyncio
async def test_version_and_provenance_services_use_apply_receipts(retrieval_session):
    receipt, story_session_service, repository = await _apply_chapter_patch(retrieval_session)
    adapter = StorySessionCoreStateAdapter(story_session_service, default_story_id="story-1")
    version_service = VersionHistoryReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    provenance_service = ProvenanceReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    versions = version_service.list_versions(target_ref)
    provenance = provenance_service.read_provenance(target_ref)

    assert versions.current_ref == "chapter.current@2"
    assert versions.versions == ["chapter.current@2", "chapter.current@1"]
    assert provenance.proposal_refs == [f"proposal:{receipt.proposal_id}"]
    assert provenance.source_refs == ["compatibility_mirror:story_session.current_state_json"]


@pytest.mark.asyncio
async def test_retrieval_broker_exposes_authoritative_lineage(retrieval_session):
    receipt, _, _ = await _apply_chapter_patch(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    versions = await broker.list_versions(MemoryListVersionsInput(target_ref=target_ref))
    provenance = await broker.read_provenance(MemoryReadProvenanceInput(target_ref=target_ref))
    state = await broker.get_state(MemoryGetStateInput(refs=[target_ref]))

    assert versions.current_ref == "chapter.current@2"
    assert provenance.proposal_refs == [f"proposal:{receipt.proposal_id}"]
    assert state.items[0].object_ref.revision == 2
    assert state.version_refs == ["chapter.current@2"]


@pytest.mark.asyncio
async def test_memory_inspection_read_service_lists_objects_slots_and_proposals(retrieval_session):
    _, story_session_service, repository = await _apply_chapter_patch(retrieval_session)
    session = story_session_service.get_latest_session_for_story("story-1")
    assert session is not None
    adapter = StorySessionCoreStateAdapter(story_session_service, default_story_id="story-1")
    version_service = VersionHistoryReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(projection_state_service),
        proposal_repository=repository,
        version_history_read_service=version_service,
    )

    authoritative_objects = inspection_service.list_authoritative_objects(session_id=session.session_id)
    projection_slots = inspection_service.list_projection_slots(session_id=session.session_id)
    proposals = inspection_service.list_proposals(story_id="story-1", session_id=session.session_id)

    chapter_entry = next(item for item in authoritative_objects if item["object_ref"]["object_id"] == "chapter.current")
    assert chapter_entry["object_ref"]["revision"] == 2
    assert chapter_entry["data"]["title"] == "Chapter Two"
    assert all(item["slot_name"] != "writer_hints" for item in projection_slots)
    assert proposals[0]["status"] == "applied"


@pytest.mark.asyncio
async def test_session_scoped_lineage_and_inspection_do_not_fall_back_to_story_latest(retrieval_session):
    receipt, story_session_service, repository = await _apply_chapter_patch(retrieval_session)
    original_session = story_session_service.get_latest_session_for_story("story-1")
    assert original_session is not None

    newer_session = story_session_service.create_session(
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
    story_session_service.create_chapter_workspace(
        session_id=newer_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found B"],
            "blueprint_digest": ["Blueprint B"],
            "current_outline_digest": ["Outline B"],
            "recent_segment_digest": ["Segment B"],
            "current_state_digest": ["State B"],
        },
    )
    story_session_service.commit()

    adapter = StorySessionCoreStateAdapter(story_session_service, default_story_id="story-1")
    version_service = VersionHistoryReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    provenance_service = ProvenanceReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(projection_state_service),
        proposal_repository=repository,
        version_history_read_service=version_service,
    )
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    versions = version_service.list_versions(target_ref, session_id=original_session.session_id)
    provenance = provenance_service.read_provenance(target_ref, session_id=original_session.session_id)
    authoritative_objects = inspection_service.list_authoritative_objects(session_id=original_session.session_id)

    assert versions.current_ref == "chapter.current@2"
    assert provenance.proposal_refs == [f"proposal:{receipt.proposal_id}"]
    chapter_entry = next(item for item in authoritative_objects if item["object_ref"]["object_id"] == "chapter.current")
    assert chapter_entry["object_ref"]["revision"] == 2
    assert chapter_entry["data"]["title"] == "Chapter Two"
