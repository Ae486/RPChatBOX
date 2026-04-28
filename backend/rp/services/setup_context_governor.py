"""Current-step context governor for setup runtime-v2 turns."""
from __future__ import annotations

from typing import Any

from rp.agent_runtime.contracts import (
    SetupContextCompactSummary,
    SetupCognitiveStateSnapshot,
    SetupCognitiveStateSummary,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.models.setup_agent import SetupAgentDialogueMessage
from rp.services.setup_context_compaction_service import SetupContextCompactionService


class SetupContextGovernorService:
    """Select prompt-visible step-local context without widening durable state."""

    _MAX_RETAINED_TOOL_OUTCOMES = 6
    _MAX_OPEN_QUESTIONS = 4
    _MAX_REJECTED_DIRECTIONS = 4
    _MAX_DRAFT_REFS = 6
    _MAX_COMMIT_BLOCKERS = 4
    _SUCCESS_RELEVANCE = {"cognitive", "draft", "question", "proposal", "asset"}

    def __init__(
        self,
        *,
        compaction_service: SetupContextCompactionService | None = None,
    ) -> None:
        self._compaction_service = compaction_service or SetupContextCompactionService()

    def govern_history(
        self,
        *,
        history: list[SetupAgentDialogueMessage],
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
        existing_summary: SetupContextCompactSummary | None,
        context_profile: str,
        current_step: str | None = None,
        estimated_input_tokens: int | None = None,
        previous_usage: dict[str, int] | None = None,
    ) -> tuple[
        list[SetupAgentDialogueMessage],
        SetupContextCompactSummary | None,
        dict[str, Any],
    ]:
        limit = self._compaction_service.raw_history_limit(context_profile=context_profile)
        compact_summary = self._compaction_service.build_summary(
            history=history,
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
            existing_summary=existing_summary,
            context_profile=context_profile,
            current_step=current_step,
        )
        summary_decision = self._compaction_service.last_summary_decision()
        kept_history = list(history[-limit:]) if len(history) > limit else list(history)
        return (
            kept_history,
            compact_summary,
            {
                "raw_history_limit": limit,
                "kept_history_count": len(kept_history),
                "compacted_history_count": max(len(history) - len(kept_history), 0),
                "estimated_input_tokens": estimated_input_tokens,
                "previous_prompt_tokens": (
                    int(previous_usage.get("prompt_tokens"))
                    if previous_usage and previous_usage.get("prompt_tokens") is not None
                    else None
                ),
                "previous_total_tokens": (
                    int(previous_usage.get("total_tokens"))
                    if previous_usage and previous_usage.get("total_tokens") is not None
                    else None
                ),
                "summary_strategy": summary_decision.get("summary_strategy") or "none",
                "summary_action": summary_decision.get("summary_action") or "none",
                "fallback_reason": summary_decision.get("fallback_reason"),
            },
        )

    def build_initial_digest(
        self,
        *,
        cognitive_state: SetupCognitiveStateSnapshot | None,
        cognitive_state_summary: SetupCognitiveStateSummary | None,
        blocking_open_question_count: int,
        last_proposal_status: str | None,
    ) -> SetupWorkingDigest | None:
        base = (
            cognitive_state_summary.working_digest.model_copy(deep=True)
            if cognitive_state_summary is not None
            and cognitive_state_summary.working_digest is not None
            else SetupWorkingDigest()
        )
        discussion_state = (
            cognitive_state.discussion_state
            if cognitive_state is not None
            else None
        )
        truth_write = (
            cognitive_state.active_truth_write
            if cognitive_state is not None
            else None
        )
        if discussion_state is not None:
            base.next_focus = discussion_state.next_focus or base.next_focus
            base.rejected_directions = [
                item.label
                for item in discussion_state.candidate_directions
                if item.status == "discarded"
            ][: self._MAX_REJECTED_DIRECTIONS]
        if cognitive_state_summary is not None and cognitive_state_summary.open_questions:
            base.open_questions = list(
                cognitive_state_summary.open_questions[: self._MAX_OPEN_QUESTIONS]
            )
        draft_refs = list(base.draft_refs[: self._MAX_DRAFT_REFS])
        if truth_write is not None and truth_write.target_ref:
            target_ref = str(truth_write.target_ref)
            if target_ref not in draft_refs:
                draft_refs.append(target_ref)
        if cognitive_state_summary is not None:
            for outcome in cognitive_state_summary.tool_outcomes:
                for ref in outcome.updated_refs:
                    value = str(ref or "").strip()
                    if value and value not in draft_refs:
                        draft_refs.append(value)
                    if len(draft_refs) >= self._MAX_DRAFT_REFS:
                        break
                if len(draft_refs) >= self._MAX_DRAFT_REFS:
                    break
        base.draft_refs = draft_refs[: self._MAX_DRAFT_REFS]

        blockers = list(base.commit_blockers[: self._MAX_COMMIT_BLOCKERS])
        if blocking_open_question_count > 0:
            blockers.append(f"{blocking_open_question_count} blocking_open_question(s)")
        if cognitive_state_summary is not None and cognitive_state_summary.invalidated:
            blockers.append("cognitive_state_invalidated")
        if cognitive_state_summary is not None:
            blockers.extend(cognitive_state_summary.remaining_open_issues[:2])
        if str(last_proposal_status or "").lower() == "rejected":
            blockers.append("proposal_rejected")
        base.commit_blockers = list(dict.fromkeys(blockers))[: self._MAX_COMMIT_BLOCKERS]

        has_content = any(
            (
                base.current_goal,
                base.next_focus,
                base.pending_obligation,
                base.open_questions,
                base.rejected_directions,
                base.draft_refs,
                base.commit_blockers,
            )
        )
        return base if has_content else None

    def retain_tool_outcomes(
        self,
        *,
        existing: list[SetupToolOutcome],
        latest_results: list[SetupToolOutcome] | None = None,
    ) -> list[SetupToolOutcome]:
        combined = [*existing, *(latest_results or [])]
        if not combined:
            return []

        failures: list[SetupToolOutcome] = []
        successes: list[SetupToolOutcome] = []
        seen_failure_keys: set[str] = set()
        seen_success_keys: set[str] = set()

        for item in reversed(combined):
            if not item.success:
                key = f"failure:{item.tool_name}:{item.error_code or ''}:{item.summary}"
                if key in seen_failure_keys:
                    continue
                seen_failure_keys.add(key)
                failures.append(item)
                continue
            if item.relevance not in self._SUCCESS_RELEVANCE:
                continue
            refs_key = ",".join(item.updated_refs)
            key = f"success:{item.tool_name}:{refs_key}"
            if key in seen_success_keys:
                continue
            seen_success_keys.add(key)
            successes.append(item)

        ordered = [*failures, *successes]
        return ordered[: self._MAX_RETAINED_TOOL_OUTCOMES]
