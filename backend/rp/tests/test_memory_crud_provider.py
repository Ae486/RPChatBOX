"""Tests for the RP memory CRUD local provider."""
import json

import pytest

from rp.models.story_runtime import LongformChapterPhase
from rp.models.memory_crud import ProposalSubmitInput
from rp.services.memory_os_service import MemoryOsService
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.local_tool_provider_registry import LocalToolProviderRegistry
from rp.services.story_session_service import StorySessionService
from rp.tools.memory_crud_provider import MemoryCrudToolProvider
from services.mcp_manager import McpManager


def test_provider_exposes_openai_tools():
    provider = MemoryCrudToolProvider()

    tools = provider.list_tools()

    assert any(tool.name == "memory.get_state" for tool in tools)
    assert any(tool.name == "proposal.submit" for tool in tools)
    proposal_tool = next(tool for tool in tools if tool.name == "proposal.submit")
    assert "without applying" not in proposal_tool.description


def _seed_story_runtime(retrieval_session) -> None:
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {"current_phase": "outline_drafting", "accepted_segments": 0},
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
            "writer_hints": ["Hint A"],
        },
    )
    service.commit()


@pytest.mark.asyncio
async def test_provider_returns_canonical_json_string(retrieval_session):
    _seed_story_runtime(retrieval_session)
    provider = MemoryCrudToolProvider(
        memory_os_service=MemoryOsService(
            retrieval_broker=RetrievalBroker(default_story_id="story-1")
        )
    )

    result = await provider.call_tool(
        tool_name="memory.get_state",
        arguments={
            "domain": "chapter",
        },
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["items"][0]["object_ref"]["domain"] == "chapter"
    assert payload["items"][0]["data"]["title"] == "Chapter One"


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
