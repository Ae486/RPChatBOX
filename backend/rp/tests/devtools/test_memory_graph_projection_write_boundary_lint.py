"""Focused tests for the MemoryGraphProjection write-boundary lint (T27)."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_memory_graph_projection_write_boundary import (
    ALLOWED_READ,
    ALLOWED_SCHEMA,
    AUTHORIZED,
    DEFAULT_BACKEND_ROOT,
    ScanResult,
    scan_memory_graph_projection_write_boundary,
)
from rp.services.memory._graph_projection_aggregate import (
    MemoryGraphProjectionAggregate,
)
from rp.services.memory.graph_projection_repository import MemoryGraphProjectionRepository


def _write_python(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _scan(backend_root: Path) -> ScanResult:
    return scan_memory_graph_projection_write_boundary(backend_root=backend_root)


def test_unexpected_importer_outside_allowlist_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "recall" / "rogue_service.py",
        "from models.rp_retrieval_store import MemoryGraphNodeRecord\n"
        "VALUE = MemoryGraphNodeRecord\n",
    )

    result = _scan(backend_root)

    assert len(result.unexpected_importers) >= 1
    assert result.unexpected_importers[0].code == "UNEXPECTED_IMPORTER"


def test_construction_outside_authorized_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "recall" / "rogue_service.py",
        "from models.rp_retrieval_store import MemoryGraphEdgeRecord\n"
        "record = MemoryGraphEdgeRecord()\n",
    )

    result = _scan(backend_root)

    assert len(result.construction_bypasses) >= 1
    assert result.construction_bypasses[0].code == "CONSTRUCTION_BYPASS"


def test_authorized_repository_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "memory" / "graph_projection_repository.py",
        "from models.rp_retrieval_store import MemoryGraphNodeRecord\n"
        "record = MemoryGraphNodeRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_read_allowlisted_file_may_import_but_not_construct(
    tmp_path: Path,
) -> None:
    backend_root = tmp_path / "backend"
    read_path = backend_root / "rp" / "retrieval" / "graph_expansion.py"
    _write_python(
        read_path,
        "from models.rp_retrieval_store import MemoryGraphEvidenceRecord\n"
        "VALUE = MemoryGraphEvidenceRecord\n",
    )

    import_only = _scan(backend_root)

    assert import_only.unexpected_importers == []
    assert import_only.construction_bypasses == []
    assert len(import_only.allowed_read) >= 1

    _write_python(
        read_path,
        "from models.rp_retrieval_store import MemoryGraphEvidenceRecord\n"
        "record = MemoryGraphEvidenceRecord()\n",
    )

    constructing = _scan(backend_root)

    assert constructing.unexpected_importers == []
    assert len(constructing.construction_bypasses) >= 1


def test_module_import_forms_are_detected(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "recall" / "from_models.py",
        "from models import rp_retrieval_store as store\n"
        "VALUE = store.MemoryGraphNodeRecord\n",
    )
    _write_python(
        backend_root / "rp" / "services" / "recall" / "plain_import.py",
        "import models.rp_retrieval_store\n"
        "VALUE = models.rp_retrieval_store.MemoryGraphEdgeRecord\n",
    )

    result = _scan(backend_root)

    assert {finding.record for finding in result.unexpected_importers} == {
        "MemoryGraphEdgeRecord",
        "MemoryGraphNodeRecord",
    }


def test_tests_dir_is_excluded(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "memory" / "test_x.py",
        "from models.rp_retrieval_store import MemoryGraphNodeRecord\n"
        "record = MemoryGraphNodeRecord()\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_tree_has_no_unexpected_importer_or_construction_bypass() -> None:
    result = scan_memory_graph_projection_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []
    assert result.unexpected_importers == []
    assert result.construction_bypasses == []


def test_real_tree_allowlists_are_exactly_classified() -> None:
    result = scan_memory_graph_projection_write_boundary(DEFAULT_BACKEND_ROOT)

    assert {finding.path for finding in result.allowed_authorized} == set(AUTHORIZED)
    assert {finding.path for finding in result.allowed_read} == set(ALLOWED_READ)
    assert {finding.path for finding in result.allowed_schema} == set(ALLOWED_SCHEMA)


def test_graph_projection_repository_structurally_satisfies_protocol() -> None:
    assert issubclass(
        MemoryGraphProjectionRepository,
        MemoryGraphProjectionAggregate,
    )
