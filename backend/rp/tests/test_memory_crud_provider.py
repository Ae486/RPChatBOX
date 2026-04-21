"""Tests for the RP memory CRUD local provider."""
import json

import pytest

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import ProposalSubmitInput
from rp.services.local_tool_provider_registry import LocalToolProviderRegistry
from rp.tools.memory_crud_provider import MemoryCrudToolProvider
from services.mcp_manager import McpManager


def test_provider_exposes_openai_tools():
    provider = MemoryCrudToolProvider()

    tools = provider.list_tools()

    assert any(tool.name == "memory.get_state" for tool in tools)
    assert any(tool.name == "proposal.submit" for tool in tools)


@pytest.mark.asyncio
async def test_provider_returns_canonical_json_string():
    provider = MemoryCrudToolProvider()

    result = await provider.call_tool(
        tool_name="memory.get_state",
        arguments={
            "domain": "scene",
        },
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["items"][0]["object_ref"]["domain"] == "scene"


@pytest.mark.asyncio
async def test_provider_validation_error_is_stable():
    provider = MemoryCrudToolProvider()

    result = await provider.call_tool(
        tool_name="proposal.submit",
        arguments={
            "story_id": "story-1",
            "mode": "longform",
            "domain": "scene",
            "operations": [],
        },
    )

    assert result["success"] is False
    assert result["error_code"] == "VALIDATION_FAILED"
    payload = json.loads(result["content"])
    assert payload["code"] == "validation_failed"


@pytest.mark.asyncio
async def test_registry_and_mcp_manager_route_to_local_provider():
    provider = MemoryCrudToolProvider()
    registry = LocalToolProviderRegistry()
    registry.register(provider)
    manager = McpManager(storage_path=None, local_tool_provider_registry=registry)

    tools = manager.get_all_tools()
    tool_names = {tool.name for tool in tools}
    assert "memory.get_state" in tool_names

    result = await manager.call_tool_by_qualified_name(
        qualified_name="rp_memory__memory.get_state",
        arguments={"domain": "scene"},
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["items"][0]["object_ref"]["domain"] == "scene"

