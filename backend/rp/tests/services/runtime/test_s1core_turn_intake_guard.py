"""Oracle node-5 Tier-A: duplicate-intake rejection (C2).

Single-active-turn invariant [TURN-012 / NUM-016 / W5 §10.4]: while a branch's
current turn is non-terminal (in-flight), a second intake on the same branch MUST
be rejected with the stable error code ``turn_in_flight``.

RED-by-design: ``StoryRuntimeIdentityService.resolve_runtime_entry_identity``
(backend/rp/services/story/runtime_identity_service.py:610) calls ``create_turn``
unconditionally — there is no in-flight guard anywhere (the string
``turn_in_flight`` exists nowhere in production today). So the second intake below
currently SUCCEEDS and creates a second concurrent turn; ``pytest.raises`` then
fails RED, pinning the missing guard. The assertion serves the SoT, not the
current (buggy) behaviour — do not weaken it to green.
"""

from __future__ import annotations

import pytest

from models.rp_story_store import StoryTurnRecord
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.story.runtime import LongformTurnCommandKind
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.runtime_identity_service import (
    StoryRuntimeIdentityService,
    StoryRuntimeIdentityServiceError,
)
from rp.tests.helpers.runtime_seed import seed_story_session


_TERMINAL_TURN_STATUSES = {
    StoryTurnStatus.SETTLED.value,
    StoryTurnStatus.FAILED.value,
}


def test_c2_duplicate_intake_rejected_while_turn_in_flight(retrieval_session) -> None:
    story_session = seed_story_session(
        retrieval_session,
        story_id="intake-guard-c2-turn-in-flight",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.intake_guard.c2",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )

    first = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    first_turn = retrieval_session.get(StoryTurnRecord, first.turn_id)
    assert first_turn is not None
    # The first turn is in-flight (non-terminal); the branch is therefore busy.
    assert first_turn.status not in _TERMINAL_TURN_STATUSES

    # SoT: a second intake on the SAME branch while the prior turn is in-flight
    # must be rejected with `turn_in_flight` (no second concurrent turn).
    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        identity_service.resolve_runtime_entry_identity(
            session_id=story_session.session_id,
            command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
            actor="story_runtime",
            requested_branch_head_id=first.branch_head_id,
            requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        )
    assert exc_info.value.code == "turn_in_flight"
