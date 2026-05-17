"""Runtime profiles and setup capability plans for RP agent execution."""

from __future__ import annotations

from rp.agent_runtime.contracts import (
    RuntimeProfile,
    SetupCapabilityGuidanceFragment,
    SetupCapabilityPlan,
)
from rp.models.setup_stage import SetupStageId

SETUP_READ_ONLY_MEMORY_TOOLS: tuple[str, ...] = (
    "setup.memory.search",
    "setup.memory.open",
    "setup.memory.read_refs",
)

SETUP_SHARED_PRIVATE_TOOLS: tuple[str, ...] = ("setup.asset.register",)

SETUP_STAGE_ENTRY_TOOLS: tuple[str, ...] = (
    "setup.stage_entry.list",
    "setup.stage_entry.read",
    "setup.stage_entry.write",
    "setup.stage_entry.edit",
    "setup.stage_entry.delete",
)

SETUP_STAGE_ENTRY_TOOL_STAGES: tuple[SetupStageId, ...] = (
    SetupStageId.WORLD_BACKGROUND,
    SetupStageId.CHARACTER_DESIGN,
    SetupStageId.PLOT_BLUEPRINT,
)

SETUP_STEP_PATCH_TOOLS: dict[str, tuple[str, ...]] = {
    "story_config": (),
    "writing_contract": (),
    "foundation": (),
    "longform_blueprint": (),
}

SETUP_STAGE_PATCH_TOOLS: dict[str, tuple[str, ...]] = {
    stage_id.value: () for stage_id in SetupStageId
}

SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS: tuple[str, ...] = ()

SETUP_AGENT_VISIBLE_TOOLS: tuple[str, ...] = (
    *SETUP_READ_ONLY_MEMORY_TOOLS,
    *SETUP_SHARED_PRIVATE_TOOLS,
    *SETUP_STAGE_ENTRY_TOOLS,
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
                *_shared_tools_for_stage(stage_id),
                *_stage_entry_tools_for_stage(stage_id),
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
            tool_name: _model_schema_mode(tool_name) for tool_name in active_tool_names
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
                for tool_name in (
                    *SETUP_READ_ONLY_MEMORY_TOOLS,
                    *_shared_tools_for_stage(stage_id),
                )
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

    if stage_id in SETUP_STAGE_ENTRY_TOOL_STAGES:
        add(
            "stage_entry.write",
            ("setup.stage_entry.write",),
            (
                "For world_background, character_design, and plot_blueprint, use "
                "setup.stage_entry.write as the primary draft write tool. Provide "
                "only entry_type, title, summary, and text sections; the backend "
                "chooses the current stage, ids, semantic paths, and section shape."
            ),
        )
        add(
            "stage_entry.read_list",
            ("setup.stage_entry.list", "setup.stage_entry.read"),
            (
                "Use setup.stage_entry.list and setup.stage_entry.read to inspect "
                "the current stage draft before editing or deleting entries."
            ),
        )
        add(
            "stage_entry.edit_delete",
            ("setup.stage_entry.edit", "setup.stage_entry.delete"),
            (
                "Use setup.stage_entry.edit or setup.stage_entry.delete only with "
                "a current target_ref and basis_fingerprint from the current stage."
            ),
        )
    add(
        "asset.register",
        ("setup.asset.register",),
        "Use setup.asset.register when the user provides a setup-scoped reference asset.",
    )
    add(
        "setup_session_memory.search",
        ("setup.memory.search", "setup.memory.open"),
        (
            "Use setup.memory.search to find setup fact refs from editable draft "
            "and accepted setup truth when the needed exact fact is not visible. "
            "Search results and navigation_summary are navigation only, not fact "
            "content. Use setup.memory.open on a chosen ref before relying on "
            "exact details. Opening a level-3 entry ref returns a level-4 section "
            "directory; opening a level-4 section ref returns clean fact content."
        ),
    )
    for tool_name in patch_tools:
        add(
            f"legacy_patch.{tool_name}",
            (tool_name,),
            f"Use {tool_name} only for its legacy step-specific draft family.",
        )
    return fragments


def _legacy_patch_tools() -> tuple[str, ...]:
    return tuple(
        tool_name
        for tool_names in SETUP_STEP_PATCH_TOOLS.values()
        for tool_name in tool_names
    )


def _shared_tools_for_stage(stage_id: SetupStageId | None) -> tuple[str, ...]:
    return SETUP_SHARED_PRIVATE_TOOLS


def _stage_entry_tools_for_stage(stage_id: SetupStageId | None) -> tuple[str, ...]:
    if stage_id in SETUP_STAGE_ENTRY_TOOL_STAGES:
        return SETUP_STAGE_ENTRY_TOOLS
    return ()


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
