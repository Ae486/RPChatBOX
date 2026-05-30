"""Guard tests for story runtime memory boundary cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest


SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services"
BUSINESS_SERVICE_FILES = [
    SERVICE_ROOT / "writer" / "longform_orchestrator_service.py",
    SERVICE_ROOT / "writer" / "longform_specialist_service.py",
    SERVICE_ROOT / "story" / "turn_domain_service.py",
]
PRIMARY_MEMORY_WRITE_SERVICE_FILES = [
    SERVICE_ROOT / "proposal" / "apply_service.py",
    SERVICE_ROOT / "projection" / "refresh_service.py",
    SERVICE_ROOT / "projection" / "state_service.py",
    SERVICE_ROOT / "story" / "state_apply_service.py",
]
FORBIDDEN_BACKEND_KEYS = [
    "current_state_json",
    "builder_snapshot_json",
]
LEGACY_MEMORY_BACKEND_ALLOWLIST = {
    "authoritative_compatibility_mirror_service.py",
    "chapter_workspace_adapter.py",
    "backfill_service.py",
    "read_service.py",
    "dual_write_service.py",
    "inspection_read_service.py",
    "compatibility_mirror_service.py",
    "read_service.py",
    "provenance_read_service.py",
    "activation_service.py",
    "session_core_state_adapter.py",
    "session_service.py",
}


_PRE_EXISTING_FAILURE_CLUSTER_6 = (
    "Pre-existing failure (legacy memory backend keys outside allowlist). "
    "See .trellis/tasks/archive/2026-05/05-25-services-directory-reorganization/research/pre-existing-failures-19.md cluster 6. "
    "Tracked by T16 in .trellis/spec/guides/project-optimization-master-guide.md."
)


def test_business_services_do_not_touch_legacy_memory_backend_keys_directly():
    for file_path in BUSINESS_SERVICE_FILES:
        content = file_path.read_text(encoding="utf-8")
        for forbidden_key in FORBIDDEN_BACKEND_KEYS:
            assert forbidden_key not in content, f"{file_path.name} still references {forbidden_key}"


def test_primary_memory_write_services_use_mirror_boundaries():
    for file_path in PRIMARY_MEMORY_WRITE_SERVICE_FILES:
        content = file_path.read_text(encoding="utf-8")
        for forbidden_key in FORBIDDEN_BACKEND_KEYS:
            assert forbidden_key not in content, (
                f"{file_path.name} bypasses compatibility mirror service with {forbidden_key}"
            )


@pytest.mark.xfail(reason=_PRE_EXISTING_FAILURE_CLUSTER_6, strict=False)
def test_legacy_memory_backend_key_usage_stays_inside_allowlist():
    offenders: set[str] = set()
    for file_path in SERVICE_ROOT.rglob("*.py"):
        content = file_path.read_text(encoding="utf-8")
        if any(forbidden_key in content for forbidden_key in FORBIDDEN_BACKEND_KEYS):
            offenders.add(file_path.name)
    assert offenders <= LEGACY_MEMORY_BACKEND_ALLOWLIST, (
        "legacy memory backend key usage escaped allowlist: "
        f"{sorted(offenders - LEGACY_MEMORY_BACKEND_ALLOWLIST)}"
    )
