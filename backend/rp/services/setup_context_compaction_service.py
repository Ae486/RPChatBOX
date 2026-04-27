"""Compaction helpers for trimmed older setup-stage discussion history."""
from __future__ import annotations

import hashlib
import json
import re

from rp.agent_runtime.contracts import (
    SetupContextCompactSummary,
    SetupToolOutcome,
    SetupWorkingDigest,
)
from rp.models.setup_agent import SetupAgentDialogueMessage


class SetupContextCompactionService:
    """Build thin carry-forward summaries for older current-step history."""

    _STANDARD_RECENT_HISTORY_MESSAGES = 6
    _COMPACT_RECENT_HISTORY_MESSAGES = 4
    _SUMMARY_LINE_LIMIT = 6
    _OPEN_THREAD_LIMIT = 4
    _DRAFT_REF_LIMIT = 6
    _MAX_SUMMARY_CHARS = 180

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
    ) -> SetupContextCompactSummary | None:
        dropped_history = self._dropped_history(
            history=history,
            context_profile=context_profile,
        )
        if not dropped_history:
            return None

        fingerprint = self._history_fingerprint(dropped_history)
        if (
            existing_summary is not None
            and existing_summary.source_fingerprint == fingerprint
            and existing_summary.source_message_count == len(dropped_history)
        ):
            return existing_summary

        return SetupContextCompactSummary(
            source_fingerprint=fingerprint,
            source_message_count=len(dropped_history),
            summary_lines=self._summary_lines(dropped_history),
            open_threads=list((working_digest.open_questions if working_digest else [])[: self._OPEN_THREAD_LIMIT]),
            draft_refs=self._draft_refs(retained_tool_outcomes),
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

    def _summary_lines(
        self,
        history: list[SetupAgentDialogueMessage],
    ) -> list[str]:
        lines: list[str] = []
        for item in history[-self._SUMMARY_LINE_LIMIT :]:
            text = self._normalize_text(item.content)
            if not text:
                continue
            prefix = "User" if item.role == "user" else "Assistant"
            line = f"{prefix}: {text[: self._MAX_SUMMARY_CHARS]}"
            if line not in lines:
                lines.append(line)
        return lines

    def _draft_refs(
        self,
        retained_tool_outcomes: list[SetupToolOutcome],
    ) -> list[str]:
        refs: list[str] = []
        for item in retained_tool_outcomes:
            for ref in item.updated_refs:
                value = str(ref or "").strip()
                if value and value not in refs:
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
