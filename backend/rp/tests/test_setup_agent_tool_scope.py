"""Unit tests for step-aware SetupAgent tool scope."""

from __future__ import annotations

import pytest

from rp.agent_runtime.profiles import (
    SETUP_AGENT_VISIBLE_TOOLS,
    build_setup_agent_tool_scope,
)
from rp.models.setup_stage import SetupStageId


LEGACY_PATCH_TOOLS = {
    "setup.patch.story_config",
    "setup.patch.writing_contract",
    "setup.patch.foundation_entry",
    "setup.patch.longform_blueprint",
}


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


def test_world_background_stage_tool_scope_uses_stage_native_truth_write_only():
    tool_scope = build_setup_agent_tool_scope("world_background")

    assert "setup.read.draft_refs" in tool_scope
    assert "setup.truth_index.search" in tool_scope
    assert "setup.truth_index.read_refs" in tool_scope
    assert "setup.truth.write" in tool_scope
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

    assert "setup.truth.write" in tool_scope
    assert LEGACY_PATCH_TOOLS.isdisjoint(tool_scope)


def test_unknown_step_falls_back_to_full_visible_tool_union():
    tool_scope = build_setup_agent_tool_scope("unknown_step")

    assert tool_scope == list(SETUP_AGENT_VISIBLE_TOOLS)
