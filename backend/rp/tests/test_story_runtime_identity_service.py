"""Tests for persistent runtime branch and turn identity allocation."""

from __future__ import annotations

import pytest
from sqlalchemy import asc
from sqlmodel import select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from models.rp_story_store import (
    BranchControlReceiptRecord,
    BranchHeadRecord,
    StorySessionRecord,
    StoryTurnRecord,
)
from rp.models.runtime_identity import (
    BranchControlKind,
    BranchHeadStatus,
    BranchVisibilityState,
    StoryTurnStatus,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    LongformChapterPhase,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
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


def _seed_settled_main_turns(
    retrieval_session,
    *,
    story_id: str,
    count: int = 2,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id=story_id,
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from=f"test.{story_id}.snapshot",
    )
    service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identities = []
    for index in range(count):
        identity = service.resolve_runtime_entry_identity(
            session_id=story_session.session_id,
            command_kind=f"continue-{index}",
            actor="story_runtime",
            requested_runtime_profile_snapshot_id=(
                snapshot.runtime_profile_snapshot_id
            ),
        )
        service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.SETTLED,
            visible_output_ref=f"artifact:{index}",
            selected_output_ref=f"artifact:{index}",
            settlement_reason="test_settled",
        )
        identities.append(identity)
    return story_session, snapshot, service, identities


def _turn_count(retrieval_session, *, session_id: str) -> int:
    return len(
        retrieval_session.exec(
            select(StoryTurnRecord).where(StoryTurnRecord.session_id == session_id)
        ).all()
    )


def _branch_receipts(
    retrieval_session,
    *,
    session_id: str,
) -> list[BranchControlReceiptRecord]:
    return list(
        retrieval_session.exec(
            select(BranchControlReceiptRecord)
            .where(BranchControlReceiptRecord.session_id == session_id)
            .order_by(asc(BranchControlReceiptRecord.created_at))
        ).all()
    )


def test_ensure_default_branch_creates_one_deterministic_row(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-default-branch",
    )
    service = StoryRuntimeIdentityService(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)

    assert story_session.active_branch_head_id == f"branch:{story_session.session_id}:main"
    assert story_session.active_runtime_profile_snapshot_id is None

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
    refreshed_session = story_session_service.get_session(story_session.session_id)
    assert refreshed_session is not None
    assert refreshed_session.active_branch_head_id == first.branch_head_id


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
    story_session_service = StorySessionService(retrieval_session)

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
    refreshed_session = story_session_service.get_session(story_session.session_id)
    assert refreshed_session is not None
    assert refreshed_session.active_branch_head_id == identity.branch_head_id
    assert refreshed_session.active_runtime_profile_snapshot_id == (
        snapshot.runtime_profile_snapshot_id
    )


def test_resolve_runtime_entry_identity_defaults_to_session_active_anchors(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-session-active-defaults",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    active_snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.identity.session_active",
    )
    service = StoryRuntimeIdentityService(retrieval_session)
    branch = service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )

    identity = service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
    )

    assert identity.branch_head_id == branch.branch_head_id
    assert identity.runtime_profile_snapshot_id == (
        active_snapshot.runtime_profile_snapshot_id
    )


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


def test_create_branch_from_settled_turn_writes_receipt_and_switches_active_branch(
    retrieval_session,
):
    story_session, _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-branch-create",
    )
    base_identity, origin_identity = identities
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=origin_identity.turn_id,
        actor="user",
        branch_name="alternate-future",
        metadata={"ui_action": "from_turn_menu"},
    )

    created_branch = retrieval_session.get(BranchHeadRecord, receipt.to_branch_head_id)
    refreshed_session = retrieval_session.get(
        StorySessionRecord,
        story_session.session_id,
    )
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )

    assert receipt.control_kind == BranchControlKind.BRANCH_CREATED
    assert receipt.branch_head_id == receipt.to_branch_head_id
    assert receipt.from_branch_head_id == base_identity.branch_head_id
    assert receipt.fork_origin_turn_id == origin_identity.turn_id
    assert receipt.fork_base_turn_id == base_identity.turn_id
    assert receipt.source_ref_ids == [f"turn:{origin_identity.turn_id}"]
    assert len(receipt_records) == 1
    assert receipt_records[0].receipt_id == receipt.receipt_id
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    assert created_branch is not None
    assert created_branch.branch_name == "alternate-future"
    assert created_branch.parent_branch_head_id == base_identity.branch_head_id
    assert created_branch.fork_origin_turn_id == origin_identity.turn_id
    assert created_branch.fork_base_turn_id == base_identity.turn_id
    assert created_branch.forked_from_turn_id == base_identity.turn_id
    assert created_branch.head_turn_id == base_identity.turn_id
    assert created_branch.last_settled_turn_id == base_identity.turn_id
    assert created_branch.status == BranchHeadStatus.ACTIVE.value
    assert created_branch.visibility_state == BranchVisibilityState.VISIBLE.value
    assert created_branch.created_by_control_receipt_id == receipt.receipt_id
    assert refreshed_session is not None
    assert refreshed_session.active_branch_head_id == created_branch.branch_head_id

    next_identity = service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue-after-branch-create",
        actor="story_runtime",
    )
    assert next_identity.branch_head_id == created_branch.branch_head_id
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before + 1
    )


def test_switch_branch_writes_receipt_without_creating_turn(retrieval_session):
    story_session, _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-branch-switch",
    )
    origin_identity = identities[-1]
    create_receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=origin_identity.turn_id,
        actor="user",
    )
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    switch_receipt = service.switch_branch(
        session_id=story_session.session_id,
        target_branch_head_id=origin_identity.branch_head_id,
        actor="user",
        metadata={"source": "branch_panel"},
    )

    refreshed_session = retrieval_session.get(
        StorySessionRecord,
        story_session.session_id,
    )
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )

    assert switch_receipt.control_kind == BranchControlKind.BRANCH_SWITCHED
    assert switch_receipt.from_branch_head_id == create_receipt.to_branch_head_id
    assert switch_receipt.to_branch_head_id == origin_identity.branch_head_id
    assert switch_receipt.metadata == {"source": "branch_panel"}
    assert [record.control_kind for record in receipt_records] == [
        BranchControlKind.BRANCH_CREATED.value,
        BranchControlKind.BRANCH_SWITCHED.value,
    ]
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    assert refreshed_session is not None
    assert refreshed_session.active_branch_head_id == origin_identity.branch_head_id

    next_identity = service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue-after-switch",
        actor="story_runtime",
    )
    assert next_identity.branch_head_id == origin_identity.branch_head_id


def test_delete_active_branch_marks_deleted_and_falls_back_without_creating_turn(
    retrieval_session,
):
    story_session, _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-branch-delete",
    )
    origin_identity = identities[-1]
    create_receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=origin_identity.turn_id,
        actor="user",
    )
    created_branch_id = create_receipt.to_branch_head_id
    assert created_branch_id is not None
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    delete_receipt = service.delete_branch(
        session_id=story_session.session_id,
        branch_head_id=created_branch_id,
        actor="user",
    )

    deleted_branch = retrieval_session.get(BranchHeadRecord, created_branch_id)
    refreshed_session = retrieval_session.get(
        StorySessionRecord,
        story_session.session_id,
    )
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )

    assert delete_receipt.control_kind == BranchControlKind.BRANCH_DELETED
    assert delete_receipt.from_branch_head_id == created_branch_id
    assert delete_receipt.to_branch_head_id == origin_identity.branch_head_id
    assert [record.control_kind for record in receipt_records] == [
        BranchControlKind.BRANCH_CREATED.value,
        BranchControlKind.BRANCH_DELETED.value,
    ]
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    assert deleted_branch is not None
    assert deleted_branch.status == BranchHeadStatus.SUPERSEDED.value
    assert deleted_branch.visibility_state == BranchVisibilityState.DELETED.value
    assert refreshed_session is not None
    assert refreshed_session.active_branch_head_id == origin_identity.branch_head_id

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        service.switch_branch(
            session_id=story_session.session_id,
            target_branch_head_id=created_branch_id,
            actor="user",
        )
    assert exc_info.value.code == "runtime_branch_head_not_active"


def test_create_branch_rejects_non_settled_turn_without_receipt(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-branch-non-settled",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.identity.branch_non_settled",
    )
    service = StoryRuntimeIdentityService(retrieval_session)
    identity = service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        service.create_branch_from_turn(
            session_id=story_session.session_id,
            origin_turn_id=identity.turn_id,
            actor="user",
        )

    assert exc_info.value.code == "runtime_branch_control_invalid_turn"
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    assert _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    ) == []


def test_rollback_to_settled_turn_writes_receipt_and_hides_later_turns(
    retrieval_session,
):
    story_session, snapshot, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-rollback-settled",
        count=3,
    )
    target_identity = identities[1]
    hidden_identity = identities[2]
    workspace_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    workspace_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="rollback-worker-candidate",
            material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
            identity=hidden_identity,
            domain="chapter",
            domain_path="chapter.runtime.worker_candidate",
            payload={"candidate": "future state to hide"},
            visibility="worker_visible",
            created_by="test.rollback",
        )
    )
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    receipt = service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
        metadata={"target_checkpoint_id": "checkpoint:target-turn"},
    )

    branch = retrieval_session.get(BranchHeadRecord, target_identity.branch_head_id)
    target_turn = retrieval_session.get(StoryTurnRecord, target_identity.turn_id)
    hidden_turn = retrieval_session.get(StoryTurnRecord, hidden_identity.turn_id)
    material = retrieval_session.get(
        RuntimeWorkspaceMaterialRecord,
        "rollback-worker-candidate",
    )
    refreshed_session = retrieval_session.get(
        StorySessionRecord,
        story_session.session_id,
    )
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )

    assert receipt.control_kind == BranchControlKind.ROLLBACK_APPLIED
    assert receipt.target_turn_id == target_identity.turn_id
    assert receipt.source_ref_ids == [f"turn:{target_identity.turn_id}"]
    assert receipt.trace_refs == [f"turn:{hidden_identity.turn_id}"]
    assert receipt.metadata["previous_head_turn_id"] == hidden_identity.turn_id
    assert receipt.metadata["previous_last_settled_turn_id"] == hidden_identity.turn_id
    assert receipt.metadata["visibility_transition"]["hidden_after_turn_id"] == (
        target_identity.turn_id
    )
    assert receipt.metadata["visibility_transition"]["hidden_turn_ids"] == [
        hidden_identity.turn_id
    ]
    assert receipt.metadata["visibility_transition"][
        "invalidated_workspace_material_ids"
    ] == ["rollback-worker-candidate"]
    assert receipt.metadata["checkpoint_binding"] == {
        "binding_kind": "branch_scoped_thread",
        "graph_thread_id": (
            "story_session:"
            f"{story_session.session_id}:branch_head:{target_identity.branch_head_id}"
        ),
        "branch_head_id": target_identity.branch_head_id,
        "target_turn_id": target_identity.turn_id,
        "target_checkpoint_id": "checkpoint:target-turn",
        "source": "application_visibility_contract",
    }
    assert len(receipt_records) == 1
    assert receipt_records[0].receipt_id == receipt.receipt_id
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    assert branch is not None
    assert branch.head_turn_id == target_identity.turn_id
    assert branch.last_settled_turn_id == target_identity.turn_id
    assert branch.metadata_json["rollback_cutoff_turn_id"] == target_identity.turn_id
    assert branch.metadata_json["rollback_hidden_turn_ids"] == [hidden_identity.turn_id]
    assert branch.metadata_json["checkpoint_binding"]["target_turn_id"] == (
        target_identity.turn_id
    )
    assert target_turn is not None
    assert target_turn.visibility_state == "active"
    assert hidden_turn is not None
    assert hidden_turn.visibility_state == "hidden_by_rollback"
    assert hidden_turn.hidden_by_control_receipt_id == receipt.receipt_id
    assert hidden_turn.hidden_after_turn_id == target_identity.turn_id
    assert material is not None
    assert material.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED.value
    assert material.invalidated_at is not None
    assert material.metadata_json["visibility_state"] == "hidden_by_rollback"
    assert material.metadata_json["hidden_after_turn_id"] == target_identity.turn_id
    assert material.metadata_json["rollback_visibility"] == {
        "hidden_by_control_receipt_id": receipt.receipt_id,
        "hidden_after_turn_id": target_identity.turn_id,
    }
    assert refreshed_session is not None
    assert refreshed_session.active_branch_head_id == target_identity.branch_head_id
    assert refreshed_session.active_runtime_profile_snapshot_id == (
        snapshot.runtime_profile_snapshot_id
    )


def test_rollback_rejects_non_settled_target_without_receipt(retrieval_session):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="identity-rollback-non-settled",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.identity.rollback_non_settled",
    )
    service = StoryRuntimeIdentityService(retrieval_session)
    identity = service.resolve_runtime_entry_identity(
        session_id=story_session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        service.rollback_to_turn(
            session_id=story_session.session_id,
            target_turn_id=identity.turn_id,
            actor="user",
        )

    assert exc_info.value.code == "runtime_branch_control_invalid_turn"
    assert "target_not_settled" in str(exc_info.value)
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    assert _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    ) == []


def test_rollback_rejects_target_from_inactive_branch_without_new_receipt(
    retrieval_session,
):
    story_session, _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-rollback-inactive-branch",
    )
    inactive_branch_target = identities[-1]
    create_receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=inactive_branch_target.turn_id,
        actor="user",
    )
    assert create_receipt.to_branch_head_id is not None
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        service.rollback_to_turn(
            session_id=story_session.session_id,
            target_turn_id=inactive_branch_target.turn_id,
            actor="user",
        )

    assert exc_info.value.code == "runtime_branch_control_invalid_turn"
    assert "target_branch_mismatch" in str(exc_info.value)
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )
    assert [record.control_kind for record in receipt_records] == [
        BranchControlKind.BRANCH_CREATED.value
    ]


def test_create_branch_rejects_hidden_rollback_origin_without_receipt(
    retrieval_session,
):
    story_session, _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-branch-hidden-origin",
        count=3,
    )
    target_identity = identities[1]
    hidden_identity = identities[2]
    service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
    )
    turn_count_before = _turn_count(
        retrieval_session,
        session_id=story_session.session_id,
    )

    with pytest.raises(StoryRuntimeIdentityServiceError) as exc_info:
        service.create_branch_from_turn(
            session_id=story_session.session_id,
            origin_turn_id=hidden_identity.turn_id,
            actor="user",
        )

    assert exc_info.value.code == "runtime_branch_control_invalid_turn"
    assert "origin_hidden_by_rollback" in str(exc_info.value)
    assert _turn_count(retrieval_session, session_id=story_session.session_id) == (
        turn_count_before
    )
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )
    assert [record.control_kind for record in receipt_records] == [
        BranchControlKind.ROLLBACK_APPLIED.value
    ]


def test_chapter_snapshot_hides_artifact_bound_to_rollback_future_turn(
    retrieval_session,
):
    story_session, _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="identity-rollback-snapshot",
        count=3,
    )
    target_identity = identities[1]
    hidden_identity = identities[2]
    story_session_service = StorySessionService(retrieval_session)
    chapter = story_session_service.create_chapter_workspace(
        session_id=story_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.SEGMENT_DRAFTING,
    )
    target_artifact = story_session_service.create_artifact(
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="visible target segment",
    )
    hidden_artifact = story_session_service.create_artifact(
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="hidden future segment",
    )
    hidden_candidate = story_session_service.create_artifact(
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="hidden future rewrite candidate",
        metadata={"runtime_turn_id": hidden_identity.turn_id},
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=hidden_candidate.artifact_id,
    )
    target_discussion = story_session_service.create_discussion_entry(
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="visible target discussion",
        linked_artifact_id=target_artifact.artifact_id,
    )
    hidden_discussion = story_session_service.create_discussion_entry(
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="hidden future discussion",
        linked_artifact_id=hidden_artifact.artifact_id,
    )
    service.update_turn_status(
        turn_id=target_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=target_artifact.artifact_id,
        selected_output_ref=target_artifact.artifact_id,
        settlement_reason="test_visible_artifact_binding",
    )
    service.update_turn_status(
        turn_id=hidden_identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=hidden_artifact.artifact_id,
        selected_output_ref=hidden_artifact.artifact_id,
        settlement_reason="test_hidden_artifact_binding",
    )

    service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
    )
    snapshot = story_session_service.build_chapter_snapshot(
        session_id=story_session.session_id,
        chapter_index=1,
    )

    assert {artifact.artifact_id for artifact in snapshot.artifacts} == {
        target_artifact.artifact_id
    }
    assert snapshot.chapter.pending_segment_artifact_id is None
    assert {entry.entry_id for entry in snapshot.discussion_entries} == {
        target_discussion.entry_id
    }
    assert hidden_discussion.entry_id not in {
        entry.entry_id for entry in snapshot.discussion_entries
    }
