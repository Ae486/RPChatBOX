"""Setup-free runtime identity seed helpers for RP runtime tests."""

from __future__ import annotations

from rp.models.story.runtime import LongformChapterPhase
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService


def seed_story_session(session, *, story_id: str, mode: str = "longform"):
    return StorySessionService(session).create_session(
        story_id=story_id,
        source_workspace_id=f"synthetic-ws:{story_id}",
        mode=mode,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def seed_runtime_identity(session, *, story_id: str, mode: str = "longform"):
    story_session = seed_story_session(session, story_id=story_id, mode=mode)
    snapshots = RuntimeProfileSnapshotService(session)
    snapshot = snapshots.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from=f"test.{story_id}.snapshot",
    )
    return StoryRuntimeIdentityService(
        session,
        runtime_profile_snapshot_service=snapshots,
    ).resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
