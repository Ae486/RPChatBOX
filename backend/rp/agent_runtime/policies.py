"""Finish, recovery, reflection, and completion policies for RP runtime execution."""
from __future__ import annotations

import json
import re
from typing import Any

from .contracts import (
    RuntimeProfile,
    RuntimeToolResult,
    SetupActionExpectation,
    SetupCompletionGuard,
    SetupCognitiveStateSummary,
    SetupContextCompactSummary,
    SetupLastFailure,
    SetupPendingObligation,
    SetupReflectionTicket,
    SetupToolOutcome,
    SetupTurnGoal,
    SetupWorkingDigest,
    SetupWorkingPlan,
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
        raw_details = payload.get("details")
        details = raw_details if isinstance(raw_details, dict) else {}

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
            payload = dict(structured_payload["error_payload"])
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
            nested = dict(payload["error"])
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
        raw_details = payload.get("details")
        details = raw_details if isinstance(raw_details, dict) else {}
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
        prior_tool_outcomes: list[SetupToolOutcome] | None = None,
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
        repeated_failure = cls._is_repeated_failure(
            failure_state=failure_state,
            prior_tool_outcomes=prior_tool_outcomes or [],
        )

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
            warnings = ["tool_schema_validation_retry"]
            if repeated_failure:
                warnings.append("repeated_tool_failure")
            return {
                "action": "continue",
                "schema_retry_count": schema_retry_count + 1,
                "warning": "tool_schema_validation_retry",
                "warnings": warnings,
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
            warnings = ["tool_failure_requires_user_input"]
            if repeated_failure:
                warnings.append("repeated_tool_failure")
            return {
                "action": "continue",
                "warning": "tool_failure_requires_user_input",
                "warnings": warnings,
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
            warnings = ["commit_reflection_required"]
            if repeated_failure:
                warnings.append("repeated_tool_failure")
            return {
                "action": "continue",
                "warning": "commit_reflection_required",
                "warnings": warnings,
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
            obligation_type="continue_after_tool_failure",
            reason=failure_state.message,
            tool_name=failure.tool_name,
        )
        warnings = ["tool_failure_continue_discussion"]
        if repeated_failure:
            warnings.append("repeated_tool_failure")
        return {
            "action": "continue",
            "warning": "tool_failure_continue_discussion",
            "warnings": warnings,
            "pending_obligation": obligation.model_dump(mode="json", exclude_none=True),
            "last_failure": failure_state.model_dump(mode="json", exclude_none=True),
            "reflection_ticket": None,
            "completion_guard": None,
        }

    @staticmethod
    def _is_repeated_failure(
        *,
        failure_state: SetupLastFailure,
        prior_tool_outcomes: list[SetupToolOutcome],
    ) -> bool:
        for item in prior_tool_outcomes:
            if item.success:
                continue
            if item.tool_name != (failure_state.tool_name or item.tool_name):
                continue
            if (item.error_code or "") != (failure_state.error_code or ""):
                continue
            if item.summary == failure_state.message:
                return True
        return False

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


class ActionDecisionPolicy:
    """Lightweight action expectations for high-certainty setup cases."""

    _READ_DRAFT_REFS_TOOL = "setup.read.draft_refs"
    _READ_DRAFT_REFS_QUALIFIED_TOOL = "rp_setup__setup.read.draft_refs"
    _EXACT_DETAIL_MARKERS = (
        "exact",
        "full",
        "complete",
        "specific",
        "concrete",
        "detail",
        "details",
        "verbatim",
        "precise",
        "准确",
        "精确",
        "具体",
        "完整",
        "原文",
        "细节",
        "详细",
        "全部",
        "是什么",
        "有哪些",
        "哪条",
    )
    _DRAFT_DETAIL_MARKERS = (
        "draft",
        "ref",
        "current",
        "previous",
        "previously",
        "written",
        "content",
        "foundation",
        "chunk",
        "entry",
        "草稿",
        "设定",
        "内容",
        "写入",
        "之前",
        "当前",
        "已写入",
        "条目",
    )

    @classmethod
    def assess(
        cls,
        *,
        user_prompt: str,
        turn_goal: SetupTurnGoal | None,
        working_plan: SetupWorkingPlan | None,
        pending_obligation: SetupPendingObligation | None,
        compact_summary: SetupContextCompactSummary | None,
        tool_results: list[RuntimeToolResult],
    ) -> SetupActionExpectation | None:
        if pending_obligation is not None and pending_obligation.unresolved:
            return None

        refs = cls._compact_draft_refs(compact_summary)
        if not refs:
            return None
        if not cls._prompt_requests_exact_draft_detail(user_prompt, refs=refs):
            return None
        if cls._has_successful_draft_ref_read(tool_results, refs=refs):
            return None

        return SetupActionExpectation(
            expectation_type="read_draft_refs",
            reason="compact_recovery_requires_draft_ref_read",
            required_tools=[cls._READ_DRAFT_REFS_TOOL],
            draft_refs=refs[:6],
            allow_text_finalize=False,
            requires_observation_first=True,
        )

    @classmethod
    def tool_batch_violation(
        cls,
        *,
        expectation: SetupActionExpectation | None,
        tool_names: list[str],
    ) -> dict[str, Any] | None:
        if expectation is None or expectation.expectation_type != "read_draft_refs":
            return None
        if not tool_names:
            return None

        read_tools = [name for name in tool_names if cls._is_draft_ref_read_tool(name)]
        non_read_tools = [name for name in tool_names if not cls._is_draft_ref_read_tool(name)]
        if read_tools and not non_read_tools:
            return None

        return {
            "reason": "required_draft_ref_read_missing",
            "required_tools": list(expectation.required_tools),
            "draft_refs": list(expectation.draft_refs),
            "blocked_tool_names": list(tool_names),
        }

    @classmethod
    def _compact_draft_refs(
        cls,
        compact_summary: SetupContextCompactSummary | None,
    ) -> list[str]:
        if compact_summary is None:
            return []
        refs: list[str] = []
        for hint in compact_summary.recovery_hints:
            ref = str(hint.ref or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
        for raw_ref in compact_summary.draft_refs:
            ref = str(raw_ref or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
        return refs[:6]

    @classmethod
    def _prompt_requests_exact_draft_detail(cls, user_prompt: str, *, refs: list[str]) -> bool:
        lowered = str(user_prompt or "").strip().lower()
        if not lowered:
            return False
        has_exact_marker = any(marker in lowered for marker in cls._EXACT_DETAIL_MARKERS)
        if not has_exact_marker:
            return False
        if any(marker in lowered for marker in cls._DRAFT_DETAIL_MARKERS):
            return True
        return any(cls._ref_marker_in_prompt(ref, lowered) for ref in refs)

    @staticmethod
    def _ref_marker_in_prompt(ref: str, lowered_prompt: str) -> bool:
        normalized = str(ref or "").strip().lower()
        if not normalized:
            return False
        if normalized in lowered_prompt:
            return True
        parts = [part for part in re.split(r"[:/_\-\s]+", normalized) if len(part) >= 3]
        return any(part in lowered_prompt for part in parts)

    @classmethod
    def _has_successful_draft_ref_read(
        cls,
        tool_results: list[RuntimeToolResult],
        *,
        refs: list[str],
    ) -> bool:
        expected_refs = {str(ref) for ref in refs if ref}
        for result in tool_results:
            if not result.success or not cls._is_draft_ref_read_tool(result.tool_name):
                continue
            observed_refs = cls._observed_draft_refs(result)
            if not expected_refs:
                return True
            if expected_refs.intersection(observed_refs):
                return True
        return False

    @staticmethod
    def _observed_draft_refs(result: RuntimeToolResult) -> set[str]:
        payload = result.structured_payload if isinstance(result.structured_payload, dict) else {}
        candidates: list[Any] = []

        def append_payload_candidates(root: dict[str, Any]) -> None:
            candidates.append(root)
            for key in ("content_payload", "result_payload"):
                nested = root.get(key)
                if isinstance(nested, dict):
                    candidates.append(nested)

        append_payload_candidates(payload)
        try:
            content_payload = json.loads(result.content_text)
        except (TypeError, json.JSONDecodeError):
            content_payload = None
        if isinstance(content_payload, dict):
            append_payload_candidates(content_payload)

        refs: set[str] = set()
        for candidate in candidates:
            items = candidate.get("items") if isinstance(candidate, dict) else None
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("found") is not False and item.get("ref"):
                        refs.add(str(item["ref"]))
            for key in ("refs", "draft_refs"):
                raw_refs = candidate.get(key) if isinstance(candidate, dict) else None
                if isinstance(raw_refs, list):
                    refs.update(str(item) for item in raw_refs if item)
        return refs

    @classmethod
    def _is_draft_ref_read_tool(cls, tool_name: str) -> bool:
        return str(tool_name or "").endswith(cls._READ_DRAFT_REFS_TOOL)


class CompletionGuardPolicy:
    """Decide whether the current assistant output may terminate the turn."""

    @classmethod
    def assess(
        cls,
        *,
        assistant_text: str,
        pending_obligation: SetupPendingObligation | None,
        reflection_ticket: SetupReflectionTicket | None,
        action_expectation: SetupActionExpectation | None = None,
        cognitive_state_summary: SetupCognitiveStateSummary | None = None,
        prior_assistant_questions: list[str] | None = None,
        working_digest: SetupWorkingDigest | None = None,
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

        if (
            action_expectation is not None
            and action_expectation.expectation_type == "read_draft_refs"
            and not action_expectation.allow_text_finalize
        ):
            guard = SetupCompletionGuard(
                allow_finalize=False,
                reason="required_draft_ref_read_missing",
                required_action="retry",
            )
            return {
                "allow_finalize": False,
                "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                "reflection_ticket": SetupReflectionTicket(
                    trigger="tool_failure",
                    summary=(
                        "Exact draft detail is required after compact, but the assistant "
                        "has not read the referenced draft refs yet. Call setup.read.draft_refs first."
                    ),
                    required_decision="retry",
                ).model_dump(mode="json", exclude_none=True),
            }

        terminal_kind = FinishPolicy.terminal_output_kind(assistant_text)
        if terminal_kind == "ask_user" and prior_assistant_questions:
            normalized_current = cls._normalize_question(assistant_text)
            repeated_question = bool(normalized_current) and any(
                normalized_current == cls._normalize_question(item)
                for item in prior_assistant_questions
            )
            if repeated_question:
                follow_up = (
                    working_digest.open_questions[0]
                    if working_digest is not None and working_digest.open_questions
                    else "Reframe the missing question or make concrete draft progress before asking again."
                )
                guard = SetupCompletionGuard(
                    allow_finalize=False,
                    reason="repeated_question_without_progress",
                    required_action="retry",
                )
                return {
                    "allow_finalize": False,
                    "completion_guard": guard.model_dump(mode="json", exclude_none=True),
                    "reflection_ticket": SetupReflectionTicket(
                        trigger="tool_failure",
                        summary=(
                            "The assistant repeated a recent question without new progress. "
                            f"Next attempt should target: {follow_up}"
                        ),
                        required_decision="retry",
                    ).model_dump(mode="json", exclude_none=True),
                }
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

            if cognitive_state_summary is not None and (
                cognitive_state_summary.invalidated
                or (
                    not cognitive_state_summary.ready_for_review
                    or bool(cognitive_state_summary.remaining_open_issues)
                )
            ):
                finish_reason = (
                    "awaiting_user_input"
                    if terminal_kind == "ask_user"
                    else "continue_discussion"
                )
                guard = SetupCompletionGuard(
                    allow_finalize=True,
                    reason=(
                        "cognitive_state_requires_follow_up"
                        if cognitive_state_summary.invalidated
                        else (
                            "truth_write_still_has_open_issues"
                            if cognitive_state_summary.remaining_open_issues
                            else "truth_write_not_ready_for_review"
                        )
                    ),
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

    @staticmethod
    def _normalize_question(text: str) -> str:
        lowered = str(text or "").strip().lower()
        lowered = re.sub(r"[\s\?\!？！，。,.]+", " ", lowered)
        return lowered.strip()


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
    def blocked_commit_ticket(
        *,
        context_bundle: dict[str, Any],
        cognitive_state_summary: SetupCognitiveStateSummary | None = None,
    ) -> dict[str, Any] | None:
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

        if cognitive_state_summary is not None and cognitive_state_summary.invalidated:
            return SetupReflectionTicket(
                trigger="before_commit_proposal",
                summary=(
                    "Commit proposal is blocked because the current cognitive state is stale "
                    "and must be reconciled with the latest draft first."
                ),
                required_decision="block_commit",
            ).model_dump(mode="json", exclude_none=True)

        if (
            cognitive_state_summary is not None
            and not cognitive_state_summary.ready_for_review
        ):
            return SetupReflectionTicket(
                trigger="before_commit_proposal",
                summary=(
                    "Commit proposal is blocked because the current truth write has not "
                    "entered review-ready state yet."
                ),
                required_decision="block_commit",
            ).model_dump(mode="json", exclude_none=True)

        if (
            cognitive_state_summary is not None
            and bool(cognitive_state_summary.remaining_open_issues)
        ):
            return SetupReflectionTicket(
                trigger="before_commit_proposal",
                summary=(
                    "Commit proposal is blocked because the current truth write still has "
                    "open issues that must be resolved first."
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
