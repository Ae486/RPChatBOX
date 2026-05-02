"""Unit tests for setup cognitive runtime policies."""
from __future__ import annotations

from rp.agent_runtime.contracts import (
    RuntimeProfile,
    RuntimeToolResult,
    SetupActionExpectation,
    SetupCognitiveStateSummary,
    SetupCompactRecoveryHint,
    SetupContextCompactSummary,
    SetupPendingObligation,
    SetupReflectionTicket,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.agent_runtime.policies import (
    ActionDecisionPolicy,
    CompletionGuardPolicy,
    ReflectionTriggerPolicy,
    RepairDecisionPolicy,
    ToolFailureClassifier,
)


def _profile() -> RuntimeProfile:
    return RuntimeProfile(
        profile_id="setup_agent",
        visible_tool_names=["setup.patch.story_config"],
        max_rounds=8,
        allow_stream=True,
        recovery_policy="setup_agent_v1",
        finish_policy="assistant_text_or_failure",
    )


def _compact_summary() -> SetupContextCompactSummary:
    return SetupContextCompactSummary(
        source_fingerprint="fp-compact",
        source_message_count=8,
        summary_lines=["Earlier current-step discussion was compacted."],
        draft_refs=["foundation:magic-law"],
        recovery_hints=[
            SetupCompactRecoveryHint(
                ref="foundation:magic-law",
                reason="Exact magic-law detail was moved into the draft.",
            )
        ],
    )


def test_action_decision_policy_requires_draft_ref_read_for_exact_compact_detail():
    expectation = ActionDecisionPolicy.assess(
        user_prompt="之前写入草稿的 magic-law 完整内容是什么？",
        turn_goal=None,
        working_plan=None,
        pending_obligation=None,
        compact_summary=_compact_summary(),
        tool_results=[],
    )

    assert expectation is not None
    assert expectation.expectation_type == "read_draft_refs"
    assert expectation.required_tools == ["setup.read.draft_refs"]
    assert expectation.draft_refs == ["foundation:magic-law"]
    assert expectation.allow_text_finalize is False


def test_action_decision_policy_ignores_general_opinion_prompt():
    expectation = ActionDecisionPolicy.assess(
        user_prompt="你对这个设定方向有什么看法？",
        turn_goal=None,
        working_plan=None,
        pending_obligation=None,
        compact_summary=_compact_summary(),
        tool_results=[],
    )

    assert expectation is None


def test_action_decision_policy_clears_after_successful_draft_ref_read():
    expectation = ActionDecisionPolicy.assess(
        user_prompt="之前写入草稿的 magic-law 完整内容是什么？",
        turn_goal=None,
        working_plan=None,
        pending_obligation=None,
        compact_summary=_compact_summary(),
        tool_results=[
            RuntimeToolResult(
                call_id="call_read",
                tool_name="rp_setup__setup.read.draft_refs",
                success=True,
                content_text='{"success": true}',
                structured_payload={
                    "content_payload": {
                        "items": [
                            {
                                "ref": "foundation:magic-law",
                                "found": True,
                            }
                        ]
                    }
                },
            )
        ],
    )

    assert expectation is None


def test_action_decision_policy_clears_after_content_text_nested_draft_ref_read():
    expectation = ActionDecisionPolicy.assess(
        user_prompt="之前写入草稿的 magic-law 完整内容是什么？",
        turn_goal=None,
        working_plan=None,
        pending_obligation=None,
        compact_summary=_compact_summary(),
        tool_results=[
            RuntimeToolResult(
                call_id="call_read",
                tool_name="rp_setup__setup.read.draft_refs",
                success=True,
                content_text=(
                    '{"success": true, "content_payload": {"items": ['
                    '{"ref": "foundation:magic-law", "found": true}'
                    "]}}"
                ),
            )
        ],
    )

    assert expectation is None


def test_action_decision_policy_keeps_expectation_when_read_does_not_observe_expected_ref():
    expectation = ActionDecisionPolicy.assess(
        user_prompt="之前写入草稿的 magic-law 完整内容是什么？",
        turn_goal=None,
        working_plan=None,
        pending_obligation=None,
        compact_summary=_compact_summary(),
        tool_results=[
            RuntimeToolResult(
                call_id="call_read",
                tool_name="rp_setup__setup.read.draft_refs",
                success=True,
                content_text='{"success": true, "items": []}',
                structured_payload={"content_payload": {"items": []}},
            )
        ],
    )

    assert expectation is not None
    assert expectation.draft_refs == ["foundation:magic-law"]


def test_action_decision_policy_blocks_mutation_batch_before_required_read():
    expectation = SetupActionExpectation(
        expectation_type="read_draft_refs",
        reason="compact_recovery_requires_draft_ref_read",
        required_tools=["setup.read.draft_refs"],
        draft_refs=["foundation:magic-law"],
    )

    violation = ActionDecisionPolicy.tool_batch_violation(
        expectation=expectation,
        tool_names=["rp_setup__setup.truth.write"],
    )

    assert violation is not None
    assert violation["reason"] == "required_draft_ref_read_missing"


def test_action_decision_policy_allows_read_only_batch_for_required_read():
    expectation = SetupActionExpectation(
        expectation_type="read_draft_refs",
        reason="compact_recovery_requires_draft_ref_read",
        required_tools=["setup.read.draft_refs"],
        draft_refs=["foundation:magic-law"],
    )

    violation = ActionDecisionPolicy.tool_batch_violation(
        expectation=expectation,
        tool_names=["rp_setup__setup.read.draft_refs"],
    )

    assert violation is None


def test_action_decision_policy_blocks_mixed_read_and_mutation_batch():
    expectation = SetupActionExpectation(
        expectation_type="read_draft_refs",
        reason="compact_recovery_requires_draft_ref_read",
        required_tools=["setup.read.draft_refs"],
        draft_refs=["foundation:magic-law"],
    )

    violation = ActionDecisionPolicy.tool_batch_violation(
        expectation=expectation,
        tool_names=[
            "rp_setup__setup.read.draft_refs",
            "rp_setup__setup.truth.write",
        ],
    )

    assert violation is not None
    assert violation["reason"] == "required_draft_ref_read_missing"


def test_completion_guard_blocks_text_when_action_expectation_requires_read():
    decision = CompletionGuardPolicy.assess(
        assistant_text="The full draft detail is that spellcasting needs permits.",
        pending_obligation=None,
        reflection_ticket=None,
        action_expectation=SetupActionExpectation(
            expectation_type="read_draft_refs",
            reason="compact_recovery_requires_draft_ref_read",
            required_tools=["setup.read.draft_refs"],
            draft_refs=["foundation:magic-law"],
        ),
    )

    assert decision["allow_finalize"] is False
    assert decision["completion_guard"]["reason"] == "required_draft_ref_read_missing"


def test_tool_failure_classifier_prefers_structured_error_payload():
    result = RuntimeToolResult(
        call_id="call_patch",
        tool_name="rp_setup__setup.patch.story_config",
        success=False,
        content_text="not-json",
        error_code="SCHEMA_VALIDATION_FAILED",
        structured_payload={
            "error_payload": {
                "code": "schema_validation_failed",
                "message": "Patch payload is missing.",
                "details": {
                    "repair_strategy": "auto_repair",
                    "required_fields": ["patch"],
                },
            }
        },
    )

    assert ToolFailureClassifier.classify(result) == "auto_repair"
    assert ToolFailureClassifier.missing_required_fields(result) == ["patch"]


def test_tool_failure_classifier_derives_nested_missing_fields_from_error_list():
    result = RuntimeToolResult(
        call_id="call_patch",
        tool_name="rp_setup__setup.patch.story_config",
        success=False,
        content_text='{"code":"schema_validation_failed"}',
        error_code="SCHEMA_VALIDATION_FAILED",
        structured_payload={
            "error_payload": {
                "code": "schema_validation_failed",
                "message": "Nested field is missing.",
                "details": {
                    "repair_strategy": "auto_repair",
                    "errors": [
                        {
                            "type": "missing",
                            "loc": ["arguments", "patch", "style_rules"],
                        },
                        {
                            "type": "string_type",
                            "loc": ["arguments", "patch", "notes"],
                        },
                    ],
                },
            }
        },
    )

    assert ToolFailureClassifier.missing_required_fields(result) == [
        "patch.style_rules"
    ]


def test_repair_decision_policy_returns_ask_user_obligation():
    result = RuntimeToolResult(
        call_id="call_question",
        tool_name="rp_setup__setup.patch.story_config",
        success=False,
        content_text='{"code":"schema_validation_failed"}',
        error_code="SCHEMA_VALIDATION_FAILED",
        structured_payload={
            "error_payload": {
                "code": "schema_validation_failed",
                "message": "Need the user's preferred style rules.",
                "details": {
                    "repair_strategy": "ask_user",
                    "ask_user": True,
                    "required_fields": ["patch.style_rules"],
                },
            }
        },
    )

    decision = RepairDecisionPolicy.assess(
        profile=_profile(),
        tool_results=[result],
        schema_retry_count=0,
        round_no=1,
    )

    assert decision["action"] == "continue"
    assert decision["pending_obligation"]["obligation_type"] == "ask_user_for_missing_info"
    assert decision["last_failure"]["failure_category"] == "ask_user"


def test_repair_decision_policy_schema_retry_budget_is_one():
    result = RuntimeToolResult(
        call_id="call_patch",
        tool_name="rp_setup__setup.patch.story_config",
        success=False,
        content_text='{"code":"schema_validation_failed"}',
        error_code="SCHEMA_VALIDATION_FAILED",
        structured_payload={
            "error_payload": {
                "code": "schema_validation_failed",
                "message": "Patch payload is still missing.",
                "details": {
                    "repair_strategy": "auto_repair",
                    "required_fields": ["patch"],
                },
            }
        },
    )

    decision = RepairDecisionPolicy.assess(
        profile=_profile(),
        tool_results=[result],
        schema_retry_count=1,
        round_no=2,
    )

    assert decision["action"] == "finalize_failure"
    assert decision["finish_reason"] == "tool_schema_validation_failed"


def test_repair_decision_policy_continue_discussion_does_not_become_commit_reassessment():
    result = RuntimeToolResult(
        call_id="call_truth_write",
        tool_name="rp_setup__setup.truth.write",
        success=False,
        content_text='{"code":"setup_tool_failed"}',
        error_code="SETUP_TOOL_FAILED",
        structured_payload={
            "error_payload": {
                "code": "setup_tool_failed",
                "message": "Draft truth write could not be applied yet.",
                "details": {
                    "repair_strategy": "continue_discussion",
                },
            }
        },
    )

    decision = RepairDecisionPolicy.assess(
        profile=_profile(),
        tool_results=[result],
        schema_retry_count=0,
        round_no=1,
    )

    assert decision["action"] == "continue"
    assert (
        decision["pending_obligation"]["obligation_type"]
        == "continue_after_tool_failure"
    )
    assert decision["last_failure"]["failure_category"] == "continue_discussion"


def test_completion_guard_blocks_unresolved_repair_obligation():
    obligation = SetupPendingObligation(
        obligation_type="repair_tool_call",
        reason="Patch payload is missing.",
        tool_name="rp_setup__setup.patch.story_config",
        required_fields=["patch"],
    )

    decision = CompletionGuardPolicy.assess(
        assistant_text="I know what failed, but I did not retry yet.",
        pending_obligation=obligation,
        reflection_ticket=None,
    )

    assert decision["allow_finalize"] is False
    assert decision["completion_guard"]["reason"] == "repair_obligation_unresolved"


def test_completion_guard_allows_question_for_ask_user_obligation():
    obligation = SetupPendingObligation(
        obligation_type="ask_user_for_missing_info",
        reason="Need the user's style preference.",
        required_fields=["patch.style_rules"],
    )

    decision = CompletionGuardPolicy.assess(
        assistant_text="Which style rules do you want me to lock in for this draft?",
        pending_obligation=obligation,
        reflection_ticket=None,
    )

    assert decision["allow_finalize"] is True
    assert decision["finish_reason"] == "awaiting_user_input"
    assert decision["pending_obligation"] is None


def test_reflection_trigger_policy_blocks_commit_from_context_ticket():
    ticket = ReflectionTriggerPolicy.blocked_commit_ticket(
        context_bundle={"blocking_open_question_count": 2}
    )

    assert ticket is not None
    assert ticket["trigger"] == "before_commit_proposal"
    assert ticket["required_decision"] == "block_commit"


def test_reflection_trigger_policy_fails_when_retry_budget_is_exhausted():
    decision = ReflectionTriggerPolicy.assess(
        profile=_profile(),
        reflection_ticket=SetupReflectionTicket(
            trigger="tool_failure",
            summary="Repair is still required.",
            required_decision="retry",
        ),
        pending_obligation=SetupPendingObligation(
            obligation_type="repair_tool_call",
            reason="Patch payload is missing.",
            tool_name="rp_setup__setup.patch.story_config",
            required_fields=["patch"],
        ),
        schema_retry_count=1,
        round_no=2,
    )

    assert decision["action"] == "finalize_failure"
    assert decision["finish_reason"] == "repair_obligation_unfulfilled"


def test_blocked_commit_ticket_respects_invalidated_cognitive_state():
    ticket = ReflectionTriggerPolicy.blocked_commit_ticket(
        context_bundle={},
        cognitive_state_summary=SetupCognitiveStateSummary(
            current_step="story_config",
            invalidated=True,
            invalidation_reasons=["user_edit_delta"],
        ),
    )

    assert ticket is not None
    assert ticket["required_decision"] == "block_commit"


def test_blocked_commit_ticket_blocks_when_truth_write_not_review_ready():
    ticket = ReflectionTriggerPolicy.blocked_commit_ticket(
        context_bundle={},
        cognitive_state_summary=SetupCognitiveStateSummary(
            current_step="story_config",
            ready_for_review=False,
            remaining_open_issues=[],
        ),
    )

    assert ticket is not None
    assert ticket["required_decision"] == "block_commit"


def test_completion_guard_downgrades_stale_state_to_continue_discussion():
    decision = CompletionGuardPolicy.assess(
        assistant_text="I updated the draft direction and we should keep refining it.",
        pending_obligation=None,
        reflection_ticket=None,
        cognitive_state_summary=SetupCognitiveStateSummary(
            current_step="foundation",
            invalidated=True,
            invalidation_reasons=["user_edit_delta"],
        ),
    )

    assert decision["allow_finalize"] is True
    assert decision["finish_reason"] == "continue_discussion"


def test_completion_guard_treats_truth_write_not_ready_for_review_as_follow_up():
    decision = CompletionGuardPolicy.assess(
        assistant_text="The draft has improved, but it is not ready for review yet.",
        pending_obligation=None,
        reflection_ticket=None,
        cognitive_state_summary=SetupCognitiveStateSummary(
            current_step="foundation",
            ready_for_review=False,
            remaining_open_issues=[],
        ),
    )

    assert decision["allow_finalize"] is True
    assert decision["finish_reason"] == "continue_discussion"
    assert decision["completion_guard"]["reason"] == "truth_write_not_ready_for_review"


def test_completion_guard_blocks_repeated_question_without_progress():
    decision = CompletionGuardPolicy.assess(
        assistant_text="Which style rules do you want me to lock in for this draft?",
        pending_obligation=None,
        reflection_ticket=None,
        prior_assistant_questions=[
            "Which style rules do you want me to lock in for this draft?"
        ],
        working_digest=SetupWorkingDigest(
            open_questions=["Need the exact style rules."],
        ),
    )

    assert decision["allow_finalize"] is False
    assert decision["completion_guard"]["reason"] == "repeated_question_without_progress"


def test_repair_decision_policy_marks_repeated_tool_failure_warning():
    result = RuntimeToolResult(
        call_id="call_truth_write",
        tool_name="rp_setup__setup.truth.write",
        success=False,
        content_text='{"code":"setup_tool_failed"}',
        error_code="SETUP_TOOL_FAILED",
        structured_payload={
            "error_payload": {
                "code": "setup_tool_failed",
                "message": "Draft truth write could not be applied yet.",
                "details": {
                    "repair_strategy": "continue_discussion",
                },
            }
        },
    )

    decision = RepairDecisionPolicy.assess(
        profile=_profile(),
        tool_results=[result],
        prior_tool_outcomes=[
            SetupToolOutcome(
                tool_name="rp_setup__setup.truth.write",
                success=False,
                summary="Draft truth write could not be applied yet.",
                updated_refs=[],
                error_code="setup_tool_failed",
                relevance="failure",
                recorded_at="2026-04-27T00:00:00Z",
            )
        ],
        schema_retry_count=0,
        round_no=1,
    )

    assert "repeated_tool_failure" in decision["warnings"]
