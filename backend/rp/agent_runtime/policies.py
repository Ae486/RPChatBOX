"""Finish, recovery, reflection, and completion policies for RP runtime execution."""
from __future__ import annotations

import json
from typing import Any

from .contracts import (
    RuntimeProfile,
    RuntimeToolResult,
    SetupCompletionGuard,
    SetupLastFailure,
    SetupPendingObligation,
    SetupReflectionTicket,
)


class FinishPolicy:
    """Terminal decision helpers."""

    @staticmethod
    def looks_like_question(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        lowered = stripped.lower()
        return (
            "?" in stripped
            or "？" in stripped
            or lowered.startswith(("what ", "which ", "could you", "can you", "do you", "would you"))
            or stripped.startswith(("请问", "你更希望", "你想要", "能否"))
        )

    @classmethod
    def terminal_output_kind(cls, text: str) -> str:
        if not text.strip():
            return "empty"
        if cls.looks_like_question(text):
            return "ask_user"
        return "text"

    @classmethod
    def completed_text_finish_reason(cls, text: str) -> str:
        return "awaiting_user_input" if cls.looks_like_question(text) else "completed_text"


class ToolFailureClassifier:
    """Classify tool failures into recovery categories."""

    @classmethod
    def classify(cls, result: RuntimeToolResult) -> str:
        if result.success:
            return "success"

        if result.error_code in {"UNKNOWN_TOOL", "PERMISSION_DENIED"}:
            return "unrecoverable"

        payload = cls.error_payload(result)
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}

        if result.error_code == "SCHEMA_VALIDATION_FAILED":
            if details.get("ask_user") is True or details.get("repair_strategy") == "ask_user":
                return "ask_user"
            return "auto_repair"

        if details.get("block_commit") is True:
            return "block_commit"

        if details.get("repair_strategy") == "ask_user":
            return "ask_user"
        if (
            details.get("repair_strategy") == "transient_retry"
            or details.get("transient_retry") is True
        ):
            return "continue_discussion"
        if details.get("repair_strategy") == "continue_discussion":
            return "continue_discussion"

        return "continue_discussion"

    @staticmethod
    def error_payload(result: RuntimeToolResult) -> dict[str, Any]:
        structured_payload = (
            result.structured_payload
            if isinstance(result.structured_payload, dict)
            else {}
        )
        if isinstance(structured_payload.get("error_payload"), dict):
            payload = structured_payload["error_payload"]
            return {
                "code": payload.get("code") or result.error_code,
                "message": payload.get("message") or result.content_text,
                "details": payload.get("details") or {},
            }

        try:
            payload = json.loads(result.content_text)
        except (TypeError, json.JSONDecodeError):
            return {
                "code": result.error_code,
                "message": result.content_text,
                "details": {},
            }

        if not isinstance(payload, dict):
            return {
                "code": result.error_code,
                "message": result.content_text,
                "details": {},
            }

        if isinstance(payload.get("error"), dict):
            nested = payload["error"]
            return {
                "code": nested.get("code") or result.error_code,
                "message": nested.get("message") or result.content_text,
                "details": nested.get("details") or payload.get("details") or {},
            }

        return {
            "code": payload.get("code") or result.error_code,
            "message": payload.get("message") or result.content_text,
            "details": payload.get("details") or {},
        }

    @classmethod
    def missing_required_fields(cls, result: RuntimeToolResult) -> list[str]:
        payload = cls.error_payload(result)
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        if isinstance(details.get("required_fields"), list):
            return [str(item) for item in details["required_fields"] if item]

        errors = details.get("errors")
        if not isinstance(errors, list):
            return []

        missing_fields: list[str] = []
        for item in errors:
            if not isinstance(item, dict):
                continue
            error_type = str(item.get("type") or "")
            if "missing" not in error_type:
                continue
            loc = item.get("loc")
            if isinstance(loc, (list, tuple)):
                field = ".".join(str(part) for part in loc if part not in {"body", "arguments"})
            elif loc:
                field = str(loc)
            else:
                field = ""
            if field and field not in missing_fields:
                missing_fields.append(field)
        return missing_fields

    @classmethod
    def build_failure_state(cls, result: RuntimeToolResult) -> SetupLastFailure:
        payload = cls.error_payload(result)
        return SetupLastFailure(
            failure_category=cls.classify(result),
            message=str(payload.get("message") or result.content_text),
            error_code=str(payload.get("code") or result.error_code or ""),
            tool_name=result.tool_name,
            details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
        )


class RepairDecisionPolicy:
    """Setup-oriented tool recovery rules."""

    @classmethod
    def assess(
        cls,
        *,
        profile: RuntimeProfile,
        tool_results: list[RuntimeToolResult],
        schema_retry_count: int,
        round_no: int,
    ) -> dict[str, Any]:
        failures = [result for result in tool_results if not result.success]
        if not failures:
            if round_no >= profile.max_rounds:
                return cls._max_rounds_failure(profile)
            return {
                "action": "continue",
                "pending_obligation": None,
                "last_failure": None,
                "reflection_ticket": None,
                "completion_guard": None,
            }

        failure = failures[0]
        failure_state = ToolFailureClassifier.build_failure_state(failure)
        category = failure_state.failure_category

        if category == "unrecoverable":
            return {
                "action": "finalize_failure",
                "finish_reason": "tool_error_unrecoverable",
                "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
                "error": {
                    "message": failure_state.message,
                    "type": "tool_error_unrecoverable",
                    "tool_name": failure.tool_name,
                    "error_code": failure.error_code,
                },
            }

        if category == "auto_repair":
            if schema_retry_count >= 1:
                return {
                    "action": "finalize_failure",
                    "finish_reason": "tool_schema_validation_failed",
                    "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
                    "error": {
                        "message": "Setup tool arguments failed validation more than once",
                        "type": "tool_schema_validation_failed",
                    },
                }
            obligation = SetupPendingObligation(
                obligation_type="repair_tool_call",
                reason=failure_state.message,
                tool_name=failure.tool_name,
                required_fields=ToolFailureClassifier.missing_required_fields(failure),
            )
            return {
                "action": "continue",
                "schema_retry_count": schema_retry_count + 1,
                "warning": "tool_schema_validation_retry",
                "pending_obligation": obligation.model_dump(mode="json", exclude_none=True),
                "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": None,
                "completion_guard": None,
            }

        if category == "ask_user":
            obligation = SetupPendingObligation(
                obligation_type="ask_user_for_missing_info",
                reason=failure_state.message,
                tool_name=failure.tool_name,
                required_fields=ToolFailureClassifier.missing_required_fields(failure),
            )
            return {
                "action": "continue",
                "warning": "tool_failure_requires_user_input",
                "pending_obligation": obligation.model_dump(mode="json", exclude_none=True),
                "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": None,
                "completion_guard": None,
            }

        if category == "block_commit":
            obligation = SetupPendingObligation(
                obligation_type="reassess_commit_readiness",
                reason=failure_state.message,
                tool_name=failure.tool_name,
            )
            return {
                "action": "continue",
                "warning": "commit_reflection_required",
                "pending_obligation": obligation.model_dump(mode="json", exclude_none=True),
                "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": SetupReflectionTicket(
                    trigger="before_commit_proposal",
                    summary=failure_state.message,
                    required_decision="block_commit",
                ).model_dump(mode="json", exclude_none=True),
                "completion_guard": None,
            }

        obligation = SetupPendingObligation(
            obligation_type="reassess_commit_readiness",
            reason=failure_state.message,
            tool_name=failure.tool_name,
        )
        return {
            "action": "continue",
            "warning": "tool_failure_continue_discussion",
            "pending_obligation": obligation.model_dump(mode="json", exclude_none=True),
            "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
            "reflection_ticket": None,
            "completion_guard": None,
        }

    @staticmethod
    def _max_rounds_failure(profile: RuntimeProfile) -> dict[str, Any]:
        return {
            "action": "finalize_failure",
            "finish_reason": "max_rounds_exceeded",
            "error": {
                "message": f"Agent runtime exceeded {profile.max_rounds} rounds",
                "type": "max_rounds_exceeded",
            },
        }


class CompletionGuardPolicy:
    """Decide whether the current assistant output may terminate the turn."""

    @classmethod
    def assess(
        cls,
        *,
        assistant_text: str,
        pending_obligation: SetupPendingObligation | None,
        reflection_ticket: SetupReflectionTicket | None,
    ) -> dict[str, Any]:
        if reflection_ticket is not None:
            guard = SetupCompletionGuard(
                allow_finalize=False,
                reason=reflection_ticket.summary,
                required_action="reflect",
            )
            return {
                "allow_finalize": False,
                "completion_guard": guard.model_dump(mode="json", exclude_none=True),
            }

        terminal_kind = FinishPolicy.terminal_output_kind(assistant_text)
        if pending_obligation is None or not pending_obligation.unresolved:
            if terminal_kind == "empty":
                guard = SetupCompletionGuard(
                    allow_finalize=False,
                    reason="assistant_output_empty",
                    required_action="retry",
                )
                return {
                    "allow_finalize": False,
                    "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                    "reflection_ticket": SetupReflectionTicket(
                        trigger="tool_failure",
                        summary="Assistant output was empty while the turn was still active.",
                        required_decision="retry",
                    ).model_dump(mode="json", exclude_none=True),
                }

            finish_reason = FinishPolicy.completed_text_finish_reason(assistant_text)
            guard = SetupCompletionGuard(
                allow_finalize=True,
                reason="terminal_output_allowed",
                required_action="finalize_success",
                finish_reason=finish_reason,
            )
            return {
                "allow_finalize": True,
                "finish_reason": finish_reason,
                "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                "pending_obligation": None,
                "reflection_ticket": None,
            }

        if pending_obligation.obligation_type == "repair_tool_call":
            guard = SetupCompletionGuard(
                allow_finalize=False,
                reason="repair_obligation_unresolved",
                required_action="retry",
            )
            return {
                "allow_finalize": False,
                "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": SetupReflectionTicket(
                    trigger="tool_failure",
                    summary="A failed tool call still requires repair before the turn may finish.",
                    required_decision="retry",
                ).model_dump(mode="json", exclude_none=True),
            }

        if pending_obligation.obligation_type == "ask_user_for_missing_info":
            if terminal_kind == "ask_user":
                guard = SetupCompletionGuard(
                    allow_finalize=True,
                    reason="assistant_asked_required_question",
                    required_action="finalize_success",
                    finish_reason="awaiting_user_input",
                )
                return {
                    "allow_finalize": True,
                    "finish_reason": "awaiting_user_input",
                    "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                    "pending_obligation": None,
                    "reflection_ticket": None,
                }

            guard = SetupCompletionGuard(
                allow_finalize=False,
                reason="ask_user_obligation_unresolved",
                required_action="ask_user",
            )
            return {
                "allow_finalize": False,
                "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": SetupReflectionTicket(
                    trigger="tool_failure",
                    summary="The runtime requires a targeted user question before the turn may finish.",
                    required_decision="ask_user",
                ).model_dump(mode="json", exclude_none=True),
            }

        if terminal_kind == "ask_user":
            finish_reason = "awaiting_user_input"
        elif terminal_kind == "text":
            finish_reason = "continue_discussion"
        else:
            guard = SetupCompletionGuard(
                allow_finalize=False,
                reason="commit_reassessment_needs_visible_reply",
                required_action="continue_discussion",
            )
            return {
                "allow_finalize": False,
                "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": SetupReflectionTicket(
                    trigger="before_commit_proposal",
                    summary="Commit readiness must be reassessed before finishing the turn.",
                    required_decision="continue_discussion",
                ).model_dump(mode="json", exclude_none=True),
            }

        guard = SetupCompletionGuard(
            allow_finalize=True,
            reason="discussion_continues_without_commit",
            required_action="finalize_success",
            finish_reason=finish_reason,
        )
        return {
            "allow_finalize": True,
            "finish_reason": finish_reason,
            "completion_guard": guard.model_dump(mode="json", exclude_none=True),
            "pending_obligation": None,
            "reflection_ticket": None,
        }


class ReflectionTriggerPolicy:
    """Decide how runtime should react after a reflection trigger is raised."""

    @staticmethod
    def assess(
        *,
        profile: RuntimeProfile,
        reflection_ticket: SetupReflectionTicket | None,
        pending_obligation: SetupPendingObligation | None,
        schema_retry_count: int,
        round_no: int,
    ) -> dict[str, Any]:
        if reflection_ticket is None:
            return {"action": "continue"}

        if round_no >= profile.max_rounds:
            return {
                "action": "finalize_failure",
                "finish_reason": "max_rounds_exceeded",
                "error": {
                    "message": f"Agent runtime exceeded {profile.max_rounds} rounds",
                    "type": "max_rounds_exceeded",
                },
            }

        if reflection_ticket.required_decision == "retry":
            if (
                pending_obligation is not None
                and pending_obligation.obligation_type == "repair_tool_call"
                and schema_retry_count >= 1
            ):
                return {
                    "action": "finalize_failure",
                    "finish_reason": "repair_obligation_unfulfilled",
                    "error": {
                        "message": "Tool repair was required, but the assistant tried to finish without issuing a corrected tool call.",
                        "type": "repair_obligation_unfulfilled",
                    },
                }
            return {"action": "continue", "warning": "reflection_retry_required"}

        if reflection_ticket.required_decision == "ask_user":
            return {"action": "continue", "warning": "reflection_requires_user_question"}

        if reflection_ticket.required_decision == "block_commit":
            return {"action": "continue", "warning": "reflection_blocked_commit"}

        return {"action": "continue", "warning": "reflection_continue_discussion"}

    @staticmethod
    def blocked_commit_ticket(*, context_bundle: dict[str, Any]) -> dict[str, Any] | None:
        blocking_open_questions = int(context_bundle.get("blocking_open_question_count") or 0)
        if blocking_open_questions > 0:
            return SetupReflectionTicket(
                trigger="before_commit_proposal",
                summary=(
                    "Commit proposal is blocked because the current step still has "
                    f"{blocking_open_questions} blocking open question(s)."
                ),
                required_decision="block_commit",
            ).model_dump(mode="json", exclude_none=True)

        if str(context_bundle.get("last_proposal_status") or "") == "rejected":
            return SetupReflectionTicket(
                trigger="proposal_rejected",
                summary=(
                    "The previous commit proposal for this step was rejected, so the agent must "
                    "continue discussion instead of immediately proposing again."
                ),
                required_decision="block_commit",
            ).model_dump(mode="json", exclude_none=True)

        return None
