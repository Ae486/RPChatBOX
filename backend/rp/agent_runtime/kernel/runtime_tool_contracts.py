"""Setup-free runtime tool contracts for RP agent execution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeToolCall(BaseModel):
    """Normalized model-declared tool call."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    source_round: int


class RuntimeToolResult(BaseModel):
    """Normalized tool execution outcome."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    success: bool
    content_text: str
    error_code: str | None = None
    structured_payload: dict[str, Any] | None = None
