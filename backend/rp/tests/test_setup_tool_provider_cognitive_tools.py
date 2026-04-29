"""Unit tests for setup cognitive tools exposed by SetupToolProvider."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from models.rp_setup_store import SetupPendingUserEditDeltaRecord
from rp.agent_runtime.contracts import ChunkCandidate, DiscussionState, DraftTruthWrite
from rp.models.setup_drafts import StoryConfigDraft
from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider


async def _call(provider: SetupToolProvider, tool_name: str, arguments: dict):
    return await provider.call_tool(tool_name=tool_name, arguments=arguments)


@pytest.mark.asyncio
async def test_setup_tool_provider_updates_cognitive_state_and_writes_truth(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-1",
        mode=StoryMode.LONGFORM,
    )

    discussion_result = await _call(
        provider,
        "setup.discussion.update_state",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.STORY_CONFIG.value,
            "discussion_state": DiscussionState(
                current_step=SetupStepId.STORY_CONFIG.value,
                discussion_topic="Runtime profile",
                confirmed_points=["Use a concise post-write policy preset."],
            ).model_dump(mode="json", exclude_none=True),
        },
    )
    discussion_payload = json.loads(discussion_result["content"])

    assert discussion_result["success"] is True
    assert discussion_payload["cognitive_state_snapshot"]["discussion_state"]["discussion_topic"] == "Runtime profile"

    chunk_result = await _call(
        provider,
        "setup.chunk.upsert",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.STORY_CONFIG.value,
            "action": "promote",
            "chunk": ChunkCandidate(
                candidate_id="chunk-story-config",
                current_step=SetupStepId.STORY_CONFIG.value,
                block_type="story_config",
                title="Story Config Notes",
                content="Use concise notes and a stable post-write preset.",
                detail_level="usable",
            ).model_dump(mode="json", exclude_none=True),
        },
    )
    chunk_payload = json.loads(chunk_result["content"])
    assert chunk_result["success"] is True
    assert chunk_payload["cognitive_state_snapshot"]["chunk_candidates"][0]["detail_level"] == "truth_candidate"

    truth_write_result = await _call(
        provider,
        "setup.truth.write",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.STORY_CONFIG.value,
            "truth_write": DraftTruthWrite(
                write_id="truth-story-config",
                current_step=SetupStepId.STORY_CONFIG.value,
                block_type="story_config",
                operation="merge",
                payload={
                    "post_write_policy_preset": "concise",
                    "notes": "Keep outputs concise and stable.",
                },
                ready_for_review=True,
            ).model_dump(mode="json", exclude_none=True),
        },
    )
    truth_write_payload = json.loads(truth_write_result["content"])
    refreshed_workspace = workspace_service.get_workspace(workspace.workspace_id)

    assert truth_write_result["success"] is True
    assert refreshed_workspace.story_config_draft is not None
    assert refreshed_workspace.story_config_draft.post_write_policy_preset == "concise"
    assert truth_write_payload["updated_refs"] == ["draft:story_config"]
    assert truth_write_payload["cognitive_state_snapshot"]["active_truth_write"]["ready_for_review"] is True


@pytest.mark.asyncio
async def test_setup_tool_provider_discussion_update_can_use_selected_user_edit_deltas(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-1b",
        mode=StoryMode.LONGFORM,
    )
    retrieval_session.add(
        SetupPendingUserEditDeltaRecord(
            delta_id="delta-selected",
            workspace_id=workspace.workspace_id,
            step_id=SetupStepId.FOUNDATION.value,
            target_block="foundation_entry",
            target_ref="foundation:selected",
            changes_json=[],
            created_at=datetime.now(timezone.utc),
            consumed_at=None,
        )
    )
    retrieval_session.add(
        SetupPendingUserEditDeltaRecord(
            delta_id="delta-other",
            workspace_id=workspace.workspace_id,
            step_id=SetupStepId.FOUNDATION.value,
            target_block="foundation_entry",
            target_ref="foundation:other",
            changes_json=[],
            created_at=datetime.now(timezone.utc),
            consumed_at=None,
        )
    )
    retrieval_session.commit()

    discussion_result = await _call(
        provider,
        "setup.discussion.update_state",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.FOUNDATION.value,
            "user_edit_delta_ids": ["delta-selected"],
            "discussion_state": DiscussionState(
                current_step=SetupStepId.FOUNDATION.value,
                discussion_topic="Reconcile one selected edit",
            ).model_dump(mode="json", exclude_none=True),
        },
    )
    discussion_payload = json.loads(discussion_result["content"])

    assert discussion_result["success"] is True
    assert discussion_payload["cognitive_state_snapshot"]["source_basis"]["pending_user_edit_delta_ids"] == [
        "delta-selected"
    ]


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_validation_failure_surfaces_schema_error(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-2",
        mode=StoryMode.LONGFORM,
    )
    result = await _call(
        provider,
        "setup.truth.write",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.FOUNDATION.value,
            "truth_write": {
                "write_id": "bad-foundation",
                "current_step": SetupStepId.FOUNDATION.value,
                "block_type": "foundation_entry",
                "operation": "create",
                "payload": {"title": "Missing required fields"},
            },
        },
    )
    payload = json.loads(result["content"])

    assert result["success"] is False
    assert result["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["code"] == "schema_validation_failed"


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_can_require_user_input(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-3",
        mode=StoryMode.LONGFORM,
    )
    result = await _call(
        provider,
        "setup.truth.write",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.WRITING_CONTRACT.value,
            "truth_write": {
                "write_id": "empty-contract",
                "current_step": SetupStepId.WRITING_CONTRACT.value,
                "block_type": "writing_contract",
                "operation": "merge",
                "payload": {},
            },
        },
    )
    payload = json.loads(result["content"])

    assert result["success"] is False
    assert result["error_code"] == "SETUP_TOOL_FAILED"
    assert payload["details"]["repair_strategy"] == "ask_user"
    assert payload["details"]["ask_user"] is True


@pytest.mark.asyncio
async def test_setup_tool_provider_commit_warns_when_truth_write_not_ready_even_without_open_issues(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-3b",
        mode=StoryMode.LONGFORM,
    )
    runtime_state_service.record_truth_write(
        workspace=workspace,
        context_packet=context_builder.build(
            SetupContextBuilderInput(
                mode=StoryMode.LONGFORM.value,
                workspace_id=workspace.workspace_id,
                current_step=SetupStepId.STORY_CONFIG.value,
                user_prompt="",
                user_edit_delta_ids=[],
                token_budget=None,
            )
        ),
        step_id=SetupStepId.STORY_CONFIG,
        truth_write=DraftTruthWrite(
            write_id="truth-not-ready",
            current_step=SetupStepId.STORY_CONFIG.value,
            block_type="story_config",
            operation="merge",
            payload={"notes": "drafted but not reviewed"},
            ready_for_review=False,
            remaining_open_issues=[],
        ),
    )

    result = await _call(
        provider,
        "setup.proposal.commit",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.STORY_CONFIG.value,
            "target_draft_refs": ["draft:story_config"],
        },
    )
    payload = json.loads(result["content"])

    assert result["success"] is True
    assert result["error_code"] is None
    assert payload["warnings"] == ["truth_write_not_ready_for_review"]
    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert refreshed is not None
    assert refreshed.commit_proposals[-1].unresolved_warnings == [
        "truth_write_not_ready_for_review"
    ]


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_merge_preserves_existing_singleton_fields(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-3c",
        mode=StoryMode.LONGFORM,
    )
    workspace_service.patch_story_config(
        workspace_id=workspace.workspace_id,
        patch=StoryConfigDraft(
            model_profile_ref="model-a",
            post_write_policy_preset="concise",
        ),
    )
    result = await _call(
        provider,
        "setup.truth.write",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.STORY_CONFIG.value,
            "truth_write": {
                "write_id": "merge-story-config",
                "current_step": SetupStepId.STORY_CONFIG.value,
                "block_type": "story_config",
                "target_ref": "draft:story_config",
                "operation": "merge",
                "payload": {
                    "notes": "new notes",
                },
                "ready_for_review": True,
            },
        },
    )
    payload = json.loads(result["content"])
    refreshed_workspace = workspace_service.get_workspace(workspace.workspace_id)

    assert result["success"] is True
    assert refreshed_workspace.story_config_draft is not None
    assert refreshed_workspace.story_config_draft.model_profile_ref == "model-a"
    assert refreshed_workspace.story_config_draft.notes == "new notes"
    assert payload["updated_refs"] == ["draft:story_config"]


@pytest.mark.asyncio
async def test_setup_tool_provider_truth_write_rejects_target_ref_mismatch(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-3d",
        mode=StoryMode.LONGFORM,
    )
    result = await _call(
        provider,
        "setup.truth.write",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.STORY_CONFIG.value,
            "truth_write": {
                "write_id": "bad-target-ref",
                "current_step": SetupStepId.STORY_CONFIG.value,
                "block_type": "story_config",
                "target_ref": "draft:writing_contract",
                "operation": "replace",
                "payload": {
                    "notes": "wrong target",
                },
            },
        },
    )
    payload = json.loads(result["content"])

    assert result["success"] is False
    assert result["error_code"] == "SETUP_TOOL_FAILED"
    assert payload["code"] == "setup_truth_write_target_ref_mismatch"


@pytest.mark.asyncio
async def test_setup_tool_provider_read_step_context_can_filter_user_edit_deltas(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-4",
        mode=StoryMode.LONGFORM,
    )
    retrieval_session.add(
        SetupPendingUserEditDeltaRecord(
            delta_id="delta-included",
            workspace_id=workspace.workspace_id,
            step_id=SetupStepId.FOUNDATION.value,
            target_block="foundation_entry",
            target_ref="foundation:included",
            changes_json=[],
            created_at=datetime.now(timezone.utc),
            consumed_at=None,
        )
    )
    retrieval_session.add(
        SetupPendingUserEditDeltaRecord(
            delta_id="delta-excluded",
            workspace_id=workspace.workspace_id,
            step_id=SetupStepId.FOUNDATION.value,
            target_block="foundation_entry",
            target_ref="foundation:excluded",
            changes_json=[],
            created_at=datetime.now(timezone.utc),
            consumed_at=None,
        )
    )
    retrieval_session.commit()

    result = await _call(
        provider,
        "setup.read.step_context",
        {
            "workspace_id": workspace.workspace_id,
            "step_id": SetupStepId.FOUNDATION.value,
            "user_edit_delta_ids": ["delta-included"],
        },
    )
    payload = json.loads(result["content"])

    assert result["success"] is True
    assert [item["delta_id"] for item in payload["user_edit_deltas"]] == ["delta-included"]
