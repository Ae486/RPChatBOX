"""Focused tests for the CoreState authoritative write-boundary lint."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_core_state_write_boundary import (
    DEFAULT_BACKEND_ROOT,
    scan_core_state_write_boundary,
)
from rp.services.core_state._aggregate import CoreStateAggregate
from rp.services.proposal.apply_service import ProposalApplyService


def _write_python(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "VALUE = 1\n", encoding="utf-8")


def _scan(backend_root: Path):
    return scan_core_state_write_boundary(
        backend_root=backend_root,
        core_state_root=backend_root / "rp" / "services" / "core_state",
        devtools_root=backend_root / "rp" / "devtools",
    )


def test_authoritative_write_outside_core_state_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "story" / "some_service.py",
        "core_repo.upsert_authoritative_object(session_id='s1')\n",
    )

    result = _scan(backend_root)

    assert len(result.violations) == 1
    assert result.violations[0].method == "upsert_authoritative_object"


def test_authoritative_write_inside_core_state_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "services" / "core_state" / "some_writer.py",
        "core_repo.upsert_authoritative_object(session_id='s1')\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_authoritative_write_inside_tests_is_allowed(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "tests" / "services" / "test_x.py",
        "core_repo.upsert_authoritative_object(session_id='s1')\n",
    )

    result = _scan(backend_root)

    assert result.errors == []


def test_real_backend_tree_has_no_core_state_write_bypass() -> None:
    result = scan_core_state_write_boundary(DEFAULT_BACKEND_ROOT)

    assert result.errors == []


def test_proposal_apply_service_structurally_satisfies_core_state_aggregate() -> None:
    assert issubclass(ProposalApplyService, CoreStateAggregate)
