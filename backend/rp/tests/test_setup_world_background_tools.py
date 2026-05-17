"""Focused cleanup guards for removed setup.world_background legacy tools."""

from __future__ import annotations

import json

import pytest

from rp.agent_runtime.profiles import (
    SETUP_STAGE_ENTRY_TOOLS,
    build_setup_agent_tool_scope,
)
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import StoryMode
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider
from rp.tools.setup_tool_registry import SETUP_TOOL_REGISTRY


LEGACY_WORLD_BACKGROUND_TOOLS = {
    "setup.world_background.list_entries",
    "setup.world_background.read_entry",
    "setup.world_background.write_entry",
    "setup.world_background.edit_entry",
    "setup.world_background.delete_entry",
}


def _provider(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    return (
        workspace_service,
        SetupToolProvider(
            workspace_service=workspace_service,
            context_builder=SetupContextBuilder(workspace_service),
            runtime_state_service=SetupAgentRuntimeStateService(retrieval_session),
        ),
    )


def test_world_background_legacy_tools_are_not_provider_registered_or_visible(
    retrieval_session,
):
    _, provider = _provider(retrieval_session)

    provider_tool_names = {tool.name for tool in provider.list_tools()}
    registry_tool_names = {entry.name for entry in SETUP_TOOL_REGISTRY}
    schema_names = set(provider._schemas)
    handler_names = set(provider._dispatch_handlers)
    setup_scope = set(build_setup_agent_tool_scope("world_background"))

    assert LEGACY_WORLD_BACKGROUND_TOOLS.isdisjoint(registry_tool_names)
    assert LEGACY_WORLD_BACKGROUND_TOOLS.isdisjoint(provider_tool_names)
    assert LEGACY_WORLD_BACKGROUND_TOOLS.isdisjoint(schema_names)
    assert LEGACY_WORLD_BACKGROUND_TOOLS.isdisjoint(handler_names)
    assert LEGACY_WORLD_BACKGROUND_TOOLS.isdisjoint(setup_scope)
    assert set(SETUP_STAGE_ENTRY_TOOLS).issubset(setup_scope)
    assert "setup.truth.write" not in setup_scope


@pytest.mark.asyncio
async def test_removed_world_background_tool_returns_unknown_tool(
    retrieval_session,
):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-world-background-legacy-removed",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.world_background.write_entry",
        arguments={
            "workspace_id": workspace.workspace_id,
            "title": "霓虹湾",
        },
    )

    payload = json.loads(result["content"])
    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_TOOL"
    assert payload["code"] == "unknown_tool"


@pytest.mark.asyncio
async def test_stage_entry_write_replaces_world_background_legacy_write_path(
    retrieval_session,
):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-world-background-stage-entry",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.stage_entry.write",
        arguments={
            "workspace_id": workspace.workspace_id,
            "entry_type": "location",
            "title": "霓虹湾",
            "summary": "霓虹湾是由潮汐墙、盐雾灯塔和走私航线维持秩序的海港城。",
            "sections": [
                {
                    "title": "地理与秩序",
                    "text": "潮汐墙保护内港，盐雾灯塔决定夜航窗口，走私航线由码头行会默许。",
                }
            ],
            "aliases": ["Neon Bay"],
            "tags": ["harbor"],
        },
    )

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert result["success"] is True
    assert payload["stage_id"] == SetupStageId.WORLD_BACKGROUND.value
    assert refreshed is not None
    world_block = refreshed.draft_blocks[SetupStageId.WORLD_BACKGROUND.value]
    assert world_block.entries[0].title == "霓虹湾"
    assert world_block.entries[0].semantic_path.startswith("world_background.")
