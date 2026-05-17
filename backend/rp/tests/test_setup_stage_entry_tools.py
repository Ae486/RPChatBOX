"""Focused tests for current-stage setup.stage_entry draft tools."""

from __future__ import annotations

import json

import pytest

from rp.models.setup_drafts import SetupStageDraftBlock
from rp.models.setup_stage import SetupStageId
from rp.models.setup_workspace import StoryMode
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider


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


async def _write_entry(provider, workspace_id: str, title: str):
    return await provider.call_tool(
        tool_name="setup.stage_entry.write",
        arguments={
            "workspace_id": workspace_id,
            "entry_type": "核心设定",
            "title": title,
            "summary": f"{title} summary.",
            "sections": [
                {
                    "title": "细节",
                    "text": f"{title} detail text.",
                    "retrieval_role": "detail",
                }
            ],
            "aliases": [f"{title} alias"],
            "tags": ["draft"],
        },
    )


@pytest.mark.parametrize(
    ("stage_id", "story_id", "title"),
    [
        (SetupStageId.WORLD_BACKGROUND, "story-stage-entry-world", "雾港"),
        (SetupStageId.CHARACTER_DESIGN, "story-stage-entry-character", "林月"),
        (SetupStageId.PLOT_BLUEPRINT, "story-stage-entry-plot", "失落钥匙"),
    ],
)
@pytest.mark.asyncio
async def test_stage_entry_write_uses_workspace_current_stage_draft_block(
    retrieval_session,
    stage_id,
    story_id,
    title,
):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(story_id=story_id, mode=StoryMode.LONGFORM)
    if stage_id != SetupStageId.WORLD_BACKGROUND:
        workspace_service.patch_stage_draft(
            workspace_id=workspace.workspace_id,
            stage_id=SetupStageId.WORLD_BACKGROUND,
            draft=SetupStageDraftBlock(stage_id=SetupStageId.WORLD_BACKGROUND),
        )
        workspace = workspace_service.accept_commit(
            workspace_id=workspace.workspace_id,
            proposal_id=workspace_service.propose_stage_commit(
                workspace_id=workspace.workspace_id,
                stage_id=SetupStageId.WORLD_BACKGROUND,
                target_draft_refs=["draft:world_background"],
            ).proposal_id,
        )[0] and workspace_service.get_workspace(workspace.workspace_id)
    if stage_id == SetupStageId.PLOT_BLUEPRINT:
        assert workspace is not None
        workspace_service.patch_stage_draft(
            workspace_id=workspace.workspace_id,
            stage_id=SetupStageId.CHARACTER_DESIGN,
            draft=SetupStageDraftBlock(stage_id=SetupStageId.CHARACTER_DESIGN),
        )
        workspace = workspace_service.accept_commit(
            workspace_id=workspace.workspace_id,
            proposal_id=workspace_service.propose_stage_commit(
                workspace_id=workspace.workspace_id,
                stage_id=SetupStageId.CHARACTER_DESIGN,
                target_draft_refs=["draft:character_design"],
            ).proposal_id,
        )[0] and workspace_service.get_workspace(workspace.workspace_id)

    assert workspace is not None
    assert workspace.current_stage == stage_id
    result = await _write_entry(provider, workspace.workspace_id, title)

    payload = json.loads(result["content"])
    refreshed = workspace_service.get_workspace(workspace.workspace_id)

    assert result["success"] is True
    assert payload["stage_id"] == stage_id.value
    assert payload["entry"]["target_ref"].startswith(f"stage:{stage_id.value}:")
    assert payload["entry"]["entry_type"]
    assert payload["entry"]["semantic_path"].startswith(f"{stage_id.value}.")
    assert refreshed is not None
    assert refreshed.draft_blocks[stage_id.value].entries[0].title == title
    for other_stage in {
        SetupStageId.WORLD_BACKGROUND,
        SetupStageId.CHARACTER_DESIGN,
        SetupStageId.PLOT_BLUEPRINT,
    } - {stage_id}:
        block = refreshed.draft_blocks.get(other_stage.value)
        assert block is None or block.entries == []


@pytest.mark.asyncio
async def test_stage_entry_schema_rejects_model_supplied_stage_id(retrieval_session):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-stage-entry-no-stage-id",
        mode=StoryMode.LONGFORM,
    )

    result = await provider.call_tool(
        tool_name="setup.stage_entry.write",
        arguments={
            "workspace_id": workspace.workspace_id,
            "stage_id": "character_design",
            "entry_type": "character",
            "title": "林月",
            "sections": [{"title": "概要", "text": "主角。"}],
        },
    )

    payload = json.loads(result["content"])
    assert result["success"] is False
    assert result["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["details"]["tool_name"] == "setup.stage_entry.write"
    assert "stage_id" in payload["details"]["provided_fields"]


@pytest.mark.asyncio
async def test_stage_entry_read_edit_delete_current_stage_entry(retrieval_session):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-stage-entry-crud",
        mode=StoryMode.LONGFORM,
    )
    write_result = await _write_entry(provider, workspace.workspace_id, "雾港")
    write_payload = json.loads(write_result["content"])
    target_ref = write_payload["entry"]["target_ref"]
    fingerprint = write_payload["entry"]["basis_fingerprint"]

    list_result = await provider.call_tool(
        tool_name="setup.stage_entry.list",
        arguments={"workspace_id": workspace.workspace_id, "include_sections": False},
    )
    list_payload = json.loads(list_result["content"])
    assert list_payload["entries"][0]["target_ref"] == target_ref
    assert "sections" not in list_payload["entries"][0]

    read_result = await provider.call_tool(
        tool_name="setup.stage_entry.read",
        arguments={"workspace_id": workspace.workspace_id, "target_ref": target_ref},
    )
    read_payload = json.loads(read_result["content"])
    assert read_payload["entry"]["basis_fingerprint"] == fingerprint

    edit_result = await provider.call_tool(
        tool_name="setup.stage_entry.edit",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": fingerprint,
            "changes": {
                "summary": "雾港由盐雾、走私航线和旧神信仰维持秩序。",
                "upsert_sections": [{"title": "禁忌", "text": "午夜后不可点灯。"}],
                "add_tags": ["harbor"],
            },
        },
    )
    edit_payload = json.loads(edit_result["content"])
    assert edit_result["success"] is True
    assert edit_payload["entry"]["basis_fingerprint"] != fingerprint
    assert "harbor" in edit_payload["entry"]["tags"]

    mismatch_result = await provider.call_tool(
        tool_name="setup.stage_entry.read",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref.replace("world_background", "character_design"),
        },
    )
    mismatch_payload = json.loads(mismatch_result["content"])
    assert mismatch_result["success"] is False
    assert mismatch_payload["code"] == "stage_entry_target_stage_mismatch"

    section_ref_result = await provider.call_tool(
        tool_name="setup.stage_entry.read",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": f"{target_ref}:summary",
        },
    )
    section_ref_payload = json.loads(section_ref_result["content"])
    assert section_ref_result["success"] is False
    assert section_ref_payload["code"] == "stage_entry_target_ref_invalid"

    delete_result = await provider.call_tool(
        tool_name="setup.stage_entry.delete",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": edit_payload["entry"]["basis_fingerprint"],
            "reason": "cleanup",
        },
    )
    assert delete_result["success"] is True
    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert refreshed is not None
    assert refreshed.draft_blocks[SetupStageId.WORLD_BACKGROUND.value].entries == []


@pytest.mark.asyncio
async def test_stage_entry_rejects_non_writable_current_stage(retrieval_session):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-stage-entry-non-writable",
        mode=StoryMode.LONGFORM,
    )
    for stage_id in (
        SetupStageId.WORLD_BACKGROUND,
        SetupStageId.CHARACTER_DESIGN,
        SetupStageId.PLOT_BLUEPRINT,
    ):
        workspace_service.patch_stage_draft(
            workspace_id=workspace.workspace_id,
            stage_id=stage_id,
            draft=SetupStageDraftBlock(stage_id=stage_id),
        )
        proposal = workspace_service.propose_stage_commit(
            workspace_id=workspace.workspace_id,
            stage_id=stage_id,
            target_draft_refs=[f"draft:{stage_id.value}"],
        )
        workspace_service.accept_commit(
            workspace_id=workspace.workspace_id,
            proposal_id=proposal.proposal_id,
        )

    result = await _write_entry(provider, workspace.workspace_id, "作家约束")
    payload = json.loads(result["content"])
    assert result["success"] is False
    assert payload["code"] == "stage_entry_stage_not_writable"
