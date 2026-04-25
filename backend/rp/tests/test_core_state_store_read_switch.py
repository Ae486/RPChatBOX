"""Tests for Phase G formal store read switch services."""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_core_state_store import CoreStateProjectionSlotRecord
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
)
from rp.services.authoritative_state_view_service import AuthoritativeStateViewService
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.core_state_read_service import CoreStateReadService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.projection_read_service import ProjectionReadService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.version_history_read_service import VersionHistoryReadService
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import LongformChapterPhase


async def _seed_dual_written_runtime(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-g-read",
        source_workspace_id="workspace-g-read",
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
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    dual_write_service = CoreStateDualWriteService(
        repository=CoreStateStoreRepository(retrieval_session)
    )
    dual_write_service.seed_activation_state(session=session, chapter=chapter)

    repository = ProposalRepository(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
            core_state_dual_write_service=dual_write_service,
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id=session.story_id,
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
    refreshed_session = story_session_service.get_session(session.session_id)
    refreshed_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    assert refreshed_session is not None
    assert refreshed_chapter is not None
    return refreshed_session, refreshed_chapter, story_session_service, repository


@pytest.mark.asyncio
async def test_core_state_and_projection_read_services_can_read_formal_store(
    retrieval_session,
):
    session, _, story_session_service, repository = await _seed_dual_written_runtime(
        retrieval_session
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    core_adapter = StorySessionCoreStateAdapter(
        story_session_service,
        default_story_id=session.story_id,
    )
    projection_adapter = ChapterWorkspaceProjectionAdapter(
        story_session_service,
        default_story_id=session.story_id,
    )
    version_service = VersionHistoryReadService(
        adapter=core_adapter,
        proposal_repository=repository,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    provenance_service = ProvenanceReadService(
        adapter=core_adapter,
        proposal_repository=repository,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    core_read_service = CoreStateReadService(
        adapter=core_adapter,
        version_history_read_service=version_service,
        provenance_read_service=provenance_service,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    projection_read_service = ProjectionReadService(
        adapter=projection_adapter,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )

    state = await core_read_service.get_state(
        MemoryGetStateInput(domain=Domain.CHAPTER)
    )
    summary = await projection_read_service.get_summary(
        MemoryGetSummaryInput(summary_ids=["projection.current_outline_digest"])
    )
    versions = await core_read_service.list_versions(
        MemoryListVersionsInput(
            target_ref=ObjectRef(
                object_id="chapter.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
            )
        )
    )
    provenance = await core_read_service.read_provenance(
        MemoryReadProvenanceInput(
            target_ref=ObjectRef(
                object_id="chapter.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
            )
        )
    )

    assert state.items[0].data["title"] == "Chapter Two"
    assert state.items[0].object_ref.revision == 2
    assert summary.items[0].summary_text == "Outline A"
    assert versions.current_ref == "chapter.current@2"
    assert provenance.target_ref.revision == 2
    assert provenance.proposal_refs
    assert provenance.source_refs[0] == "core_state_store:authoritative_revision"


@pytest.mark.asyncio
async def test_store_backed_view_and_inspection_services_read_formal_store(
    retrieval_session,
):
    session, _, story_session_service, repository = await _seed_dual_written_runtime(
        retrieval_session
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    core_adapter = StorySessionCoreStateAdapter(story_session_service)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    authoritative_state_view_service = AuthoritativeStateViewService(
        adapter=core_adapter,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    version_history_read_service = VersionHistoryReadService(
        adapter=core_adapter,
        proposal_repository=repository,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        proposal_repository=repository,
        version_history_read_service=version_history_read_service,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )

    chapter_digest = authoritative_state_view_service.get_chapter_digest(
        session_id=session.session_id
    )
    projection_map = projection_state_service.get_slot_map(
        session_id=session.session_id
    )
    authoritative_items = inspection_service.list_authoritative_objects(
        session_id=session.session_id
    )
    projection_items = inspection_service.list_projection_slots(
        session_id=session.session_id
    )

    assert chapter_digest["title"] == "Chapter Two"
    assert projection_map["current_outline_digest"] == ["Outline A"]
    chapter_item = next(
        item
        for item in authoritative_items
        if item["object_ref"]["object_id"] == "chapter.current"
    )
    assert chapter_item["data"]["title"] == "Chapter Two"
    assert any(
        item["summary_id"] == "projection.current_outline_digest"
        for item in projection_items
    )


@pytest.mark.asyncio
async def test_inspection_projection_includes_mirror_only_slots_during_partial_store_cutover(
    retrieval_session,
):
    (
        session,
        chapter,
        story_session_service,
        repository,
    ) = await _seed_dual_written_runtime(retrieval_session)
    core_repo = CoreStateStoreRepository(retrieval_session)
    outline_row = core_repo.get_projection_slot(
        chapter_workspace_id=chapter.chapter_workspace_id,
        summary_id="projection.current_outline_digest",
    )
    assert outline_row is not None
    for revision_row in core_repo.list_projection_slot_revisions(
        chapter_workspace_id=chapter.chapter_workspace_id,
        summary_id="projection.current_outline_digest",
    ):
        retrieval_session.delete(revision_row)
    retrieval_session.delete(outline_row)
    retrieval_session.flush()
    assert not retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id
            == chapter.chapter_workspace_id,
            CoreStateProjectionSlotRecord.summary_id
            == "projection.current_outline_digest",
        )
    ).first()

    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        proposal_repository=repository,
        version_history_read_service=VersionHistoryReadService(
            adapter=StorySessionCoreStateAdapter(story_session_service),
            proposal_repository=repository,
            core_state_store_repository=core_repo,
            store_read_enabled=True,
        ),
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )

    projection_items = inspection_service.list_projection_slots(
        session_id=session.session_id
    )
    outline_item = next(
        item
        for item in projection_items
        if item["summary_id"] == "projection.current_outline_digest"
    )

    assert outline_item["slot_name"] == "current_outline_digest"
    assert outline_item["items"] == ["Outline A"]
    assert outline_item["backend"] == "compatibility_mirror"
