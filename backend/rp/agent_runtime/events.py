"""Runtime events and typed-SSE adaptation."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeEvent(BaseModel):
    """Internal runtime event emitted during one run."""

    model_config = ConfigDict(extra="forbid")

    type: str
    run_id: str
    sequence_no: int
    payload: dict[str, Any] = Field(default_factory=dict)


class SetupEventSink:
    """Public transcript boundary for setup runtime events."""

    PUBLIC_EVENT_TYPES = frozenset(
        {
            "text_delta",
            "thinking_delta",
            "tool_call",
            "tool_started",
            "tool_result",
            "tool_error",
            "usage",
            "error",
            "done",
        }
    )
    PUBLIC_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
        "text_delta": frozenset({"delta"}),
        "thinking_delta": frozenset({"delta"}),
        "tool_call": frozenset({"tool_calls"}),
        "tool_started": frozenset({"call_id", "tool_name"}),
        "tool_result": frozenset({"call_id", "tool_name", "result"}),
        "tool_error": frozenset({"call_id", "tool_name", "error"}),
        "usage": frozenset(
            {"prompt_tokens", "completion_tokens", "total_tokens"}
        ),
        "error": frozenset({"error"}),
        "done": frozenset({"status", "finish_reason"}),
    }
    PRIVATE_PAYLOAD_KEYS = frozenset(
        {
            "debug",
            "exception",
            "model_gateway_diagnostics",
            "private_details",
            "private_diagnostics",
            "provider_delta",
            "raw",
            "raw_delta",
            "raw_provider_delta",
            "raw_provider_deltas",
            "stack",
            "stacktrace",
            "trace",
        }
    )

    @classmethod
    def to_public_payload(cls, event: RuntimeEvent) -> dict[str, Any] | None:
        """Return the public-safe SSE payload, or None for private events."""

        if event.type not in cls.PUBLIC_EVENT_TYPES:
            return None
        allowed_keys = cls.PUBLIC_PAYLOAD_KEYS.get(event.type, frozenset())
        payload: dict[str, Any] = {"type": event.type}
        for key in allowed_keys:
            if key not in event.payload:
                continue
            payload[key] = cls._sanitize_public_value(event.payload[key])
        return payload

    @classmethod
    def _sanitize_public_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._sanitize_public_value(item)
                for key, item in value.items()
                if key not in cls.PRIVATE_PAYLOAD_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize_public_value(item) for item in value]
        return value


class TypedSseEventAdapter:
    """Render runtime events as the existing typed SSE protocol."""

    @staticmethod
    def to_payload(event: RuntimeEvent) -> dict[str, Any] | None:
        return SetupEventSink.to_public_payload(event)

    @classmethod
    def to_sse_line(cls, event: RuntimeEvent) -> str | None:
        payload = cls.to_payload(event)
        if payload is None:
            return None
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
