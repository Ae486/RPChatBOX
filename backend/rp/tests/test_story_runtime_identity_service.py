"""Tests for persistent runtime branch and turn identity allocation."""

from __future__ import annotations

import pytest
from sqlmodel import select

from models.rp_story_store import BranchHeadRecord, StoryTurnRecord
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_runtime_identity_service import (
    StoryRuntimeIdentityService,
    StoryRuntimeIdentityServiceError,
)
from rp.services.story_session_service import StorySessionService


def _seed_story_session(retrieval_session, *, story_id: str):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    return StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def test_ensure_default_branch_creates_one_deterministic_row(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-default-branch",
    )
    service = StoryRuntimeIdentityService(retrieval_session)

    first = service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )
    second = service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )
    rows = retrieval_session.exec(
        select(BranchHeadRecord).where(
            BranchHeadRecord.session_id == story_session.session_id
        )
    ).all()

    assert first.branch_head_id == f"branch:{story_session.session_id}:main"
    assert second.branch_head_id == first.branch_head_id
    assert first.branch_name == "main"
    assert len(rows) == 1


def test_resolve_runtime_entry_identity_allocates_turn_and_updates_branch_head(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-turn-allocation",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.identity.active",
    )
    service = StoryRuntimeIdentityService(retrieval_session)

    identity = service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    branch = service.require_branch_head(identity.branch_head_id)
    turn = retrieval_session.get(StoryTurnRecord, identity.turn_id)

    assert identity.story_id == story_session.story_id
    assert identity.session_id == story_session.session_id
    assert identity.runtime_profile_snapshot_id == snapshot.runtime_profile_snapshot_id
    assert branch.head_turn_id == identity.turn_id
    assert turn is not None
    assert turn.branch_head_id == identity.branch_head_id
    assert turn.runtime_profile_snapshot_id == identity.runtime_profile_snapshot_id
    assert turn.status == "started"


def test_create_turn_rejects_non_active_snapshot(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-inactive-snapshot",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    draft_snapshot = snapshot_service.compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.identity.draft",
    )
    identity_service = StoryRuntimeIdentityService(retrieval_session)
    branch = identity_service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        identity_service.create_turn(
            session_id=story_session.session_id,
            story_id=story_session.story_id,
            branch_head_id=branch.branch_head_id,
            runtime_profile_snapshot_id=draft_snapshot.runtime_profile_snapshot_id,
            turn_kind="generation",
            command_kind="continue",
            actor="story_runtime",
        )

    assert exc_info.value.code == "runtime_identity_resolution_failed"
    assert "snapshot_not_active" in str(exc_info.value)


def test_resolve_memory_identity_rejects_turn_snapshot_mismatch(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-mismatch",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    first_snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.identity.first",
    )
    identity_service = StoryRuntimeIdentityService(retrieval_session)
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=first_snapshot.runtime_profile_snapshot_id,
    )
    second_snapshot = snapshot_service.compile_snapshot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        mode=story_session.mode,
        created_from="test.identity.second",
    )
    snapshot_service.publish_snapshot(second_snapshot.runtime_profile_snapshot_id)

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        identity_service.resolve_memory_identity(
            session_id=story_session.session_id,
            story_id=story_session.story_id,
            branch_head_id=identity.branch_head_id,
            turn_id=identity.turn_id,
            runtime_profile_snapshot_id=second_snapshot.runtime_profile_snapshot_id,
        )

    assert exc_info.value.code == "runtime_identity_resolution_failed"
    assert "turn_mismatch" in str(exc_info.value)
