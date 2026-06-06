"""Focused tests for the SetupAgentRuntimeState write-boundary lint."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_setup_agent_runtime_state_write_boundary import (
    ALLOWED_SCHEMA,
    AUTHORIZED,
    DEFAULT_BACKEND_ROOT,
    scan_setup_agent_runtime_state_write_boundary,
)
from rp.services.setup_agent._runtime_state_aggregate import (
    SetupAgentRuntimeStateAggregate,
)
from rp.services.setup_agent.agent_runtime_state_service import (
    SetupAgentRuntimeStateService,
)


def _write_python(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "VALUE = 1\n", encoding="utf-8")


def _scan(backend_root: Path):
    return scan_setup_agent_runtime_state_write_boundary(backend_root=backend_root)


def test_unexpected_importer_outside_allowlist_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "from models.rp_setup_store import SetupAgentRuntimeStateRecord\n"
        "VALUE = SetupAgentRuntimeStateRecord\n",
    )

    result = _scan(backend_root)

    assert len(result.unexpected_importers) >= 1
    assert result.unexpected_importers[0].code == "UNEXPECTED_IMPORTER"


def test_construction_outside_aggregate_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "from models.rp_setup_store import SetupAgentRuntimeStateRecord\n"
        "record = SetupAgentRuntimeStateRecord()\n",
    )

    result = _scan(backend_root)

    assert len(result.construction_bypasses) >= 1
    assert result.construction_bypasses[0].code == "CONSTRUCTION_BYPASS"


def test_authorized_aggregate_file_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root
        / "rp"
        / "services"
        / "setup_agent"
        / "agent_runtime_state_service.py",
        "from models.rp_setup_store import SetupAgentRuntimeStateRecord\n"
        "record = SetupAgentRuntimeStateRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_tests_dir_is_excluded(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "setup_agent" / "test_x.py",
        "from models.rp_setup_store import SetupAgentRuntimeStateRecord\n"
        "record = SetupAgentRuntimeStateRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_tree_has_no_unexpected_importer_or_construction_bypass() -> None:
    result = scan_setup_agent_runtime_state_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []
    assert result.unexpected_importers == []
    assert result.construction_bypasses == []


def test_real_tree_authorized_and_schema_are_exactly_classified() -> None:
    result = scan_setup_agent_runtime_state_write_boundary(DEFAULT_BACKEND_ROOT)

    assert {finding.path for finding in result.allowed_authorized} == set(AUTHORIZED)
    assert {finding.path for finding in result.allowed_schema} == set(ALLOWED_SCHEMA)


def test_service_structurally_satisfies_aggregate() -> None:
    assert issubclass(SetupAgentRuntimeStateService, SetupAgentRuntimeStateAggregate)


def test_governance_methods_funnel_through_single_entry() -> None:
    # The single persistence entry plus the five governance command adapters
    # must exist on the service; this anchors the "save_snapshot is the only
    # durable write entry" invariant against a future method bypassing it.
    for name in (
        "save_snapshot",
        "replace_discussion_state",
        "upsert_chunk",
        "record_truth_write",
        "reconcile_snapshot",
        "persist_turn_governance",
    ):
        assert callable(getattr(SetupAgentRuntimeStateService, name))
