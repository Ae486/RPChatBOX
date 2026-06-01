"""Enforce RP service file/function/class size ratchets.

The RP services organization contract defines soft and hard size limits for
service files, functions, and classes. This checker intentionally implements the
contract directly instead of leaning on generic lint rules whose metrics differ
from the contract:

* file size is the physical text line count;
* function and class size is the AST ``lineno`` to ``end_lineno`` span,
  inclusive;
* current hard offenders are allowed only at the exact size captured in the
  baseline, so any new hard offender, growth, or unclaimed shrink fails.

Soft offenders are advisory at T8 landing time. They are reported so future
decomposition work can prioritize them, but they do not block the hook.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SizeThresholds:
    """Contract thresholds for the three service-size dimensions."""

    file_soft: int = 500
    file_hard: int = 1000
    function_soft: int = 50
    function_hard: int = 100
    class_soft: int = 300
    class_hard: int = 600

    def soft_for(self, kind: str) -> int:
        return {
            "file": self.file_soft,
            "function": self.function_soft,
            "class": self.class_soft,
        }[kind]

    def hard_for(self, kind: str) -> int:
        return {
            "file": self.file_hard,
            "function": self.function_hard,
            "class": self.class_hard,
        }[kind]

    def as_mapping(self) -> dict[str, dict[str, int]]:
        return {
            "file": {"soft": self.file_soft, "hard": self.file_hard},
            "function": {"soft": self.function_soft, "hard": self.function_hard},
            "class": {"soft": self.class_soft, "hard": self.class_hard},
        }


DEFAULT_THRESHOLDS = SizeThresholds()
CHECKER_PATH = Path(__file__).resolve()
REPO_ROOT = CHECKER_PATH.parents[3]
DEFAULT_SERVICE_ROOT = CHECKER_PATH.parents[1] / "services"
DEFAULT_BASELINE_PATH = CHECKER_PATH.with_name("service_size_baseline.json")
BASELINE_SCHEMA_VERSION = 1
VALID_KINDS = {"file", "function", "class"}


@dataclass(frozen=True)
class Finding:
    """A file/function/class whose measured size reached the soft limit."""

    kind: str
    path: str
    symbol: str | None
    lines: int
    soft_limit: int
    hard_limit: int

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.path, self.symbol or "")

    @property
    def is_hard(self) -> bool:
        return self.lines >= self.hard_limit

    @property
    def display(self) -> str:
        if self.symbol:
            return f"{self.path}::{self.symbol}"
        return self.path


@dataclass(frozen=True)
class BaselineEntry:
    """A grandfathered hard offender and its ratchet line count."""

    kind: str
    path: str
    symbol: str | None
    lines: int
    reason: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.path, self.symbol or "")

    @property
    def display(self) -> str:
        if self.symbol:
            return f"{self.path}::{self.symbol}"
        return self.path


@dataclass(frozen=True)
class ScanResult:
    findings: list[Finding]
    parse_errors: list[str]
    files_scanned: int


@dataclass(frozen=True)
class CheckResult:
    scan: ScanResult
    baseline_entries: dict[tuple[str, str, str], BaselineEntry]
    baseline_errors: list[str]
    policy_errors: list[str]
    service_root: Path
    baseline_path: Path

    @property
    def errors(self) -> list[str]:
        return [*self.scan.parse_errors, *self.baseline_errors, *self.policy_errors]

    @property
    def hard_findings(self) -> list[Finding]:
        return [finding for finding in self.scan.findings if finding.is_hard]

    @property
    def soft_findings(self) -> list[Finding]:
        return [finding for finding in self.scan.findings if not finding.is_hard]

    def hard_counts(self) -> Counter[str]:
        return Counter(finding.kind for finding in self.hard_findings)

    def soft_counts(self) -> Counter[str]:
        return Counter(finding.kind for finding in self.soft_findings)

    def baseline_counts(self) -> Counter[str]:
        return Counter(entry.kind for entry in self.baseline_entries.values())


class _AstSizeVisitor(ast.NodeVisitor):
    """Collect function/class findings while preserving qualified names."""

    def __init__(
        self,
        *,
        relative_path: str,
        thresholds: SizeThresholds,
        findings: list[Finding],
    ) -> None:
        self._relative_path = relative_path
        self._thresholds = thresholds
        self._findings = findings
        self._scope: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        symbol = self._qualified_name(node.name)
        lines = _node_span(node)
        self._add_finding_if_needed("class", symbol, lines)
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        symbol = self._qualified_name(node.name)
        lines = _node_span(node)
        self._add_finding_if_needed("function", symbol, lines)
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def _qualified_name(self, name: str) -> str:
        if not self._scope:
            return name
        return ".".join([*self._scope, name])

    def _add_finding_if_needed(self, kind: str, symbol: str, lines: int) -> None:
        soft_limit = self._thresholds.soft_for(kind)
        if lines < soft_limit:
            return
        self._findings.append(
            Finding(
                kind=kind,
                path=self._relative_path,
                symbol=symbol,
                lines=lines,
                soft_limit=soft_limit,
                hard_limit=self._thresholds.hard_for(kind),
            )
        )


def _node_span(node: ast.AST) -> int:
    return int(node.end_lineno) - int(node.lineno) + 1


def _relative_posix(file_path: Path, root: Path) -> str:
    return file_path.relative_to(root).as_posix()


def count_text_lines(text: str) -> int:
    """Return the physical line count used for service-file size checks."""

    if not text:
        return 0
    return len(text.splitlines())


def scan_services(
    service_root: Path = DEFAULT_SERVICE_ROOT,
    *,
    thresholds: SizeThresholds = DEFAULT_THRESHOLDS,
) -> ScanResult:
    findings: list[Finding] = []
    parse_errors: list[str] = []
    files = sorted(service_root.rglob("*.py"))

    for file_path in files:
        relative_path = _relative_posix(file_path, service_root)
        text = file_path.read_text(encoding="utf-8")
        file_lines = count_text_lines(text)
        if file_lines >= thresholds.file_soft:
            findings.append(
                Finding(
                    kind="file",
                    path=relative_path,
                    symbol=None,
                    lines=file_lines,
                    soft_limit=thresholds.file_soft,
                    hard_limit=thresholds.file_hard,
                )
            )
        try:
            tree = ast.parse(text, filename=str(file_path))
        except SyntaxError as exc:
            parse_errors.append(
                f"{relative_path}: syntax error at line {exc.lineno}, column {exc.offset}: "
                f"{exc.msg}"
            )
            continue
        _AstSizeVisitor(
            relative_path=relative_path,
            thresholds=thresholds,
            findings=findings,
        ).visit(tree)

    return ScanResult(findings=findings, parse_errors=parse_errors, files_scanned=len(files))


def load_baseline(
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    *,
    thresholds: SizeThresholds = DEFAULT_THRESHOLDS,
) -> tuple[dict[tuple[str, str, str], BaselineEntry], list[str]]:
    if not baseline_path.exists():
        return {}, [f"baseline file is missing: {baseline_path}"]

    try:
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"baseline JSON is invalid: {baseline_path}: {exc}"]

    errors: list[str] = []
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        errors.append(
            "baseline schema_version must be "
            f"{BASELINE_SCHEMA_VERSION}, got {payload.get('schema_version')!r}"
        )
    if payload.get("thresholds") != thresholds.as_mapping():
        errors.append("baseline thresholds do not match the checker contract thresholds")

    raw_entries = payload.get("hard_allowlist")
    if not isinstance(raw_entries, list):
        errors.append("baseline hard_allowlist must be a list")
        return {}, errors

    entries: dict[tuple[str, str, str], BaselineEntry] = {}
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            errors.append(f"baseline entry #{index} must be an object")
            continue
        entry = _parse_baseline_entry(raw_entry, index, errors)
        if entry is None:
            continue
        if entry.key in entries:
            errors.append(f"duplicate baseline entry for {entry.display}")
            continue
        entries[entry.key] = entry

    return entries, errors


def _parse_baseline_entry(
    raw_entry: dict[str, Any],
    index: int,
    errors: list[str],
) -> BaselineEntry | None:
    kind = raw_entry.get("kind")
    path = raw_entry.get("path")
    symbol = raw_entry.get("symbol")
    lines = raw_entry.get("lines")
    reason = raw_entry.get("reason")

    if kind not in VALID_KINDS:
        errors.append(f"baseline entry #{index} has invalid kind: {kind!r}")
        return None
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("../"):
        errors.append(f"baseline entry #{index} has invalid relative path: {path!r}")
        return None
    if kind == "file":
        if symbol is not None:
            errors.append(f"baseline file entry #{index} must use symbol=null")
            return None
    elif not isinstance(symbol, str) or not symbol:
        errors.append(f"baseline {kind} entry #{index} must include a symbol")
        return None
    if not isinstance(lines, int) or lines <= 0:
        errors.append(f"baseline entry #{index} has invalid lines: {lines!r}")
        return None
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"baseline entry #{index} must include a non-empty reason")
        return None

    return BaselineEntry(
        kind=kind,
        path=path,
        symbol=symbol,
        lines=lines,
        reason=reason.strip(),
    )


def check_service_sizes(
    service_root: Path = DEFAULT_SERVICE_ROOT,
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    *,
    thresholds: SizeThresholds = DEFAULT_THRESHOLDS,
) -> CheckResult:
    scan = scan_services(service_root, thresholds=thresholds)
    baseline_entries, baseline_errors = load_baseline(baseline_path, thresholds=thresholds)
    policy_errors = _compare_hard_findings_to_baseline(
        hard_findings=[finding for finding in scan.findings if finding.is_hard],
        baseline_entries=baseline_entries,
        baseline_path=baseline_path,
    )
    return CheckResult(
        scan=scan,
        baseline_entries=baseline_entries,
        baseline_errors=baseline_errors,
        policy_errors=policy_errors,
        service_root=service_root,
        baseline_path=baseline_path,
    )


def _compare_hard_findings_to_baseline(
    *,
    hard_findings: list[Finding],
    baseline_entries: dict[tuple[str, str, str], BaselineEntry],
    baseline_path: Path,
) -> list[str]:
    errors: list[str] = []
    current_by_key: dict[tuple[str, str, str], Finding] = {}

    for finding in hard_findings:
        if finding.key in current_by_key:
            errors.append(
                "duplicate hard finding key; baseline cannot distinguish "
                f"{finding.display}. Use a more specific checker key before enforcing."
            )
            continue
        current_by_key[finding.key] = finding

    for key, entry in baseline_entries.items():
        current = current_by_key.get(key)
        if current is None:
            errors.append(
                "stale hard baseline entry: "
                f"{entry.display} is no longer a hard offender; remove it from "
                f"{baseline_path.as_posix()}"
            )
            continue
        if current.lines > entry.lines:
            errors.append(
                "hard service-size baseline grew: "
                f"{current.display} is {current.lines} lines, baseline allows {entry.lines}. "
                "Split/refactor it or update the baseline only with an explicit reason."
            )
        elif current.lines < entry.lines:
            errors.append(
                "hard service-size baseline can shrink: "
                f"{current.display} is {current.lines} lines, baseline records {entry.lines}. "
                "Update the baseline downward, or remove the entry if it is below the hard limit."
            )

    for key, finding in current_by_key.items():
        if key in baseline_entries:
            continue
        errors.append(
            "new hard service-size offender: "
            f"{finding.display} is {finding.lines} lines "
            f"(hard limit {finding.hard_limit}). Split/refactor it or add a justified "
            "baseline entry."
        )

    return errors


def format_report(result: CheckResult, *, verbose_soft: bool = False) -> str:
    hard_counts = result.hard_counts()
    soft_counts = result.soft_counts()
    baseline_counts = result.baseline_counts()

    lines = [
        "RP service size lint",
        f"scope: {result.service_root.as_posix()}",
        f"baseline: {result.baseline_path.as_posix()}",
        f"files scanned: {result.scan.files_scanned}",
        (
            "hard offenders: "
            f"file={hard_counts['file']} "
            f"function={hard_counts['function']} "
            f"class={hard_counts['class']}"
        ),
        (
            "hard baseline: "
            f"file={baseline_counts['file']} "
            f"function={baseline_counts['function']} "
            f"class={baseline_counts['class']}"
        ),
        (
            "soft advisory: "
            f"file={soft_counts['file']} "
            f"function={soft_counts['function']} "
            f"class={soft_counts['class']}"
        ),
    ]

    if result.soft_findings:
        lines.extend(_format_soft_advisory(result.soft_findings, verbose=verbose_soft))

    if result.errors:
        lines.append("")
        lines.append("ERRORS:")
        lines.extend(f"- {error}" for error in result.errors)
        lines.append("")
        lines.append("result: FAIL")
    else:
        lines.append("")
        lines.append("result: PASS")

    return "\n".join(lines)


def _format_soft_advisory(findings: list[Finding], *, verbose: bool) -> list[str]:
    max_items_per_kind = None if verbose else 5
    lines = ["", "soft advisory largest offenders (non-blocking):"]
    for kind in ("file", "function", "class"):
        kind_findings = sorted(
            [finding for finding in findings if finding.kind == kind],
            key=lambda finding: (-finding.lines, finding.display),
        )
        if not kind_findings:
            continue
        shown = kind_findings
        if max_items_per_kind is not None:
            shown = kind_findings[:max_items_per_kind]
        lines.append(f"{kind}:")
        for finding in shown:
            lines.append(
                f"  - {finding.lines} lines "
                f"(soft {finding.soft_limit}, hard {finding.hard_limit}) "
                f"{finding.display}"
            )
        hidden_count = len(kind_findings) - len(shown)
        if hidden_count > 0:
            lines.append(f"  - ... {hidden_count} more {kind} soft offenders")
    return lines


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--services-root",
        type=Path,
        default=DEFAULT_SERVICE_ROOT,
        help="Service tree to scan. Defaults to backend/rp/services.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="Hard-offender baseline JSON path.",
    )
    parser.add_argument(
        "--verbose-soft",
        action="store_true",
        help="Print every soft advisory offender instead of the largest few per kind.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = check_service_sizes(
        service_root=args.services_root,
        baseline_path=args.baseline,
    )
    print(format_report(result, verbose_soft=args.verbose_soft))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
