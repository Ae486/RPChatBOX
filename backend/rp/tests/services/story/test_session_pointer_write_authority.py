"""StorySession active-pointer write-authority characterization (T27 S5d).

These guards prove the StorySession active-pointer field writes flow only through
the owner aggregate (StorySessionService), and that rerouting preserved behavior
(no spurious updated_at bump, shared activation timestamp, no extra flush). They
are the field-mutation teeth that the import+construction lint cannot provide.
"""

from __future__ import annotations

import ast

from models.rp_story_store import StorySessionRecord
from rp.devtools.check_story_session_write_boundary import DEFAULT_BACKEND_ROOT
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import LongformChapterPhase
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
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


def _seed_session(retrieval_session, *, story_id: str):
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


def test_active_runtime_profile_snapshot_pointer_assigned_only_in_owner():
    """Static teeth: only StorySessionService may assign this active pointer."""
    assert _files_assigning_field("active_runtime_profile_snapshot_id") == {
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
