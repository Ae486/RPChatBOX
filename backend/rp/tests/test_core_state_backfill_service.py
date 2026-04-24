"""Tests for Phase G Core State store backfill service."""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_core_state_store import (
    CoreStateAuthoritativeObjectRecord,
    CoreStateAuthoritativeRevisionRecord,
    CoreStateProjectionSlotRecord,
    CoreStateProjectionSlotRevisionRecord,
)
from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import LongformChapterPhase
from rp.services.core_state_backfill_service import CoreStateBackfillService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService


async def _seed_session_with_apply(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-phase-g",
        source_workspace_id="workspace-phase-g",
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
    proposal_receipt = await workflow.submit_and_route(
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
    refreshed_chapter = story_session_service.get_chapter_workspace(chapter.chapter_workspace_id)
    assert refreshed_session is not None
    assert refreshed_chapter is not None
    return refreshed_session, refreshed_chapter, story_session_service, repository, proposal_receipt


@pytest.mark.asyncio
async def test_core_state_backfill_reconstructs_current_rows_revisions_and_links(retrieval_session):
    session, chapter, story_session_service, repository, proposal_receipt = await _seed_session_with_apply(
        retrieval_session
    )
    backfill_service = CoreStateBackfillService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        core_state_store_repository=CoreStateStoreRepository(retrieval_session),
    )

    result = backfill_service.backfill_story_session(session_id=session.session_id)

    assert result == {"authoritative_objects": 6, "projection_slots": 5}

    current_row = retrieval_session.exec(
        select(CoreStateAuthoritativeObjectRecord).where(
            CoreStateAuthoritativeObjectRecord.session_id == session.session_id,
            CoreStateAuthoritativeObjectRecord.object_id == "chapter.current",
        )
    ).one()
    revisions = retrieval_session.exec(
        select(CoreStateAuthoritativeRevisionRecord).where(
            CoreStateAuthoritativeRevisionRecord.session_id == session.session_id,
            CoreStateAuthoritativeRevisionRecord.object_id == "chapter.current",
        ).order_by(CoreStateAuthoritativeRevisionRecord.revision.asc())
    ).all()
    projection_rows = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id == chapter.chapter_workspace_id
        )
    ).all()
    projection_revisions = retrieval_session.exec(
        select(CoreStateProjectionSlotRevisionRecord).where(
            CoreStateProjectionSlotRevisionRecord.chapter_workspace_id == chapter.chapter_workspace_id
        )
    ).all()
    apply_receipt = repository.list_apply_receipts_for_proposal(proposal_receipt.proposal_id)[0]
    apply_links = repository.list_apply_target_links_for_apply(apply_receipt.apply_id)

    assert current_row.current_revision == 2
    assert current_row.latest_apply_id == apply_receipt.apply_id
    assert current_row.data_json["title"] == "Chapter Two"
    assert [item.revision for item in revisions] == [1, 2]
    assert revisions[0].data_json["title"] == "Chapter One"
    assert revisions[1].data_json["title"] == "Chapter Two"
    assert revisions[1].source_apply_id == apply_receipt.apply_id
    assert revisions[1].source_proposal_id == proposal_receipt.proposal_id
    assert len(apply_links) == 1
    assert apply_links[0].authoritative_revision_id == revisions[1].authoritative_revision_id
    assert len(projection_rows) == 5
    assert len(projection_revisions) == 5


@pytest.mark.asyncio
async def test_core_state_backfill_is_idempotent_for_same_session(retrieval_session):
    session, chapter, story_session_service, repository, _ = await _seed_session_with_apply(
        retrieval_session
    )
    backfill_service = CoreStateBackfillService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        core_state_store_repository=CoreStateStoreRepository(retrieval_session),
    )

    backfill_service.backfill_story_session(session_id=session.session_id)
    backfill_service.backfill_story_session(session_id=session.session_id)

    authoritative_rows = retrieval_session.exec(
        select(CoreStateAuthoritativeObjectRecord).where(
            CoreStateAuthoritativeObjectRecord.session_id == session.session_id
        )
    ).all()
    authoritative_revisions = retrieval_session.exec(
        select(CoreStateAuthoritativeRevisionRecord).where(
            CoreStateAuthoritativeRevisionRecord.session_id == session.session_id
        )
    ).all()
    projection_rows = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id == chapter.chapter_workspace_id
        )
    ).all()
    projection_revisions = retrieval_session.exec(
        select(CoreStateProjectionSlotRevisionRecord).where(
            CoreStateProjectionSlotRevisionRecord.chapter_workspace_id == chapter.chapter_workspace_id
        )
    ).all()

    assert len(authoritative_rows) == 6
    assert len(authoritative_revisions) == 7
    assert len(projection_rows) == 5
    assert len(projection_revisions) == 5
