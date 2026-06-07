"""Focused tests for the StorySession/RuntimeTurn write-boundary lint (T27 S5a)."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_story_session_write_boundary import (
    ALLOWED_READ,
    ALLOWED_SCHEMA,
    AUTHORIZED,
    DEFAULT_BACKEND_ROOT,
    NONPROD_BYPASS_DEBT,
    PRODUCTION_BYPASS_DEBT,
    STORY_RECORD_NAMES,
    scan_story_session_write_boundary,
)


def _write_python(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _scan(backend_root: Path):
    return scan_story_session_write_boundary(backend_root=backend_root)


def test_unexpected_importer_outside_allowlist_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "rogue" / "rogue_service.py",
        "from models.rp_story_store import StoryTurnRecord\n"
        "VALUE = StoryTurnRecord\n",
    )

    result = _scan(backend_root)

    assert len(result.unexpected_importers) >= 1
    assert result.unexpected_importers[0].code == "UNEXPECTED_IMPORTER"


def test_construction_outside_authorized_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "rogue" / "rogue_service.py",
        "from models.rp_story_store import BranchHeadRecord\n"
        "record = BranchHeadRecord()\n",
    )

    result = _scan(backend_root)

    assert len(result.construction_bypasses) >= 1
    assert result.construction_bypasses[0].code == "CONSTRUCTION_BYPASS"


def test_authorized_sink_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "runtime" / "workflow_job_service.py",
        "from models.rp_story_store import RuntimeWorkflowJobRecord\n"
        "record = RuntimeWorkflowJobRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_read_allowlisted_file_may_import_but_not_construct(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "retrieval" / "search.py",
        "from models.rp_story_store import RuntimeProfileSnapshotRecord\n"
        "record = RuntimeProfileSnapshotRecord()\n",
    )

    result = _scan(backend_root)

    assert result.unexpected_importers == []
    assert len(result.allowed_read) >= 1
    assert len(result.construction_bypasses) >= 1


def test_tests_dir_is_excluded(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "test_x.py",
        "from models.rp_story_store import StorySessionRecord\n"
        "record = StorySessionRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_tree_has_no_unexpected_importer_or_construction_bypass() -> None:
    result = scan_story_session_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []
    assert result.unexpected_importers == []
    assert result.construction_bypasses == []


def test_real_tree_allowlists_are_exactly_classified() -> None:
    result = scan_story_session_write_boundary(DEFAULT_BACKEND_ROOT)

    assert {f.path for f in result.allowed_authorized} == set(AUTHORIZED)
    assert {f.path for f in result.allowed_read} == set(ALLOWED_READ)
    assert {f.path for f in result.allowed_schema} == set(ALLOWED_SCHEMA)
    assert {f.path for f in result.production_bypass_debt} == set(
        PRODUCTION_BYPASS_DEBT
    )
    assert {f.path for f in result.nonprod_bypass_debt} == set(NONPROD_BYPASS_DEBT)


def test_story_record_names_are_exactly_pinned() -> None:
    assert STORY_RECORD_NAMES == {
        "StorySessionRecord",
        "ChapterWorkspaceRecord",
        "StoryArtifactRecord",
        "StoryDiscussionEntryRecord",
        "StoryBlockConsumerStateRecord",
        "BranchHeadRecord",
        "BranchControlReceiptRecord",
        "RuntimeProfileSnapshotRecord",
        "RuntimeConfigControlReceiptRecord",
        "StoryTurnRecord",
        "RuntimeWorkflowJobRecord",
    }
