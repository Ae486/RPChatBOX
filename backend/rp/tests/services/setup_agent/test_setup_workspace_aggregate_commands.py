"""Behavioral-equivalence tests for SetupWorkspace aggregate write helpers."""

from __future__ import annotations

import pytest

from models.rp_setup_store import SetupPendingUserEditDeltaRecord, SetupWorkspaceRecord
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.services.setup_agent.workspace_service import SetupWorkspaceService


def test_stage_pending_user_edit_delta_stages_row_with_caller_owned_flush_commit(
    retrieval_session,
) -> None:
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(story_id="story-stage-delta", mode=StoryMode.LONGFORM)

    changes = [{"op": "replace", "path": "entries.0.text", "value": "Updated text"}]
    service.stage_pending_user_edit_delta(
        workspace_id=workspace.workspace_id,
        delta_id="delta-1",
        step_id=SetupStepId.FOUNDATION.value,
        target_block="foundation",
        target_ref="entry-1",
        changes=changes,
    )

    retrieval_session.flush()
    retrieval_session.commit()

    record = retrieval_session.get(SetupPendingUserEditDeltaRecord, "delta-1")
    assert record is not None
    assert record.delta_id == "delta-1"
    assert record.workspace_id == workspace.workspace_id
    assert record.step_id == SetupStepId.FOUNDATION.value
    assert record.target_block == "foundation"
    assert record.target_ref == "entry-1"
    assert record.changes_json == changes
    assert record.consumed_at is None
    assert record.created_at is not None


def test_seed_current_step_updates_only_current_step_and_commits(
    retrieval_session,
) -> None:
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(story_id="story-seed-step", mode=StoryMode.LONGFORM)

    record_before = retrieval_session.get(SetupWorkspaceRecord, workspace.workspace_id)
    assert record_before is not None
    current_stage_before = record_before.current_stage

    service.seed_current_step(
        workspace_id=workspace.workspace_id,
        current_step=SetupStepId.STORY_CONFIG.value,
    )
    retrieval_session.rollback()

    record_after = retrieval_session.get(SetupWorkspaceRecord, workspace.workspace_id)
    assert record_after is not None
    assert record_after.current_step == SetupStepId.STORY_CONFIG.value
    assert record_after.current_stage == current_stage_before
    assert record_after.current_stage == SetupStageId.WORLD_BACKGROUND.value


def test_seed_current_step_missing_workspace_raises_exact_error(
    retrieval_session,
) -> None:
    service = SetupWorkspaceService(retrieval_session)

    with pytest.raises(
        ValueError,
        match="^Workspace missing while seeding current_step: missing-workspace$",
    ):
        service.seed_current_step(
            workspace_id="missing-workspace",
            current_step=SetupStepId.STORY_CONFIG.value,
        )


def test_clear_activated_story_session_clears_pointer_and_preserves_state_fields(
    retrieval_session,
) -> None:
    service = SetupWorkspaceService(retrieval_session)
    workspace = service.create_workspace(story_id="story-clear-activation", mode=StoryMode.LONGFORM)
    service.mark_activated_story_session(
        workspace_id=workspace.workspace_id,
        session_id="session-1",
    )

    record_before = retrieval_session.get(SetupWorkspaceRecord, workspace.workspace_id)
    assert record_before is not None
    workspace_state_before = record_before.workspace_state
    activated_at_before = record_before.activated_at
    updated_at_before = record_before.updated_at
    assert activated_at_before is not None

    service.clear_activated_story_session(workspace_id=workspace.workspace_id)
    # Caller owns the commit (the entry only session.add's); commit so the
    # re-read reloads from SQLite consistently with updated_at_before, which
    # SQLite returns tz-naive (it does not persist timezone).
    retrieval_session.commit()

    record_after = retrieval_session.get(SetupWorkspaceRecord, workspace.workspace_id)
    assert record_after is not None
    assert record_after.activated_story_session_id is None
    assert record_after.workspace_state == workspace_state_before
    assert record_after.activated_at == activated_at_before
    assert record_after.updated_at > updated_at_before
