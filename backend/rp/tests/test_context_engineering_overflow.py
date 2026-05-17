"""Overflow signal classification tests."""

from __future__ import annotations

from rp.context_engineering.overflow import classify_overflow_signal


def test_obvious_context_length_message_classifies_as_context_error():
    signal = classify_overflow_signal(
        provider_name="openai",
        raw_message="This model's maximum context length is 128000 tokens.",
    )

    assert signal.signal_kind == "context_length_error"
    assert signal.recommended_action == "compact_retry"


def test_unknown_message_classifies_as_unknown_without_retry_wiring():
    signal = classify_overflow_signal(
        provider_name="unknown",
        raw_message="temporary upstream issue",
    )

    assert signal.signal_kind == "unknown"
    assert signal.recommended_action == "fail_closed"
