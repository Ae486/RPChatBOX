"""Compaction helpers for trimmed older setup-stage discussion history."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from models.chat import ChatMessage
from rp.agent_runtime.contracts import (
    SetupCompactRecoveryHint,
    SetupContextCompactSummary,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.models.setup_agent import SetupAgentDialogueMessage

CompactPromptProvider = Callable[
    [list[ChatMessage]], dict[str, Any] | Awaitable[dict[str, Any]]
]


class SetupContextCompactionService:
    """Build thin carry-forward summaries for older current-step history."""

    _STANDARD_RECENT_HISTORY_MESSAGES = 6
    _COMPACT_RECENT_HISTORY_MESSAGES = 4
    _SUMMARY_LINE_LIMIT = 6
    _CONFIRMED_POINT_LIMIT = 8
    _OPEN_THREAD_LIMIT = 4
    _REJECTED_DIRECTION_LIMIT = 4
    _DRAFT_REF_LIMIT = 6
    _RECOVERY_HINT_LIMIT = 6
    _MUST_NOT_INFER_LIMIT = 4
    _MAX_SUMMARY_CHARS = 180
    _VALID_DRAFT_REF_PREFIXES = (
        "draft:story_config",
        "draft:writing_contract",
        "draft:longform_blueprint",
        "foundation:",
    )

    def __init__(
        self,
        *,
        compact_prompt_provider: CompactPromptProvider | None = None,
    ) -> None:
        self._compact_prompt_provider = compact_prompt_provider
        self._last_summary_decision: dict[str, Any] = {
            "summary_strategy": "none",
            "summary_action": "none",
            "fallback_reason": None,
        }

    def last_summary_decision(self) -> dict[str, Any]:
        """Return metadata for the most recent compact-summary build."""

        return dict(self._last_summary_decision)

    def raw_history_limit(self, *, context_profile: str) -> int:
        if context_profile == "compact":
            return self._COMPACT_RECENT_HISTORY_MESSAGES
        return self._STANDARD_RECENT_HISTORY_MESSAGES

    def build_summary(
        self,
        *,
        history: list[SetupAgentDialogueMessage],
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
        existing_summary: SetupContextCompactSummary | None,
        context_profile: str,
        current_step: str | None = None,
    ) -> SetupContextCompactSummary | None:
        return self._build_summary_sync(
            history=history,
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
            existing_summary=existing_summary,
            context_profile=context_profile,
            current_step=current_step,
        )

    async def build_summary_async(
        self,
        *,
        history: list[SetupAgentDialogueMessage],
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
        existing_summary: SetupContextCompactSummary | None,
        context_profile: str,
        current_step: str | None = None,
    ) -> SetupContextCompactSummary | None:
        result = self._build_summary(
            history=history,
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
            existing_summary=existing_summary,
            context_profile=context_profile,
            current_step=current_step,
            allow_async_provider=True,
        )
        if inspect.isawaitable(result):
            return await result
        return result

    def _build_summary_sync(
        self,
        *,
        history: list[SetupAgentDialogueMessage],
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
        existing_summary: SetupContextCompactSummary | None,
        context_profile: str,
        current_step: str | None = None,
    ) -> SetupContextCompactSummary | None:
        result = self._build_summary(
            history=history,
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
            existing_summary=existing_summary,
            context_profile=context_profile,
            current_step=current_step,
            allow_async_provider=False,
        )
        if inspect.isawaitable(result):
            raise RuntimeError("compact_prompt_provider_returned_awaitable")
        return result

    def _build_summary(
        self,
        *,
        history: list[SetupAgentDialogueMessage],
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
        existing_summary: SetupContextCompactSummary | None,
        context_profile: str,
        current_step: str | None = None,
        allow_async_provider: bool,
    ) -> SetupContextCompactSummary | None | Awaitable[SetupContextCompactSummary | None]:
        dropped_history = self._dropped_history(
            history=history,
            context_profile=context_profile,
        )
        if not dropped_history:
            self._last_summary_decision = {
                "summary_strategy": "none",
                "summary_action": "none",
                "fallback_reason": None,
            }
            return None

        fingerprint = self._history_fingerprint(dropped_history)
        if (
            existing_summary is not None
            and existing_summary.source_fingerprint == fingerprint
            and existing_summary.source_message_count == len(dropped_history)
        ):
            self._last_summary_decision = {
                "summary_strategy": "deterministic_prefix_summary",
                "summary_action": "reused_existing",
                "fallback_reason": None,
            }
            return existing_summary

        newly_compacted_history = self._newly_compacted_history(
            dropped_history=dropped_history,
            existing_summary=existing_summary,
        )
        summary_action = (
            "updated_existing"
            if newly_compacted_history is not None and existing_summary is not None
            else "rebuilt"
        )
        draft_refs = self._draft_refs(
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
        )
        if self._compact_prompt_provider is not None:
            try:
                prompt_messages = self.build_compact_prompt(
                    dropped_history=dropped_history,
                    newly_compacted_history=newly_compacted_history,
                    existing_summary=(
                        existing_summary if summary_action == "updated_existing" else None
                    ),
                    working_digest=working_digest,
                    retained_tool_outcomes=retained_tool_outcomes,
                    current_step=str(current_step or "unknown_step"),
                    draft_refs=draft_refs,
                )
                payload = self._compact_prompt_provider(prompt_messages)
                if inspect.isawaitable(payload):
                    if not allow_async_provider:
                        close = getattr(payload, "close", None)
                        if callable(close):
                            close()
                        raise RuntimeError("compact_prompt_provider_returned_awaitable")
                    return self._validate_async_compact_payload(
                        payload=payload,
                        dropped_history=dropped_history,
                        fingerprint=fingerprint,
                        source_message_count=len(dropped_history),
                        summary_action=summary_action,
                        existing_summary=existing_summary,
                        newly_compacted_history=newly_compacted_history,
                        retained_tool_outcomes=retained_tool_outcomes,
                        working_digest=working_digest,
                    )
                summary = self.validate_compact_prompt_summary(
                    payload=payload,
                    source_fingerprint=fingerprint,
                    source_message_count=len(dropped_history),
                )
                self._last_summary_decision = {
                    "summary_strategy": "compact_prompt_summary",
                    "summary_action": summary_action,
                    "fallback_reason": None,
                }
                return summary
            except Exception as exc:
                self._last_summary_decision = {
                    "summary_strategy": "deterministic_prefix_summary",
                    "summary_action": summary_action,
                    "fallback_reason": self._fallback_reason(exc),
                }
                if summary_action == "updated_existing" and existing_summary is not None:
                    return self._deterministic_incremental_summary(
                        existing_summary=existing_summary,
                        newly_compacted_history=newly_compacted_history or [],
                        fingerprint=fingerprint,
                        source_message_count=len(dropped_history),
                        retained_tool_outcomes=retained_tool_outcomes,
                        working_digest=working_digest,
                    )
                return self._deterministic_summary(
                    dropped_history=dropped_history,
                    fingerprint=fingerprint,
                    retained_tool_outcomes=retained_tool_outcomes,
                    working_digest=working_digest,
                )

        self._last_summary_decision = {
            "summary_strategy": "deterministic_prefix_summary",
            "summary_action": summary_action,
            "fallback_reason": None,
        }
        if summary_action == "updated_existing" and existing_summary is not None:
            return self._deterministic_incremental_summary(
                existing_summary=existing_summary,
                newly_compacted_history=newly_compacted_history or [],
                fingerprint=fingerprint,
                source_message_count=len(dropped_history),
                retained_tool_outcomes=retained_tool_outcomes,
                working_digest=working_digest,
            )
        return self._deterministic_summary(
            dropped_history=dropped_history,
            fingerprint=fingerprint,
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
        )

    async def _validate_async_compact_payload(
        self,
        *,
        payload: Awaitable[dict[str, Any]],
        dropped_history: list[SetupAgentDialogueMessage],
        fingerprint: str,
        source_message_count: int,
        summary_action: str,
        existing_summary: SetupContextCompactSummary | None,
        newly_compacted_history: list[SetupAgentDialogueMessage] | None,
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
    ) -> SetupContextCompactSummary:
        try:
            summary = self.validate_compact_prompt_summary(
                payload=await payload,
                source_fingerprint=fingerprint,
                source_message_count=source_message_count,
            )
            self._last_summary_decision = {
                "summary_strategy": "compact_prompt_summary",
                "summary_action": summary_action,
                "fallback_reason": None,
            }
            return summary
        except Exception as exc:
            self._last_summary_decision = {
                "summary_strategy": "deterministic_prefix_summary",
                "summary_action": summary_action,
                "fallback_reason": self._fallback_reason(exc),
            }
            if summary_action == "updated_existing" and existing_summary is not None:
                return self._deterministic_incremental_summary(
                    existing_summary=existing_summary,
                    newly_compacted_history=newly_compacted_history or [],
                    fingerprint=fingerprint,
                    source_message_count=source_message_count,
                    retained_tool_outcomes=retained_tool_outcomes,
                    working_digest=working_digest,
                )
            return self._deterministic_summary(
                dropped_history=dropped_history,
                fingerprint=fingerprint,
                retained_tool_outcomes=retained_tool_outcomes,
                working_digest=working_digest,
            )

    def build_compact_prompt(
        self,
        *,
        dropped_history: list[SetupAgentDialogueMessage],
        existing_summary: SetupContextCompactSummary | None,
        working_digest: SetupWorkingDigest | None,
        retained_tool_outcomes: list[SetupToolOutcome],
        current_step: str,
        draft_refs: list[str],
        newly_compacted_history: list[SetupAgentDialogueMessage] | None = None,
    ) -> list[ChatMessage]:
        """Build the no-tools compact prompt pass for one setup stage."""

        incremental_update = (
            newly_compacted_history is not None and existing_summary is not None
        )
        newly_compacted_messages = (
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in newly_compacted_history
            ]
            if incremental_update and newly_compacted_history is not None
            else None
        )
        payload = {
            "current_step": current_step,
            "dropped_current_step_fingerprint": self._history_fingerprint(
                dropped_history
            ),
            "dropped_current_step_message_count": len(dropped_history),
            "incremental_update": incremental_update,
            "dropped_current_step_messages": (
                None
                if incremental_update
                else [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in dropped_history
                ]
            ),
            "newly_compacted_current_step_messages": newly_compacted_messages,
            "previous_compact_summary": (
                existing_summary.model_dump(mode="json", exclude_none=True)
                if existing_summary is not None
                else None
            ),
            "working_digest": (
                working_digest.model_dump(mode="json", exclude_none=True)
                if working_digest is not None
                else None
            ),
            "retained_tool_outcomes": [
                item.model_dump(mode="json", exclude_none=True)
                for item in retained_tool_outcomes[:6]
            ],
            "draft_refs": list(draft_refs[: self._DRAFT_REF_LIMIT]),
        }
        return [
            ChatMessage(
                role="system",
                content=(
                    "You are running SetupStageCompactPrompt. Produce a compact "
                    "carry-forward summary for older current-step setup discussion. "
                    "Do not call tools. "
                    "Do not write drafts. Do not decide readiness or commit. Preserve only "
                    "facts, decisions, open threads, draft refs, and unresolved blockers "
                    "needed for the next SetupAgent turn in this same stage. When "
                    "incremental_update is true, update previous_compact_summary using only "
                    "newly_compacted_current_step_messages; the recent raw window is still "
                    "prompt-visible elsewhere and must not be duplicated. Output JSON only."
                ),
            ),
            ChatMessage(
                role="user",
                content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        ]

    def validate_compact_prompt_summary(
        self,
        *,
        payload: dict[str, Any],
        source_fingerprint: str,
        source_message_count: int,
    ) -> SetupContextCompactSummary:
        """Validate and cap compact prompt-pass output before persistence."""

        if not isinstance(payload, dict):
            raise ValueError("compact_prompt_summary_not_json_object")
        allowed_fields = {
            "source_fingerprint",
            "source_message_count",
            "summary_lines",
            "confirmed_points",
            "open_threads",
            "rejected_directions",
            "draft_refs",
            "recovery_hints",
            "must_not_infer",
        }
        extra_fields = sorted(set(payload) - allowed_fields)
        if extra_fields:
            raise ValueError(
                f"compact_prompt_summary_forbidden_fields:{','.join(extra_fields)}"
            )

        draft_refs = self._string_list(
            payload.get("draft_refs"),
            limit=self._DRAFT_REF_LIMIT,
        )
        self._ensure_supported_refs(draft_refs)
        recovery_hints = self._recovery_hints(payload.get("recovery_hints"))
        self._ensure_supported_refs([item.ref for item in recovery_hints])
        return SetupContextCompactSummary(
            source_fingerprint=source_fingerprint,
            source_message_count=source_message_count,
            summary_lines=self._string_list(
                payload.get("summary_lines"),
                limit=self._SUMMARY_LINE_LIMIT,
            ),
            confirmed_points=self._string_list(
                payload.get("confirmed_points"),
                limit=self._CONFIRMED_POINT_LIMIT,
            ),
            open_threads=self._string_list(
                payload.get("open_threads"),
                limit=self._OPEN_THREAD_LIMIT,
            ),
            rejected_directions=self._string_list(
                payload.get("rejected_directions"),
                limit=self._REJECTED_DIRECTION_LIMIT,
            ),
            draft_refs=draft_refs,
            recovery_hints=recovery_hints,
            must_not_infer=self._string_list(
                payload.get("must_not_infer"),
                limit=self._MUST_NOT_INFER_LIMIT,
            ),
        )

    def _deterministic_summary(
        self,
        *,
        dropped_history: list[SetupAgentDialogueMessage],
        fingerprint: str,
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
    ) -> SetupContextCompactSummary:
        draft_refs = self._draft_refs(
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
        )
        return SetupContextCompactSummary(
            source_fingerprint=fingerprint,
            source_message_count=len(dropped_history),
            summary_lines=self._summary_lines(dropped_history),
            open_threads=list(
                (working_digest.open_questions if working_digest else [])[
                    : self._OPEN_THREAD_LIMIT
                ]
            ),
            rejected_directions=list(
                (working_digest.rejected_directions if working_digest else [])[
                    : self._REJECTED_DIRECTION_LIMIT
                ]
            ),
            draft_refs=draft_refs,
            recovery_hints=[
                SetupCompactRecoveryHint(
                    ref=ref,
                    reason="recover_exact_draft_detail",
                    detail="Use setup.read.draft_refs if exact current draft detail is needed.",
                )
                for ref in draft_refs[: self._RECOVERY_HINT_LIMIT]
            ],
        )

    def _deterministic_incremental_summary(
        self,
        *,
        existing_summary: SetupContextCompactSummary,
        newly_compacted_history: list[SetupAgentDialogueMessage],
        fingerprint: str,
        source_message_count: int,
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
    ) -> SetupContextCompactSummary:
        draft_refs = self._draft_refs(
            retained_tool_outcomes=retained_tool_outcomes,
            working_digest=working_digest,
        )
        merged_draft_refs = self._merge_string_lists(
            existing_summary.draft_refs,
            draft_refs,
            limit=self._DRAFT_REF_LIMIT,
        )
        return SetupContextCompactSummary(
            source_fingerprint=fingerprint,
            source_message_count=source_message_count,
            summary_lines=self._merge_string_lists(
                existing_summary.summary_lines,
                self._summary_lines(newly_compacted_history),
                limit=self._SUMMARY_LINE_LIMIT,
            ),
            confirmed_points=self._merge_string_lists(
                existing_summary.confirmed_points,
                [],
                limit=self._CONFIRMED_POINT_LIMIT,
            ),
            open_threads=self._merge_string_lists(
                existing_summary.open_threads,
                list(
                    (working_digest.open_questions if working_digest else [])[
                        : self._OPEN_THREAD_LIMIT
                    ]
                ),
                limit=self._OPEN_THREAD_LIMIT,
            ),
            rejected_directions=self._merge_string_lists(
                existing_summary.rejected_directions,
                list(
                    (working_digest.rejected_directions if working_digest else [])[
                        : self._REJECTED_DIRECTION_LIMIT
                    ]
                ),
                limit=self._REJECTED_DIRECTION_LIMIT,
            ),
            draft_refs=merged_draft_refs,
            recovery_hints=self._merge_recovery_hints(
                existing_summary.recovery_hints,
                merged_draft_refs,
            ),
            must_not_infer=self._merge_string_lists(
                existing_summary.must_not_infer,
                [],
                limit=self._MUST_NOT_INFER_LIMIT,
            ),
        )

    def _dropped_history(
        self,
        *,
        history: list[SetupAgentDialogueMessage],
        context_profile: str,
    ) -> list[SetupAgentDialogueMessage]:
        limit = self.raw_history_limit(context_profile=context_profile)
        if len(history) <= limit:
            return []
        return list(history[:-limit])

    def _newly_compacted_history(
        self,
        *,
        dropped_history: list[SetupAgentDialogueMessage],
        existing_summary: SetupContextCompactSummary | None,
    ) -> list[SetupAgentDialogueMessage] | None:
        if existing_summary is None:
            return None
        previous_count = int(existing_summary.source_message_count or 0)
        if previous_count <= 0 or previous_count >= len(dropped_history):
            return None
        previous_prefix = dropped_history[:previous_count]
        if (
            self._history_fingerprint(previous_prefix)
            != existing_summary.source_fingerprint
        ):
            return None
        return list(dropped_history[previous_count:])

    def _summary_lines(
        self,
        history: list[SetupAgentDialogueMessage],
    ) -> list[str]:
        lines: list[str] = []
        for item in history[: self._SUMMARY_LINE_LIMIT]:
            text = self._sanitize_summary_text(self._normalize_text(item.content))
            if not text:
                continue
            prefix = "User" if item.role == "user" else "Assistant"
            line = f"{prefix}: {text[: self._MAX_SUMMARY_CHARS]}"
            if line not in lines:
                lines.append(line)
        return lines

    def _draft_refs(
        self,
        *,
        retained_tool_outcomes: list[SetupToolOutcome],
        working_digest: SetupWorkingDigest | None,
    ) -> list[str]:
        refs: list[str] = []
        if working_digest is not None:
            for ref in working_digest.draft_refs:
                value = str(ref or "").strip()
                if value and self._is_supported_ref(value) and value not in refs:
                    refs.append(value)
                if len(refs) >= self._DRAFT_REF_LIMIT:
                    return refs
        for item in retained_tool_outcomes:
            for ref in item.updated_refs:
                value = str(ref or "").strip()
                if value and self._is_supported_ref(value) and value not in refs:
                    refs.append(value)
                if len(refs) >= self._DRAFT_REF_LIMIT:
                    return refs
        return refs

    def _history_fingerprint(
        self,
        history: list[SetupAgentDialogueMessage],
    ) -> str:
        payload = [
            {
                "role": item.role,
                "content": self._normalize_text(item.content),
            }
            for item in history
        ]
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    @staticmethod
    def _sanitize_summary_text(text: str) -> str:
        return re.sub(
            r"\b[A-Z]{2,}(?:_[A-Z]{2,}){2,}\b",
            lambda match: match.group(0).replace("_", " "),
            text,
        )

    def _string_list(self, value: Any, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = self._normalize_text(str(item or ""))
            if not text or text in items:
                continue
            items.append(text[: self._MAX_SUMMARY_CHARS])
            if len(items) >= limit:
                break
        return items

    def _merge_string_lists(
        self,
        existing: list[str],
        incoming: list[str],
        *,
        limit: int,
    ) -> list[str]:
        merged: list[str] = []
        for item in [*existing, *incoming]:
            text = self._normalize_text(str(item or ""))
            if not text or text in merged:
                continue
            merged.append(text[: self._MAX_SUMMARY_CHARS])
        if len(merged) <= limit:
            return merged
        return merged[:limit]

    def _recovery_hints(self, value: Any) -> list[SetupCompactRecoveryHint]:
        if not isinstance(value, list):
            return []
        hints: list[SetupCompactRecoveryHint] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            ref = self._normalize_text(str(item.get("ref") or ""))
            reason = self._normalize_text(str(item.get("reason") or ""))
            if not ref or not reason:
                continue
            detail = item.get("detail")
            hints.append(
                SetupCompactRecoveryHint(
                    ref=ref,
                    reason=reason[: self._MAX_SUMMARY_CHARS],
                    detail=(
                        self._normalize_text(str(detail))[: self._MAX_SUMMARY_CHARS]
                        if detail is not None
                        else None
                    ),
                )
            )
            if len(hints) >= self._RECOVERY_HINT_LIMIT:
                break
        return hints

    def _merge_recovery_hints(
        self,
        existing: list[SetupCompactRecoveryHint],
        refs: list[str],
    ) -> list[SetupCompactRecoveryHint]:
        hints = list(existing)
        seen_refs = {item.ref for item in hints}
        for ref in refs:
            if ref in seen_refs:
                continue
            hints.append(
                SetupCompactRecoveryHint(
                    ref=ref,
                    reason="recover_exact_draft_detail",
                    detail="Use setup.read.draft_refs if exact current draft detail is needed.",
                )
            )
            seen_refs.add(ref)
        if len(hints) <= self._RECOVERY_HINT_LIMIT:
            return hints
        return hints[: self._RECOVERY_HINT_LIMIT]

    def _ensure_supported_refs(self, refs: list[str]) -> None:
        unsupported = [ref for ref in refs if not self._is_supported_ref(ref)]
        if unsupported:
            raise ValueError(
                f"compact_prompt_summary_unsupported_refs:{','.join(unsupported)}"
            )

    def _is_supported_ref(self, ref: str) -> bool:
        if ref in self._VALID_DRAFT_REF_PREFIXES[:3]:
            return True
        return ref.startswith("foundation:") and bool(
            ref.removeprefix("foundation:").strip()
        )

    @staticmethod
    def _fallback_reason(exc: Exception) -> str:
        text = str(exc).strip()
        if not text:
            return exc.__class__.__name__
        return text[:160]
