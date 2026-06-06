"""Enforce the SetupWorkspace authoritative write boundary.

SetupWorkspaceService is the only authorized production aggregate for the S2
setup workspace records. This lint keeps direct record imports and construction
sites visible so future S2b/S3 work can close the remaining bypass debt without
changing runtime behavior in this additive guard slice.
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
AUTHORIZED = frozenset({"rp/services/setup_agent/workspace_service.py"})
ALLOWED_READ = frozenset(
    {
        "rp/devtools/legal_longform_session_seed.py",
        "rp/services/retrieval/minimal_ingestion_service.py",
        "rp/services/retrieval/runtime_config_service.py",
    }
)
ALLOWED_SCHEMA = frozenset({"services/database.py"})
KNOWN_BYPASS_DEBT = frozenset()
S2_RECORD_NAMES = frozenset(
    {
        "SetupWorkspaceRecord",
        "SetupStepStateRecord",
        "SetupDraftBlockRecord",
        "SetupImportedAssetRecord",
        "SetupStepAssetBindingRecord",
        "SetupOpenQuestionRecord",
        "SetupCommitProposalRecord",
        "SetupAcceptedCommitRecord",
        "SetupRetrievalIngestionJobRecord",
        "SetupPendingUserEditDeltaRecord",
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
    """Lint finding for setup workspace record boundary checks."""

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
    """Result of scanning production Python files for setup record bypasses."""

    files_scanned: int
    unexpected_importers: list[Finding]
    construction_bypasses: list[Finding]
    mutation_bypasses: list[Finding]
    allowed_authorized: list[Finding]
    allowed_read: list[Finding]
    allowed_schema: list[Finding]
    known_bypass_debt: list[Finding]
    parse_errors: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [
            *self.parse_errors,
            *self.unexpected_importers,
            *self.construction_bypasses,
            *self.mutation_bypasses,
        ]


def scan_setup_workspace_write_boundary(
    backend_root: Path = DEFAULT_BACKEND_ROOT,
) -> ScanResult:
    """Scan production files for setup workspace record import/write bypasses."""

    unexpected_importers: list[Finding] = []
    construction_bypasses: list[Finding] = []
    mutation_bypasses: list[Finding] = []
    allowed_authorized: list[Finding] = []
    allowed_read: list[Finding] = []
    allowed_schema: list[Finding] = []
    known_bypass_debt: list[Finding] = []
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
            _classify_import_finding(
                finding=finding,
                unexpected_importers=unexpected_importers,
                allowed_authorized=allowed_authorized,
                allowed_read=allowed_read,
                allowed_schema=allowed_schema,
                known_bypass_debt=known_bypass_debt,
            )

        for finding in _construction_findings(tree, display_path):
            _classify_construction_finding(
                finding=finding,
                construction_bypasses=construction_bypasses,
                allowed_authorized=allowed_authorized,
                known_bypass_debt=known_bypass_debt,
            )

        for finding in _mutation_findings(tree, display_path):
            _classify_mutation_finding(
                finding=finding,
                mutation_bypasses=mutation_bypasses,
                allowed_authorized=allowed_authorized,
                known_bypass_debt=known_bypass_debt,
            )

    return ScanResult(
        files_scanned=files_scanned,
        unexpected_importers=unexpected_importers,
        construction_bypasses=construction_bypasses,
        mutation_bypasses=mutation_bypasses,
        allowed_authorized=allowed_authorized,
        allowed_read=allowed_read,
        allowed_schema=allowed_schema,
        known_bypass_debt=known_bypass_debt,
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
    if file_path.name == "_aggregate.py":
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
                    if alias.name in S2_RECORD_NAMES:
                        findings.append(
                            Finding(
                                code="UNEXPECTED_IMPORTER",
                                path=display_path,
                                line=node.lineno,
                                record=alias.name,
                                bypass_type="import",
                                message=(
                                    "S2 setup store records must be imported only "
                                    "through the SetupWorkspaceService boundary"
                                ),
                            )
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
            Finding(
                code="UNEXPECTED_IMPORTER",
                path=display_path,
                line=getattr(node, "lineno", 0),
                record=record,
                bypass_type="module-import",
                message=(
                    "S2 setup store records must be imported only through the "
                    "SetupWorkspaceService boundary"
                ),
            )
        )

    return findings


def _module_record_reference(
    node: ast.AST,
    *,
    module_aliases: set[str],
    has_plain_models_rp_setup_store_import: bool,
) -> str | None:
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr not in S2_RECORD_NAMES:
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
        if node.func.id not in S2_RECORD_NAMES:
            continue
        findings.append(
            Finding(
                code="CONSTRUCTION_BYPASS",
                path=display_path,
                line=node.lineno,
                record=node.func.id,
                bypass_type="construction",
                message=(
                    "S2 setup store record construction must stay inside "
                    "rp/services/setup_agent/workspace_service.py"
                ),
            )
        )
    return findings


def _mutation_findings(tree: ast.AST, display_path: str) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(
                _mutation_findings_in_statements(
                    node.body,
                    display_path=display_path,
                    bindings=_parameter_record_bindings(node),
                )
            )
    return findings


def _mutation_findings_in_statements(
    statements: list[ast.stmt],
    *,
    display_path: str,
    bindings: dict[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    current_bindings = dict(bindings)

    for stmt in statements:
        findings.extend(
            _statement_mutation_findings(
                stmt,
                display_path=display_path,
                bindings=current_bindings,
            )
        )

        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            loop_bindings = dict(current_bindings)
            loop_binding = _loop_record_binding(stmt)
            if loop_binding is not None:
                loop_bindings[loop_binding[0]] = loop_binding[1]
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.body,
                    display_path=display_path,
                    bindings=loop_bindings,
                )
            )
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.orelse,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
        elif isinstance(stmt, ast.If):
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.body,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.orelse,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.body,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
        elif isinstance(stmt, ast.Try):
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.body,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
            for handler in stmt.handlers:
                findings.extend(
                    _mutation_findings_in_statements(
                        handler.body,
                        display_path=display_path,
                        bindings=current_bindings,
                    )
                )
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.orelse,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
            findings.extend(
                _mutation_findings_in_statements(
                    stmt.finalbody,
                    display_path=display_path,
                    bindings=current_bindings,
                )
            )
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                findings.extend(
                    _mutation_findings_in_statements(
                        case.body,
                        display_path=display_path,
                        bindings=current_bindings,
                    )
                )

        current_bindings = _update_record_bindings(current_bindings, stmt)

    return findings


def _statement_mutation_findings(
    stmt: ast.stmt,
    *,
    display_path: str,
    bindings: dict[str, str],
) -> list[Finding]:
    targets: list[ast.expr] = []
    if isinstance(stmt, ast.Assign):
        targets = list(stmt.targets)
    elif isinstance(stmt, ast.AnnAssign):
        targets = [stmt.target]
    elif isinstance(stmt, ast.AugAssign):
        targets = [stmt.target]
    else:
        return []

    findings: list[Finding] = []
    for target in targets:
        attr_target = target if isinstance(target, ast.Attribute) else None
        if attr_target is None:
            continue
        if not isinstance(attr_target.value, ast.Name):
            continue
        record = bindings.get(attr_target.value.id)
        if record is None:
            continue
        findings.append(
            Finding(
                code="MUTATION_BYPASS",
                path=display_path,
                line=stmt.lineno,
                record=record,
                bypass_type="mutation",
                message=(
                    "S2 setup store record attribute mutation must stay inside "
                    "rp/services/setup_agent/workspace_service.py"
                ),
            )
        )
    return findings


def _update_record_bindings(
    bindings: dict[str, str],
    stmt: ast.stmt,
) -> dict[str, str]:
    updated = dict(bindings)

    if isinstance(stmt, ast.Assign):
        record_name = _session_get_record_name(stmt.value)
        for target in stmt.targets:
            for name in _assigned_names(target):
                if record_name is not None and isinstance(target, ast.Name):
                    updated[name] = record_name
                else:
                    updated.pop(name, None)
    elif isinstance(stmt, ast.AnnAssign):
        record_name = _session_get_record_name(stmt.value)
        for name in _assigned_names(stmt.target):
            if record_name is not None and isinstance(stmt.target, ast.Name):
                updated[name] = record_name
            else:
                updated.pop(name, None)

    return updated


def _assigned_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.List, ast.Tuple)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_assigned_names(item))
        return names
    return []


def _parameter_record_bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    parameters = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        parameters.append(node.args.vararg)
    if node.args.kwarg is not None:
        parameters.append(node.args.kwarg)

    for parameter in parameters:
        record_name = _annotation_record_name(parameter.annotation)
        if record_name is not None:
            bindings[parameter.arg] = record_name
    return bindings


def _annotation_record_name(annotation: ast.AST | None) -> str | None:
    if annotation is None:
        return None
    record_names = {
        child.id
        for child in ast.walk(annotation)
        if isinstance(child, ast.Name) and child.id in S2_RECORD_NAMES
    }
    if len(record_names) != 1:
        return None
    return next(iter(record_names))


def _session_get_record_name(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
        return None

    model_node: ast.expr | None = None
    if node.args:
        model_node = node.args[0]
    else:
        for keyword in node.keywords:
            if keyword.arg in {"entity", "model"}:
                model_node = keyword.value
                break
    if isinstance(model_node, ast.Name) and model_node.id in S2_RECORD_NAMES:
        return model_node.id
    return None


def _loop_record_binding(stmt: ast.For | ast.AsyncFor) -> tuple[str, str] | None:
    if not isinstance(stmt.target, ast.Name):
        return None
    record_name = _exec_select_record_name(stmt.iter)
    if record_name is None:
        return None
    return stmt.target.id, record_name


def _exec_select_record_name(node: ast.AST) -> str | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not isinstance(child.func, ast.Attribute) or child.func.attr != "exec":
            continue
        for arg in child.args:
            record_name = _select_record_name(arg)
            if record_name is not None:
                return record_name
    return None


def _select_record_name(node: ast.AST) -> str | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not isinstance(child.func, ast.Name) or child.func.id != "select":
            continue
        if not child.args:
            continue
        first_arg = child.args[0]
        if isinstance(first_arg, ast.Name) and first_arg.id in S2_RECORD_NAMES:
            return first_arg.id
    return None


def _classify_import_finding(
    *,
    finding: Finding,
    unexpected_importers: list[Finding],
    allowed_authorized: list[Finding],
    allowed_read: list[Finding],
    allowed_schema: list[Finding],
    known_bypass_debt: list[Finding],
) -> None:
    if finding.path in AUTHORIZED:
        allowed_authorized.append(_replace_code(finding, "AUTHORIZED_AGGREGATE"))
    elif finding.path in ALLOWED_READ:
        allowed_read.append(_replace_code(finding, "ALLOWED_READ"))
    elif finding.path in ALLOWED_SCHEMA:
        allowed_schema.append(_replace_code(finding, "ALLOWED_SCHEMA"))
    elif finding.path in KNOWN_BYPASS_DEBT:
        known_bypass_debt.append(_replace_code(finding, "KNOWN_BYPASS_DEBT"))
    else:
        unexpected_importers.append(finding)


def _classify_construction_finding(
    *,
    finding: Finding,
    construction_bypasses: list[Finding],
    allowed_authorized: list[Finding],
    known_bypass_debt: list[Finding],
) -> None:
    if finding.path in AUTHORIZED:
        allowed_authorized.append(_replace_code(finding, "AUTHORIZED_AGGREGATE"))
    elif finding.path in KNOWN_BYPASS_DEBT:
        known_bypass_debt.append(_replace_code(finding, "KNOWN_BYPASS_DEBT"))
    else:
        construction_bypasses.append(finding)


def _classify_mutation_finding(
    *,
    finding: Finding,
    mutation_bypasses: list[Finding],
    allowed_authorized: list[Finding],
    known_bypass_debt: list[Finding],
) -> None:
    if finding.path in AUTHORIZED:
        allowed_authorized.append(_replace_code(finding, "AUTHORIZED_AGGREGATE"))
    elif finding.path in KNOWN_BYPASS_DEBT:
        known_bypass_debt.append(_replace_code(finding, "KNOWN_BYPASS_DEBT"))
    else:
        mutation_bypasses.append(finding)


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
    mutation_counts = Counter(finding.record for finding in result.mutation_bypasses)
    parse_count = len(result.parse_errors)
    debt_files = _paths_with_findings(result.known_bypass_debt)
    lines = [
        "SetupWorkspace write boundary lint",
        f"files scanned: {result.files_scanned}",
        f"unexpected-importer(hard): {len(result.unexpected_importers)}",
        f"construction-bypass(hard): {len(result.construction_bypasses)}",
        f"mutation-bypass(hard): {len(result.mutation_bypasses)}",
        f"allowed-authorized: {len(_paths_with_findings(result.allowed_authorized))} files",
        f"allowed-read: {len(_paths_with_findings(result.allowed_read))} files",
        f"allowed-schema: {len(_paths_with_findings(result.allowed_schema))} files",
        f"known-bypass-debt: {len(debt_files)} files",
        f"parse errors: {parse_count}",
    ]

    if unexpected_counts:
        lines.append("unexpected-importer records:")
        for record, count in sorted(unexpected_counts.items()):
            lines.append(f"  - {record}: {count}")

    if construction_counts:
        lines.append("construction-bypass records:")
        for record, count in sorted(construction_counts.items()):
            lines.append(f"  - {record}: {count}")

    if mutation_counts:
        lines.append("mutation-bypass records:")
        for record, count in sorted(mutation_counts.items()):
            lines.append(f"  - {record}: {count}")

    lines.extend(_format_file_category("allowed-read", result.allowed_read))
    lines.extend(
        _format_file_category(
            "allowed-schema (DDL/metadata only; no data seeding)",
            result.allowed_schema,
        )
    )
    lines.extend(
        _format_file_category(
            "KNOWN-BYPASS-DEBT (S2b MUST CLOSE)",
            result.known_bypass_debt,
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
            lines.append(
                f"  - line {finding.line}: {finding.bypass_type} {finding.record}"
            )
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
    result = scan_setup_workspace_write_boundary(backend_root=args.backend_root)
    print(format_report(result))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
