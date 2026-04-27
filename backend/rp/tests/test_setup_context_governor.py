"""Unit tests for setup stage-local context governance helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from rp.agent_runtime.contracts import (
    DiscussionCandidateDirection,
    DiscussionState,
    SetupCognitiveSourceBasis,
    SetupCognitiveStateSnapshot,
    SetupCognitiveStateSummary,
    SetupToolOutcome,
)
from rp.models.setup_agent import SetupAgentDialogueMessage
from rp.services.setup_context_governor import SetupContextGovernorService


def _history(count: int) -> list[SetupAgentDialogueMessage]:
    items: list[SetupAgentDialogueMessage] = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        items.append(
            SetupAgentDialogueMessage(
                role=role,
                content=f"{role} message {index}",
            )
        )
    return items


def test_context_governor_keeps_recent_history_and_builds_compact_summary():
    governor = SetupContextGovernorService()
    history = _history(8)
    retained_outcomes = [
        SetupToolOutcome(
            tool_name="rp_setup__setup.patch.story_config",
            success=True,
            summary="Updated story config draft",
            updated_refs=["draft:story_config"],
            relevance="draft",
            recorded_at=datetime.now(timezone.utc),
        )
    ]

    kept_history, compact_summary, metadata = governor.govern_history(
        history=history,
        retained_tool_outcomes=retained_outcomes,
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
    )

    assert len(kept_history) == 4
    assert kept_history[0].content == "user message 4"
    assert compact_summary is not None
    assert compact_summary.source_message_count == 4
    assert compact_summary.draft_refs == ["draft:story_config"]
    assert metadata["compacted_history_count"] == 4


def test_context_governor_reuses_compact_summary_when_prefix_is_unchanged():
    governor = SetupContextGovernorService()
    history = _history(7)

    _, compact_summary, _ = governor.govern_history(
        history=history,
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="standard",
    )
    assert compact_summary is not None

    _, reused_summary, _ = governor.govern_history(
        history=history,
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=compact_summary,
        context_profile="standard",
    )

    assert reused_summary is compact_summary


def test_context_governor_retains_failure_before_superseded_successes():
    governor = SetupContextGovernorService()
    existing = [
        SetupToolOutcome(
            tool_name="rp_setup__setup.patch.story_config",
            success=True,
            summary="Updated story config draft",
            updated_refs=["draft:story_config"],
            relevance="draft",
            recorded_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
        )
    ]
    latest = [
        SetupToolOutcome(
            tool_name="rp_setup__setup.patch.story_config",
            success=True,
            summary="Updated story config draft again",
            updated_refs=["draft:story_config"],
            relevance="draft",
            recorded_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        ),
        SetupToolOutcome(
            tool_name="rp_setup__setup.truth.write",
            success=False,
            summary="Truth write still needs refinement.",
            updated_refs=[],
            error_code="SETUP_TOOL_FAILED",
            relevance="failure",
            recorded_at=datetime(2026, 4, 28, 1, tzinfo=timezone.utc),
        ),
    ]

    retained = governor.retain_tool_outcomes(existing=existing, latest_results=latest)

    assert retained[0].success is False
    assert retained[0].tool_name == "rp_setup__setup.truth.write"
    assert len([item for item in retained if item.tool_name.endswith("story_config")]) == 1


def test_context_governor_builds_initial_digest_from_cognitive_state():
    governor = SetupContextGovernorService()
    snapshot = SetupCognitiveStateSnapshot(
        workspace_id="workspace-1",
        current_step="foundation",
        discussion_state=DiscussionState(
            current_step="foundation",
            discussion_topic="World rules",
            open_questions=["How costly is spellcasting?"],
            next_focus="Clarify magic cost",
            candidate_directions=[
                DiscussionCandidateDirection(
                    direction_id="dir-1",
                    label="Public magic",
                    summary="Magic is public knowledge.",
                    status="discarded",
                )
            ],
        ),
        source_basis=SetupCognitiveSourceBasis(
            workspace_version=1,
            current_step="foundation",
        ),
    )
    summary = SetupCognitiveStateSummary(
        current_step="foundation",
        open_questions=["How costly is spellcasting?"],
        remaining_open_issues=["Need one concrete guild rule."],
    )

    digest = governor.build_initial_digest(
        cognitive_state=snapshot,
        cognitive_state_summary=summary,
        blocking_open_question_count=1,
        last_proposal_status="rejected",
    )

    assert digest is not None
    assert digest.next_focus == "Clarify magic cost"
    assert digest.open_questions == ["How costly is spellcasting?"]
    assert digest.rejected_directions == ["Public magic"]
    assert "1 blocking_open_question(s)" in digest.commit_blockers
    assert "proposal_rejected" in digest.commit_blockers
