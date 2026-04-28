"""Unit tests for step-aware SetupAgent tool scope."""
from __future__ import annotations

from rp.agent_runtime.profiles import (
    SETUP_AGENT_VISIBLE_TOOLS,
    build_setup_agent_tool_scope,
)


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


def test_unknown_step_falls_back_to_full_visible_tool_union():
    tool_scope = build_setup_agent_tool_scope("unknown_step")

    assert tool_scope == list(SETUP_AGENT_VISIBLE_TOOLS)
