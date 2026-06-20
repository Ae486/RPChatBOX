"""Oracle node-5 Tier-A: accepted-segment count is branch-scoped (C3).

Branch-fork visibility [TURN-014]: after forking a new branch from an earlier
turn, the accepted-segment count seen on the fork must stay branch-scoped (only
the segments at/under the fork cutoff), NOT the global session count.

``StorySessionService.active_branch_accepted_story_segments``
(backend/rp/services/story/session_service.py:595) resolves the count by walking
the active branch lineage (``_active_branch_visible_turn_records``) with fork
cutoffs, so this is a CHARACTERIZATION test: branch-scoping is already
implemented and this is expected to pass (green-lock), guarding against a
regression to global counting.
"""

from __future__ import annotations

from rp.models.story.runtime import StoryArtifactStatus
from rp.tests.services._helpers.runtime_visible_segment_helpers import (
    seed_runtime_visible_story_segment,
)
from rp.tests.services.projection.test_projection_builder_services import (
    _seed_story_runtime,
)


def test_c3_accepted_segment_count_is_branch_scoped(retrieval_session) -> None:
    session, chapter, service = _seed_story_runtime(retrieval_session)
    base_branch_id = "branch:c3-base"

    seg_one, identity_one, identity_service = seed_runtime_visible_story_segment(
        retrieval_session,
        service,
        session=session,
        chapter=chapter,
        branch_head_id=base_branch_id,
        scene_ref=None,
        content_text="Branch-scoped segment one.",
        status=StoryArtifactStatus.ACCEPTED,
    )
    seg_two, _identity_two, _svc = seed_runtime_visible_story_segment(
        retrieval_session,
        service,
        session=session,
        chapter=chapter,
        branch_head_id=base_branch_id,
        scene_ref=None,
        content_text="Branch-scoped segment two.",
        status=StoryArtifactStatus.ACCEPTED,
    )

    # On the base branch both accepted segments are visible (N == 2).
    base_segments = service.active_branch_accepted_story_segments(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert [artifact.artifact_id for artifact in base_segments] == [
        seg_one.artifact_id,
        seg_two.artifact_id,
    ]

    # Fork a new branch from the FIRST turn; it immediately becomes active.
    identity_service.create_branch_from_turn(
        session_id=session.session_id,
        origin_turn_id=identity_one.turn_id,
        actor="test.c3.fork",
        branch_name="c3-fork",
    )

    # On the fork only segment one is in scope (N == 1) — seg_two is past the
    # fork cutoff and must NOT leak in via global counting.
    forked_segments = service.active_branch_accepted_story_segments(
        session_id=session.session_id,
        chapter_index=chapter.chapter_index,
    )
    assert [artifact.artifact_id for artifact in forked_segments] == [
        seg_one.artifact_id
    ]
    assert seg_two.artifact_id not in {a.artifact_id for a in forked_segments}
