"""Focused tests for the RP service size lint ratchet."""

from __future__ import annotations

import json
from pathlib import Path

from rp.devtools.check_service_sizes import (
    DEFAULT_THRESHOLDS,
    BaselineEntry,
    Finding,
    SizeThresholds,
    check_service_sizes,
    scan_services,
)


def _write_python(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_baseline(
    path: Path,
    entries: list[dict[str, object]],
    *,
    thresholds: SizeThresholds = DEFAULT_THRESHOLDS,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "thresholds": thresholds.as_mapping(),
                "hard_allowlist": entries,
            }
        ),
        encoding="utf-8",
    )


def _baseline_entry(
    *,
    kind: str,
    service_path: str,
    symbol: str | None,
    lines: int,
) -> dict[str, object]:
    return {
        "kind": kind,
        "path": service_path,
        "symbol": symbol,
        "lines": lines,
        "reason": "test baseline reason",
    }


def _function_source(name: str, lines: int) -> str:
    body_lines = ["    value = 0"]
    body_lines.extend(f"    value += {index}" for index in range(lines - 3))
    body_lines.append("    return value")
    return "\n".join([f"def {name}():", *body_lines]) + "\n"


def _class_source(name: str, lines: int) -> str:
    body_lines = ["    value = 0"]
    body_lines.extend(f"    field_{index} = {index}" for index in range(lines - 2))
    return "\n".join([f"class {name}:", *body_lines]) + "\n"


def test_scan_services_recurses_and_uses_ast_inclusive_spans(tmp_path: Path) -> None:
    service_root = tmp_path / "services"
    nested_file = service_root / "retrieval" / "sample_service.py"
    _write_python(
        nested_file,
        "\n".join(
            [
                "class SampleService:",
                "    def hard_method(self):",
                *["        pass" for _ in range(6)],
                "",
            ]
        ),
    )

    result = scan_services(
        service_root,
        thresholds=SizeThresholds(
            file_soft=99,
            file_hard=199,
            function_soft=7,
            function_hard=70,
            class_soft=8,
            class_hard=80,
        ),
    )

    assert result.files_scanned == 1
    assert result.parse_errors == []
    assert {
        (finding.kind, finding.path, finding.symbol, finding.lines)
        for finding in result.findings
    } == {
        ("function", "retrieval/sample_service.py", "SampleService.hard_method", 7),
        ("class", "retrieval/sample_service.py", "SampleService", 8),
    }


def test_soft_findings_are_advisory_and_do_not_require_baseline(tmp_path: Path) -> None:
    service_root = tmp_path / "services"
    baseline_path = tmp_path / "baseline.json"
    thresholds = SizeThresholds(
        file_soft=99,
        file_hard=199,
        function_soft=4,
        function_hard=10,
        class_soft=99,
        class_hard=199,
    )
    _write_python(service_root / "memory" / "soft_service.py", _function_source("soft_func", 4))
    _write_baseline(baseline_path, [], thresholds=thresholds)

    result = check_service_sizes(
        service_root,
        baseline_path,
        thresholds=thresholds,
    )

    assert result.errors == []
    assert [(finding.kind, finding.display, finding.lines) for finding in result.soft_findings] == [
        ("function", "memory/soft_service.py::soft_func", 4)
    ]


def test_new_hard_offender_fails_without_baseline(tmp_path: Path) -> None:
    service_root = tmp_path / "services"
    baseline_path = tmp_path / "baseline.json"
    thresholds = SizeThresholds(
        file_soft=99,
        file_hard=199,
        function_soft=4,
        function_hard=10,
        class_soft=99,
        class_hard=199,
    )
    _write_python(service_root / "story" / "new_hard_service.py", _function_source("hard_func", 10))
    _write_baseline(baseline_path, [], thresholds=thresholds)

    result = check_service_sizes(
        service_root,
        baseline_path,
        thresholds=thresholds,
    )

    assert any("new hard service-size offender" in error for error in result.errors)


def test_hard_baseline_growth_fails(tmp_path: Path) -> None:
    service_root = tmp_path / "services"
    baseline_path = tmp_path / "baseline.json"
    service_path = "writer/growing_service.py"
    thresholds = SizeThresholds(
        file_soft=99,
        file_hard=199,
        function_soft=99,
        function_hard=199,
        class_soft=4,
        class_hard=10,
    )
    _write_python(service_root / service_path, _class_source("GrowingService", 12))
    _write_baseline(
        baseline_path,
        [
            _baseline_entry(
                kind="class",
                service_path=service_path,
                symbol="GrowingService",
                lines=10,
            )
        ],
        thresholds=thresholds,
    )

    result = check_service_sizes(
        service_root,
        baseline_path,
        thresholds=thresholds,
    )

    assert any("baseline grew" in error for error in result.errors)


def test_stale_hard_baseline_entry_fails(tmp_path: Path) -> None:
    service_root = tmp_path / "services"
    baseline_path = tmp_path / "baseline.json"
    service_path = "setup_agent/refactored_service.py"
    thresholds = SizeThresholds(
        file_soft=99,
        file_hard=199,
        function_soft=4,
        function_hard=10,
        class_soft=99,
        class_hard=199,
    )
    _write_python(service_root / service_path, "def small():\n    return 1\n")
    _write_baseline(
        baseline_path,
        [
            _baseline_entry(
                kind="function",
                service_path=service_path,
                symbol="small",
                lines=10,
            )
        ],
        thresholds=thresholds,
    )

    result = check_service_sizes(
        service_root,
        baseline_path,
        thresholds=thresholds,
    )

    assert any("stale hard baseline entry" in error for error in result.errors)


def test_hard_baseline_shrink_fails_until_baseline_updates(tmp_path: Path) -> None:
    service_root = tmp_path / "services"
    baseline_path = tmp_path / "baseline.json"
    service_path = "runtime/shrinking_service.py"
    thresholds = SizeThresholds(
        file_soft=99,
        file_hard=199,
        function_soft=4,
        function_hard=10,
        class_soft=99,
        class_hard=199,
    )
    _write_python(service_root / service_path, _function_source("shrinking_func", 10))
    _write_baseline(
        baseline_path,
        [
            _baseline_entry(
                kind="function",
                service_path=service_path,
                symbol="shrinking_func",
                lines=12,
            )
        ],
        thresholds=thresholds,
    )

    result = check_service_sizes(
        service_root,
        baseline_path,
        thresholds=thresholds,
    )

    assert any("baseline can shrink" in error for error in result.errors)


def test_baseline_file_requires_reason_metadata(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    _write_python(tmp_path / "services" / "core_state" / "empty.py", "")
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "thresholds": DEFAULT_THRESHOLDS.as_mapping(),
                "hard_allowlist": [
                    {
                        "kind": "file",
                        "path": "core_state/empty.py",
                        "symbol": None,
                        "lines": 1000,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = check_service_sizes(tmp_path / "services", baseline_path)

    assert any("non-empty reason" in error for error in result.errors)


def test_baseline_entry_displays_symbol_scope() -> None:
    entry = BaselineEntry(
        kind="function",
        path="retrieval/broker.py",
        symbol="RetrievalBroker._search",
        lines=115,
        reason="T6 / Task B grandfather",
    )
    finding = Finding(
        kind="function",
        path="retrieval/broker.py",
        symbol="RetrievalBroker._search",
        lines=115,
        soft_limit=50,
        hard_limit=100,
    )

    assert entry.key == finding.key
    assert entry.display == "retrieval/broker.py::RetrievalBroker._search"
