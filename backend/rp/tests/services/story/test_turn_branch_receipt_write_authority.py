"""Write-authority characterization for turn/branch/receipt owner-only mutations."""

from __future__ import annotations

import ast

from models.rp_story_store import BranchControlReceiptRecord, StoryTurnRecord
from rp.devtools.check_story_session_write_boundary import (
    DEFAULT_BACKEND_ROOT,
    scan_story_session_write_boundary,
)
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver

from .test_session_pointer_write_authority import _seed_settled_main_turns
from .test_story_runtime_identity_service import _branch_receipts


def _files_assigning_field(field: str) -> set[str]:
    """Relative-posix paths of production rp files that ASSIGN `record.<field>`."""

    backend_root = DEFAULT_BACKEND_ROOT
    offenders: set[str] = set()
    for path in (backend_root / "rp").rglob("*.py"):
        parts = path.parts
        if "tests" in parts or "__pycache__" in parts:
            continue
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr == field:
                    offenders.add(path.relative_to(backend_root).as_posix())
    return offenders


def _naive(dt):
    if dt is None or getattr(dt, "tzinfo", None) is None:
        return dt
    return dt.replace(tzinfo=None)


class _RecordingTurnCoreStateBindingPort:
    def __init__(self) -> None:
        self.calls: list[tuple[StoryTurnRecord, str]] = []

    def stage_turn_core_state_binding(
        self,
        *,
        turn: StoryTurnRecord,
        snapshot_id: str,
    ) -> None:
        self.calls.append((turn, snapshot_id))


def test_core_state_snapshot_id_assigned_only_in_runtime_identity_service():
    """Static sole-writer guard for StoryTurn.core_state_snapshot_id."""

    assert _files_assigning_field("core_state_snapshot_id") == {
        "rp/services/story/runtime_identity_service.py"
    }


def test_stage_turn_core_state_binding_is_noop_for_same_snapshot_id(
    retrieval_session,
    monkeypatch,
):
    """Owner seam must skip flush and mutation when the snapshot id is unchanged."""

    _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5e-turn-core-state-noop",
        count=1,
    )
    turn = retrieval_session.get(StoryTurnRecord, identities[0].turn_id)
    assert turn is not None
    turn.core_state_snapshot_id = "snapshot:same"

    flush_calls: list[int] = []
    monkeypatch.setattr(
        retrieval_session, "flush", lambda *args, **kwargs: flush_calls.append(1)
    )

    service.stage_turn_core_state_binding(
        turn=turn,
        snapshot_id="snapshot:same",
    )

    assert flush_calls == []
    assert turn.core_state_snapshot_id == "snapshot:same"


def test_stage_turn_core_state_binding_flushes_without_commit_on_change(
    retrieval_session,
    monkeypatch,
):
    """Owner seam flushes the row but never commits the transaction itself."""

    _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5e-turn-core-state-change",
        count=1,
    )
    turn = retrieval_session.get(StoryTurnRecord, identities[0].turn_id)
    assert turn is not None

    commit_calls: list[int] = []
    monkeypatch.setattr(
        retrieval_session, "commit", lambda *args, **kwargs: commit_calls.append(1)
    )

    service.stage_turn_core_state_binding(
        turn=turn,
        snapshot_id="snapshot:new",
    )

    assert commit_calls == []
    assert turn.core_state_snapshot_id == "snapshot:new"


def test_stage_turn_core_state_binding_mutates_only_core_state_snapshot_id(
    retrieval_session,
):
    """The owner seam must not touch any collateral StoryTurn fields."""

    _, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5e-turn-core-state-side-effects",
        count=1,
    )
    turn = retrieval_session.get(StoryTurnRecord, identities[0].turn_id)
    assert turn is not None
    before = turn.model_dump()

    service.stage_turn_core_state_binding(
        turn=turn,
        snapshot_id="snapshot:side-effect-check",
    )

    after = turn.model_dump()
    changed_keys = {
        key for key in set(before) | set(after) if before.get(key) != after.get(key)
    }
    assert changed_keys == {"core_state_snapshot_id"}


def test_as_of_resolver_turn_binding_is_fully_delegated(retrieval_session):
    """The resolver must delegate the write entirely through the injected port."""

    _, _, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5e-as-of-turn-binding-delegation",
        count=1,
    )
    turn = retrieval_session.get(StoryTurnRecord, identities[0].turn_id)
    assert turn is not None
    before_snapshot_id = turn.core_state_snapshot_id
    fake_port = _RecordingTurnCoreStateBindingPort()
    resolver = CoreStateAsOfResolver(
        session=retrieval_session,
        turn_core_state_binding_port=fake_port,
    )

    resolver._bind_turn_to_manifest(
        turn=turn,
        snapshot_id="snapshot:delegated-only",
    )

    assert fake_port.calls == [(turn, "snapshot:delegated-only")]
    assert turn.core_state_snapshot_id == before_snapshot_id


def test_branch_control_receipt_construction_is_owned_by_runtime_identity_service():
    """BranchControlReceipt construction remains owned by the runtime identity aggregate."""

    result = scan_story_session_write_boundary(DEFAULT_BACKEND_ROOT)
    construction_findings = [
        finding
        for finding in result.allowed_authorized
        if finding.bypass_type == "construction"
        and finding.record == "BranchControlReceiptRecord"
    ]

    assert construction_findings
    assert {finding.path for finding in construction_findings} == {
        "rp/services/story/runtime_identity_service.py"
    }


def test_rollback_receipt_metadata_enrichment_is_owner_applied(retrieval_session):
    """Rollback metadata_json enrichment must be applied on the owner-owned receipt row."""

    story_session, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5e-rollback-receipt-enrichment",
        count=3,
    )
    target_identity = identities[1]
    hidden_identity = identities[2]

    # Roll back the ACTIVE main branch (head at the last settled turn) to an
    # earlier turn so the later turn is genuinely hidden. A no-op rollback (e.g.
    # rolling back to the head of a freshly forked branch) would hide nothing and
    # leave the enrichment assertions toothless.
    receipt = service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
        metadata={"target_checkpoint_id": "checkpoint:owner-enrichment"},
    )
    receipt_record = retrieval_session.get(BranchControlReceiptRecord, receipt.receipt_id)

    assert receipt_record is not None
    assert receipt_record.metadata_json == receipt.metadata
    assert receipt_record.metadata_json["visibility_transition"]["hidden_after_turn_id"] == (
        target_identity.turn_id
    )
    assert receipt_record.metadata_json["visibility_transition"]["hidden_turn_ids"] == [
        hidden_identity.turn_id
    ]
    assert receipt_record.metadata_json["visibility_transition"][
        "invalidated_workspace_material_ids"
    ] == []
    assert receipt_record.metadata_json["previous"]["ignored_checkpoint_inputs"] == {
        "target_checkpoint_id": "checkpoint:owner-enrichment"
    }


def test_branch_head_lifecycle_fields_are_owned_by_runtime_identity_service():
    """Static field-authority guard for branch lifecycle fields unique to BranchHeadRecord."""

    expected_owner = {"rp/services/story/runtime_identity_service.py"}
    # parent_branch_head_id is construction-only (set via the BranchHeadRecord(...)
    # constructor, never attribute-assigned), so it is covered by the S5a
    # construction lint, not by this attribute-assignment guard. Including it here
    # would assert against an empty set and fail. The three fields below ARE
    # attribute-assigned in production and are unique to BranchHeadRecord.
    unique_branch_fields = {
        "head_turn_id",
        "last_settled_turn_id",
        "created_by_control_receipt_id",
    }
    for field in unique_branch_fields:
        assert _files_assigning_field(field) == expected_owner


def test_turn_hidden_by_rollback_fields_are_owned_by_runtime_identity_service():
    """Static field-authority guard for rollback-only StoryTurn lifecycle fields."""

    expected_owner = {"rp/services/story/runtime_identity_service.py"}
    rollback_turn_fields = {
        "hidden_by_control_receipt_id",
        "hidden_after_turn_id",
    }
    for field in rollback_turn_fields:
        assert _files_assigning_field(field) == expected_owner


def test_branch_create_and_rollback_receipts_share_persisted_timestamps(
    retrieval_session,
):
    """SQLite reloads receipt times tz-naive; compare normalized in-memory and persisted rows."""

    story_session, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5e-receipt-timestamp-normalization",
        count=3,
    )
    create_receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=identities[1].turn_id,
        actor="user",
        branch_name="receipt-time-branch",
    )
    create_receipt_record = retrieval_session.get(
        BranchControlReceiptRecord, create_receipt.receipt_id
    )
    assert create_receipt_record is not None
    assert create_receipt_record.created_at == _naive(create_receipt.created_at)

    rollback_receipt = service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=identities[1].turn_id,
        actor="user",
    )
    rollback_receipt_record = retrieval_session.get(
        BranchControlReceiptRecord, rollback_receipt.receipt_id
    )
    assert rollback_receipt_record is not None
    assert rollback_receipt_record.created_at == _naive(rollback_receipt.created_at)
    receipt_records = _branch_receipts(
        retrieval_session,
        session_id=story_session.session_id,
    )
    assert {record.receipt_id for record in receipt_records} >= {
        create_receipt.receipt_id,
        rollback_receipt.receipt_id,
    }
