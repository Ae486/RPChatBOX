"""Internal structured stream events for backend LLM streaming."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


StreamEventKind = Literal[
    "thinking",
    "text",
    "tool_call",
    "tool_started",
    "tool_result",
    "tool_error",
    "usage",
    "error",
    "raw",
]


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """Backend-internal stream event before compatibility emission."""

    kind: StreamEventKind
    text: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_output: str | None = None
    tool_error_message: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    raw_chunk: dict[str, Any] | None = None

    @classmethod
    def thinking(cls, text: str) -> "StreamEvent":
        return cls(kind="thinking", text=text)

    @classmethod
    def text_delta(cls, text: str) -> "StreamEvent":
        return cls(kind="text", text=text)

    @classmethod
    def tool_call(cls, tool_calls: list[dict[str, Any]]) -> "StreamEvent":
        return cls(kind="tool_call", tool_calls=tool_calls)

    @classmethod
    def tool_started(
        cls,
        *,
        call_id: str,
        tool_name: str | None = None,
    ) -> "StreamEvent":
        return cls(kind="tool_started", tool_call_id=call_id, tool_name=tool_name)

    @classmethod
    def tool_result(
        cls,
        *,
        call_id: str,
        result: str,
        tool_name: str | None = None,
    ) -> "StreamEvent":
        return cls(
            kind="tool_result",
            tool_call_id=call_id,
            tool_name=tool_name,
            tool_output=result,
        )

    @classmethod
    def tool_error(
        cls,
        *,
        call_id: str,
        error_message: str,
        tool_name: str | None = None,
    ) -> "StreamEvent":
        return cls(
            kind="tool_error",
            tool_call_id=call_id,
            tool_name=tool_name,
            tool_error_message=error_message,
        )

    @classmethod
    def usage(
        cls,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> "StreamEvent":
        return cls(
            kind="usage",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @classmethod
    def error(cls, raw_chunk: dict[str, Any]) -> "StreamEvent":
        return cls(kind="error", raw_chunk=raw_chunk)

    @classmethod
    def raw(cls, raw_chunk: dict[str, Any]) -> "StreamEvent":
        return cls(kind="raw", raw_chunk=raw_chunk)
