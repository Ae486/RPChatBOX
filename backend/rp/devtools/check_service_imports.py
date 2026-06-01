"""Enforce RP services import-shape contracts.

The RP services organization contract is partly about dependency shape and
partly about source spelling. Generic import-graph tools can tell that module A
depends on module B, but they cannot tell whether the same edge was written as a
same-directory relative import or as a longer absolute path. This checker keeps
those project-specific rules explicit and self-contained.

Hard failures are limited to mechanically safe zero-baseline rules. Cross-domain
absolute imports and facade-bypass candidates are advisory so T26 does not
rewrite future T6 decomposition work or invent facade semantics prematurely.
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
DEFAULT_SERVICE_ROOT = CHECKER_PATH.parents[1] / "services"
SERVICE_PACKAGE = ("rp", "services")
FACADE_CANDIDATE_DOMAINS = frozenset({"memory", "retrieval", "proposal", "runtime"})
PUBLIC_SURFACE_MODULES = {
    "memory": frozenset({"os_service"}),
    "retrieval": frozenset({"broker"}),
    "proposal": frozenset({"apply_service", "service"}),
    "runtime": frozenset({"read_manifest_service"}),
}
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
class ServiceDomainMap:
    """Actual domain/module inventory under backend/rp/services."""

    service_root: Path
    domains: frozenset[str]
    modules_by_domain: dict[str, frozenset[str]]

    def has_domain(self, domain: str | None) -> bool:
        return domain in self.domains if domain is not None else False

    def has_module(self, domain: str | None, module: str | None) -> bool:
        if domain is None or module is None:
            return False
        return module in self.modules_by_domain.get(domain, frozenset())


@dataclass(frozen=True)
class ImporterContext:
    """Importer's file/package position, derived without importing project code."""

    file_path: Path
    display_path: str
    module_parts: tuple[str, ...]
    package_parts: tuple[str, ...]
    service_domain: str | None

    @property
    def in_services(self) -> bool:
        return self.service_domain is not None


@dataclass(frozen=True)
class ServiceReference:
    """A parsed reference to rp.services, valid or invalid."""

    parts: tuple[str, ...]
    domain: str | None
    module: str | None

    @property
    def dotted(self) -> str:
        return ".".join(self.parts)


@dataclass(frozen=True)
class ImportRecord:
    """One import target observed in a Python file."""

    importer: ImporterContext
    line: int
    module_parts: tuple[str, ...]
    imported_names: tuple[str, ...]
    text: str
    is_relative: bool
    level: int


@dataclass(frozen=True)
class Finding:
    """Hard-fail lint violation."""

    code: str
    path: str
    line: int
    message: str
    import_text: str

    @property
    def display(self) -> str:
        return f"{self.path}:{self.line}: {self.code}: {self.message}"


@dataclass(frozen=True)
class AdvisoryFinding:
    """Report-only lint finding."""

    code: str
    path: str
    line: int
    target_domain: str
    target_module: str
    import_text: str


@dataclass(frozen=True)
class ScanResult:
    files_scanned: int
    hard_findings: list[Finding]
    advisory_findings: list[AdvisoryFinding]
    parse_errors: list[Finding]

    @property
    def errors(self) -> list[Finding]:
        return [*self.parse_errors, *self.hard_findings]


def build_service_domain_map(service_root: Path = DEFAULT_SERVICE_ROOT) -> ServiceDomainMap:
    modules_by_domain: dict[str, set[str]] = defaultdict(set)
    domains: set[str] = set()

    if not service_root.exists():
        return ServiceDomainMap(
            service_root=service_root,
            domains=frozenset(),
            modules_by_domain={},
        )

    for child in sorted(service_root.iterdir()):
        if child.is_dir() and not child.name.startswith("__"):
            domains.add(child.name)

    for file_path in _iter_python_files(service_root):
        relative = file_path.relative_to(service_root)
        if len(relative.parts) < 2 or relative.name == "__init__.py":
            continue
        domain = relative.parts[0]
        if domain not in domains:
            continue
        module = ".".join(relative.with_suffix("").parts[1:])
        modules_by_domain[domain].add(module)

    return ServiceDomainMap(
        service_root=service_root,
        domains=frozenset(domains),
        modules_by_domain={
            domain: frozenset(modules)
            for domain, modules in sorted(modules_by_domain.items())
        },
    )


def scan_backend_imports(
    backend_root: Path = DEFAULT_BACKEND_ROOT,
    service_root: Path = DEFAULT_SERVICE_ROOT,
    *,
    strict_facade_bypass: bool = False,
) -> ScanResult:
    domain_map = build_service_domain_map(service_root)
    hard_findings: list[Finding] = []
    advisory_findings: list[AdvisoryFinding] = []
    parse_errors: list[Finding] = []
    files_scanned = 0

    for file_path in _iter_python_files(backend_root):
        files_scanned += 1
        importer = _importer_context(
            file_path=file_path,
            backend_root=backend_root,
            service_root=service_root,
            domains=domain_map.domains,
        )
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except SyntaxError as exc:
            parse_errors.append(
                Finding(
                    code="PARSE_ERROR",
                    path=importer.display_path,
                    line=exc.lineno or 0,
                    message=f"syntax error: {exc.msg}",
                    import_text="",
                )
            )
            continue

        for record in _iter_import_records(tree, importer):
            _classify_import(
                record=record,
                domain_map=domain_map,
                hard_findings=hard_findings,
                advisory_findings=advisory_findings,
            )

    if strict_facade_bypass:
        hard_findings.extend(
            Finding(
                code="FACADE_BYPASS",
                path=finding.path,
                line=finding.line,
                message=(
                    "cross-domain service import is a facade-bypass candidate; "
                    "strict mode requires a public-surface policy"
                ),
                import_text=finding.import_text,
            )
            for finding in advisory_findings
            if finding.code == "FACADE_BYPASS_CANDIDATE"
        )

    return ScanResult(
        files_scanned=files_scanned,
        hard_findings=hard_findings,
        advisory_findings=advisory_findings,
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


def _importer_context(
    *,
    file_path: Path,
    backend_root: Path,
    service_root: Path,
    domains: frozenset[str],
) -> ImporterContext:
    module_parts = _module_parts_for_file(file_path, backend_root)
    package_parts = module_parts if file_path.name == "__init__.py" else module_parts[:-1]
    display_path = _relative_posix(file_path, backend_root)
    service_domain = _service_domain_for_file(file_path, service_root, domains)
    return ImporterContext(
        file_path=file_path,
        display_path=display_path,
        module_parts=module_parts,
        package_parts=package_parts,
        service_domain=service_domain,
    )


def _module_parts_for_file(file_path: Path, backend_root: Path) -> tuple[str, ...]:
    relative = file_path.relative_to(backend_root)
    parts = relative.with_suffix("").parts
    if relative.name == "__init__.py":
        parts = parts[:-1]
    return tuple(parts)


def _service_domain_for_file(
    file_path: Path,
    service_root: Path,
    domains: frozenset[str],
) -> str | None:
    try:
        relative = file_path.relative_to(service_root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    domain = relative.parts[0]
    if domain in domains:
        return domain
    return None


def _relative_posix(file_path: Path, root: Path) -> str:
    return file_path.relative_to(root).as_posix()


def _iter_import_records(tree: ast.AST, importer: ImporterContext) -> Iterable[ImportRecord]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module_parts = _resolve_import_from(node, importer.package_parts)
            imported_names = tuple(alias.name for alias in node.names)
            yield ImportRecord(
                importer=importer,
                line=node.lineno,
                module_parts=module_parts,
                imported_names=imported_names,
                text=_format_import_from(node),
                is_relative=node.level > 0,
                level=node.level,
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield ImportRecord(
                    importer=importer,
                    line=node.lineno,
                    module_parts=tuple(alias.name.split(".")),
                    imported_names=(alias.name,),
                    text=f"import {alias.name}",
                    is_relative=False,
                    level=0,
                )


def _resolve_import_from(
    node: ast.ImportFrom,
    package_parts: tuple[str, ...],
) -> tuple[str, ...]:
    module_parts = tuple(node.module.split(".")) if node.module else ()
    if node.level == 0:
        return module_parts

    keep_count = len(package_parts) - (node.level - 1)
    if keep_count < 0:
        return module_parts
    return (*package_parts[:keep_count], *module_parts)


def _format_import_from(node: ast.ImportFrom) -> str:
    prefix = "." * node.level
    module = node.module or ""
    names = ", ".join(alias.name for alias in node.names)
    return f"from {prefix}{module} import {names}".strip()


def _classify_import(
    *,
    record: ImportRecord,
    domain_map: ServiceDomainMap,
    hard_findings: list[Finding],
    advisory_findings: list[AdvisoryFinding],
) -> None:
    reference = _service_reference(record.module_parts)

    if _imports_rp_services_package(record):
        hard_findings.append(
            _finding(
                record,
                "NON_CONCRETE_SERVICE_IMPORT",
                "rp.services import must target a concrete current service module",
            )
        )
        return

    if record.importer.in_services:
        _classify_service_internal_import(
            record=record,
            reference=reference,
            domain_map=domain_map,
            hard_findings=hard_findings,
            advisory_findings=advisory_findings,
        )
        return

    _classify_service_external_import(
        record=record,
        reference=reference,
        domain_map=domain_map,
        hard_findings=hard_findings,
        advisory_findings=advisory_findings,
    )


def _classify_service_internal_import(
    *,
    record: ImportRecord,
    reference: ServiceReference | None,
    domain_map: ServiceDomainMap,
    hard_findings: list[Finding],
    advisory_findings: list[AdvisoryFinding],
) -> None:
    if record.is_relative:
        if reference is None:
            if record.level >= 2:
                hard_findings.append(
                    _finding(
                        record,
                        "ROOT_RELATIVE_SERVICE_IMPORT",
                        "service relative import escapes rp.services domains",
                    )
                )
            return

        if not domain_map.has_domain(reference.domain):
            hard_findings.append(
                _finding(
                    record,
                    "ROOT_RELATIVE_SERVICE_IMPORT",
                    "from ..<root_module> is not a service domain import",
                )
            )
            return

        if reference.domain == record.importer.service_domain and reference.module is None:
            hard_findings.append(
                _finding(
                    record,
                    "NON_CONCRETE_SERVICE_IMPORT",
                    "service import must target a concrete current service module",
                )
            )
            return

        if not domain_map.has_module(reference.domain, reference.module):
            hard_findings.append(
                _finding(
                    record,
                    "STALE_RELATIVE_SERVICE_IMPORT",
                    "relative service import points to no current service module",
                )
            )
            return
        _maybe_add_facade_candidate(record, reference, advisory_findings)
        return

    if reference is None:
        return

    if not _validate_concrete_service_reference(
        record=record,
        reference=reference,
        domain_map=domain_map,
        hard_findings=hard_findings,
    ):
        return

    if reference.domain == record.importer.service_domain:
        hard_findings.append(
            _finding(
                record,
                "SAME_SUBDIR_ABSOLUTE_IMPORT",
                "same-service-domain peer import must use from .<peer> import X",
            )
        )
        return

    advisory_findings.append(
        AdvisoryFinding(
            code="CROSS_DOMAIN_ABSOLUTE_IMPORT",
            path=record.importer.display_path,
            line=record.line,
            target_domain=reference.domain or "",
            target_module=reference.module or "",
            import_text=record.text,
        )
    )
    _maybe_add_facade_candidate(record, reference, advisory_findings)


def _classify_service_external_import(
    *,
    record: ImportRecord,
    reference: ServiceReference | None,
    domain_map: ServiceDomainMap,
    hard_findings: list[Finding],
    advisory_findings: list[AdvisoryFinding],
) -> None:
    if record.is_relative:
        if reference is not None:
            hard_findings.append(
                _finding(
                    record,
                    "EXTERNAL_RELATIVE_SERVICE_IMPORT",
                    "files outside rp.services must import services via absolute rp.services paths",
                )
            )
        return

    local_reference = _local_service_reference(record.module_parts)
    if local_reference is not None and domain_map.has_domain(local_reference.domain):
        hard_findings.append(
            _finding(
                record,
                "EXTERNAL_NON_ABSOLUTE_SERVICE_IMPORT",
                "files outside rp.services must use rp.services.<domain>.<module>",
            )
        )
        return

    if reference is None:
        return

    if not _validate_concrete_service_reference(
        record=record,
        reference=reference,
        domain_map=domain_map,
        hard_findings=hard_findings,
    ):
        return

    _maybe_add_facade_candidate(record, reference, advisory_findings)


def _service_reference(parts: tuple[str, ...]) -> ServiceReference | None:
    if len(parts) < len(SERVICE_PACKAGE):
        return None
    if parts[: len(SERVICE_PACKAGE)] != SERVICE_PACKAGE:
        return None

    domain = parts[2] if len(parts) >= 3 else None
    module = ".".join(parts[3:]) if len(parts) >= 4 else None
    return ServiceReference(parts=parts, domain=domain, module=module)


def _imports_rp_services_package(record: ImportRecord) -> bool:
    return (
        not record.is_relative
        and record.module_parts == ("rp",)
        and "services" in record.imported_names
    )


def _local_service_reference(parts: tuple[str, ...]) -> ServiceReference | None:
    if len(parts) < 2 or parts[0] != "services":
        return None
    domain = parts[1]
    module = ".".join(parts[2:]) if len(parts) >= 3 else None
    return ServiceReference(parts=parts, domain=domain, module=module)


def _validate_concrete_service_reference(
    *,
    record: ImportRecord,
    reference: ServiceReference,
    domain_map: ServiceDomainMap,
    hard_findings: list[Finding],
) -> bool:
    if not domain_map.has_domain(reference.domain):
        hard_findings.append(
            _finding(
                record,
                "OLD_SHIM_OR_ROOT_SERVICE_IMPORT",
                "rp.services import does not name a current service domain",
            )
        )
        return False

    if not domain_map.has_module(reference.domain, reference.module):
        hard_findings.append(
            _finding(
                record,
                "NON_CONCRETE_SERVICE_IMPORT",
                "rp.services import must target a concrete current service module",
            )
        )
        return False

    return True


def _maybe_add_facade_candidate(
    record: ImportRecord,
    reference: ServiceReference,
    advisory_findings: list[AdvisoryFinding],
) -> None:
    if reference.domain is None or reference.module is None:
        return
    if reference.domain not in FACADE_CANDIDATE_DOMAINS:
        return
    if reference.domain == record.importer.service_domain:
        return
    if _looks_like_public_surface(reference.domain, reference.module):
        return
    advisory_findings.append(
        AdvisoryFinding(
            code="FACADE_BYPASS_CANDIDATE",
            path=record.importer.display_path,
            line=record.line,
            target_domain=reference.domain,
            target_module=reference.module,
            import_text=record.text,
        )
    )


def _looks_like_public_surface(domain: str, module: str) -> bool:
    if module in PUBLIC_SURFACE_MODULES.get(domain, frozenset()):
        return True
    leaf = module.rsplit(".", maxsplit=1)[-1]
    if leaf.startswith("_"):
        return False
    return leaf.endswith("_facade") or leaf.endswith("_controller")


def _finding(record: ImportRecord, code: str, message: str) -> Finding:
    return Finding(
        code=code,
        path=record.importer.display_path,
        line=record.line,
        message=message,
        import_text=record.text,
    )


def format_report(result: ScanResult, *, verbose_advisory: bool = False) -> str:
    hard_counts = Counter(finding.code for finding in result.hard_findings)
    parse_count = len(result.parse_errors)
    advisory_counts = Counter(finding.code for finding in result.advisory_findings)

    lines = [
        "RP service import lint",
        f"files scanned: {result.files_scanned}",
        f"hard violations: {len(result.hard_findings)}",
        f"parse errors: {parse_count}",
        (
            "advisory: "
            f"cross-domain-absolute={advisory_counts['CROSS_DOMAIN_ABSOLUTE_IMPORT']} "
            f"facade-bypass-candidates={advisory_counts['FACADE_BYPASS_CANDIDATE']}"
        ),
    ]

    if hard_counts:
        lines.append("hard violation counts:")
        for code, count in sorted(hard_counts.items()):
            lines.append(f"  - {code}: {count}")

    advisory_lines = _format_advisory(result.advisory_findings, verbose=verbose_advisory)
    if advisory_lines:
        lines.extend(["", *advisory_lines])

    if result.errors:
        lines.append("")
        lines.append("ERRORS:")
        lines.extend(f"- {finding.display} ({finding.import_text})" for finding in result.errors)
        lines.append("")
        lines.append("result: FAIL")
    else:
        lines.append("")
        lines.append("result: PASS")

    return "\n".join(lines)


def _format_advisory(findings: list[AdvisoryFinding], *, verbose: bool) -> list[str]:
    if not findings:
        return []

    lines = ["advisory report-only imports:"]
    lines.extend(
        _format_module_summary(
            findings,
            code="CROSS_DOMAIN_ABSOLUTE_IMPORT",
            verbose=verbose,
        )
    )
    lines.extend(_format_facade_summary(findings, verbose=verbose))

    return lines


def _format_module_summary(
    findings: list[AdvisoryFinding],
    *,
    code: str,
    verbose: bool,
) -> list[str]:
    by_domain_module: Counter[tuple[str, str]] = Counter(
        (finding.target_domain, finding.target_module)
        for finding in findings
        if finding.code == code
    )
    if not by_domain_module:
        return []

    lines = [f"{code}:"]
    limit = len(by_domain_module) if verbose else 12
    for (domain, module), count in by_domain_module.most_common(limit):
        lines.append(f"  - {domain}.{module}: {count}")
    hidden = len(by_domain_module) - limit
    if hidden > 0:
        lines.append(f"  - ... {hidden} more target modules")
    return lines


def _format_facade_summary(findings: list[AdvisoryFinding], *, verbose: bool) -> list[str]:
    by_domain: dict[str, Counter[str]] = defaultdict(Counter)
    for finding in findings:
        if finding.code == "FACADE_BYPASS_CANDIDATE":
            by_domain[finding.target_domain][finding.target_module] += 1

    if not by_domain:
        return []

    lines = ["FACADE_BYPASS_CANDIDATE:"]
    for domain in sorted(by_domain):
        module_counts = by_domain[domain]
        total = sum(module_counts.values())
        lines.append(f"  - {domain}: {total}")
        limit = len(module_counts) if verbose else 5
        for module, count in module_counts.most_common(limit):
            lines.append(f"    - {module}: {count}")
        hidden = len(module_counts) - limit
        if hidden > 0:
            lines.append(f"    - ... {hidden} more target modules")
    return lines


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=DEFAULT_BACKEND_ROOT,
        help="Backend tree to scan. Defaults to backend/.",
    )
    parser.add_argument(
        "--services-root",
        type=Path,
        default=DEFAULT_SERVICE_ROOT,
        help="RP services tree. Defaults to backend/rp/services.",
    )
    parser.add_argument(
        "--strict-facade-bypass",
        action="store_true",
        help="Promote facade-bypass candidates to hard failures.",
    )
    parser.add_argument(
        "--verbose-advisory",
        action="store_true",
        help="Print every advisory target module instead of the top few.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = scan_backend_imports(
        backend_root=args.backend_root,
        service_root=args.services_root,
        strict_facade_bypass=args.strict_facade_bypass,
    )
    print(format_report(result, verbose_advisory=args.verbose_advisory))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
