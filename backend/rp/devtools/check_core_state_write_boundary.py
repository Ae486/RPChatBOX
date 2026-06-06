"""Enforce the CoreState authoritative write boundary.

CoreState is the authoritative aggregate root for formal story state. Direct
calls to the authoritative upsert methods must stay inside the core_state
domain so proposal/apply remains the governed command entry and
CoreStateDualWriteService remains the executor.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CHECKER_PATH = Path(__file__).resolve()
DEFAULT_BACKEND_ROOT = CHECKER_PATH.parents[2]
DEFAULT_CORE_STATE_ROOT = CHECKER_PATH.parents[1] / "services" / "core_state"
DEFAULT_DEVTOOLS_ROOT = CHECKER_PATH.parent
AUTHORITATIVE_WRITE_METHODS = frozenset(
    {
        "upsert_authoritative_object",
        "upsert_authoritative_revision",
    }
)
IGNORED_SCAN_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "downloaded_files",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class Finding:
    """Hard-fail lint violation."""

    code: str
    path: str
    line: int
    method: str
    message: str

    @property
    def display(self) -> str:
        return f"{self.path}:{self.line}: {self.code}: {self.message}"


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning production Python files for boundary bypasses."""

    files_scanned: int
    violations: list[Finding]
    parse_errors: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [*self.parse_errors, *self.violations]


def scan_core_state_write_boundary(
    backend_root: Path = DEFAULT_BACKEND_ROOT,
    core_state_root: Path | None = None,
    devtools_root: Path | None = None,
) -> ScanResult:
    """Scan production files for CoreState authoritative write bypasses.

    Tests, devtools, and files inside rp/services/core_state are excluded. The
    remaining production tree must not call the repository-level authoritative
    upsert methods directly.
    """

    core_state_root = core_state_root or backend_root / "rp" / "services" / "core_state"
    devtools_root = devtools_root or backend_root / "rp" / "devtools"
    violations: list[Finding] = []
    parse_errors: list[Finding] = []
    files_scanned = 0

    for file_path in _iter_python_files(backend_root):
        if _is_excluded_file(
            file_path,
            backend_root=backend_root,
            core_state_root=core_state_root,
            devtools_root=devtools_root,
        ):
            continue
        files_scanned += 1
        display_path = _relative_posix(file_path, backend_root)
        try:
            tree = ast.parse(
                file_path.read_text(encoding="utf-8"),
                filename=str(file_path),
            )
        except SyntaxError as exc:
            parse_errors.append(
                Finding(
                    code="PARSE_ERROR",
                    path=display_path,
                    line=exc.lineno or 0,
                    method="",
                    message=f"syntax error: {exc.msg}",
                )
            )
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            if method not in AUTHORITATIVE_WRITE_METHODS:
                continue
            violations.append(
                Finding(
                    code="CORE_STATE_WRITE_BYPASS",
                    path=display_path,
                    line=node.lineno,
                    method=method,
                    message=(
                        "authoritative CoreState writes must stay inside "
                        "rp.services.core_state"
                    ),
                )
            )

    return ScanResult(
        files_scanned=files_scanned,
        violations=violations,
        parse_errors=parse_errors,
    )


def _iter_python_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (
        path
        for path in sorted(root.rglob("*.py"))
        if not any(part in IGNORED_SCAN_DIRS for part in path.parts)
    )


def _is_excluded_file(
    file_path: Path,
    *,
    backend_root: Path,
    core_state_root: Path,
    devtools_root: Path,
) -> bool:
    if _is_relative_to(file_path, core_state_root):
        return True
    if _is_relative_to(file_path, devtools_root):
        return True
    if "tests" in file_path.relative_to(backend_root).parts:
        return True
    return file_path.name == "conftest.py" or file_path.name.startswith("test_")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _relative_posix(file_path: Path, root: Path) -> str:
    return file_path.relative_to(root).as_posix()


def format_report(result: ScanResult) -> str:
    violation_counts = Counter(finding.method for finding in result.violations)
    parse_count = len(result.parse_errors)
    lines = [
        "CoreState authoritative write boundary lint",
        f"files scanned: {result.files_scanned}",
        f"violations: {len(result.violations)}",
        f"parse errors: {parse_count}",
    ]

    if violation_counts:
        lines.append("violation counts:")
        for method, count in sorted(violation_counts.items()):
            lines.append(f"  - {method}: {count}")

    if result.errors:
        lines.append("")
        lines.append("ERRORS:")
        lines.extend(
            f"- {finding.display} ({finding.method})" for finding in result.errors
        )
        lines.append("")
        lines.append("result: FAIL")
    else:
        lines.append("")
        lines.append("result: PASS")

    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=DEFAULT_BACKEND_ROOT,
        help="Backend tree to scan. Defaults to backend/.",
    )
    parser.add_argument(
        "--core-state-root",
        type=Path,
        default=DEFAULT_CORE_STATE_ROOT,
        help="CoreState service tree. Defaults to backend/rp/services/core_state.",
    )
    parser.add_argument(
        "--devtools-root",
        type=Path,
        default=DEFAULT_DEVTOOLS_ROOT,
        help="Devtools tree to exclude. Defaults to backend/rp/devtools.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = scan_core_state_write_boundary(
        backend_root=args.backend_root,
        core_state_root=args.core_state_root,
        devtools_root=args.devtools_root,
    )
    print(format_report(result))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
