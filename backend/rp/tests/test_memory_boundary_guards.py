"""Guard tests for story runtime memory boundary cleanup."""

from __future__ import annotations

from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services"
BUSINESS_SERVICE_FILES = [
    SERVICE_ROOT / "longform_orchestrator_service.py",
    SERVICE_ROOT / "longform_specialist_service.py",
    SERVICE_ROOT / "story_turn_domain_service.py",
]
PRIMARY_MEMORY_WRITE_SERVICE_FILES = [
    SERVICE_ROOT / "proposal_apply_service.py",
    SERVICE_ROOT / "projection_refresh_service.py",
    SERVICE_ROOT / "projection_state_service.py",
    SERVICE_ROOT / "story_state_apply_service.py",
]
FORBIDDEN_BACKEND_KEYS = [
    "current_state_json",
    "builder_snapshot_json",
]
LEGACY_MEMORY_BACKEND_ALLOWLIST = {
    "authoritative_compatibility_mirror_service.py",
    "chapter_workspace_projection_adapter.py",
    "core_state_backfill_service.py",
    "core_state_read_service.py",
    "core_state_dual_write_service.py",
    "memory_inspection_read_service.py",
    "projection_compatibility_mirror_service.py",
    "projection_read_service.py",
    "provenance_read_service.py",
    "story_activation_service.py",
    "story_session_core_state_adapter.py",
    "story_session_service.py",
}


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


def test_legacy_memory_backend_key_usage_stays_inside_allowlist():
    offenders: set[str] = set()
    for file_path in SERVICE_ROOT.glob("*.py"):
        content = file_path.read_text(encoding="utf-8")
        if any(forbidden_key in content for forbidden_key in FORBIDDEN_BACKEND_KEYS):
            offenders.add(file_path.name)
    assert offenders <= LEGACY_MEMORY_BACKEND_ALLOWLIST, (
        "legacy memory backend key usage escaped allowlist: "
        f"{sorted(offenders - LEGACY_MEMORY_BACKEND_ALLOWLIST)}"
    )
