"""Focused tests for the SetupWorkspace write-boundary lint."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_setup_workspace_write_boundary import (
    ALLOWED_READ,
    AUTHORIZED,
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


def test_get_then_setattr_outside_aggregate_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "from models.rp_setup_store import SetupWorkspaceRecord\n"
        "def mutate(session, workspace_id):\n"
        "    record = session.get(SetupWorkspaceRecord, workspace_id)\n"
        "    record.current_step = 'story_config'\n",
    )

    result = _scan(backend_root)

    assert len(result.mutation_bypasses) >= 1
    assert result.mutation_bypasses[0].code == "MUTATION_BYPASS"


def test_select_loop_setattr_outside_aggregate_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "from sqlmodel import select\n"
        "from models.rp_setup_store import SetupWorkspaceRecord\n"
        "def mutate(session):\n"
        "    for record in session.exec(select(SetupWorkspaceRecord)).all():\n"
        "        record.current_step = 'story_config'\n",
    )

    result = _scan(backend_root)

    assert len(result.mutation_bypasses) >= 1
    assert result.mutation_bypasses[0].code == "MUTATION_BYPASS"


def test_allowed_read_path_setattr_write_is_hard_failure(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "retrieval" / "runtime_config_service.py",
        "from models.rp_setup_store import SetupWorkspaceRecord\n"
        "def mutate(session, workspace_id):\n"
        "    record = session.get(SetupWorkspaceRecord, workspace_id)\n"
        "    record.current_step = 'story_config'\n",
    )

    result = _scan(backend_root)

    assert {finding.path for finding in result.allowed_read} == {
        "rp/services/retrieval/runtime_config_service.py"
    }
    assert len(result.mutation_bypasses) >= 1
    assert result.errors != []


def test_authorized_aggregate_file_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "setup_agent" / "workspace_service.py",
        "from models.rp_setup_store import SetupDraftBlockRecord\n"
        "record = SetupDraftBlockRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_authorized_aggregate_setattr_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "setup_agent" / "workspace_service.py",
        "from models.rp_setup_store import SetupWorkspaceRecord\n"
        "def mutate(session, workspace_id):\n"
        "    record = session.get(SetupWorkspaceRecord, workspace_id)\n"
        "    record.current_step = 'story_config'\n",
    )

    result = _scan(backend_root)

    assert result.errors == []
    assert {finding.path for finding in result.allowed_authorized} == {
        "rp/services/setup_agent/workspace_service.py"
    }
    assert any(
        finding.bypass_type == "mutation" for finding in result.allowed_authorized
    )


def test_tests_dir_is_excluded(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "setup_agent" / "test_x.py",
        "from models.rp_setup_store import SetupDraftBlockRecord\n"
        "record = SetupDraftBlockRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_tree_has_no_hard_write_boundary_failures() -> None:
    result = scan_setup_workspace_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []
    assert result.unexpected_importers == []
    assert result.construction_bypasses == []
    assert result.mutation_bypasses == []


def test_real_tree_classification_matches_locked_s2b2_expectations() -> None:
    result = scan_setup_workspace_write_boundary(DEFAULT_BACKEND_ROOT)

    assert {finding.path for finding in result.allowed_authorized} == set(AUTHORIZED)
    assert {finding.path for finding in result.allowed_read} == set(ALLOWED_READ)
    assert {finding.path for finding in result.known_bypass_debt} == set(
        KNOWN_BYPASS_DEBT
    )
    assert {finding.path for finding in result.known_bypass_debt} == set()
    assert "rp/services/retrieval/minimal_ingestion_service.py" in {
        finding.path for finding in result.allowed_read
    }


def test_setup_workspace_service_structurally_satisfies_aggregate() -> None:
    assert issubclass(SetupWorkspaceService, SetupWorkspaceAggregate)
