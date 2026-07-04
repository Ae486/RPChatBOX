"""S6-5 named guards for lock v2 / re-open+re-adopt / trigger-time snapshot.

These pin the frozen invariants introduced by S6-5:

- REV-006 rev 2 maintenance mutual-exclusion (a second maintenance run on the same
  branch defers instead of double-running) and the trigger-time accepted-segment
  snapshot (id+revision resolve, never status-filtered).
- REV-025 re-open -> edit -> re-adopt: new revision ACCEPTED + old SUPERSEDED + the
  continuation base moves to the re-edited tail (and a mid-segment re-open keeps the
  chapter tail as the continuation base — A6).
- REV-025 completed-chapter re-open does not re-fire maintenance; single pending slot.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_story_store import RuntimeWorkflowJobRecord
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    StoryArtifactStatus,
)
from rp.tests.services.story.test_story_runtime_product_wiring_writer_constraints import (
    _create_settled_story_segment,
    _resolve_runtime_identity,
    _seed_review_required_proposal,
)
from rp.tests.services.writer.test_longform_chapter_runtime_service import (
    _accept_outline,
    _build_turn_domain_service,
    _seed_story_runtime,
)


def _seed_two_accepted_segments(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    seg1_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s65.seg1",
        actor="s65.seg1",
    )
    seg1 = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=seg1_identity,
        content_text="Beat one original.",
        target_beat_id="beat_001",
    )
    seg2_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s65.seg2",
        actor="s65.seg2",
    )
    seg2 = _create_settled_story_segment(
        story_session_service,
        identity_service,
        session=session,
        chapter=chapter,
        identity=seg2_identity,
        content_text="Beat two original.",
        target_beat_id="beat_002",
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
        accepted_segment_ids=[seg1.artifact_id, seg2.artifact_id],
    )
    retrieval_session.commit()
    return story_session_service, session, chapter, seg1, seg2


def _accepted_ids(turn_domain_service, story_session_service, chapter):
    return [
        artifact.artifact_id
        for artifact in turn_domain_service.accepted_segments(
            story_session_service.get_chapter_workspace(chapter.chapter_workspace_id)
        )
    ]


@pytest.mark.asyncio
async def test_reopen_readopt_moves_continuation_base(retrieval_session):
    story_session_service, session, chapter, seg1, seg2 = _seed_two_accepted_segments(
        retrieval_session
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    assert _accepted_ids(turn_domain_service, story_session_service, chapter) == [
        seg1.artifact_id,
        seg2.artifact_id,
    ]

    # Re-open the TAIL segment -> revision+1 DRAFT into the pending slot.
    await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id,
        artifact_id=seg2.artifact_id,
    )
    reopened_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    draft_id = reopened_chapter.pending_segment_artifact_id
    assert draft_id is not None and draft_id != seg2.artifact_id
    draft = story_session_service.get_artifact(draft_id)
    assert draft.status == StoryArtifactStatus.DRAFT
    assert draft.revision == seg2.revision + 1
    assert reopened_chapter.phase == LongformChapterPhase.SEGMENT_REVIEW

    # Edit the reopened draft on the existing draft-first seam, then re-adopt it.
    story_session_service.update_artifact(
        artifact_id=draft_id,
        content_text="Beat two rewritten.",
    )
    story_session_service.commit()
    await turn_domain_service.re_adopt_pending_segment(
        session_id=session.session_id,
        target_artifact_id=draft_id,
    )

    new_tail = story_session_service.get_artifact(draft_id)
    old_tail = story_session_service.get_artifact(seg2.artifact_id)
    assert new_tail.status == StoryArtifactStatus.ACCEPTED
    assert old_tail.status == StoryArtifactStatus.SUPERSEDED
    # Continuation base moved to the re-edited tail revision (REV-004/005).
    accepted_after = _accepted_ids(turn_domain_service, story_session_service, chapter)
    assert accepted_after == [seg1.artifact_id, draft_id]
    assert accepted_after[-1] == draft_id
    # New adoption receipt is keyed on the re-adopted artifact.
    receipt = turn_domain_service._longform_chapter_runtime_service.get_latest_accepted_segment_adoption_receipt(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id=new_tail.metadata["runtime_branch_head_id"],
        accepted_artifact_id=draft_id,
    )
    assert receipt is not None


@pytest.mark.asyncio
async def test_reopen_midsegment_preserves_tail_continuation_base(retrieval_session):
    # A6 sub-case: re-opening a MID segment keeps its position and leaves the chapter
    # tail as the continuation base — [-1] not moving is the CORRECT behavior.
    story_session_service, session, chapter, seg1, seg2 = _seed_two_accepted_segments(
        retrieval_session
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id,
        artifact_id=seg1.artifact_id,
    )
    draft_id = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    ).pending_segment_artifact_id
    story_session_service.update_artifact(
        artifact_id=draft_id,
        content_text="Beat one rewritten.",
    )
    story_session_service.commit()
    await turn_domain_service.re_adopt_pending_segment(
        session_id=session.session_id,
        target_artifact_id=draft_id,
    )

    assert (
        story_session_service.get_artifact(seg1.artifact_id).status
        == StoryArtifactStatus.SUPERSEDED
    )
    accepted_after = _accepted_ids(turn_domain_service, story_session_service, chapter)
    assert accepted_after == [draft_id, seg2.artifact_id]
    # Tail (continuation base) is unchanged — mid-segment re-open must not move it.
    assert accepted_after[-1] == seg2.artifact_id


@pytest.mark.asyncio
async def test_reopen_rejected_while_pending_exists(retrieval_session):
    story_session_service, session, chapter, seg1, seg2 = _seed_two_accepted_segments(
        retrieval_session
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        pending_segment_artifact_id=seg1.artifact_id,
    )
    story_session_service.commit()
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    with pytest.raises(ValueError, match="segment_reopen_pending_exists"):
        await turn_domain_service.reopen_accepted_segment(
            session_id=session.session_id,
            artifact_id=seg2.artifact_id,
        )


@pytest.mark.asyncio
async def test_completed_chapter_reopen_does_not_refire_maintenance(retrieval_session):
    story_session_service, session, chapter, seg1, seg2 = _seed_two_accepted_segments(
        retrieval_session
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.CHAPTER_COMPLETED,
    )
    story_session_service.commit()
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    jobs_before = len(retrieval_session.exec(select(RuntimeWorkflowJobRecord)).all())

    await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id,
        artifact_id=seg2.artifact_id,
    )

    reopened = story_session_service.get_chapter_workspace(chapter.chapter_workspace_id)
    # Completed chapter keeps CHAPTER_COMPLETED and fires no new maintenance job.
    assert reopened.phase == LongformChapterPhase.CHAPTER_COMPLETED
    assert reopened.pending_segment_artifact_id is not None
    jobs_after = len(retrieval_session.exec(select(RuntimeWorkflowJobRecord)).all())
    assert jobs_after == jobs_before


def test_maintenance_reads_trigger_time_snapshot_not_live_edits(retrieval_session):
    story_session_service, session, chapter, seg1, seg2 = _seed_two_accepted_segments(
        retrieval_session
    )
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )
    live_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    frozen = turn_domain_service._freeze_accepted_segment_snapshot(
        chapter=live_chapter,
        captured_turn_id="turn-freeze-capture",
    )
    assert [ref["artifact_id"] for ref in frozen["refs"]] == [
        seg1.artifact_id,
        seg2.artifact_id,
    ]

    # Simulate a mid-maintenance re-adopt: supersede the tail (drops out of the LIVE
    # accepted read model), leaving the frozen ref pointing at the superseded row.
    story_session_service.update_artifact(
        artifact_id=seg2.artifact_id,
        status=StoryArtifactStatus.SUPERSEDED,
    )
    story_session_service.commit()

    live_ids = [
        artifact.artifact_id
        for artifact in turn_domain_service.accepted_segments(
            story_session_service.get_chapter_workspace(chapter.chapter_workspace_id)
        )
    ]
    assert seg2.artifact_id not in live_ids

    # Frozen resolve returns the row by id+revision WITHOUT a status filter — the
    # snapshot must NOT drop the superseded row (else the maintenance window loses it).
    resolved = turn_domain_service._resolve_accepted_segment_snapshot(snapshot=frozen)
    assert [artifact.artifact_id for artifact in resolved] == [
        seg1.artifact_id,
        seg2.artifact_id,
    ]
    superseded = next(a for a in resolved if a.artifact_id == seg2.artifact_id)
    assert superseded.status == StoryArtifactStatus.SUPERSEDED


def test_maintenance_mutual_exclusion_same_scope(retrieval_session):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    turn_a_identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s65.mutex.turn_a",
        actor="s65.mutex.turn_a",
    )
    _seed_review_required_proposal(retrieval_session, identity=turn_a_identity)
    # Turn A's writer turn must terminalize before turn B's writer intake resolves
    # (S1-core single-active-turn guard); its maintenance proposal stays in flight.
    identity_service.update_turn_status(
        turn_id=turn_a_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        settlement_reason="s65_mutex_turn_a_settled",
    )
    turn_b_identity, _ = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from="s65.mutex.turn_b",
        actor="s65.mutex.turn_b",
    )
    retrieval_session.commit()
    turn_domain_service = _build_turn_domain_service(
        story_session_service,
        retrieval_session,
    )

    # Turn B sees turn A's in-flight maintenance on the same branch -> it would defer.
    assert (
        turn_domain_service._branch_maintenance_active_excluding_turn(
            identity=turn_b_identity
        )
        is True
    )
    # Turn A never defers on its own maintenance obligations (excluded by turn id).
    assert (
        turn_domain_service._branch_maintenance_active_excluding_turn(
            identity=turn_a_identity
        )
        is False
    )
