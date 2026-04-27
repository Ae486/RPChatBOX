"""Tests for the RP memory CRUD local provider."""

import json

import pytest

from config import get_settings
from rp.models.dsl import Domain, Layer
from rp.models.story_runtime import LongformChapterPhase
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_os_service import MemoryOsService
from rp.services.proposal_repository import ProposalRepository
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
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
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


def _seed_formal_authoritative_history(
    retrieval_session,
    *,
    revision: int = 5,
    title: str = "Formal Chapter",
) -> str:
    service = StorySessionService(retrieval_session)
    session = service.get_latest_session_for_story("story-1")
    assert session is not None
    core_repo = CoreStateStoreRepository(retrieval_session)
    row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=revision,
        data_json={"current_chapter": 1, "title": title},
        metadata_json={"test_marker": "provider_formal_history"},
        latest_apply_id="apply-provider-formal-history",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=revision,
        data_json={"current_chapter": 1, "title": title},
        revision_source_kind="provider_test",
        source_apply_id="apply-provider-formal-history",
        metadata_json={"test_marker": "provider_formal_history_revision"},
    )
    retrieval_session.commit()
    return row.authoritative_object_id


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
async def test_provider_returns_block_fallback_state_as_canonical_json(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED", "1")
    get_settings.cache_clear()
    _seed_story_runtime(retrieval_session)
    story_session = StorySessionService(retrieval_session).get_latest_session_for_story(
        "story-1"
    )
    assert story_session is not None
    core_repo = CoreStateStoreRepository(retrieval_session)
    core_repo.upsert_authoritative_object(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.WORLD_RULE.value,
        domain_path="world_rule.archive_policy",
        object_id="world_rule.archive_policy",
        scope="story",
        current_revision=7,
        data_json={"rule": "archive doors seal at dawn"},
        metadata_json={"test_marker": "provider_unmapped_state"},
        latest_apply_id="apply-provider-unmapped-state",
        payload_schema_ref="schema://core-state/world-rule",
    )
    retrieval_session.commit()
    provider = MemoryCrudToolProvider(
        memory_os_service=MemoryOsService(
            retrieval_broker=RetrievalBroker(default_story_id="story-1")
        )
    )

    result = await provider.call_tool(
        tool_name="memory.get_state",
        arguments={
            "refs": [
                {
                    "object_id": "world_rule.archive_policy",
                    "layer": "core_state.authoritative",
                    "domain": "world_rule",
                    "domain_path": "world_rule.archive_policy",
                    "scope": "story",
                }
            ]
        },
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["warnings"] == []
    assert payload["version_refs"] == ["world_rule.archive_policy@7"]
    assert payload["items"][0]["object_ref"]["object_id"] == "world_rule.archive_policy"
    assert payload["items"][0]["object_ref"]["revision"] == 7
    assert payload["items"][0]["data"] == {"rule": "archive doors seal at dawn"}
    assert payload["items"][0]["warnings"] == []
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_provider_returns_projection_block_metadata_and_unmapped_summary(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED", "1")
    get_settings.cache_clear()
    _seed_story_runtime(retrieval_session)
    story_session_service = StorySessionService(retrieval_session)
    story_session = story_session_service.get_latest_session_for_story("story-1")
    assert story_session is not None
    chapter = story_session_service.get_current_chapter(story_session.session_id)
    assert chapter is not None
    core_repo = CoreStateStoreRepository(retrieval_session)
    projection_row = core_repo.upsert_projection_slot(
        story_id=story_session.story_id,
        session_id=story_session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.side_notes_digest",
        summary_id="projection.side_notes_digest",
        slot_name="side_notes_digest",
        scope="chapter",
        current_revision=5,
        items_json=["Side A", "Side B"],
        metadata_json={"test_marker": "provider_unmapped_summary"},
        last_refresh_kind="test_refresh",
        payload_schema_ref="schema://core-state/projection-slot",
    )
    retrieval_session.commit()
    provider = MemoryCrudToolProvider(
        memory_os_service=MemoryOsService(
            retrieval_broker=RetrievalBroker(default_story_id="story-1")
        )
    )

    result = await provider.call_tool(
        tool_name="memory.get_summary",
        arguments={
            "summary_ids": [
                "foundation_digest",
                "projection.side_notes_digest",
            ]
        },
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["warnings"] == []
    assert [item["summary_id"] for item in payload["items"]] == [
        "projection.foundation_digest",
        "projection.side_notes_digest",
    ]
    foundation_item = payload["items"][0]
    side_notes_item = payload["items"][1]
    assert foundation_item["summary_text"] == "Found A"
    assert foundation_item["metadata"]["source"] in {
        "compatibility_mirror",
        "core_state_store",
    }
    assert foundation_item["metadata"]["block_route"] in {
        "chapter_workspace.builder_snapshot_json",
        "core_state_store",
    }
    assert foundation_item["metadata"]["revision"] >= 1
    assert foundation_item["metadata"]["block_id"]
    assert side_notes_item["summary_text"] == "Side A\nSide B"
    assert side_notes_item["metadata"]["block_id"] == projection_row.projection_slot_id
    assert side_notes_item["metadata"]["source"] == "core_state_store"
    assert side_notes_item["metadata"]["source_row_id"] == (
        projection_row.projection_slot_id
    )
    assert side_notes_item["metadata"]["revision"] == 5
    assert side_notes_item["metadata"]["payload_schema_ref"] == (
        "schema://core-state/projection-slot"
    )
    assert side_notes_item["metadata"]["block_route"] == "core_state_store"
    assert side_notes_item["metadata"]["chapter_workspace_id"] == (
        chapter.chapter_workspace_id
    )
    assert side_notes_item["metadata"]["slot_name"] == "side_notes_digest"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_provider_returns_versions_and_provenance_for_formal_state(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED", "1")
    get_settings.cache_clear()
    _seed_story_runtime(retrieval_session)
    _seed_formal_authoritative_history(
        retrieval_session,
        revision=5,
        title="Formal Provider Chapter",
    )
    provider = MemoryCrudToolProvider(
        memory_os_service=MemoryOsService(
            retrieval_broker=RetrievalBroker(default_story_id="story-1")
        )
    )

    versions_result = await provider.call_tool(
        tool_name="memory.list_versions",
        arguments={
            "target_ref": {
                "object_id": "chapter.current",
                "layer": "core_state.authoritative",
                "domain": "chapter",
                "domain_path": "chapter.current",
                "scope": "story",
            }
        },
    )
    provenance_result = await provider.call_tool(
        tool_name="memory.read_provenance",
        arguments={
            "target_ref": {
                "object_id": "chapter.current",
                "layer": "core_state.authoritative",
                "domain": "chapter",
                "domain_path": "chapter.current",
                "scope": "story",
            }
        },
    )

    assert versions_result["success"] is True
    versions_payload = json.loads(versions_result["content"])
    assert versions_payload == {
        "current_ref": "chapter.current@5",
        "versions": ["chapter.current@5"],
    }

    assert provenance_result["success"] is True
    provenance_payload = json.loads(provenance_result["content"])
    assert provenance_payload["target_ref"] == {
        "object_id": "chapter.current",
        "layer": "core_state.authoritative",
        "domain": "chapter",
        "domain_path": "chapter.current",
        "scope": "story",
        "revision": 5,
    }
    assert provenance_payload["source_refs"] == [
        "core_state_store:authoritative_revision"
    ]
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_provider_submits_proposal_and_returns_canonical_receipt(
    retrieval_session,
):
    _seed_story_runtime(retrieval_session)
    provider = MemoryCrudToolProvider()

    result = await provider.call_tool(
        tool_name="proposal.submit",
        arguments={
            "story_id": "story-1",
            "mode": "longform",
            "domain": "chapter",
            "domain_path": "chapter.current",
            "operations": [
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": "core_state.authoritative",
                        "domain": "chapter",
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Provider Proposal Chapter"},
                }
            ],
            "reason": "provider canonical receipt",
            "trace_id": "trace-provider-submit",
        },
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["status"] == "review_required"
    assert payload["domain"] == "chapter"
    assert payload["domain_path"] == "chapter.current"
    assert payload["operation_kinds"] == ["patch_fields"]
    repository = ProposalRepository(retrieval_session)
    persisted = repository.get_proposal_input(payload["proposal_id"])
    assert persisted.reason == "provider canonical receipt"
    assert persisted.trace_id == "trace-provider-submit"
    assert persisted.operations[0].target_ref.object_id == "chapter.current"


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
async def test_registry_and_mcp_manager_route_to_local_provider_with_block_reads(
    retrieval_session,
    monkeypatch,
):
    monkeypatch.setenv("CHATBOX_BACKEND_RP_MEMORY_CORE_STATE_STORE_READ_ENABLED", "1")
    get_settings.cache_clear()
    _seed_story_runtime(retrieval_session)
    provider = MemoryCrudToolProvider(
        memory_os_service=MemoryOsService(
            retrieval_broker=RetrievalBroker(default_story_id="story-1")
        )
    )
    registry = LocalToolProviderRegistry()
    registry.register(provider)
    manager = McpManager(
        storage_path=None,
        local_tool_provider_registry=registry,
        register_default_local_providers=False,
    )

    tools = manager.get_all_tools()
    tool_names = {tool.name for tool in tools}
    assert "memory.get_summary" in tool_names

    result = await manager.call_tool_by_qualified_name(
        qualified_name="rp_memory__memory.get_summary",
        arguments={"summary_ids": ["foundation_digest"]},
    )

    assert result["success"] is True
    payload = json.loads(result["content"])
    assert payload["items"][0]["summary_id"] == "projection.foundation_digest"
    assert payload["items"][0]["metadata"]["source"] in {
        "compatibility_mirror",
        "core_state_store",
    }
    assert payload["items"][0]["metadata"]["block_id"]
    get_settings.cache_clear()
