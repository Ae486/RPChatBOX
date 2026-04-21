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


class TypedSseEventAdapter:
    """Render runtime events as the existing typed SSE protocol."""

    @staticmethod
    def to_payload(event: RuntimeEvent) -> dict[str, Any]:
        payload = {"type": event.type}
        payload.update(event.payload)
        return payload

    @classmethod
    def to_sse_line(cls, event: RuntimeEvent) -> str:
        return f"data: {json.dumps(cls.to_payload(event), ensure_ascii=False)}\n\n"

