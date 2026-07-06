"""S6-7 O-6 oracle: comments-as-memo (follow/stale) + rewrite decoupling.

Named guard for O-6 (``02-slice-plan.md:53``) + REV-007改 (``invariants-list.md:186``
— a batch comment stays active after a rewrite and downgrades into a passive
"memo": it survives a segment reopen and resolves ``follow_state`` best-effort by
excerpt substring search, marking ``stale`` when it can no longer follow) +
REV-022改 (the live rewrite package never carries memo/comment payload). Five
fake-role offline cases, no network / no key:

  (a) REV-007改 no-touch: a live selection-rewrite neither reads nor mutates an
      active memo — ``touched_comment_ids`` stays empty and ``follow_state`` is
      untouched.
  (b) follow/stale + F2, at two levels: the carry+follow logic is tested at the
      SERVICE seam — carry_comments_to_revision with excerpt-present vs
      excerpt-absent content resolves following vs stale, mints a fresh
      ``comment_id`` + records ``carried_from_comment_id``, and never re-points the
      old row (F2) — AND end to end via the faithful F1 two-cycle
      reopen->edit->readopt->reopen turn flow (following on cycle 1, stale on
      cycle 2).
  (c) REV-022改 decoupling: the live-shaped rewrite request carries no
      memo/comment payload, so a deleted memo trivially cannot enter it.
  (d) never-block: a pending draft loaded with active + stale memos still
      re-adopts cleanly.
  (F3) legacy artifact reopen: an accepted segment without runtime_* metadata
       reopens without raising — the memo carry is a no-op skip (try-derive).
"""

from __future__ import annotations

import pytest

from rp.models.runtime.identity import StoryTurnStatus
from rp.models.story.runtime import (
    LongformTurnCommandKind,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.core_state.revision_overlay_service import RevisionOverlayService
from rp.services.writer.rewrite_candidate_service import RewriteCandidateService
from rp.tests.services.writer.test_longform_chapter_runtime_service import (
    _artifact_runtime_metadata,
    _build_turn_domain_service,
    _resolve_runtime_identity,
    _seed_story_runtime,
)
from rp.tests.services.writer.test_rewrite_candidate_service import (
    _identity,
    _rewrite_request,
    _writer_result,
)


def _seed_accepted_segment_with_memo(
    retrieval_session,
    *,
    content_text: str,
    excerpt: str,
    instruction: str,
    turn_actor: str,
):
    """A-c seed chain: mint DRAFT -> add_comment -> accept -> (caller reopens).

    The comment is authored while the artifact is a DRAFT (comments require a
    DRAFT overlay); the segment is then promoted to ACCEPTED with its origin turn
    settled, mirroring ``_create_settled_story_segment``. The runtime_* metadata
    matches the resolved identity so the reopen hook can try-derive it. Returns
    ``(service, session, chapter, identity, segment, memo, overlay_service)``.
    """
    service, session, chapter = _seed_story_runtime(retrieval_session)
    identity, identity_service = _resolve_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        created_from=turn_actor,
        actor=turn_actor,
    )
    segment = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text=content_text,
        metadata=_artifact_runtime_metadata(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            turn_id=identity.turn_id,
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
        ),
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    overlay = overlay_service.create_or_update_overlay(
        identity=identity,
        draft_ref=f"artifact:{segment.artifact_id}",
        mode="viewing",
    )
    memo = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text=instruction,
        selected_excerpt=excerpt,
    )
    service.update_artifact(
        artifact_id=segment.artifact_id,
        status=StoryArtifactStatus.ACCEPTED,
    )
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=segment.artifact_id,
        selected_output_ref=segment.artifact_id,
        settlement_reason="o6_seed_accepted_segment",
    )
    service.commit()
    return service, session, chapter, identity, segment, memo, overlay_service


def _find_comment(overlay_service, *, identity, overlay_id, comment_id):
    inspection = overlay_service.inspect_overlay(identity=identity, overlay_id=overlay_id)
    for comment in inspection.comments:
        if comment.comment_id == comment_id:
            return comment
    return None


def _overlay_comments(overlay_service, *, identity, draft_ref):
    overlay = overlay_service.find_overlay_for_draft_ref(
        identity=identity, draft_ref=draft_ref
    )
    assert overlay is not None
    return overlay_service.inspect_overlay(
        identity=identity, overlay_id=overlay.overlay_id
    ).comments


def _carried_memos(overlay_service, *, identity, draft_ref):
    return [
        comment
        for comment in _overlay_comments(
            overlay_service, identity=identity, draft_ref=draft_ref
        )
        if comment.metadata_json.get("carried_from_comment_id")
    ]


def test_o6a_live_rewrite_never_reads_or_touches_memo(retrieval_session):
    identity = _identity(turn_id="turn-o6a")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    overlay = overlay_service.create_or_update_overlay(
        identity=identity, draft_ref="artifact:o6a", mode="viewing"
    )
    memo = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Keep the bell motif.",
        selected_excerpt="the bell motif",
    )
    assert memo.status == "active"
    assert memo.follow_state == "following"

    candidate = RewriteCandidateService(
        session=retrieval_session
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=_rewrite_request(
            identity,
            draft_ref="artifact:o6a",
            global_instruction="Rewrite with quieter tension.",
        ),
        writer_result=_writer_result(
            identity=identity,
            output_text="A quieter version of the scene.",
        ),
    )

    # REV-007改: the live rewrite path never reads comments, so it neither
    # auto-resolves/deletes the memo nor touches its follow_state.
    assert candidate.touched_comment_ids == []
    after = _find_comment(
        overlay_service,
        identity=identity,
        overlay_id=overlay.overlay_id,
        comment_id=memo.comment_id,
    )
    assert after is not None
    assert after.status == "active"
    assert after.follow_state == "following"


def test_o6b_service_seam_carry_resolves_following_then_stale(retrieval_session):
    # SERVICE SEAM (per leader unblock): exercises carry_comments_to_revision +
    # follow-resolve directly — the exact logic S6-7 adds — with no reopen/readopt
    # turn machinery. The follow (excerpt present) and stale (excerpt absent)
    # branches are both driven by the content passed to carry; F1's full
    # reopen->edit->readopt->reopen two-cycle turn flow is intentionally not driven
    # (fragile) — the hook wiring is covered thinly by the turn-level test below.
    identity = _identity(turn_id="turn-o6b-seam")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    old_overlay = overlay_service.create_or_update_overlay(
        identity=identity, draft_ref="artifact:o6b:old", mode="viewing"
    )
    memo = overlay_service.add_comment(
        identity=identity,
        overlay_id=old_overlay.overlay_id,
        instruction_text="Keep the ZEBRAX chime.",
        selected_excerpt="ZEBRAX chimed",
    )
    assert memo.follow_state == "following"

    # New content still holds the excerpt -> following.
    carried_following = overlay_service.carry_comments_to_revision(
        identity=identity,
        old_draft_ref="artifact:o6b:old",
        new_draft_ref="artifact:o6b:new1",
        new_content_text="The clocktower ZEBRAX chimed twice at dawn.",
    )
    assert len(carried_following) == 1
    following = carried_following[0]
    assert following.follow_state == "following"
    assert following.status == "active"
    assert following.selected_excerpt == memo.selected_excerpt
    assert following.instruction_text == memo.instruction_text
    # F2: fresh comment_id, provenance recorded, created_by preserved.
    assert following.comment_id != memo.comment_id
    assert following.metadata_json["carried_from_comment_id"] == memo.comment_id
    assert following.metadata_json["carried_from_draft_ref"] == "artifact:o6b:old"
    assert following.created_by == memo.created_by
    # F2: the OLD row on the source overlay is untouched (never re-pointed).
    seed_after = _find_comment(
        overlay_service,
        identity=identity,
        overlay_id=old_overlay.overlay_id,
        comment_id=memo.comment_id,
    )
    assert seed_after is not None
    assert seed_after.comment_id == memo.comment_id
    assert seed_after.draft_ref == old_overlay.draft_ref
    assert seed_after.follow_state == "following"

    # New content OMITS the excerpt -> stale (the memo persists, still active).
    carried_stale = overlay_service.carry_comments_to_revision(
        identity=identity,
        old_draft_ref="artifact:o6b:old",
        new_draft_ref="artifact:o6b:new2",
        new_content_text="The clocktower stayed silent at dawn.",
    )
    assert len(carried_stale) == 1
    stale = carried_stale[0]
    assert stale.follow_state == "stale"
    assert stale.status == "active"
    assert stale.comment_id not in (memo.comment_id, following.comment_id)
    assert stale.metadata_json["carried_from_comment_id"] == memo.comment_id


@pytest.mark.asyncio
async def test_o6b_reopen_carries_memo_following_then_stale_across_two_cycles(
    retrieval_session,
):
    # TURN LEVEL (full E2E): the faithful F1 two-cycle — reopen#1 copies the full
    # source content so the excerpt is present (following); the excerpt is edited
    # out and re-adopted; reopen#2 then carries onto content that no longer holds
    # it (stale). Complements the service-seam test above with real reopen/readopt
    # machinery. F2 is pinned on both the carried row and the untouched old row.
    (
        service,
        session,
        chapter,
        identity,
        segment,
        memo,
        overlay_service,
    ) = _seed_accepted_segment_with_memo(
        retrieval_session,
        content_text="The clocktower ZEBRAX chimed twice at dawn.",
        excerpt="ZEBRAX chimed",
        instruction="Confirm the chime count stays two.",
        turn_actor="o6b.seed",
    )
    turn_domain_service = _build_turn_domain_service(service, retrieval_session)

    # Cycle 1: reopen copies the full source content, so the excerpt is present
    # and the carried memo follows.
    await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id, artifact_id=segment.artifact_id
    )
    draft1_id = service.get_chapter_workspace(
        chapter.chapter_workspace_id
    ).pending_segment_artifact_id
    assert draft1_id is not None and draft1_id != segment.artifact_id

    carried1 = _carried_memos(
        overlay_service, identity=identity, draft_ref=f"artifact:{draft1_id}"
    )
    assert len(carried1) == 1
    following = carried1[0]
    assert following.follow_state == "following"
    assert following.status == "active"
    assert following.selected_excerpt == memo.selected_excerpt
    assert following.instruction_text == memo.instruction_text
    # F2: carry mints a fresh comment_id, records provenance, preserves created_by.
    assert following.comment_id != memo.comment_id
    assert following.metadata_json["carried_from_comment_id"] == memo.comment_id
    assert (
        following.metadata_json["carried_from_draft_ref"]
        == f"artifact:{segment.artifact_id}"
    )
    assert following.created_by == memo.created_by
    # F2: the old row on the superseded segment's overlay is never re-pointed.
    seg_overlay = overlay_service.find_overlay_for_draft_ref(
        identity=identity, draft_ref=f"artifact:{segment.artifact_id}"
    )
    seed_after = _find_comment(
        overlay_service,
        identity=identity,
        overlay_id=seg_overlay.overlay_id,
        comment_id=memo.comment_id,
    )
    assert seed_after is not None
    assert seed_after.comment_id == memo.comment_id
    assert seed_after.follow_state == "following"

    # Edit the excerpt out of the reopened draft, then re-adopt it as the new tail.
    service.update_artifact(
        artifact_id=draft1_id,
        content_text="The clocktower stayed silent at dawn.",
    )
    service.commit()
    await turn_domain_service.re_adopt_pending_segment(
        session_id=session.session_id, target_artifact_id=draft1_id
    )
    assert service.get_artifact(draft1_id).status == StoryArtifactStatus.ACCEPTED
    assert (
        service.get_artifact(segment.artifact_id).status
        == StoryArtifactStatus.SUPERSEDED
    )

    # Cycle 2: reopen the re-edited tail; its content no longer holds the excerpt,
    # so the carried memo follows nothing and is marked stale (still a live memo).
    await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id, artifact_id=draft1_id
    )
    draft2_id = service.get_chapter_workspace(
        chapter.chapter_workspace_id
    ).pending_segment_artifact_id
    assert draft2_id is not None and draft2_id not in (segment.artifact_id, draft1_id)

    carried2 = _carried_memos(
        overlay_service, identity=identity, draft_ref=f"artifact:{draft2_id}"
    )
    assert len(carried2) == 1
    stale = carried2[0]
    assert stale.follow_state == "stale"
    assert stale.status == "active"
    assert stale.comment_id != following.comment_id
    assert stale.metadata_json["carried_from_comment_id"] == following.comment_id


def test_o6c_deleted_memo_never_enters_rewrite_package(retrieval_session):
    identity = _identity(turn_id="turn-o6c")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    overlay = overlay_service.create_or_update_overlay(
        identity=identity, draft_ref="artifact:o6c", mode="viewing"
    )
    memo = overlay_service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Drop this aside.",
        selected_excerpt="this aside",
    )
    overlay_service.delete_comment(identity=identity, comment_id=memo.comment_id)

    # REV-022改 / O-6(c): the live assistant rewrite request never carries
    # memo/comment payload, so a deleted memo trivially cannot enter the package.
    request = _rewrite_request(
        identity, draft_ref="artifact:o6c", global_instruction="Rewrite quietly."
    )
    assert request.comment_refs == []
    assert request.comments == []
    assert request.tracked_changes == []
    assert request.tracked_change_refs == []
    assert memo.comment_id not in request.comment_refs


@pytest.mark.asyncio
async def test_o6d_active_and_stale_memos_never_block_readopt(retrieval_session):
    (
        service,
        session,
        chapter,
        identity,
        segment,
        _memo,
        overlay_service,
    ) = _seed_accepted_segment_with_memo(
        retrieval_session,
        content_text="The lighthouse QUARTZ beam swept the fog.",
        excerpt="QUARTZ beam",
        instruction="Verify the beam timing.",
        turn_actor="o6d.seed",
    )
    turn_domain_service = _build_turn_domain_service(service, retrieval_session)
    await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id, artifact_id=segment.artifact_id
    )
    draft_id = service.get_chapter_workspace(
        chapter.chapter_workspace_id
    ).pending_segment_artifact_id
    draft_ref = f"artifact:{draft_id}"

    # Pile the pending draft with extra active memos (reopen already carried one
    # following memo) ...
    draft_overlay = overlay_service.find_overlay_for_draft_ref(
        identity=identity, draft_ref=draft_ref
    )
    for index in range(3):
        overlay_service.add_comment(
            identity=identity,
            overlay_id=draft_overlay.overlay_id,
            instruction_text=f"Active memo {index}.",
            selected_excerpt=f"beam detail {index}",
        )
    # ... and one stale memo (carry the seed memo over content lacking its excerpt).
    overlay_service.carry_comments_to_revision(
        identity=identity,
        old_draft_ref=f"artifact:{segment.artifact_id}",
        new_draft_ref=draft_ref,
        new_content_text="No beam remained after the storm.",
    )
    service.commit()

    comments = _overlay_comments(
        overlay_service, identity=identity, draft_ref=draft_ref
    )
    assert len(comments) >= 5
    assert {comment.follow_state for comment in comments} == {"following", "stale"}
    assert any(comment.follow_state == "stale" for comment in comments)
    assert all(comment.status == "active" for comment in comments)

    # Accept proceeds regardless of memo count / follow_state (never-block).
    await turn_domain_service.re_adopt_pending_segment(
        session_id=session.session_id, target_artifact_id=draft_id
    )
    assert service.get_artifact(draft_id).status == StoryArtifactStatus.ACCEPTED
    assert (
        service.get_artifact(segment.artifact_id).status
        == StoryArtifactStatus.SUPERSEDED
    )


@pytest.mark.asyncio
async def test_o6_f3_legacy_artifact_without_runtime_metadata_reopens_without_raise(
    retrieval_session,
):
    service, session, chapter = _seed_story_runtime(retrieval_session)
    # A legacy / hand-planted accepted segment with NO runtime_* metadata: the
    # reopen hook cannot try-derive an identity, so the carry must skip (no-op)
    # rather than raise (F3).
    legacy = service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="A legacy segment predating runtime identity metadata.",
        metadata={"note": "no runtime_* keys"},
    )
    service.commit()
    turn_domain_service = _build_turn_domain_service(service, retrieval_session)

    snapshot = await turn_domain_service.reopen_accepted_segment(
        session_id=session.session_id, artifact_id=legacy.artifact_id
    )

    assert snapshot is not None
    draft_id = service.get_chapter_workspace(
        chapter.chapter_workspace_id
    ).pending_segment_artifact_id
    assert draft_id is not None and draft_id != legacy.artifact_id
    assert service.get_artifact(draft_id).status == StoryArtifactStatus.DRAFT
