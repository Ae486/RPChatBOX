"""Runtime profiles for RP agent execution."""

from __future__ import annotations

from rp.agent_runtime.contracts import RuntimeProfile
from rp.models.setup_stage import SetupStageId

SETUP_READ_ONLY_MEMORY_TOOLS: tuple[str, ...] = (
    "memory.get_state",
    "memory.get_summary",
    "memory.search_recall",
    "memory.search_archival",
    "memory.list_versions",
    "memory.read_provenance",
)

SETUP_SHARED_PRIVATE_TOOLS: tuple[str, ...] = (
    "setup.discussion.update_state",
    "setup.chunk.upsert",
    "setup.truth.write",
    "setup.question.raise",
    "setup.asset.register",
    "setup.proposal.commit",
    "setup.read.workspace",
    "setup.read.step_context",
    "setup.read.draft_refs",
    "setup.truth_index.search",
    "setup.truth_index.read_refs",
)

SETUP_STEP_PATCH_TOOLS: dict[str, tuple[str, ...]] = {
    "story_config": ("setup.patch.story_config",),
    "writing_contract": ("setup.patch.writing_contract",),
    "foundation": ("setup.patch.foundation_entry",),
    "longform_blueprint": ("setup.patch.longform_blueprint",),
}

SETUP_STAGE_PATCH_TOOLS: dict[str, tuple[str, ...]] = {
    stage_id.value: () for stage_id in SetupStageId
}

SETUP_AGENT_VISIBLE_TOOLS: tuple[str, ...] = (
    *SETUP_READ_ONLY_MEMORY_TOOLS,
    *SETUP_SHARED_PRIVATE_TOOLS,
    *tuple(
        tool_name
        for tool_names in SETUP_STEP_PATCH_TOOLS.values()
        for tool_name in tool_names
    ),
)


def build_setup_agent_tool_scope(current_step: str | None) -> list[str]:
    """Return the step-aware default tool scope for one setup turn."""

    if not current_step:
        return list(SETUP_AGENT_VISIBLE_TOOLS)

    current_key = str(current_step)
    patch_tools = SETUP_STEP_PATCH_TOOLS.get(current_key)
    if patch_tools is None:
        patch_tools = SETUP_STAGE_PATCH_TOOLS.get(current_key)
    if patch_tools is None:
        return list(SETUP_AGENT_VISIBLE_TOOLS)

    return [
        *SETUP_READ_ONLY_MEMORY_TOOLS,
        *SETUP_SHARED_PRIVATE_TOOLS,
        *patch_tools,
    ]


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
