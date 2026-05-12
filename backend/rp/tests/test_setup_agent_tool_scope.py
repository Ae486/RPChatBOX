"""Unit tests for step-aware SetupAgent tool scope."""

from __future__ import annotations

import pytest

from models.mcp_config import McpToolInfo
from rp.agent_runtime.tools import RuntimeToolRegistryView
from rp.agent_runtime.profiles import (
    SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS,
    SETUP_AGENT_VISIBLE_TOOLS,
    build_setup_agent_capability_plan,
    build_setup_agent_tool_scope,
)
from rp.models.setup_stage import SetupStageId


LEGACY_PATCH_TOOLS = {
    "setup.patch.story_config",
    "setup.patch.writing_contract",
    "setup.patch.foundation_entry",
    "setup.patch.longform_blueprint",
}


class _FakeMcpManager:
    def __init__(self, tool_names: list[str]) -> None:
        self._tool_names = list(tool_names)

    def get_all_tools(self) -> list[McpToolInfo]:
        return [
            McpToolInfo(
                server_id="rp_setup",
                server_name="rp_setup",
                name=tool_name,
                description=f"Tool {tool_name}",
                input_schema={"type": "object", "properties": {}},
            )
            for tool_name in self._tool_names
        ]


def test_story_config_tool_scope_keeps_shared_tools_and_story_patch_only():
    tool_scope = build_setup_agent_tool_scope("story_config")

    assert "setup.read.workspace" in tool_scope
    assert "setup.proposal.commit" in tool_scope
    assert "setup.patch.story_config" in tool_scope
    assert "setup.patch.writing_contract" not in tool_scope
    assert "setup.patch.foundation_entry" not in tool_scope
    assert "setup.patch.longform_blueprint" not in tool_scope


def test_foundation_tool_scope_keeps_shared_tools_and_foundation_patch_only():
    tool_scope = build_setup_agent_tool_scope("foundation")

    assert "setup.chunk.upsert" in tool_scope
    assert "setup.truth.write" in tool_scope
    assert "setup.patch.foundation_entry" in tool_scope
    assert "setup.patch.story_config" not in tool_scope
    assert "setup.patch.writing_contract" not in tool_scope
    assert "setup.patch.longform_blueprint" not in tool_scope


def test_world_background_stage_tool_scope_uses_shared_tools_without_crud_pilot():
    tool_scope = build_setup_agent_tool_scope("world_background")

    assert "setup.read.workspace" in tool_scope
    assert "setup.question.raise" in tool_scope
    assert "setup.proposal.commit" in tool_scope
    assert "setup.truth.write" in tool_scope
    assert "setup.world_background.list_entries" not in tool_scope
    assert "setup.world_background.write_entry" not in tool_scope
    assert "setup.patch.foundation_entry" not in tool_scope
    assert "setup.patch.story_config" not in tool_scope
    assert "setup.patch.longform_blueprint" not in tool_scope


def test_plot_blueprint_stage_tool_scope_uses_stage_native_truth_write_only():
    tool_scope = build_setup_agent_tool_scope("plot_blueprint")

    assert "setup.truth.write" in tool_scope
    assert "setup.patch.longform_blueprint" not in tool_scope
    assert "setup.patch.foundation_entry" not in tool_scope
    assert "setup.patch.story_config" not in tool_scope


@pytest.mark.parametrize("stage_id", list(SetupStageId))
def test_known_canonical_stage_tool_scope_hides_all_legacy_patch_tools(stage_id):
    tool_scope = build_setup_agent_tool_scope(stage_id.value)

    if stage_id == SetupStageId.WORLD_BACKGROUND:
        assert "setup.world_background.write_entry" not in tool_scope
    assert "setup.truth.write" in tool_scope
    assert LEGACY_PATCH_TOOLS.isdisjoint(tool_scope)


def test_unknown_step_falls_back_to_full_visible_tool_union():
    tool_scope = build_setup_agent_tool_scope("unknown_step")

    assert tool_scope == list(SETUP_AGENT_VISIBLE_TOOLS)


def test_capability_plan_snapshot_for_stage_keeps_required_shared_read_tools():
    plan = build_setup_agent_capability_plan(
        "foundation",
        current_stage=SetupStageId.WORLD_BACKGROUND.value,
    )

    assert plan.stage_id == SetupStageId.WORLD_BACKGROUND.value
    assert plan.step_id == "foundation"
    assert plan.active_tool_names == plan.runtime_allowlist
    assert plan.snapshot_expectations["fallback_to_full_union"] is False
    assert plan.snapshot_expectations["shared_tools_visible"] is True
    assert "setup.truth.write" in plan.active_tool_names
    assert "setup.read.draft_refs" in plan.active_tool_names
    assert LEGACY_PATCH_TOOLS.isdisjoint(plan.active_tool_names)
    assert set(SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS).issubset(
        plan.candidate_exclusions
    )


def test_capability_plan_snapshot_for_legacy_step_keeps_only_current_patch_family():
    plan = build_setup_agent_capability_plan("story_config")

    assert plan.stage_id is None
    assert plan.step_id == "story_config"
    assert "setup.patch.story_config" in plan.active_tool_names
    assert "setup.patch.foundation_entry" not in plan.active_tool_names
    assert plan.snapshot_expectations["visible_legacy_patch_tools"] == [
        "setup.patch.story_config"
    ]


def test_capability_plan_guidance_only_references_active_tools():
    plan = build_setup_agent_capability_plan(
        "foundation",
        current_stage=SetupStageId.WORLD_BACKGROUND.value,
    )
    active_tools = set(plan.active_tool_names)

    assert plan.prompt_guidance_fragments
    for fragment in plan.prompt_guidance_fragments:
        assert set(fragment.tool_names).issubset(active_tools)
    assert not any(
        candidate in fragment.text
        for candidate in SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS
        for fragment in plan.prompt_guidance_fragments
    )


def test_capability_plan_drives_schema_visible_tools_and_runtime_allowlist():
    plan = build_setup_agent_capability_plan(
        "foundation",
        current_stage=SetupStageId.WORLD_BACKGROUND.value,
    )
    registry = RuntimeToolRegistryView(
        mcp_manager=_FakeMcpManager(
            [
                *SETUP_AGENT_VISIBLE_TOOLS,
                *SETUP_AGENT_CANDIDATE_EXCLUDED_TOOLS,
            ]
        )
    )

    schema_visible = {
        tool.name
        for tool in registry.get_visible_tools(
            visible_tool_names=plan.runtime_allowlist
        )
    }

    assert schema_visible == set(plan.runtime_allowlist)
    assert "setup.world_background.write_entry" not in schema_visible
    assert "setup.patch.foundation_entry" not in schema_visible


def test_character_design_skill_pack_does_not_change_capability_plan_or_tool_scope():
    plan = build_setup_agent_capability_plan(
        "foundation",
        current_stage=SetupStageId.CHARACTER_DESIGN.value,
    )

    assert plan.runtime_allowlist == build_setup_agent_tool_scope(
        SetupStageId.CHARACTER_DESIGN.value
    )
    assert "setup.truth.write" in plan.runtime_allowlist
    assert "setup.read.draft_refs" in plan.runtime_allowlist
    assert LEGACY_PATCH_TOOLS.isdisjoint(plan.runtime_allowlist)
    assert "setup.world_background.write_entry" not in plan.runtime_allowlist
