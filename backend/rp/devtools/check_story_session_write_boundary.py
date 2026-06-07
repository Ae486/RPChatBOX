"""Enforce the StorySession/RuntimeTurn import+construction write boundary (T27 S5a, ADR-0015 S5).

The 11 story-session/runtime-turn records -- StorySessionRecord,
ChapterWorkspaceRecord, StoryArtifactRecord, StoryDiscussionEntryRecord,
StoryBlockConsumerStateRecord, BranchHeadRecord, BranchControlReceiptRecord,
RuntimeProfileSnapshotRecord, RuntimeConfigControlReceiptRecord,
StoryTurnRecord, RuntimeWorkflowJobRecord -- are constructed only by six
authorized story/runtime sinks (session_service, runtime_identity_service,
profile_snapshot_service, config_control_service, workflow_job_service,
block_consumer_state_service). This lint keeps direct import and construction
sites visible so future write-authority debt stays explicit without changing
runtime behavior here.

Scope limits (anti-fitting / honest disclosure):
- This lint detects IMPORT + CONSTRUCTION in AST. It does NOT detect field
  mutation (x.field = ...).
- StorySession owner-pointer field authority is enforced separately by
  characterization tests (`test_session_pointer_write_authority.py`) because a
  future foreign `x.field = ...` write would still be invisible to this lint if
  it happened inside an otherwise AUTHORIZED constructor service.
- rp/services/core_state/as_of_resolver.py is in PRODUCTION_BYPASS_DEBT
  precisely because it writes StoryTurnRecord.core_state_snapshot_id (:516),
  the one penetration this lint can keep visible only through its import
  surface; it is cleared in S5e via port inversion.
- This lint does NOT fully enforce the boundary. It formalizes the import +
  construction boundary only. Listing as_of_resolver as ALLOWED_READ would be
  dishonest because it mutates a Story record field in production.
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

AUTHORIZED = frozenset(
    {
        "rp/services/story/session_service.py",
        "rp/services/story/runtime_identity_service.py",
        "rp/services/runtime/profile_snapshot_service.py",
        "rp/services/runtime/config_control_service.py",
        "rp/services/runtime/workflow_job_service.py",
        "rp/services/story/block_consumer_state_service.py",
    }
)

ALLOWED_READ = frozenset(
    {
        "rp/services/story/turn_domain_service.py",
        "rp/services/writer/worker_memory_service.py",
        "rp/services/retrieval/search.py",
        "rp/services/retrieval/runtime_config_service.py",
        "rp/services/story/runtime_debug_query_service.py",
        "rp/services/proposal/post_write_governance_service.py",
        "rp/services/story/archival_evolution_service.py",
        "rp/services/proposal/post_write_scheduler_service.py",
        "rp/services/runtime/read_manifest_service.py",
        "rp/eval/runner.py",
        "rp/devtools/legal_longform_session_seed.py",
    }
)

ALLOWED_SCHEMA = frozenset({"services/database.py"})
PRODUCTION_BYPASS_DEBT = frozenset({"rp/services/core_state/as_of_resolver.py"})
NONPROD_BYPASS_DEBT = frozenset()

STORY_RECORD_NAMES = frozenset(
    {
        "StorySessionRecord",
        "ChapterWorkspaceRecord",
        "StoryArtifactRecord",
        "StoryDiscussionEntryRecord",
        "StoryBlockConsumerStateRecord",
        "BranchHeadRecord",
        "BranchControlReceiptRecord",
        "RuntimeProfileSnapshotRecord",
        "RuntimeConfigControlReceiptRecord",
        "StoryTurnRecord",
        "RuntimeWorkflowJobRecord",
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
    """Lint finding for a story-session/runtime-turn boundary check."""

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
    """Result of scanning production files for story record bypasses."""

    files_scanned: int
    unexpected_importers: list[Finding]
    construction_bypasses: list[Finding]
    allowed_authorized: list[Finding]
    allowed_read: list[Finding]
    allowed_schema: list[Finding]
    production_bypass_debt: list[Finding]
    nonprod_bypass_debt: list[Finding]
    parse_errors: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [
            *self.parse_errors,
            *self.unexpected_importers,
            *self.construction_bypasses,
        ]


def scan_story_session_write_boundary(
    backend_root: Path = DEFAULT_BACKEND_ROOT,
) -> ScanResult:
    """Scan production files for story record import/write bypasses."""

    unexpected_importers: list[Finding] = []
    construction_bypasses: list[Finding] = []
    allowed_authorized: list[Finding] = []
    allowed_read: list[Finding] = []
    allowed_schema: list[Finding] = []
    production_bypass_debt: list[Finding] = []
    nonprod_bypass_debt: list[Finding] = []
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
                production_bypass_debt=production_bypass_debt,
                nonprod_bypass_debt=nonprod_bypass_debt,
            )

        for finding in _construction_findings(tree, display_path):
            _classify_construction_finding(
                finding=finding,
                construction_bypasses=construction_bypasses,
                allowed_authorized=allowed_authorized,
                production_bypass_debt=production_bypass_debt,
                nonprod_bypass_debt=nonprod_bypass_debt,
            )

    return ScanResult(
        files_scanned=files_scanned,
        unexpected_importers=unexpected_importers,
        construction_bypasses=construction_bypasses,
        allowed_authorized=allowed_authorized,
        allowed_read=allowed_read,
        allowed_schema=allowed_schema,
        production_bypass_debt=production_bypass_debt,
        nonprod_bypass_debt=nonprod_bypass_debt,
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
    return relative.as_posix() == "models/rp_story_store.py"


def _relative_posix(file_path: Path, root: Path) -> str:
    return file_path.relative_to(root).as_posix()


def _record_import_findings(tree: ast.AST, display_path: str) -> list[Finding]:
    findings: list[Finding] = []
    module_aliases: set[str] = set()
    has_plain_models_rp_story_store_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "models.rp_story_store":
                for alias in node.names:
                    if alias.name in STORY_RECORD_NAMES:
                        findings.append(_import_finding(display_path, node.lineno, alias.name, "import"))
            elif node.module == "models":
                for alias in node.names:
                    if alias.name == "rp_story_store":
                        module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name != "models.rp_story_store":
                    continue
                if alias.asname:
                    module_aliases.add(alias.asname)
                else:
                    has_plain_models_rp_story_store_import = True

    for node in ast.walk(tree):
        record = _module_record_reference(
            node,
            module_aliases=module_aliases,
            has_plain_models_rp_story_store_import=has_plain_models_rp_story_store_import,
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
            "story-session/runtime-turn records must be imported only through the "
            "six authorized story/runtime sinks"
        ),
    )


def _module_record_reference(
    node: ast.AST,
    *,
    module_aliases: set[str],
    has_plain_models_rp_story_store_import: bool,
) -> str | None:
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr not in STORY_RECORD_NAMES:
        return None
    if isinstance(node.value, ast.Name) and node.value.id in module_aliases:
        return node.attr
    if (
        has_plain_models_rp_story_store_import
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "rp_story_store"
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
        if node.func.id not in STORY_RECORD_NAMES:
            continue
        findings.append(
            Finding(
                code="CONSTRUCTION_BYPASS",
                path=display_path,
                line=node.lineno,
                record=node.func.id,
                bypass_type="construction",
                message=(
                    "story-session/runtime-turn record construction must stay "
                    "inside one of the six authorized story/runtime sinks"
                ),
            )
        )
    return findings


def _classify_import_finding(
    *,
    finding: Finding,
    unexpected_importers: list[Finding],
    allowed_authorized: list[Finding],
    allowed_read: list[Finding],
    allowed_schema: list[Finding],
    production_bypass_debt: list[Finding],
    nonprod_bypass_debt: list[Finding],
) -> None:
    if finding.path in AUTHORIZED:
        allowed_authorized.append(_replace_code(finding, "AUTHORIZED_AGGREGATE"))
    elif finding.path in ALLOWED_READ:
        allowed_read.append(_replace_code(finding, "ALLOWED_READ"))
    elif finding.path in ALLOWED_SCHEMA:
        allowed_schema.append(_replace_code(finding, "ALLOWED_SCHEMA"))
    elif finding.path in PRODUCTION_BYPASS_DEBT:
        production_bypass_debt.append(_replace_code(finding, "PRODUCTION_BYPASS_DEBT"))
    elif finding.path in NONPROD_BYPASS_DEBT:
        nonprod_bypass_debt.append(_replace_code(finding, "NONPROD_BYPASS_DEBT"))
    else:
        unexpected_importers.append(finding)


def _classify_construction_finding(
    *,
    finding: Finding,
    construction_bypasses: list[Finding],
    allowed_authorized: list[Finding],
    production_bypass_debt: list[Finding],
    nonprod_bypass_debt: list[Finding],
) -> None:
    if finding.path in AUTHORIZED:
        allowed_authorized.append(_replace_code(finding, "AUTHORIZED_AGGREGATE"))
    elif finding.path in PRODUCTION_BYPASS_DEBT:
        production_bypass_debt.append(_replace_code(finding, "PRODUCTION_BYPASS_DEBT"))
    elif finding.path in NONPROD_BYPASS_DEBT:
        nonprod_bypass_debt.append(_replace_code(finding, "NONPROD_BYPASS_DEBT"))
    else:
        construction_bypasses.append(finding)


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
        "StorySession/RuntimeTurn write boundary lint",
        f"files scanned: {result.files_scanned}",
        f"unexpected-importer(hard): {len(result.unexpected_importers)}",
        f"construction-bypass(hard): {len(result.construction_bypasses)}",
        f"allowed-authorized: {len(_paths_with_findings(result.allowed_authorized))} files",
        f"allowed-read: {len(_paths_with_findings(result.allowed_read))} files",
        f"allowed-schema: {len(_paths_with_findings(result.allowed_schema))} files",
        f"production-bypass-debt: {len(_paths_with_findings(result.production_bypass_debt))} files",
        f"nonprod-bypass-debt: {len(_paths_with_findings(result.nonprod_bypass_debt))} files",
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

    lines.extend(_format_file_category("allowed-read", result.allowed_read))
    lines.extend(
        _format_file_category(
            "allowed-schema (DDL/metadata only; no row writes)",
            result.allowed_schema,
        )
    )
    lines.extend(
        _format_file_category(
            "production-bypass-debt (visible production field-write debt)",
            result.production_bypass_debt,
        )
    )
    lines.extend(
        _format_file_category(
            "nonprod-bypass-debt (seed/eval; lower priority)",
            result.nonprod_bypass_debt,
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
    result = scan_story_session_write_boundary(backend_root=args.backend_root)
    print(format_report(result))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
