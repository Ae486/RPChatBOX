"""Enforce the rp.agent_runtime kernel/setup/story import boundary.

The ``rp.agent_runtime`` package is physically split into shared ``kernel``,
setup-only ``setup``, and story-only ``story`` implementation zones. Root-level
modules may exist only as compatibility shims; this lint scans the real
implementation zones so future maintenance cannot wire setup runtime code into
the story harness path, or let the shared kernel depend on a side-specific
layer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CHECKER_PATH = Path(__file__).resolve()
DEFAULT_BACKEND_ROOT = CHECKER_PATH.parents[2]
ZoneName = Literal["kernel", "setup", "story"]

ZONES: dict[str, ZoneName] = {
    "kernel/state.py": "kernel",
    "kernel/graph.py": "kernel",
    "kernel/runtime_tool_contracts.py": "kernel",
    "setup/contracts.py": "setup",
    "setup/executor.py": "setup",
    "setup/policies.py": "setup",
    "setup/adapters.py": "setup",
    "setup/profiles.py": "setup",
    "setup/events.py": "setup",
    "setup/tools.py": "setup",
    "setup/prompts/__init__.py": "setup",
    "setup/prompts/compact.py": "setup",
    "setup/prompts/main.py": "setup",
    "setup/prompts/stages.py": "setup",
    "setup/prompts/tools.py": "setup",
    "setup/skill_packs/__init__.py": "setup",
    "setup/skill_packs/registry.py": "setup",
    "story/story_harness.py": "story",
}

LEGACY_MODULE_ZONES: dict[str, ZoneName] = {
    "state": "kernel",
    "graph": "kernel",
    "runtime_tool_contracts": "kernel",
    "contracts": "setup",
    "executor": "setup",
    "policies": "setup",
    "adapters": "setup",
    "profiles": "setup",
    "events": "setup",
    "tools": "setup",
    "story_harness": "story",
}

KERNEL_LEAK = "KERNEL_LEAK"
SETUP_TO_STORY = "SETUP_TO_STORY"
STORY_TO_SETUP = "STORY_TO_SETUP"


@dataclass(frozen=True)
class ImportViolation:
    """Lint finding for an agent-runtime zone-boundary import."""

    code: str
    path: str
    line: int
    imported: str
    message: str

    @property
    def display(self) -> str:
        return f"{self.path}:{self.line}: {self.code}: {self.message}"


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning the agent-runtime zone-boundary imports."""

    files_scanned: int
    kernel_leaks: list[ImportViolation]
    setup_to_story: list[ImportViolation]
    story_to_setup: list[ImportViolation]

    @property
    def errors(self) -> list[ImportViolation]:
        return [*self.kernel_leaks, *self.setup_to_story, *self.story_to_setup]


@dataclass(frozen=True)
class ImportReference:
    """Normalized import target found in one Python file."""

    path: str
    line: int
    imported: str


def scan_agent_runtime_zone_boundary(*, backend_root: Path) -> ScanResult:
    """Scan ``rp.agent_runtime`` and setup services for zone-boundary leaks."""

    kernel_leaks: list[ImportViolation] = []
    setup_to_story: list[ImportViolation] = []
    story_to_setup: list[ImportViolation] = []
    scanned_paths: set[Path] = set()
    files_scanned = 0

    agent_runtime_root = backend_root / "rp" / "agent_runtime"
    for relative_path, zone in sorted(ZONES.items()):
        file_path = agent_runtime_root / relative_path
        if not file_path.exists():
            continue
        scanned_paths.add(file_path)
        files_scanned += 1
        references = _import_references(file_path, backend_root=backend_root)
        if zone == "kernel":
            kernel_leaks.extend(_kernel_leaks(references))
        elif zone == "setup":
            setup_to_story.extend(_setup_to_story(references))
        elif zone == "story":
            story_to_setup.extend(_story_to_setup(references))

    setup_runtime_root = agent_runtime_root / "setup"
    for file_path in _iter_python_files(setup_runtime_root):
        if file_path in scanned_paths:
            continue
        scanned_paths.add(file_path)
        files_scanned += 1
        references = _import_references(file_path, backend_root=backend_root)
        setup_to_story.extend(_setup_to_story(references))

    setup_services_root = backend_root / "rp" / "services" / "setup_agent"
    for file_path in _iter_python_files(setup_services_root):
        files_scanned += 1
        references = _import_references(file_path, backend_root=backend_root)
        setup_to_story.extend(_setup_to_story(references))

    return ScanResult(
        files_scanned=files_scanned,
        kernel_leaks=kernel_leaks,
        setup_to_story=setup_to_story,
        story_to_setup=story_to_setup,
    )


def _iter_python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.py"))


def _import_references(file_path: Path, *, backend_root: Path) -> list[ImportReference]:
    display_path = _relative_posix(file_path, backend_root)
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    references: list[ImportReference] = []
    current_package = _package_name(file_path, backend_root=backend_root)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                references.append(
                    ImportReference(
                        path=display_path,
                        line=node.lineno,
                        imported=alias.name,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module_name = _resolve_import_from(node, current_package=current_package)
            references.extend(
                ImportReference(path=display_path, line=node.lineno, imported=target)
                for target in _import_from_targets(module_name, node)
            )

    return references


def _package_name(file_path: Path, *, backend_root: Path) -> str:
    relative = file_path.relative_to(backend_root).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1])
    return ".".join(parts[:-1])


def _resolve_import_from(node: ast.ImportFrom, *, current_package: str) -> str:
    if node.level == 0:
        return node.module or ""

    package_parts = current_package.split(".") if current_package else []
    prefix_len = max(0, len(package_parts) - node.level + 1)
    prefix = ".".join(package_parts[:prefix_len])
    if node.module:
        return f"{prefix}.{node.module}" if prefix else node.module
    return prefix


def _import_from_targets(module_name: str, node: ast.ImportFrom) -> list[str]:
    if not module_name:
        return []

    # ``from rp.agent_runtime.story import story_harness`` names the concrete
    # module only through the imported alias, so resolve package-level forms as
    # the concrete child module. For normal ``from x.y import Symbol`` imports,
    # the owning module ``x.y`` is the boundary-relevant target.
    if module_name in {
        "rp.agent_runtime",
        "rp.agent_runtime.kernel",
        "rp.agent_runtime.setup",
        "rp.agent_runtime.setup.prompts",
        "rp.agent_runtime.setup.skill_packs",
        "rp.agent_runtime.story",
        "rp.agent_runtime.prompts.setup_agent",
        "rp.agent_runtime.skill_packs",
        "rp.services",
        "rp.models",
    }:
        return [
            f"{module_name}.{alias.name}"
            for alias in node.names
            if alias.name != "*"
        ]
    if node.module is None:
        return [
            f"{module_name}.{alias.name}"
            for alias in node.names
            if alias.name != "*"
        ]
    return [module_name]


def _kernel_leaks(references: list[ImportReference]) -> list[ImportViolation]:
    findings: list[ImportViolation] = []
    for reference in references:
        zone = _agent_runtime_zone(reference.imported)
        if zone in {"setup", "story"}:
            findings.append(
                _violation(
                    code=KERNEL_LEAK,
                    reference=reference,
                    message="kernel files must not import setup/story agent-runtime modules",
                )
            )
        elif _is_rp_service(reference.imported):
            findings.append(
                _violation(
                    code=KERNEL_LEAK,
                    reference=reference,
                    message="kernel files must not import rp.services modules",
                )
            )
        elif _is_setup_model(reference.imported):
            findings.append(
                _violation(
                    code=KERNEL_LEAK,
                    reference=reference,
                    message="kernel files must not import rp.models.setup_agent modules",
                )
            )
    return findings


def _setup_to_story(references: list[ImportReference]) -> list[ImportViolation]:
    findings: list[ImportViolation] = []
    for reference in references:
        if not _is_story_harness(reference.imported):
            continue
        findings.append(
            _violation(
                code=SETUP_TO_STORY,
                reference=reference,
                message="setup runtime files and setup services must not import story_harness",
            )
        )
    return findings


def _story_to_setup(references: list[ImportReference]) -> list[ImportViolation]:
    findings: list[ImportViolation] = []
    for reference in references:
        zone = _agent_runtime_zone(reference.imported)
        if zone is not None and zone != "kernel":
            findings.append(
                _violation(
                    code=STORY_TO_SETUP,
                    reference=reference,
                    message="story_harness may import only kernel agent-runtime modules",
                )
            )
        elif _is_setup_service(reference.imported):
            findings.append(
                _violation(
                    code=STORY_TO_SETUP,
                    reference=reference,
                    message="story_harness must not import rp.services.setup_agent modules",
                )
            )
    return findings


def _agent_runtime_zone(imported: str) -> ZoneName | None:
    prefix = "rp.agent_runtime."
    if not imported.startswith(prefix):
        return None
    relative = imported[len(prefix) :]
    child = relative.split(".", maxsplit=1)[0]
    if child in {"kernel", "setup", "story"}:
        return child  # type: ignore[return-value]
    return LEGACY_MODULE_ZONES.get(child)


def _is_story_harness(imported: str) -> bool:
    return (
        imported == "rp.agent_runtime.story.story_harness"
        or imported.startswith("rp.agent_runtime.story.story_harness.")
        or imported == "rp.agent_runtime.story_harness"
        or imported.startswith("rp.agent_runtime.story_harness.")
        or (
            imported.startswith("rp.agent_runtime.")
            and imported.split(".")[-1] == "story_harness"
        )
    )


def _is_rp_service(imported: str) -> bool:
    return imported == "rp.services" or imported.startswith("rp.services.")


def _is_setup_service(imported: str) -> bool:
    return imported == "rp.services.setup_agent" or imported.startswith(
        "rp.services.setup_agent."
    )


def _is_setup_model(imported: str) -> bool:
    return imported == "rp.models.setup_agent" or imported.startswith(
        "rp.models.setup_agent."
    )


def _violation(*, code: str, reference: ImportReference, message: str) -> ImportViolation:
    return ImportViolation(
        code=code,
        path=reference.path,
        line=reference.line,
        imported=reference.imported,
        message=f"{message}: {reference.imported}",
    )


def _relative_posix(file_path: Path, root: Path) -> str:
    return file_path.relative_to(root).as_posix()
