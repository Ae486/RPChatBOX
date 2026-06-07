"""StorySession active-pointer write-authority characterization (T27 S5d).

These guards prove the StorySession active-pointer field writes flow only through
the owner aggregate (StorySessionService), and that rerouting preserved behavior
(no spurious updated_at bump, shared activation timestamp, no extra flush). They
are the field-mutation teeth that the import+construction lint cannot provide.
"""

from __future__ import annotations

import ast
from types import SimpleNamespace

from models.rp_story_store import (
    BranchControlReceiptRecord,
    BranchHeadRecord,
    StorySessionRecord,
)
from rp.models.runtime.config_contracts import RuntimeConfigPatchRequest
from rp.devtools.check_story_session_write_boundary import DEFAULT_BACKEND_ROOT
from rp.models.setup_agent.workspace import StoryMode
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.story.runtime import LongformChapterPhase
from rp.services.runtime.config_control_service import RuntimeConfigControlService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_service import StorySessionService


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


class _FakeProviderRegistry:
    def __init__(self, providers: dict[str, object] | None = None) -> None:
        self._providers = providers or {}

    def get_entry(self, provider_id: str):
        return self._providers.get(provider_id)


class _FakeModelRegistry:
    def __init__(self, models: dict[str, object] | None = None) -> None:
        self._models = models or {}

    def get_entry(self, model_id: str):
        return self._models.get(model_id)


def _seed_session(
    retrieval_session,
    *,
    story_id: str,
    runtime_story_config: dict | None = None,
):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    return StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config=dict(runtime_story_config or {}),
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def _control_service(retrieval_session) -> RuntimeConfigControlService:
    provider = SimpleNamespace(provider_id="provider-runtime", is_enabled=True)
    model = SimpleNamespace(
        id="model-runtime",
        provider_id="provider-runtime",
        is_enabled=True,
    )
    return RuntimeConfigControlService(
        retrieval_session,
        model_registry_service=_FakeModelRegistry({"model-runtime": model}),
        provider_registry_service=_FakeProviderRegistry({"provider-runtime": provider}),
    )


def _seed_settled_main_turns(
    retrieval_session,
    *,
    story_id: str,
    count: int = 2,
):
    story_session = _seed_session(retrieval_session, story_id=story_id)
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
            requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        )
        service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.SETTLED,
            visible_output_ref=f"artifact:{index}",
            selected_output_ref=f"artifact:{index}",
            settlement_reason="test_settled",
        )
        identities.append(identity)
    return story_session, service, identities


def _naive(dt):
    if dt is None or getattr(dt, "tzinfo", None) is None:
        return dt
    return dt.replace(tzinfo=None)


def test_active_runtime_profile_snapshot_pointer_assigned_only_in_owner():
    """Static teeth: only StorySessionService may assign this active pointer."""
    assert _files_assigning_field("active_runtime_profile_snapshot_id") == {
        "rp/services/story/session_service.py"
    }


def test_runtime_story_config_assigned_only_in_owner():
    """Static teeth: only StorySessionService may assign runtime story config."""
    assert _files_assigning_field("runtime_story_config_json") == {
        "rp/services/story/session_service.py"
    }


def test_active_branch_head_pointer_assigned_only_in_owner():
    """Static teeth: only StorySessionService may assign the active branch head."""
    assert _files_assigning_field("active_branch_head_id") == {
        "rp/services/story/session_service.py"
    }


def test_set_active_runtime_profile_snapshot_seam_is_flush_free(
    retrieval_session, monkeypatch
):
    """The owner seam assigns the field without flushing (caller owns the txn)."""
    session = _seed_session(
        retrieval_session, story_id="s5d1-seam-flush-free"
    )
    record = retrieval_session.get(StorySessionRecord, session.session_id)
    service = StorySessionService(retrieval_session)

    flush_calls: list[int] = []
    monkeypatch.setattr(
        retrieval_session, "flush", lambda *a, **k: flush_calls.append(1)
    )
    service.set_active_runtime_profile_snapshot(record, "snap-seam-test")

    assert record.active_runtime_profile_snapshot_id == "snap-seam-test"
    assert flush_calls == []


def test_ensure_active_snapshot_pins_session_and_shares_timestamp(retrieval_session):
    """Behavior preserved: activation pins the session and shares the timestamp."""
    session = _seed_session(retrieval_session, story_id="s5d1-pins-and-timestamp")
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)

    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.s5d1.pin",
    )
    record = retrieval_session.get(StorySessionRecord, session.session_id)

    assert (
        record.active_runtime_profile_snapshot_id
        == snapshot.runtime_profile_snapshot_id
    )
    # SQLite stores DATETIME tz-naive, so the reloaded session record drops tzinfo
    # while the in-memory snapshot keeps it. Normalizing the in-memory side proves
    # the shared instant (microseconds still compared) without the storage artifact.
    assert record.updated_at == snapshot.activated_at.replace(tzinfo=None)


def test_publish_already_active_snapshot_does_not_bump_session_updated_at(
    retrieval_session,
):
    """H5 no-op: re-pinning the already-active snapshot must not bump updated_at."""
    session = _seed_session(retrieval_session, story_id="s5d1-noop-no-bump")
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.s5d1.noop",
    )
    record = retrieval_session.get(StorySessionRecord, session.session_id)
    before_updated_at = record.updated_at

    snapshot_service.publish_snapshot(snapshot.runtime_profile_snapshot_id)

    assert record.updated_at == before_updated_at


def test_publish_patch_preserves_nested_runtime_story_config_siblings(
    retrieval_session,
):
    """Config reroute must full-replace the deep-merged result, not a shallow patch."""
    session = _seed_session(
        retrieval_session,
        story_id="s5d23-runtime-config-deep-merge",
        runtime_story_config={
            "custom_runtime": {
                "siblings": {"keep_me": 2, "touch_me": 1},
            }
        },
    )
    RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.s5d23.runtime_config.initial",
    )
    service = _control_service(retrieval_session)

    service.publish_patch(
        RuntimeConfigPatchRequest(
            session_id=session.session_id,
            runtime_story_config={
                "custom_runtime": {
                    "siblings": {"touch_me": 7},
                }
            },
        )
    )

    record = retrieval_session.get(StorySessionRecord, session.session_id)

    assert record is not None
    assert record.runtime_story_config_json == {
        "custom_runtime": {
            "siblings": {"keep_me": 2, "touch_me": 7},
        }
    }


def test_create_branch_from_turn_shares_branch_session_receipt_timestamp(
    retrieval_session,
):
    """Branch creation keeps one shared now across branch/session/receipt writes."""
    story_session, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5d23-branch-create-timestamp",
    )

    receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=identities[-1].turn_id,
        actor="user",
        branch_name="timestamp-branch",
    )

    session_record = retrieval_session.get(StorySessionRecord, story_session.session_id)
    branch_record = retrieval_session.get(BranchHeadRecord, receipt.to_branch_head_id)
    receipt_record = retrieval_session.get(BranchControlReceiptRecord, receipt.receipt_id)

    assert session_record is not None
    assert branch_record is not None
    assert receipt_record is not None
    assert session_record.updated_at == branch_record.updated_at == _naive(
        receipt.created_at
    )
    assert session_record.updated_at == receipt_record.created_at


def test_switch_branch_shares_session_receipt_timestamp_without_touching_branch_row(
    retrieval_session,
):
    """Switch reroute keeps the session/receipt now and does not mutate branch time."""
    story_session, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="s5d23-branch-switch-timestamp",
    )
    create_receipt = service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=identities[-1].turn_id,
        actor="user",
    )
    target_branch = retrieval_session.get(BranchHeadRecord, identities[-1].branch_head_id)
    assert target_branch is not None
    target_updated_at_before = target_branch.updated_at

    receipt = service.switch_branch(
        session_id=story_session.session_id,
        target_branch_head_id=identities[-1].branch_head_id,
        actor="user",
    )

    session_record = retrieval_session.get(StorySessionRecord, story_session.session_id)
    target_branch = retrieval_session.get(BranchHeadRecord, identities[-1].branch_head_id)
    receipt_record = retrieval_session.get(BranchControlReceiptRecord, receipt.receipt_id)

    assert create_receipt.to_branch_head_id is not None
    assert session_record is not None
    assert target_branch is not None
    assert receipt_record is not None
    assert session_record.updated_at == _naive(receipt.created_at)
    assert session_record.updated_at == receipt_record.created_at
    assert target_branch.updated_at == target_updated_at_before


def test_set_runtime_story_config_seam_is_flush_free(
    retrieval_session, monkeypatch
):
    """The owner seam full-replaces the config without flushing (caller owns txn)."""
    session = _seed_session(retrieval_session, story_id="s5d2-seam-flush-free")
    record = retrieval_session.get(StorySessionRecord, session.session_id)
    service = StorySessionService(retrieval_session)

    flush_calls: list[int] = []
    monkeypatch.setattr(
        retrieval_session, "flush", lambda *a, **k: flush_calls.append(1)
    )
    service.set_runtime_story_config(record, {"seam": "replace"})

    assert record.runtime_story_config_json == {"seam": "replace"}
    assert flush_calls == []


def test_set_active_branch_head_seam_is_flush_free(
    retrieval_session, monkeypatch
):
    """The owner seam assigns the branch head without flushing (caller owns txn)."""
    session = _seed_session(retrieval_session, story_id="s5d3-seam-flush-free")
    record = retrieval_session.get(StorySessionRecord, session.session_id)
    service = StorySessionService(retrieval_session)

    flush_calls: list[int] = []
    monkeypatch.setattr(
        retrieval_session, "flush", lambda *a, **k: flush_calls.append(1)
    )
    service.set_active_branch_head(record, "branch-seam-test")

    assert record.active_branch_head_id == "branch-seam-test"
    assert flush_calls == []
