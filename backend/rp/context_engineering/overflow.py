"""Provider overflow signal classification."""

from __future__ import annotations

from collections.abc import Sequence

from rp.context_engineering.contracts import ContextOverflowSignal


def classify_overflow_signal(
    *,
    provider_name: str,
    raw_message: str | None,
    known_signals: Sequence[str] = (),
) -> ContextOverflowSignal:
    """Classify obvious provider context-window failures without retry wiring."""

    text = str(raw_message or "").lower()
    known = [signal.lower() for signal in known_signals]
    context_markers = [
        "context length",
        "maximum context",
        "context window",
        "too many tokens",
        "token limit",
        "prompt is too long",
        "maximum tokens",
    ]
    if any(signal and signal in text for signal in known) or any(
        marker in text for marker in context_markers
    ):
        return ContextOverflowSignal(
            provider_name=provider_name,
            signal_kind="context_length_error",
            raw_message=raw_message,
            recommended_action="compact_retry",
        )
    if "tool result" in text and ("too large" in text or "exceeds" in text):
        return ContextOverflowSignal(
            provider_name=provider_name,
            signal_kind="tool_result_too_large",
            raw_message=raw_message,
            recommended_action="trim_retry",
        )
    return ContextOverflowSignal(
        provider_name=provider_name,
        signal_kind="unknown",
        raw_message=raw_message,
        recommended_action="fail_closed",
    )
