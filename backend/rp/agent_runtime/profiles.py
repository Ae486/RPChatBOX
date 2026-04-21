"""Runtime profiles for RP agent execution."""
from __future__ import annotations

from rp.agent_runtime.contracts import RuntimeProfile

SETUP_READ_ONLY_MEMORY_TOOLS: tuple[str, ...] = (
    "memory.get_state",
    "memory.get_summary",
    "memory.search_recall",
    "memory.search_archival",
    "memory.list_versions",
    "memory.read_provenance",
)

SETUP_PRIVATE_TOOLS: tuple[str, ...] = (
    "setup.patch.story_config",
    "setup.patch.writing_contract",
    "setup.patch.foundation_entry",
    "setup.patch.longform_blueprint",
    "setup.question.raise",
    "setup.asset.register",
    "setup.proposal.commit",
    "setup.read.workspace",
    "setup.read.step_context",
)

SETUP_AGENT_VISIBLE_TOOLS: tuple[str, ...] = (
    *SETUP_READ_ONLY_MEMORY_TOOLS,
    *SETUP_PRIVATE_TOOLS,
)


def build_setup_agent_profile() -> RuntimeProfile:
    """Return the frozen setup-agent runtime profile."""

    return RuntimeProfile(
        profile_id="setup_agent",
        supports_tools=True,
        visible_tool_names=list(SETUP_AGENT_VISIBLE_TOOLS),
        max_rounds=8,
        allow_stream=True,
        recovery_policy="setup_agent_v1",
        finish_policy="assistant_text_or_failure",
    )

