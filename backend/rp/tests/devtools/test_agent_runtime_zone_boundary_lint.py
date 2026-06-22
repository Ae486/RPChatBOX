"""Focused tests for the rp.agent_runtime zone-boundary lint."""

from __future__ import annotations

from pathlib import Path

from rp.devtools.check_agent_runtime_zone_boundary import (
    DEFAULT_BACKEND_ROOT,
    KERNEL_LEAK,
    SETUP_TO_STORY,
    STORY_TO_SETUP,
    scan_agent_runtime_zone_boundary,
)


def _write_python(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "VALUE = 1\n", encoding="utf-8")


def _scan(backend_root: Path):
    return scan_agent_runtime_zone_boundary(backend_root=backend_root)


def test_real_tree_is_clean() -> None:
    result = scan_agent_runtime_zone_boundary(backend_root=DEFAULT_BACKEND_ROOT)

    assert result.kernel_leaks == []
    assert result.setup_to_story == []
    assert result.story_to_setup == []


def test_kernel_leak_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "agent_runtime" / "kernel" / "state.py",
        "from rp.services.setup_agent.context_governor import "
        "SetupContextGovernorService\n",
    )

    result = _scan(backend_root)

    assert [finding.code for finding in result.kernel_leaks] == [KERNEL_LEAK]
    assert result.kernel_leaks[0].imported == "rp.services.setup_agent.context_governor"
    assert result.setup_to_story == []
    assert result.story_to_setup == []


def test_setup_to_story_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "agent_runtime" / "setup" / "contracts.py",
        "from rp.agent_runtime.story.story_harness import create_story_harness\n",
    )
    _write_python(
        backend_root / "rp" / "services" / "setup_agent" / "runtime_controller.py",
        "from rp.agent_runtime.story import story_harness\n",
    )

    result = _scan(backend_root)

    assert [finding.code for finding in result.setup_to_story] == [
        SETUP_TO_STORY,
        SETUP_TO_STORY,
    ]
    assert {finding.path for finding in result.setup_to_story} == {
        "rp/agent_runtime/setup/contracts.py",
        "rp/services/setup_agent/runtime_controller.py",
    }
    assert result.kernel_leaks == []
    assert result.story_to_setup == []


def test_story_to_setup_fails(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    _write_python(
        backend_root / "rp" / "agent_runtime" / "story" / "story_harness.py",
        "from rp.agent_runtime.setup.contracts import SetupCapabilityPlan\n"
        "from rp.services.setup_agent.context_governor import "
        "SetupContextGovernorService\n",
    )

    result = _scan(backend_root)

    assert [finding.code for finding in result.story_to_setup] == [
        STORY_TO_SETUP,
        STORY_TO_SETUP,
    ]
    assert {finding.imported for finding in result.story_to_setup} == {
        "rp.agent_runtime.setup.contracts",
        "rp.services.setup_agent.context_governor",
    }
    assert result.kernel_leaks == []
    assert result.setup_to_story == []
