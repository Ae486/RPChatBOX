"""State schema for the phase-1 SetupGraph shell."""
from __future__ import annotations

from typing import Any, TypedDict


class SetupGraphState(TypedDict, total=False):
    workspace_id: str
    mode: str
    current_step: str
    target_step: str | None
    model_id: str
    provider_id: str | None
    user_prompt: str
    history: list[dict[str, str]]
    stream_mode: bool
    status: str
    context_packet: dict[str, Any]
    assistant_text: str
    finish_reason: str | None
    warnings: list[str]
    response_payload: dict[str, Any]
    error: dict[str, str] | None
