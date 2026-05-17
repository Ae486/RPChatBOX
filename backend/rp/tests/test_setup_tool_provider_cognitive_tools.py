"""Unit tests for setup cognitive tools exposed by SetupToolProvider."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from models.rp_setup_store import SetupPendingUserEditDeltaRecord
from rp.agent_runtime.contracts import ChunkCandidate, DiscussionState, DraftTruthWrite
from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.tools.setup_tool_provider import SetupToolProvider


async def _call(provider: SetupToolProvider, tool_name: str, arguments: dict):
    return await provider.call_tool(tool_name=tool_name, arguments=arguments)


@pytest.mark.asyncio
async def test_runtime_state_service_updates_cognitive_state(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)

    workspace = workspace_service.create_workspace(
        story_id="story-cognitive-tools-1",
        mode=StoryMode.LONGFORM,
    )

    context_packet = context_builder.build(
        SetupContextBuilderInput(
            mode=StoryMode.LONGFORM.value,
            workspace_id=workspace.workspace_id,
            current_step=SetupStepId.STORY_CONFIG.value,
            user_prompt="",
            user_edit_delta_ids=[],
            token_budget=None,
        )
    )
    discussion_snapshot = runtime_state_service.replace_discussion_state(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.STORY_CONFIG,
        discussion_state=DiscussionState(
            current_step=SetupStepId.STORY_CONFIG.value,
            discussion_topic="Runtime profile",
            confirmed_points=["Use a concise post-write policy preset."],
        ),
    )
    chunk_snapshot = runtime_state_service.upsert_chunk(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.STORY_CONFIG,
        action="promote",
        chunk=ChunkCandidate(
            candidate_id="chunk-story-config",
            current_step=SetupStepId.STORY_CONFIG.value,
            block_type="story_config",
            title="Story Config Notes",
            content="Use concise notes and a stable post-write preset.",
            detail_level="usable",
        ),
    )

    assert discussion_snapshot.discussion_state is not None
    assert discussion_snapshot.discussion_state.discussion_topic == "Runtime profile"
    assert chunk_snapshot.chunk_candidates[0].detail_level == "truth_candidate"


@pytest.mark.asyncio
async def test_runtime_state_service_discussion_update_can_use_selected_user_edit_deltas(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)

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

    context_packet = context_builder.build(
        SetupContextBuilderInput(
            mode=StoryMode.LONGFORM.value,
            workspace_id=workspace.workspace_id,
            current_step=SetupStepId.FOUNDATION.value,
            user_prompt="",
            user_edit_delta_ids=["delta-selected"],
            token_budget=None,
        )
    )
    snapshot = runtime_state_service.replace_discussion_state(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        discussion_state=DiscussionState(
            current_step=SetupStepId.FOUNDATION.value,
            discussion_topic="Reconcile one selected edit",
        ),
    )

    assert snapshot.source_basis.pending_user_edit_delta_ids == [
        "delta-selected"
    ]


@pytest.mark.parametrize(
    "tool_name",
    [
        "setup.truth.write",
        "setup.read.step_context",
    ],
)
@pytest.mark.asyncio
async def test_setup_tool_provider_removed_cognitive_tools_are_no_longer_agent_callable(
    retrieval_session,
    tool_name,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    provider = SetupToolProvider(
        workspace_service=workspace_service,
        context_builder=context_builder,
        runtime_state_service=runtime_state_service,
    )

    result = await _call(
        provider,
        tool_name,
        {
            "workspace_id": "workspace-removed",
            "step_id": SetupStepId.FOUNDATION.value,
        },
    )
    payload = json.loads(result["content"])

    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_TOOL"
    assert payload["code"] == "unknown_tool"


@pytest.mark.asyncio
async def test_setup_tool_provider_commit_warns_when_truth_write_not_ready_even_without_open_issues(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)

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

    proposal = workspace_service.propose_commit(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
        target_draft_refs=["draft:story_config"],
        unresolved_warnings=["truth_write_not_ready_for_review"],
    )

    refreshed = workspace_service.get_workspace(workspace.workspace_id)
    assert refreshed is not None
    assert proposal.unresolved_warnings == ["truth_write_not_ready_for_review"]
    assert refreshed.commit_proposals[-1].unresolved_warnings == [
        "truth_write_not_ready_for_review"
    ]
