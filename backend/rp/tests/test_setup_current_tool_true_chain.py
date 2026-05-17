"""Provider-level true-chain coverage for the current SetupAgent tool surface."""

from __future__ import annotations

import json
from typing import Any

import pytest

from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import StoryMode
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider


def _provider(retrieval_session) -> tuple[SetupWorkspaceService, SetupToolProvider]:
    workspace_service = SetupWorkspaceService(retrieval_session)
    return (
        workspace_service,
        SetupToolProvider(
            workspace_service=workspace_service,
            context_builder=SetupContextBuilder(workspace_service),
            runtime_state_service=SetupAgentRuntimeStateService(retrieval_session),
        ),
    )


async def _call(
    provider: SetupToolProvider,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = await provider.call_tool(tool_name=tool_name, arguments=arguments)
    payload = json.loads(result["content"])
    assert result["success"] is True, payload
    return payload


def _search_refs(payload: dict[str, Any]) -> list[str]:
    return [item["ref"] for item in payload["items"]]


@pytest.mark.asyncio
async def test_current_setup_tools_round_trip_stage_entry_and_memory_true_chain(
    retrieval_session,
):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-current-tool-true-chain",
        mode=StoryMode.LONGFORM,
    )

    assert workspace.current_stage == SetupStageId.WORLD_BACKGROUND

    write_payload = await _call(
        provider,
        "setup.stage_entry.write",
        {
            "workspace_id": workspace.workspace_id,
            "entry_type": "location",
            "title": "Violet Harbor",
            "summary": "Violet Harbor guards the tidewall lattice.",
            "sections": [
                {
                    "title": "Signal Code",
                    "text": "Blue lanterns unlock the tidewall lattice archive.",
                    "retrieval_role": "rule",
                    "tags": ["lantern"],
                }
            ],
            "aliases": ["VH-9"],
            "tags": ["harbor", "tidewall"],
        },
    )
    target_ref = write_payload["entry"]["target_ref"]
    section_ref = f"{target_ref}:signal_code"
    initial_fingerprint = write_payload["entry"]["basis_fingerprint"]

    assert write_payload["stage_id"] == SetupStageId.WORLD_BACKGROUND.value
    assert target_ref.startswith("stage:world_background:")
    assert write_payload["entry"]["semantic_path"].startswith("world_background.")
    assert "stage_id" not in write_payload["entry"]

    list_payload = await _call(
        provider,
        "setup.stage_entry.list",
        {
            "workspace_id": workspace.workspace_id,
            "query": "Violet",
            "include_sections": True,
        },
    )
    assert [item["target_ref"] for item in list_payload["entries"]] == [target_ref]
    assert list_payload["entries"][0]["sections"][1]["section_id"] == "signal_code"

    read_payload = await _call(
        provider,
        "setup.stage_entry.read",
        {
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "include_sections": True,
        },
    )
    assert read_payload["entry"]["title"] == "Violet Harbor"
    assert read_payload["entry"]["basis_fingerprint"] == initial_fingerprint

    search_payload = await _call(
        provider,
        "setup.memory.search",
        {
            "workspace_id": workspace.workspace_id,
            "query": "tidewall lattice lanterns",
            "limit": 10,
        },
    )
    refs = _search_refs(search_payload)
    assert target_ref in refs
    assert section_ref in refs
    assert all("payload" not in item for item in search_payload["items"])
    assert all("source_kind" not in item for item in search_payload["items"])
    assert all("score" not in item for item in search_payload["items"])
    search_items = {item["ref"]: item for item in search_payload["items"]}
    assert search_items[target_ref]["scope"] == "entry"
    assert search_items[section_ref]["scope"] == "section"
    assert "open" in search_items[section_ref]["message"]

    entry_open_payload = await _call(
        provider,
        "setup.memory.open",
        {
            "workspace_id": workspace.workspace_id,
            "ref": target_ref,
            "max_chars": 4000,
        },
    )
    assert entry_open_payload["result_type"] == "index"
    assert "content" not in entry_open_payload
    assert section_ref in {item["ref"] for item in entry_open_payload["sections"]}

    section_open_payload = await _call(
        provider,
        "setup.memory.open",
        {
            "workspace_id": workspace.workspace_id,
            "ref": section_ref,
            "max_chars": 4000,
        },
    )
    assert section_open_payload["result_type"] == "content"
    assert section_open_payload["content"]["text"] == (
        "Blue lanterns unlock the tidewall lattice archive."
    )

    edit_payload = await _call(
        provider,
        "setup.stage_entry.edit",
        {
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": initial_fingerprint,
            "changes": {
                "summary": "Violet Harbor now tracks the eclipse ledger.",
                "upsert_sections": [
                    {
                        "title": "Eclipse Ledger",
                        "text": "The eclipse ledger reroutes every harbor oath.",
                        "retrieval_role": "detail",
                    }
                ],
                "add_tags": ["eclipse"],
                "remove_tags": ["tidewall"],
            },
        },
    )
    edited_fingerprint = edit_payload["entry"]["basis_fingerprint"]
    edited_section_ref = f"{target_ref}:eclipse_ledger"

    assert edited_fingerprint != initial_fingerprint
    assert edit_payload["entry"]["summary"] == (
        "Violet Harbor now tracks the eclipse ledger."
    )
    assert "eclipse" in edit_payload["entry"]["tags"]
    assert "tidewall" not in edit_payload["entry"]["tags"]

    edited_search_payload = await _call(
        provider,
        "setup.memory.search",
        {
            "workspace_id": workspace.workspace_id,
            "query": "eclipse ledger oath",
            "limit": 10,
        },
    )
    edited_refs = _search_refs(edited_search_payload)
    assert target_ref in edited_refs
    assert edited_section_ref in edited_refs

    edited_entry_open_payload = await _call(
        provider,
        "setup.memory.open",
        {
            "workspace_id": workspace.workspace_id,
            "ref": target_ref,
            "max_chars": 4000,
        },
    )
    assert edited_entry_open_payload["result_type"] == "index"
    assert edited_section_ref in {
        item["ref"] for item in edited_entry_open_payload["sections"]
    }

    edited_section_open_payload = await _call(
        provider,
        "setup.memory.open",
        {
            "workspace_id": workspace.workspace_id,
            "ref": edited_section_ref,
            "max_chars": 4000,
        },
    )
    assert edited_section_open_payload["content"]["text"] == (
        "The eclipse ledger reroutes every harbor oath."
    )

    delete_payload = await _call(
        provider,
        "setup.stage_entry.delete",
        {
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": edited_fingerprint,
            "reason": "integration cleanup",
        },
    )
    assert delete_payload["removed_refs"] == [target_ref]

    empty_list_payload = await _call(
        provider,
        "setup.stage_entry.list",
        {
            "workspace_id": workspace.workspace_id,
            "query": "Violet",
            "include_sections": True,
        },
    )
    assert empty_list_payload["entries"] == []

    empty_search_payload = await _call(
        provider,
        "setup.memory.search",
        {
            "workspace_id": workspace.workspace_id,
            "query": "eclipse ledger oath violet",
            "limit": 10,
        },
    )
    assert _search_refs(empty_search_payload) == []
