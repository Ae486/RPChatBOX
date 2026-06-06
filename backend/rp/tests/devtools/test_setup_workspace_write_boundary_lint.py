"""Focused tests for the SetupWorkspace write-boundary lint."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_setup_workspace_write_boundary import (
    DEFAULT_BACKEND_ROOT,
    KNOWN_BYPASS_DEBT,
    scan_setup_workspace_write_boundary,
)
from rp.services.setup_agent._aggregate import SetupWorkspaceAggregate
from rp.services.setup_agent.workspace_service import SetupWorkspaceService


def _write_python(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "VALUE = 1\n", encoding="utf-8")


def _scan(backend_root: Path):
    return scan_setup_workspace_write_boundary(backend_root=backend_root)


def test_unexpected_importer_outside_allowlist_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "from models.rp_setup_store import SetupWorkspaceRecord\n"
        "VALUE = SetupWorkspaceRecord\n",
    )

    result = _scan(backend_root)

    assert len(result.unexpected_importers) >= 1
    assert result.unexpected_importers[0].code == "UNEXPECTED_IMPORTER"


def test_construction_outside_aggregate_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "from models.rp_setup_store import SetupDraftBlockRecord\n"
        "record = SetupDraftBlockRecord()\n",
    )

    result = _scan(backend_root)

    assert len(result.construction_bypasses) >= 1
    assert result.construction_bypasses[0].code == "CONSTRUCTION_BYPASS"


def test_authorized_aggregate_file_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "setup_agent" / "workspace_service.py",
        "from models.rp_setup_store import SetupDraftBlockRecord\n"
        "record = SetupDraftBlockRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_tests_dir_is_excluded(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "setup_agent" / "test_x.py",
        "from models.rp_setup_store import SetupDraftBlockRecord\n"
        "record = SetupDraftBlockRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_tree_has_no_unexpected_importer_or_construction_bypass() -> None:
    result = scan_setup_workspace_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []
    assert result.unexpected_importers == []
    assert result.construction_bypasses == []


def test_real_tree_known_bypass_debt_is_exactly_three() -> None:
    result = scan_setup_workspace_write_boundary(DEFAULT_BACKEND_ROOT)

    assert {finding.path for finding in result.known_bypass_debt} == set(
        KNOWN_BYPASS_DEBT
    )


def test_setup_workspace_service_structurally_satisfies_aggregate() -> None:
    assert issubclass(SetupWorkspaceService, SetupWorkspaceAggregate)
