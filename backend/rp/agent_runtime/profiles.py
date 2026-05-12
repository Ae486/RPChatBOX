"""Runtime profiles and setup capability plans for RP agent execution."""

from __future__ import annotations

from rp.agent_runtime.contracts import (
    RuntimeProfile,
    SetupCapabilityGuidanceFragment,
    SetupCapabilityPlan,
)
from rp.models.setup_stage import SetupStageId, get_stage_module

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

SETUP_WORLD_BACKGROUND_CANDIDATE_TOOLS: tuple[str, ...] = (
    "setup.world_background.list_entries",
    "setup.world_background.read_entry",
    "setup.world_background.write_entry",
    "setup.world_background.edit_entry",
    "setup.world_background.delete_entry",
)

SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS: tuple[str, ...] = (
    *SETUP_WORLD_BACKGROUND_CANDIDATE_TOOLS,
)

SETUP_AGENT_VISIBLE_TOOLS: tuple[str, ...] = (
    *SETUP_READ_ONLY_MEMORY_TOOLS,
    *SETUP_SHARED_PRIVATE_TOOLS,
    *tuple(
        tool_name
        for tool_names in SETUP_STEP_PATCH_TOOLS.values()
        for tool_name in tool_names
    ),
)


def build_setup_agent_capability_plan(
    current_step: str | None,
    *,
    current_stage: str | None = None,
) -> SetupCapabilityPlan:
    """Return the authoritative setup tool package for one runtime turn."""

    scope_key = (
        str(current_stage or current_step) if current_stage or current_step else None
    )
    stage_id = _coerce_stage_id(scope_key)
    step_id = str(current_step) if current_step is not None else None
    patch_tools = _patch_tools_for_scope(scope_key)
    fallback_to_full_union = scope_key is None or patch_tools is None
    scoped_patch_tools = tuple(patch_tools or ())
    active_tool_names = (
        list(SETUP_AGENT_VISIBLE_TOOLS)
        if fallback_to_full_union
        else _ordered_unique(
            [
                *SETUP_READ_ONLY_MEMORY_TOOLS,
                *SETUP_SHARED_PRIVATE_TOOLS,
                *scoped_patch_tools,
            ]
        )
    )
    active_set = set(active_tool_names)
    return SetupCapabilityPlan(
        stage_id=stage_id.value if stage_id is not None else None,
        step_id=step_id,
        active_tool_names=list(active_tool_names),
        model_schema_modes={
            tool_name: _model_schema_mode(tool_name)
            for tool_name in active_tool_names
        },
        runtime_allowlist=list(active_tool_names),
        prompt_guidance_fragments=_prompt_guidance_fragments(
            active_set=active_set,
            stage_id=stage_id,
            patch_tools=scoped_patch_tools,
        ),
        candidate_exclusions=[
            tool_name
            for tool_name in SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS
            if tool_name not in active_set
        ],
        snapshot_expectations={
            "scope_key": scope_key,
            "fallback_to_full_union": fallback_to_full_union,
            "shared_tools_visible": all(
                tool_name in active_set
                for tool_name in (*SETUP_READ_ONLY_MEMORY_TOOLS, *SETUP_SHARED_PRIVATE_TOOLS)
            ),
            "legacy_patch_tools": list(_legacy_patch_tools()),
            "visible_legacy_patch_tools": [
                tool_name
                for tool_name in _legacy_patch_tools()
                if tool_name in active_set
            ],
            "candidate_tools_hidden": [
                tool_name
                for tool_name in SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS
                if tool_name not in active_set
            ],
        },
    )


def build_setup_agent_tool_scope(current_step: str | None) -> list[str]:
    """Return the step-aware default tool scope for one setup turn."""

    return build_setup_agent_capability_plan(current_step).runtime_allowlist


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


def _patch_tools_for_scope(scope_key: str | None) -> tuple[str, ...] | None:
    if scope_key is None:
        return None
    patch_tools = SETUP_STEP_PATCH_TOOLS.get(scope_key)
    if patch_tools is None:
        patch_tools = SETUP_STAGE_PATCH_TOOLS.get(scope_key)
    return patch_tools


def _coerce_stage_id(scope_key: str | None) -> SetupStageId | None:
    if scope_key is None:
        return None
    try:
        return SetupStageId(scope_key)
    except ValueError:
        return None


def _model_schema_mode(tool_name: str) -> str:
    if tool_name == "setup.truth.write":
        return "setup_truth_write_runtime_adapted"
    return "provider_default"


def _prompt_guidance_fragments(
    *,
    active_set: set[str],
    stage_id: SetupStageId | None,
    patch_tools: tuple[str, ...],
) -> list[SetupCapabilityGuidanceFragment]:
    fragments: list[SetupCapabilityGuidanceFragment] = []

    def add(fragment_id: str, tool_names: tuple[str, ...], text: str) -> None:
        if all(tool_name in active_set for tool_name in tool_names):
            fragments.append(
                SetupCapabilityGuidanceFragment(
                    fragment_id=fragment_id,
                    tool_names=list(tool_names),
                    text=text,
                )
            )

    add(
        "draft_refs.read",
        ("setup.read.draft_refs",),
        (
            "If compact_summary contains draft_refs or recovery_hints and exact "
            "draft detail is needed, call setup.read.draft_refs."
        ),
    )
    add(
        "discussion.update_state",
        ("setup.discussion.update_state",),
        (
            "Use setup.discussion.update_state when the current-step discussion "
            "map needs refresh or reconciliation."
        ),
    )
    add(
        "chunk.upsert",
        ("setup.chunk.upsert",),
        (
            "Use setup.chunk.upsert when one concrete truth candidate is emerging "
            "from discussion."
        ),
    )
    add(
        "truth.write",
        ("setup.truth.write",),
        (
            "Use setup.truth.write when one chunk is stable enough to land in the "
            "current draft. If setup.truth.write fails, repair it from current "
            "context when possible; only ask the user when the missing information "
            "is truly user-exclusive."
        ),
    )
    if stage_id is not None:
        add(
            "truth.write.stage_hint",
            ("setup.truth.write",),
            _stage_truth_write_hint(stage_id),
        )
    add(
        "question.raise",
        ("setup.question.raise",),
        (
            "Use setup.question.raise when an ambiguity is blocking or needs an "
            "explicit user decision."
        ),
    )
    add(
        "asset.register",
        ("setup.asset.register",),
        "Use setup.asset.register when the user provides a setup-scoped reference asset.",
    )
    add(
        "proposal.commit",
        ("setup.proposal.commit",),
        (
            "Before calling setup.proposal.commit, self-check readiness; if the "
            "user explicitly asked to commit, carry unresolved issues as warnings "
            "instead of blocking."
        ),
    )
    add(
        "workspace.read",
        ("setup.read.workspace",),
        "Use setup.read.workspace when you need the latest SetupWorkspace truth view.",
    )
    add(
        "step_context.read",
        ("setup.read.step_context",),
        (
            "Use setup.read.step_context when deterministic current step or "
            "canonical-stage context needs readback."
        ),
    )
    add(
        "truth_index.search",
        ("setup.truth_index.search",),
        "Use setup.truth_index.search for small candidate ref lists from accepted setup truth.",
    )
    add(
        "truth_index.read_refs",
        ("setup.truth_index.read_refs",),
        "Use setup.truth_index.read_refs for exact accepted setup truth refs.",
    )
    if all(tool_name in active_set for tool_name in SETUP_READ_ONLY_MEMORY_TOOLS):
        fragments.append(
            SetupCapabilityGuidanceFragment(
                fragment_id="memory.read_only",
                tool_names=list(SETUP_READ_ONLY_MEMORY_TOOLS),
                text=(
                    "Use active read-only memory tools only when needed for "
                    "clarification or archival lookup."
                ),
            )
        )
    for tool_name in patch_tools:
        add(
            f"legacy_patch.{tool_name}",
            (tool_name,),
            f"Use {tool_name} only for its legacy step-specific draft family.",
        )
    return fragments


def _stage_truth_write_hint(stage_id: SetupStageId) -> str:
    module = get_stage_module(stage_id)
    preferred_entry_types = (
        ", ".join(module.default_entry_types) or "stage-specific types"
    )
    return (
        "For canonical stage setup.truth.write calls, prefer one entry payload "
        "instead of a full stage block unless you are intentionally replacing or "
        "merging the whole block. Minimal entry fields: entry_id, entry_type, "
        "semantic_path, title. Optional fields: summary, sections. A text section "
        'must look like {"section_id":"summary","title":"Summary","kind":"text",'
        '"content":{"text":"..."}}. '
        f"Preferred entry_type values for this stage: {preferred_entry_types}."
    )


def _legacy_patch_tools() -> tuple[str, ...]:
    return tuple(
        tool_name
        for tool_names in SETUP_STEP_PATCH_TOOLS.values()
        for tool_name in tool_names
    )


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
