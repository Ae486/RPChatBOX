"""Unit tests for setup cognitive runtime policies."""
from __future__ import annotations

from rp.agent_runtime.contracts import (
    RuntimeProfile,
    RuntimeToolResult,
    SetupPendingObligation,
    SetupReflectionTicket,
)
from rp.agent_runtime.policies import (
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
