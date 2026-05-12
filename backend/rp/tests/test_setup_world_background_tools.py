"""Focused tests for world_background stage-local draft editing tools."""

from __future__ import annotations

import json

import pytest

from rp.agent_runtime.profiles import build_setup_agent_tool_scope
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


def test_world_background_provider_registration_does_not_make_tool_model_visible(
    retrieval_session,
):
    _, provider = _provider(retrieval_session)

    provider_tool_names = {tool.name for tool in provider.list_tools()}
    setup_scope = set(build_setup_agent_tool_scope("world_background"))

    assert "setup.world_background.write_entry" in provider_tool_names
    assert "setup.world_background.write_entry" not in setup_scope
    assert "setup.truth.write" in setup_scope


@pytest.mark.asyncio
async def test_world_background_tools_write_edit_delete_cyberpunk_entry(
    retrieval_session,
):
    workspace_service, provider = _provider(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-cyberpunk-world-tools",
        mode=StoryMode.LONGFORM,
    )

    write_result = await provider.call_tool(
        tool_name="setup.world_background.write_entry",
        arguments={
            "workspace_id": workspace.workspace_id,
            "entry_type": {
                "type_key": "city_state",
                "display_name": "城市国家",
                "description": "用于描述拥有独立治理结构的城市级政治实体。",
                "aliases": ["arcology_city"],
                "examples": ["霓虹湾"],
            },
            "title": "霓虹湾",
            "summary": "赛博朋克海湾城邦，由企业议会、街区帮派和底层黑市共同维持脆弱秩序。",
            "content_blocks": [
                {
                    "key": "权力结构",
                    "value": {
                        "企业议会": "控制税收、执法外包和主干网络。",
                        "街区帮派": "控制夜市、义体维修和地下交通。",
                    },
                    "retrieval_role": "detail",
                    "tags": ["governance", "corporate"],
                },
                {
                    "key": "黑市规则",
                    "value": [
                        "禁止出售未清洗的记忆芯片",
                        "义体医生必须向街区缴纳保护费",
                    ],
                    "retrieval_role": "rule",
                    "tags": ["black_market"],
                },
                {
                    "key": "与外海数据城的关系",
                    "value": "双方共享走私数据链路，但公开外交上互相否认合作。",
                    "retrieval_role": "relationship",
                    "tags": ["foreign_relation"],
                },
            ],
            "aliases": ["Neon Bay"],
            "tags": ["cyberpunk", "city"],
        },
    )

    assert write_result["success"] is True
    write_payload = json.loads(write_result["content"])
    entry = write_payload["entry"]
    target_ref = entry["target_ref"]
    original_fingerprint = entry["basis_fingerprint"]
    assert target_ref.startswith("stage:world_background:city_state_")
    assert entry["entry_type"] == "city_state"
    assert entry["semantic_path"].startswith("world_background.city_state.")
    assert entry["tags"] == ["world_background", "city_state", "cyberpunk", "city"]
    assert write_payload["entry_type_registry"][0]["type_key"] == "city_state"
    assert {section["title"] for section in entry["sections"]} == {
        "Summary",
        "权力结构",
        "黑市规则",
        "与外海数据城的关系",
    }
    assert {section["retrieval_role"] for section in entry["sections"]} >= {
        "summary",
        "detail",
        "rule",
        "relationship",
    }

    read_result = await provider.call_tool(
        tool_name="setup.world_background.read_entry",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "include_sections": True,
        },
    )
    read_payload = json.loads(read_result["content"])
    basis_fingerprint = read_payload["entry"]["basis_fingerprint"]
    assert basis_fingerprint == original_fingerprint

    edit_result = await provider.call_tool(
        tool_name="setup.world_background.edit_entry",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": basis_fingerprint,
            "changes": {
                "summary": "霓虹湾是被企业安保、街区自治和黑市协议共同切分的海湾城邦。",
                "upsert_content_blocks": [
                    {
                        "key": "黑市规则",
                        "value": [
                            "禁止出售未清洗的记忆芯片",
                            "义体医生必须向街区缴纳保护费",
                            "深网钥匙交易必须经过中立数据经纪人担保",
                        ],
                        "retrieval_role": "rule",
                        "tags": ["black_market", "deepnet"],
                    }
                ],
                "add_tags": ["corporate_city"],
            },
        },
    )

    assert edit_result["success"] is True
    edit_payload = json.loads(edit_result["content"])
    edited_entry = edit_payload["entry"]
    assert edited_entry["basis_fingerprint"] != basis_fingerprint
    assert "corporate_city" in edited_entry["tags"]
    black_market = next(
        section
        for section in edited_entry["sections"]
        if section["title"] == "黑市规则"
    )
    assert (
        black_market["content"]["items"][-1] == "深网钥匙交易必须经过中立数据经纪人担保"
    )

    stale_result = await provider.call_tool(
        tool_name="setup.world_background.edit_entry",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": basis_fingerprint,
            "changes": {"summary": "过期修改不应覆盖新草稿。"},
        },
    )
    assert stale_result["success"] is False
    assert stale_result["error_code"] == "SETUP_TOOL_FAILED"
    stale_payload = json.loads(stale_result["content"])
    assert stale_payload["code"] == "world_background_basis_fingerprint_mismatch"

    delete_result = await provider.call_tool(
        tool_name="setup.world_background.delete_entry",
        arguments={
            "workspace_id": workspace.workspace_id,
            "target_ref": target_ref,
            "basis_fingerprint": edited_entry["basis_fingerprint"],
            "reason": "端到端删除验证",
        },
    )
    assert delete_result["success"] is True

    final_workspace = workspace_service.get_workspace(workspace.workspace_id)
    assert final_workspace is not None
    block = final_workspace.draft_blocks[SetupStageId.WORLD_BACKGROUND.value]
    assert block.entries == []
    assert block.schema_metadata is not None
    assert block.schema_metadata.entry_types[0].type_key == "city_state"
