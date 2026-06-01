"""Focused tests for the RP services import-shape lint."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_service_imports import (
    format_report,
    scan_backend_imports,
)


def _write_python(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "VALUE = 1\n", encoding="utf-8")


def _service_module(backend_root: Path, domain: str, module: str, text: str = "") -> Path:
    return backend_root / "rp" / "services" / domain / f"{module}.py"


def _scan(backend_root: Path, *, strict_facade_bypass: bool = False):
    return scan_backend_imports(
        backend_root=backend_root,
        service_root=backend_root / "rp" / "services",
        strict_facade_bypass=strict_facade_bypass,
    )


def _error_codes(result) -> set[str]:
    return {finding.code for finding in result.errors}


def _advisory_codes(result) -> set[str]:
    return {finding.code for finding in result.advisory_findings}


def test_same_subdir_absolute_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        _service_module(backend_root, "retrieval", "broker"),
        "from rp.services.retrieval.service import RetrievalService\n",
    )

    result = _scan(backend_root)

    assert "SAME_SUBDIR_ABSOLUTE_IMPORT" in _error_codes(result)


def test_same_subdir_relative_import_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        _service_module(backend_root, "retrieval", "broker"),
        "from .service import RetrievalService\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_cross_domain_absolute_import_is_report_only(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        _service_module(backend_root, "story", "activation_service"),
        "from rp.services.retrieval.service import RetrievalService\n",
    )

    result = _scan(backend_root)

    assert result.errors == []
    assert "CROSS_DOMAIN_ABSOLUTE_IMPORT" in _advisory_codes(result)


def test_service_root_level_non_domain_relative_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        _service_module(backend_root, "story", "activation_service"),
        "from ..legacy_story_service import LegacyStoryService\n",
    )

    result = _scan(backend_root)

    assert "ROOT_RELATIVE_SERVICE_IMPORT" in _error_codes(result)


def test_old_shim_basename_absolute_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "memory", "os_service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from rp.services.memory_os_service import MemoryOsService\n",
    )

    result = _scan(backend_root)

    assert "OLD_SHIM_OR_ROOT_SERVICE_IMPORT" in _error_codes(result)


def test_stale_same_domain_relative_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        _service_module(backend_root, "memory", "os_service"),
        "from .memory_os_service import MemoryOsService\n",
    )

    result = _scan(backend_root)

    assert "STALE_RELATIVE_SERVICE_IMPORT" in _error_codes(result)


def test_same_domain_package_import_fails_as_non_concrete(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "memory", "object_mapper"))
    _write_python(
        _service_module(backend_root, "memory", "os_service"),
        "from . import object_mapper\n",
    )

    result = _scan(backend_root)

    assert "NON_CONCRETE_SERVICE_IMPORT" in _error_codes(result)


def test_external_relative_service_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from ..services.retrieval.service import RetrievalService\n",
    )

    result = _scan(backend_root)

    assert "EXTERNAL_RELATIVE_SERVICE_IMPORT" in _error_codes(result)


def test_external_non_absolute_service_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from services.retrieval.service import RetrievalService\n",
    )

    result = _scan(backend_root)

    assert "EXTERNAL_NON_ABSOLUTE_SERVICE_IMPORT" in _error_codes(result)


def test_backend_root_services_package_import_is_not_rp_service_import(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        backend_root / "api" / "rp_story.py",
        "from services.database import get_engine\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_external_absolute_concrete_service_import_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from rp.services.retrieval.service import RetrievalService\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_external_non_concrete_service_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from rp.services.retrieval import service\n",
    )

    result = _scan(backend_root)

    assert "NON_CONCRETE_SERVICE_IMPORT" in _error_codes(result)


def test_external_rp_services_package_import_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from rp import services\n",
    )

    result = _scan(backend_root)

    assert "NON_CONCRETE_SERVICE_IMPORT" in _error_codes(result)


def test_facade_bypass_is_default_report_only_and_strict_optional(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "document_service"))
    _write_python(
        backend_root / "rp" / "runtime" / "factory.py",
        "from rp.services.retrieval.document_service import RetrievalDocumentService\n",
    )

    default_result = _scan(backend_root)
    strict_result = _scan(backend_root, strict_facade_bypass=True)

    assert default_result.errors == []
    assert "FACADE_BYPASS_CANDIDATE" in _advisory_codes(default_result)
    assert "FACADE_BYPASS" in _error_codes(strict_result)


def test_report_includes_advisory_summary_without_failing(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(_service_module(backend_root, "retrieval", "document_service"))
    _write_python(
        _service_module(backend_root, "story", "activation_service"),
        "from rp.services.retrieval.document_service import RetrievalDocumentService\n",
    )

    report = format_report(_scan(backend_root))

    assert "result: PASS" in report
    assert "CROSS_DOMAIN_ABSOLUTE_IMPORT" in report
    assert "FACADE_BYPASS_CANDIDATE" in report
