"""Unit tests for setup stage-local context governance helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from rp.agent_runtime.contracts import (
    DiscussionCandidateDirection,
    DiscussionState,
    SetupCognitiveSourceBasis,
    SetupCognitiveStateSnapshot,
    SetupCognitiveStateSummary,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.models.setup_agent import SetupAgentDialogueMessage
from rp.services.setup_context_compaction_service import SetupContextCompactionService
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
    assert compact_summary.recovery_hints[0].ref == "draft:story_config"
    assert metadata["compacted_history_count"] == 4
    assert metadata["raw_history_limit"] == 4
    assert metadata["summary_strategy"] == "deterministic_prefix_summary"
    assert metadata["summary_action"] == "rebuilt"

    standard_history, _, standard_metadata = governor.govern_history(
        history=history,
        retained_tool_outcomes=retained_outcomes,
        working_digest=None,
        existing_summary=None,
        context_profile="standard",
    )
    assert len(standard_history) == 6
    assert standard_metadata["raw_history_limit"] == 6


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

    _, reused_summary, metadata = governor.govern_history(
        history=history,
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=compact_summary,
        context_profile="standard",
    )

    assert reused_summary is compact_summary
    assert metadata["summary_action"] == "reused_existing"


def test_context_governor_updates_compact_summary_incrementally():
    governor = SetupContextGovernorService()

    _, compact_summary, _ = governor.govern_history(
        history=_history(8),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
    )
    assert compact_summary is not None

    kept_history, updated_summary, metadata = governor.govern_history(
        history=_history(10),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=compact_summary,
        context_profile="compact",
    )

    assert updated_summary is not None
    assert updated_summary is not compact_summary
    assert metadata["summary_action"] == "updated_existing"
    assert updated_summary.source_message_count == 6
    assert kept_history[0].content == "user message 6"
    assert "User: user message 4" in updated_summary.summary_lines
    assert "Assistant: assistant message 5" in updated_summary.summary_lines
    assert all(
        "message 6" not in line and "message 7" not in line
        for line in updated_summary.summary_lines
    )


def test_context_governor_first_compact_summary_starts_at_dropped_prefix_beginning():
    governor = SetupContextGovernorService()
    history = [
        SetupAgentDialogueMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=f"preface message {index}",
        )
        for index in range(12)
    ]

    kept_history, compact_summary, metadata = governor.govern_history(
        history=history,
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
    )

    assert compact_summary is not None
    assert metadata["summary_action"] == "rebuilt"
    assert compact_summary.source_message_count == 8
    assert kept_history[0].content == "preface message 8"
    assert compact_summary.summary_lines[0] == "User: preface message 0"
    assert compact_summary.summary_lines[-1] == "Assistant: preface message 5"
    assert all("message 8" not in line for line in compact_summary.summary_lines)


def test_context_governor_rebuilds_compact_summary_when_prefix_mismatches():
    governor = SetupContextGovernorService()

    _, compact_summary, _ = governor.govern_history(
        history=_history(8),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
    )
    assert compact_summary is not None

    changed_history = _history(10)
    changed_history[0] = SetupAgentDialogueMessage(
        role="user",
        content="changed user message 0",
    )

    _, rebuilt_summary, metadata = governor.govern_history(
        history=changed_history,
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=compact_summary,
        context_profile="compact",
    )

    assert rebuilt_summary is not None
    assert metadata["summary_action"] == "rebuilt"
    assert rebuilt_summary.source_message_count == 6
    assert rebuilt_summary.source_fingerprint != compact_summary.source_fingerprint
    assert rebuilt_summary.summary_lines[0].startswith("User: changed user message")


def test_context_governor_validates_compact_prompt_summary_and_records_strategy():
    def _compact_prompt_provider(_messages):
        return {
            "summary_lines": [f"line {index}" for index in range(8)],
            "confirmed_points": [f"point {index}" for index in range(10)],
            "open_threads": ["Need exact policy preset."],
            "rejected_directions": ["Do not use generic memory."],
            "draft_refs": ["draft:story_config"],
            "recovery_hints": [
                {
                    "ref": "draft:story_config",
                    "reason": "Need exact configured preset.",
                    "detail": "Recover through setup.read.draft_refs.",
                }
            ],
            "must_not_infer": ["Do not infer prior-stage raw discussion."],
        }

    governor = SetupContextGovernorService(
        compaction_service=SetupContextCompactionService(
            compact_prompt_provider=_compact_prompt_provider
        )
    )

    _, compact_summary, metadata = governor.govern_history(
        history=_history(8),
        retained_tool_outcomes=[],
        working_digest=SetupWorkingDigest(draft_refs=["draft:story_config"]),
        existing_summary=None,
        context_profile="compact",
        current_step="story_config",
    )

    assert compact_summary is not None
    assert metadata["summary_strategy"] == "compact_prompt_summary"
    assert metadata["summary_action"] == "rebuilt"
    assert metadata["fallback_reason"] is None
    assert len(compact_summary.summary_lines) == 6
    assert len(compact_summary.confirmed_points) == 8
    assert compact_summary.recovery_hints[0].ref == "draft:story_config"


def test_context_governor_passes_only_newly_compacted_messages_to_incremental_prompt():
    prompt_payloads: list[dict[str, Any]] = []

    def _compact_prompt_provider(messages):
        payload = json.loads(str(messages[1].content))
        prompt_payloads.append(payload)
        return {
            "summary_lines": [f"line {index}" for index in range(3)],
            "confirmed_points": ["point 0"],
            "open_threads": ["Need exact policy preset."],
            "rejected_directions": ["Do not use generic memory."],
            "draft_refs": ["draft:story_config"],
            "recovery_hints": [
                {
                    "ref": "draft:story_config",
                    "reason": "Need exact configured preset.",
                    "detail": "Recover through setup.read.draft_refs.",
                }
            ],
            "must_not_infer": ["Do not infer prior-stage raw discussion."],
        }

    governor = SetupContextGovernorService(
        compaction_service=SetupContextCompactionService(
            compact_prompt_provider=_compact_prompt_provider
        )
    )

    _, first_summary, first_metadata = governor.govern_history(
        history=_history(8),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
        current_step="story_config",
    )

    assert first_summary is not None
    assert first_metadata["summary_action"] == "rebuilt"
    assert len(prompt_payloads) == 1
    assert prompt_payloads[0]["incremental_update"] is False
    assert prompt_payloads[0]["newly_compacted_current_step_messages"] is None
    assert len(prompt_payloads[0]["dropped_current_step_messages"]) == 4
    assert prompt_payloads[0]["previous_compact_summary"] is None

    _, updated_summary, updated_metadata = governor.govern_history(
        history=_history(10),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=first_summary,
        context_profile="compact",
        current_step="story_config",
    )

    assert updated_summary is not None
    assert updated_metadata["summary_action"] == "updated_existing"
    assert updated_summary.source_message_count == 6
    assert len(prompt_payloads) == 2
    assert prompt_payloads[1]["incremental_update"] is True
    assert prompt_payloads[1]["previous_compact_summary"]["source_message_count"] == 4
    assert prompt_payloads[1]["dropped_current_step_messages"] is None
    assert [
        item["content"]
        for item in prompt_payloads[1]["newly_compacted_current_step_messages"]
    ] == ["user message 4", "assistant message 5"]
    assert "message 6" not in json.dumps(prompt_payloads[1], ensure_ascii=False)
    assert "message 7" not in json.dumps(prompt_payloads[1], ensure_ascii=False)


def test_context_governor_falls_back_when_compact_prompt_summary_is_invalid():
    def _invalid_compact_prompt_provider(_messages):
        return {
            "summary_lines": ["expert output should be rejected"],
            "analysis": "forbidden scratchpad",
        }

    governor = SetupContextGovernorService(
        compaction_service=SetupContextCompactionService(
            compact_prompt_provider=_invalid_compact_prompt_provider
        )
    )

    _, compact_summary, metadata = governor.govern_history(
        history=_history(8),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
        current_step="foundation",
    )

    assert compact_summary is not None
    assert metadata["summary_strategy"] == "deterministic_prefix_summary"
    assert metadata["summary_action"] == "rebuilt"
    assert "forbidden_fields" in metadata["fallback_reason"]
    assert compact_summary.summary_lines[0].startswith("User: user message")


def test_context_governor_falls_back_when_compact_prompt_summary_uses_unsupported_ref():
    def _unsupported_ref_provider(_messages):
        return {
            "summary_lines": ["Looks valid except for the ref."],
            "draft_refs": ["draft:story_config_extra"],
        }

    governor = SetupContextGovernorService(
        compaction_service=SetupContextCompactionService(
            compact_prompt_provider=_unsupported_ref_provider
        )
    )

    _, compact_summary, metadata = governor.govern_history(
        history=_history(8),
        retained_tool_outcomes=[],
        working_digest=None,
        existing_summary=None,
        context_profile="compact",
        current_step="story_config",
    )

    assert compact_summary is not None
    assert metadata["summary_strategy"] == "deterministic_prefix_summary"
    assert "unsupported_refs" in metadata["fallback_reason"]
    assert compact_summary.draft_refs == []


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
