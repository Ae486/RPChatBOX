"""Enforce the SetupAgentRuntimeState authoritative write boundary.

SetupAgentRuntimeStateService is the only authorized production aggregate for the
single ``SetupAgentRuntimeStateRecord`` (runtime-private cognitive state). This
lint keeps direct record imports and construction sites visible so the
``save_snapshot`` single-persistence-entry invariant is not silently bypassed by
a future cross-domain writer. Scan is import + construction (AST); leader review
additionally rules out string-table-name / raw-SQL / merge writes that AST cannot
see (T27 S3a, ADR-0015).
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CHECKER_PATH = Path(__file__).resolve()
DEFAULT_BACKEND_ROOT = CHECKER_PATH.parents[2]
AUTHORIZED = frozenset({"rp/services/setup_agent/agent_runtime_state_service.py"})
ALLOWED_SCHEMA = frozenset({"services/database.py"})
S3_RECORD_NAMES = frozenset({"SetupAgentRuntimeStateRecord"})
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
    """Lint finding for the setup-agent runtime-state record boundary."""

    code: str
    path: str
    line: int
    record: str
    bypass_type: str
    message: str

    @property
    def display(self) -> str:
        return f"{self.path}:{self.line}: {self.code}: {self.message}"


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning production files for runtime-state record bypasses."""

    files_scanned: int
    unexpected_importers: list[Finding]
    construction_bypasses: list[Finding]
    allowed_authorized: list[Finding]
    allowed_schema: list[Finding]
    parse_errors: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [
            *self.parse_errors,
            *self.unexpected_importers,
            *self.construction_bypasses,
        ]


def scan_setup_agent_runtime_state_write_boundary(
    backend_root: Path = DEFAULT_BACKEND_ROOT,
) -> ScanResult:
    """Scan production files for runtime-state record import/write bypasses."""

    unexpected_importers: list[Finding] = []
    construction_bypasses: list[Finding] = []
    allowed_authorized: list[Finding] = []
    allowed_schema: list[Finding] = []
    parse_errors: list[Finding] = []
    files_scanned = 0

    for file_path in _iter_python_files(backend_root):
        if _is_excluded_file(file_path, backend_root=backend_root):
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
                    record="",
                    bypass_type="parse",
                    message=f"syntax error: {exc.msg}",
                )
            )
            continue

        for finding in _record_import_findings(tree, display_path):
            _classify_finding(
                finding=finding,
                unexpected_importers=unexpected_importers,
                allowed_authorized=allowed_authorized,
                allowed_schema=allowed_schema,
            )

        for finding in _construction_findings(tree, display_path):
            _classify_finding(
                finding=finding,
                unexpected_importers=construction_bypasses,
                allowed_authorized=allowed_authorized,
                allowed_schema=allowed_schema,
            )

    return ScanResult(
        files_scanned=files_scanned,
        unexpected_importers=unexpected_importers,
        construction_bypasses=construction_bypasses,
        allowed_authorized=allowed_authorized,
        allowed_schema=allowed_schema,
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


def _is_excluded_file(file_path: Path, *, backend_root: Path) -> bool:
    relative = file_path.relative_to(backend_root)
    if "tests" in relative.parts:
        return True
    if file_path.name == "conftest.py" or file_path.name.startswith("test_"):
        return True
    if file_path.name == "_runtime_state_aggregate.py":
        return True
    return relative.as_posix() == "models/rp_setup_store.py"


def _relative_posix(file_path: Path, root: Path) -> str:
    return file_path.relative_to(root).as_posix()


def _record_import_findings(tree: ast.AST, display_path: str) -> list[Finding]:
    findings: list[Finding] = []
    module_aliases: set[str] = set()
    has_plain_models_rp_setup_store_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "models.rp_setup_store":
                for alias in node.names:
                    if alias.name in S3_RECORD_NAMES:
                        findings.append(
                            _import_finding(display_path, node.lineno, alias.name, "import")
                        )
            elif node.module == "models":
                for alias in node.names:
                    if alias.name == "rp_setup_store":
                        module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name != "models.rp_setup_store":
                    continue
                if alias.asname:
                    module_aliases.add(alias.asname)
                else:
                    has_plain_models_rp_setup_store_import = True

    for node in ast.walk(tree):
        record = _module_record_reference(
            node,
            module_aliases=module_aliases,
            has_plain_models_rp_setup_store_import=has_plain_models_rp_setup_store_import,
        )
        if record is None:
            continue
        findings.append(
            _import_finding(display_path, getattr(node, "lineno", 0), record, "module-import")
        )

    return findings


def _import_finding(display_path: str, line: int, record: str, bypass_type: str) -> Finding:
    return Finding(
        code="UNEXPECTED_IMPORTER",
        path=display_path,
        line=line,
        record=record,
        bypass_type=bypass_type,
        message=(
            "SetupAgentRuntimeStateRecord must be imported only through the "
            "SetupAgentRuntimeStateService boundary"
        ),
    )


def _module_record_reference(
    node: ast.AST,
    *,
    module_aliases: set[str],
    has_plain_models_rp_setup_store_import: bool,
) -> str | None:
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr not in S3_RECORD_NAMES:
        return None
    if isinstance(node.value, ast.Name) and node.value.id in module_aliases:
        return node.attr
    if (
        has_plain_models_rp_setup_store_import
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "rp_setup_store"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "models"
    ):
        return node.attr
    return None


def _construction_findings(tree: ast.AST, display_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in S3_RECORD_NAMES:
            continue
        findings.append(
            Finding(
                code="CONSTRUCTION_BYPASS",
                path=display_path,
                line=node.lineno,
                record=node.func.id,
                bypass_type="construction",
                message=(
                    "SetupAgentRuntimeStateRecord construction must stay inside "
                    "rp/services/setup_agent/agent_runtime_state_service.py"
                ),
            )
        )
    return findings


def _classify_finding(
    *,
    finding: Finding,
    unexpected_importers: list[Finding],
    allowed_authorized: list[Finding],
    allowed_schema: list[Finding],
) -> None:
    if finding.path in AUTHORIZED:
        allowed_authorized.append(_replace_code(finding, "AUTHORIZED_AGGREGATE"))
    elif finding.path in ALLOWED_SCHEMA:
        allowed_schema.append(_replace_code(finding, "ALLOWED_SCHEMA"))
    else:
        unexpected_importers.append(finding)


def _replace_code(finding: Finding, code: str) -> Finding:
    return Finding(
        code=code,
        path=finding.path,
        line=finding.line,
        record=finding.record,
        bypass_type=finding.bypass_type,
        message=finding.message,
    )


def format_report(result: ScanResult) -> str:
    unexpected_counts = Counter(finding.record for finding in result.unexpected_importers)
    construction_counts = Counter(finding.record for finding in result.construction_bypasses)
    lines = [
        "SetupAgentRuntimeState write boundary lint",
        f"files scanned: {result.files_scanned}",
        f"unexpected-importer(hard): {len(result.unexpected_importers)}",
        f"construction-bypass(hard): {len(result.construction_bypasses)}",
        f"allowed-authorized: {len(_paths_with_findings(result.allowed_authorized))} files",
        f"allowed-schema: {len(_paths_with_findings(result.allowed_schema))} files",
        f"parse errors: {len(result.parse_errors)}",
    ]

    if unexpected_counts:
        lines.append("unexpected-importer records:")
        for record, count in sorted(unexpected_counts.items()):
            lines.append(f"  - {record}: {count}")

    if construction_counts:
        lines.append("construction-bypass records:")
        for record, count in sorted(construction_counts.items()):
            lines.append(f"  - {record}: {count}")

    lines.extend(_format_file_category("allowed-authorized", result.allowed_authorized))
    lines.extend(
        _format_file_category(
            "allowed-schema (DDL/metadata only; no data seeding)",
            result.allowed_schema,
        )
    )

    if result.errors:
        lines.append("")
        lines.append("ERRORS:")
        lines.extend(
            f"- {finding.display} ({finding.bypass_type}:{finding.record})"
            for finding in result.errors
        )
        lines.append("")
        lines.append("result: FAIL")
    else:
        lines.append("")
        lines.append("result: PASS")

    return "\n".join(lines)


def _paths_with_findings(findings: list[Finding]) -> set[str]:
    return {finding.path for finding in findings}


def _format_file_category(title: str, findings: list[Finding]) -> list[str]:
    if not findings:
        return []

    by_path: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_path[finding.path].append(finding)

    lines = ["", f"{title}:"]
    for path in sorted(by_path):
        lines.append(f"- {path}")
        for finding in sorted(by_path[path], key=lambda item: (item.line, item.record)):
            lines.append(f"  - line {finding.line}: {finding.bypass_type} {finding.record}")
    return lines


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=DEFAULT_BACKEND_ROOT,
        help="Backend tree to scan. Defaults to backend/.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = scan_setup_agent_runtime_state_write_boundary(backend_root=args.backend_root)
    print(format_report(result))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
