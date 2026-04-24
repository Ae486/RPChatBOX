"""Unit tests for setup-agent runtime-private cognitive state storage."""
from __future__ import annotations

from datetime import datetime, timezone

from models.rp_setup_store import SetupPendingUserEditDeltaRecord
from rp.agent_runtime.contracts import ChunkCandidate, DiscussionState, DraftTruthWrite
from rp.models.setup_drafts import FoundationEntry
from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_workspace import SetupStepId, StoryMode
from rp.services.setup_agent_runtime_state_service import SetupAgentRuntimeStateService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService


def _build_context_packet(*, context_builder, workspace_id: str, step_id: SetupStepId):
    return context_builder.build(
        SetupContextBuilderInput(
            mode=StoryMode.LONGFORM.value,
            workspace_id=workspace_id,
            current_step=step_id.value,
            user_prompt="Let's continue setup.",
            user_edit_delta_ids=[],
            token_budget=None,
        )
    )


def test_runtime_state_service_persists_snapshot_and_summary(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-state-1",
        mode=StoryMode.LONGFORM,
    )
    context_packet = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
    )

    snapshot = runtime_state_service.replace_discussion_state(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        discussion_state=DiscussionState(
            current_step=SetupStepId.FOUNDATION.value,
            discussion_topic="World rules",
            confirmed_points=["Magic is public knowledge."],
            open_questions=["How costly is spellcasting?"],
        ),
    )
    snapshot = runtime_state_service.upsert_chunk(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        action="promote",
        chunk=ChunkCandidate(
            candidate_id="chunk-1",
            current_step=SetupStepId.FOUNDATION.value,
            block_type="foundation_entry",
            target_ref="foundation:magic",
            title="Magic Rules",
            content="Magic is public and regulated by guild law.",
            detail_level="usable",
        ),
    )
    snapshot = runtime_state_service.record_truth_write(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        truth_write=DraftTruthWrite(
            write_id="write-1",
            current_step=SetupStepId.FOUNDATION.value,
            block_type="foundation_entry",
            target_ref="foundation:magic",
            operation="create",
            payload=FoundationEntry(
                entry_id="magic",
                domain="rule",
                path="world.magic",
                content={"summary": "Magic is public and regulated."},
            ).model_dump(mode="json", exclude_none=True),
            ready_for_review=True,
        ),
    )

    loaded = runtime_state_service.get_snapshot(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
    )
    summary = runtime_state_service.summarize_for_prompt(loaded)

    assert loaded is not None
    assert loaded.discussion_state is not None
    assert loaded.discussion_state.discussion_topic == "World rules"
    assert loaded.chunk_candidates[0].detail_level == "truth_candidate"
    assert loaded.active_truth_write is not None
    assert loaded.active_truth_write.ready_for_review is True
    assert summary is not None
    assert summary.discussion_topic == "World rules"
    assert summary.candidate_titles == ["Magic Rules"]
    assert summary.truth_write_status == "ready_for_review"


def test_runtime_state_service_invalidates_snapshot_after_user_edit_delta(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-state-2",
        mode=StoryMode.LONGFORM,
    )
    context_packet = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
    )
    runtime_state_service.replace_discussion_state(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        discussion_state=DiscussionState(
            current_step=SetupStepId.FOUNDATION.value,
            discussion_topic="Guild law",
        ),
    )
    runtime_state_service.upsert_chunk(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        action="promote",
        chunk=ChunkCandidate(
            candidate_id="chunk-affected",
            current_step=SetupStepId.FOUNDATION.value,
            block_type="foundation_entry",
            target_ref="foundation:law",
            title="Guild Law",
            content="Guild law regulates magic.",
            detail_level="truth_candidate",
        ),
    )
    runtime_state_service.record_truth_write(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        truth_write=DraftTruthWrite(
            write_id="write-law",
            current_step=SetupStepId.FOUNDATION.value,
            block_type="foundation_entry",
            target_ref="foundation:law",
            operation="create",
            payload=FoundationEntry(
                entry_id="law",
                domain="rule",
                path="world.law",
                content={"summary": "Guild law regulates magic."},
            ).model_dump(mode="json", exclude_none=True),
            ready_for_review=True,
        ),
    )

    retrieval_session.add(
        SetupPendingUserEditDeltaRecord(
            delta_id="delta-1",
            workspace_id=workspace.workspace_id,
            step_id=SetupStepId.FOUNDATION.value,
            target_block="foundation_entry",
            target_ref="foundation:law",
            changes_json=[],
            created_at=datetime.now(timezone.utc),
            consumed_at=None,
        )
    )
    retrieval_session.commit()

    refreshed_workspace = workspace_service.get_workspace(workspace.workspace_id)
    refreshed_context = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
    )
    reconciled = runtime_state_service.reconcile_snapshot(
        workspace=refreshed_workspace,
        context_packet=refreshed_context,
        step_id=SetupStepId.FOUNDATION,
    )

    assert reconciled is not None
    assert reconciled.invalidated is True
    assert "user_edit_delta" in reconciled.invalidation_reasons
    assert reconciled.chunk_candidates[0].detail_level == "usable"
    assert reconciled.active_truth_write is not None
    assert reconciled.active_truth_write.ready_for_review is False
    assert "Latest draft changed after user edits." in reconciled.active_truth_write.remaining_open_issues


def test_runtime_state_service_keeps_unaffected_truth_candidates_stable(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-state-3",
        mode=StoryMode.LONGFORM,
    )
    context_packet = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
    )
    runtime_state_service.upsert_chunk(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        action="promote",
        chunk=ChunkCandidate(
            candidate_id="chunk-unaffected",
            current_step=SetupStepId.FOUNDATION.value,
            block_type="foundation_entry",
            target_ref="foundation:stable",
            title="Stable Fact",
            content="A stable fact.",
            detail_level="truth_candidate",
        ),
    )
    runtime_state_service.record_truth_write(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.FOUNDATION,
        truth_write=DraftTruthWrite(
            write_id="write-stable",
            current_step=SetupStepId.FOUNDATION.value,
            block_type="foundation_entry",
            target_ref="foundation:stable",
            operation="create",
            payload=FoundationEntry(
                entry_id="stable",
                domain="rule",
                path="world.stable",
                content={"summary": "A stable fact."},
            ).model_dump(mode="json", exclude_none=True),
            ready_for_review=True,
        ),
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

    refreshed_workspace = workspace_service.get_workspace(workspace.workspace_id)
    refreshed_context = context_builder.build(
        SetupContextBuilderInput(
            mode=StoryMode.LONGFORM.value,
            workspace_id=workspace.workspace_id,
            current_step=SetupStepId.FOUNDATION.value,
            user_prompt="Keep going.",
            user_edit_delta_ids=["delta-other"],
            token_budget=None,
        )
    )
    reconciled = runtime_state_service.reconcile_snapshot(
        workspace=refreshed_workspace,
        context_packet=refreshed_context,
        step_id=SetupStepId.FOUNDATION,
    )

    assert reconciled is not None
    assert reconciled.invalidated is True
    assert reconciled.chunk_candidates[0].detail_level == "truth_candidate"
    assert reconciled.chunk_candidates[0].unresolved_issues == []
    assert reconciled.active_truth_write is not None
    assert reconciled.active_truth_write.ready_for_review is True
