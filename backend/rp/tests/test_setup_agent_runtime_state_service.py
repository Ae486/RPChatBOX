"""Unit tests for setup-agent runtime-private cognitive state storage."""

from __future__ import annotations

from datetime import datetime, timezone

from models.rp_setup_store import SetupPendingUserEditDeltaRecord

from rp.agent_runtime.contracts import (
    ChunkCandidate,
    DiscussionState,
    DraftTruthWrite,
    SetupContextCompactSummary,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.models.setup_drafts import (
    ChapterBlueprintEntry,
    FoundationEntry,
    LongformBlueprintDraft,
)
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

    runtime_state_service.replace_discussion_state(
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
    runtime_state_service.upsert_chunk(
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
    runtime_state_service.record_truth_write(
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


def test_runtime_state_service_persists_turn_governance(retrieval_session):
    workspace_service = SetupWorkspaceService(retrieval_session)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-governance-1",
        mode=StoryMode.LONGFORM,
    )
    context_packet = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
    )

    runtime_state_service.persist_turn_governance(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.STORY_CONFIG,
        working_digest=SetupWorkingDigest(
            current_goal="Clarify story config",
            next_focus="Lock the post-write policy",
            open_questions=["Which policy preset should be used?"],
            draft_refs=["draft:story_config"],
            commit_blockers=["1 blocking_open_question(s)"],
        ),
        tool_outcomes=[
            SetupToolOutcome(
                tool_name="rp_setup__setup.patch.story_config",
                success=True,
                summary="Updated story config draft",
                updated_refs=["draft:story_config"],
                relevance="draft",
                recorded_at=datetime.now(timezone.utc),
            )
        ],
        compact_summary=SetupContextCompactSummary(
            source_fingerprint="history-fp-1",
            source_message_count=4,
            summary_lines=["User: wants a stricter policy preset."],
            open_threads=["Need exact preset name."],
            draft_refs=["draft:story_config"],
        ),
    )

    loaded = runtime_state_service.get_snapshot(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
    )
    summary = runtime_state_service.summarize_for_prompt(loaded)

    assert loaded is not None
    assert loaded.working_digest is not None
    assert loaded.working_digest.current_goal == "Clarify story config"
    assert loaded.tool_outcomes[0].tool_name == "rp_setup__setup.patch.story_config"
    assert loaded.compact_summary is not None
    assert loaded.compact_summary.source_message_count == 4
    assert summary is not None
    assert summary.working_digest is not None
    assert summary.working_digest.next_focus == "Lock the post-write policy"
    assert summary.tool_outcomes[0].updated_refs == ["draft:story_config"]
    assert summary.compact_summary is not None
    assert summary.compact_summary.open_threads == ["Need exact preset name."]


def test_runtime_state_service_turn_governance_snapshot_excludes_loop_trace_fields(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    runtime_state_service = SetupAgentRuntimeStateService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-governance-2",
        mode=StoryMode.LONGFORM,
    )
    context_packet = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
    )

    runtime_state_service.persist_turn_governance(
        workspace=workspace,
        context_packet=context_packet,
        step_id=SetupStepId.STORY_CONFIG,
        working_digest=SetupWorkingDigest(current_goal="Clarify story config"),
        tool_outcomes=[],
        compact_summary=None,
    )

    raw_record = runtime_state_service._get_record(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.STORY_CONFIG,
    )

    assert raw_record is not None
    assert "loop_trace" not in raw_record.snapshot_json
    assert "continue_reason" not in raw_record.snapshot_json
    assert "context_report" not in raw_record.snapshot_json


def test_runtime_state_service_invalidates_snapshot_after_user_edit_delta(
    retrieval_session,
):
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
    assert (
        "Latest draft changed after user edits."
        in reconciled.active_truth_write.remaining_open_issues
    )


def test_runtime_state_service_keeps_unaffected_truth_candidates_stable(
    retrieval_session,
):
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


def test_context_builder_prefers_compact_prior_stage_handoffs_for_new_stage_context(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-state-4",
        mode=StoryMode.LONGFORM,
    )
    workspace = workspace_service.patch_foundation_entry(
        workspace_id=workspace.workspace_id,
        entry=FoundationEntry(
            entry_id="magic-law",
            domain="rule",
            path="world.magic.law",
            title="Magic Law",
            content={
                "summary": "Public spellcasting is regulated by guild permits.",
                "open_issues": ["Need guild exception process."],
            },
        ),
    )
    proposal = workspace_service.propose_commit(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
        target_draft_refs=["draft:foundation"],
    )
    workspace_service.accept_commit(
        workspace_id=workspace.workspace_id,
        proposal_id=proposal.proposal_id,
    )

    workspace = workspace_service.patch_longform_blueprint(
        workspace_id=workspace.workspace_id,
        patch=LongformBlueprintDraft(
            premise="A guild clerk uncovers illegal spell permits.",
        ),
    )
    retrieval_session.add(
        SetupPendingUserEditDeltaRecord(
            delta_id="delta-blueprint",
            workspace_id=workspace.workspace_id,
            step_id=SetupStepId.LONGFORM_BLUEPRINT.value,
            target_block="longform_blueprint",
            target_ref="longform_blueprint",
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
            current_step=SetupStepId.LONGFORM_BLUEPRINT.value,
            user_prompt="Build the chapter plan next.",
            user_edit_delta_ids=["delta-blueprint"],
            token_budget=None,
        )
    )

    assert context_packet.current_draft_snapshot["premise"] == (
        "A guild clerk uncovers illegal spell permits."
    )
    assert [item["delta_id"] for item in context_packet.user_edit_deltas] == [
        "delta-blueprint"
    ]
    assert [
        handoff.step_id.value for handoff in context_packet.prior_stage_handoffs
    ] == [SetupStepId.FOUNDATION.value]
    foundation_handoff = context_packet.prior_stage_handoffs[0]
    assert foundation_handoff.workspace_id == workspace.workspace_id
    assert foundation_handoff.from_step == SetupStepId.FOUNDATION
    assert foundation_handoff.to_step == SetupStepId.LONGFORM_BLUEPRINT
    assert foundation_handoff.summary == "world.magic.law"
    assert foundation_handoff.summary_tier_0 == "Committed 1 foundation entries"
    assert foundation_handoff.summary_tier_1 == "world.magic.law"
    assert foundation_handoff.spotlights == ["Magic Law"]
    assert foundation_handoff.open_issues == ["Need guild exception process."]
    assert foundation_handoff.retrieval_refs == ["magic-law"]
    assert foundation_handoff.warnings == []
    assert foundation_handoff.source_basis.workspace_id == workspace.workspace_id
    assert foundation_handoff.source_basis.commit_id
    assert foundation_handoff.source_basis.snapshot_block_types == ["foundation"]
    assert foundation_handoff.chunk_descriptions[0].title == "Magic Law"
    assert foundation_handoff.chunk_descriptions[0].description == (
        "rule | world.magic.law - Public spellcasting is regulated by guild permits."
    )
    assert context_packet.committed_summaries == ["world.magic.law"]
    assert context_packet.spotlights == ["Magic Law"]


def test_context_builder_derives_blueprint_handoff_chunk_descriptions_from_accepted_commit(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-state-5",
        mode=StoryMode.LONGFORM,
    )
    workspace = workspace_service.patch_foundation_entry(
        workspace_id=workspace.workspace_id,
        entry=FoundationEntry(
            entry_id="city",
            domain="world",
            path="setting.city",
            title="Permit City",
            content={"summary": "Guild bureaucracy controls urban magic."},
        ),
    )
    foundation_proposal = workspace_service.propose_commit(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
        target_draft_refs=["draft:foundation"],
    )
    workspace_service.accept_commit(
        workspace_id=workspace.workspace_id,
        proposal_id=foundation_proposal.proposal_id,
    )

    workspace = workspace_service.patch_longform_blueprint(
        workspace_id=workspace.workspace_id,
        patch=LongformBlueprintDraft(
            premise="A permit clerk finds a forged license ring.",
            central_conflict="Truth threatens the guild hierarchy.",
            chapter_strategy="Escalate from office intrigue to public exposure.",
            chapter_blueprints=[
                ChapterBlueprintEntry(
                    chapter_id="ch1",
                    title="Audit Day",
                    purpose="Introduce the forged permits and the clerk's dilemma.",
                ),
                ChapterBlueprintEntry(
                    chapter_id="ch2",
                    title="Silent Witness",
                    purpose="Show the cost of speaking up inside the guild.",
                ),
            ],
        ),
    )
    blueprint_proposal = workspace_service.propose_commit(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.LONGFORM_BLUEPRINT,
        target_draft_refs=["draft:blueprint"],
    )
    workspace_service.accept_commit(
        workspace_id=workspace.workspace_id,
        proposal_id=blueprint_proposal.proposal_id,
    )

    context_packet = _build_context_packet(
        context_builder=context_builder,
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.WRITING_CONTRACT,
    )

    assert [
        handoff.step_id.value for handoff in context_packet.prior_stage_handoffs
    ] == [
        SetupStepId.FOUNDATION.value,
        SetupStepId.LONGFORM_BLUEPRINT.value,
    ]
    blueprint_handoff = context_packet.prior_stage_handoffs[1]
    assert blueprint_handoff.from_step == SetupStepId.LONGFORM_BLUEPRINT
    assert blueprint_handoff.to_step == SetupStepId.WRITING_CONTRACT
    assert blueprint_handoff.summary == "A permit clerk finds a forged license ring."
    assert blueprint_handoff.summary_tier_0 == "Committed longform blueprint"
    assert blueprint_handoff.summary_tier_1 == (
        "A permit clerk finds a forged license ring."
    )
    assert blueprint_handoff.retrieval_refs == ["longform_blueprint"]
    assert blueprint_handoff.warnings == []
    assert blueprint_handoff.open_issues == []
    assert blueprint_handoff.source_basis.snapshot_block_types == [
        "longform_blueprint"
    ]
    assert [chunk.title for chunk in blueprint_handoff.chunk_descriptions] == [
        "Blueprint Overview",
        "Audit Day",
        "Silent Witness",
    ]
    assert blueprint_handoff.chunk_descriptions[1].description == (
        "Introduce the forged permits and the clerk's dilemma."
    )
    assert blueprint_handoff.chunk_descriptions[2].metadata["chapter_id"] == "ch2"


def test_context_builder_drops_chunk_descriptions_when_token_budget_is_compact(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    context_builder = SetupContextBuilder(workspace_service)

    workspace = workspace_service.create_workspace(
        story_id="story-runtime-state-6",
        mode=StoryMode.LONGFORM,
    )
    workspace = workspace_service.patch_foundation_entry(
        workspace_id=workspace.workspace_id,
        entry=FoundationEntry(
            entry_id="guild-law",
            domain="rule",
            path="world.guild_law",
            title="Guild Law",
            content={"summary": "Guild law regulates public spellcasting."},
        ),
    )
    proposal = workspace_service.propose_commit(
        workspace_id=workspace.workspace_id,
        step_id=SetupStepId.FOUNDATION,
        target_draft_refs=["draft:foundation"],
    )
    workspace_service.accept_commit(
        workspace_id=workspace.workspace_id,
        proposal_id=proposal.proposal_id,
    )

    context_packet = context_builder.build(
        SetupContextBuilderInput(
            mode=StoryMode.LONGFORM.value,
            workspace_id=workspace.workspace_id,
            current_step=SetupStepId.LONGFORM_BLUEPRINT.value,
            user_prompt="Keep planning.",
            user_edit_delta_ids=[],
            token_budget=600,
        )
    )

    assert context_packet.context_profile == "compact"
    assert context_packet.prior_stage_handoffs
    assert context_packet.prior_stage_handoffs[0].chunk_descriptions == []
    assert context_packet.prior_stage_handoffs[0].retrieval_refs == ["guild-law"]
    assert context_packet.prior_stage_handoffs[0].summary_tier_0 == (
        "Committed 1 foundation entries"
    )
    assert context_packet.committed_summaries == ["Committed 1 foundation entries"]
