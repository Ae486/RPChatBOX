"""Oracle node-5 Tier-B: S0 harness substrate contract-split (S0-O1, S0-O2).

These pin the S0 *target* before it is built (oracle-first), so both are RED today.

S0-O1 [HAR-003] import audit: the story-harness import path must be setup-free.
Today it is NOT — spike#1 proved ``rp.agent_runtime.tools`` transitively pulls
``rp.models.setup_agent.*`` via ``contracts.py:10-11``. We import the harness
entry modules in a FRESH interpreter and assert no ``setup_agent`` module is
loaded; this fails RED until S0 extracts a setup-free ``runtime_tool_contracts``.

S0-O2 [HAR-009/012/013] consumer-backed factory: the real ``create_story_harness``
test factory must compile ``build_runtime_graph`` on the split substrate and run a
definition-layer-registered fake executor through >=2 tool-rounds. The factory
does not exist yet; the import is guarded so this file COLLECTS, then a clean
assertion fails on the gap. Target shape is the pi-mono-adapted seam
(_borrowable-pi-mono-harness.md): test_minimal profile + per-harness fake
registration + scripted response queue + abort contract + cleanup.

Neither assertion may be weakened to green — they serve the S0 SoT, not today's code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# backend/rp/tests/agent_runtime/test_s0_harness_substrate.py -> parents[3] == backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]

# Harness entry modules whose transitive imports must be free of setup_agent.
_HARNESS_ENTRY_MODULES = (
    "rp.agent_runtime.story_harness",
    "rp.agent_runtime.graph",
    "rp.agent_runtime.tools",
)

# S0-O2 target: the setup-free harness factory + its test_minimal profile. Guarded
# so a missing module yields a clean failing assertion, not a collection error.
try:  # pragma: no cover - exercised once S0 lands
    from rp.agent_runtime.story_harness import (  # type: ignore[attr-defined]
        TEST_MINIMAL_PROFILE,
        create_story_harness,
    )
except ImportError:  # pragma: no cover - the RED state today
    create_story_harness = None  # type: ignore[assignment]
    TEST_MINIMAL_PROFILE = None  # type: ignore[assignment]


def test_s0_o1_story_harness_import_path_is_setup_free() -> None:
    script = (
        "import importlib, sys\n"
        f"for module_name in {_HARNESS_ENTRY_MODULES!r}:\n"
        "    importlib.import_module(module_name)\n"
        "leaked = sorted(name for name in sys.modules if 'setup_agent' in name)\n"
        "sys.stdout.write(repr(leaked))\n"
        "sys.exit(1 if leaked else 0)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "HAR-003: the story-harness import path still pulls setup_agent modules "
        "(spike#1 leakage via rp.agent_runtime.contracts:10-11). S0 must extract a "
        f"setup-free runtime_tool_contracts. Leaked modules: {proc.stdout.strip()}\n"
        f"{proc.stderr.strip()}"
    )


def test_s0_o2_create_story_harness_runs_fake_through_two_tool_rounds() -> None:
    assert create_story_harness is not None and TEST_MINIMAL_PROFILE is not None, (
        "S0 substrate not built: rp.agent_runtime.story_harness.create_story_harness "
        "(+ TEST_MINIMAL_PROFILE) must compile build_runtime_graph on the setup-free "
        "split substrate and run a definition-layer-registered fake executor through "
        ">=2 tool-rounds (HAR-009/012/013)."
    )

    # Target contract (runs once S0 lands): the pi-mono-adapted seam - a per-harness
    # fake registered against the test_minimal profile, driven by a scripted queue
    # that emits a tool call (round 1) then final text (round 2), with cleanup.
    harness = create_story_harness(profile=TEST_MINIMAL_PROFILE)
    try:
        harness.set_responses(
            [
                harness.tool_call("noop", {}),  # round 1: model asks for a tool
                harness.final_text("done"),     # round 2: model finalizes
            ]
        )
        result = harness.run(turn_goal="oracle smoke")
        assert result.succeeded
        assert harness.model_call_count >= 2
        successes = [r for r in result.tool_results if r.success]
        assert len(successes) == 1 and successes[0].tool_name.endswith("noop")
    finally:
        harness.cleanup()
