"""Writing runtime packet models for active-story MVP."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WritingPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str
    session_id: str
    chapter_workspace_id: str
    output_kind: Literal["chapter_outline", "discussion_message", "story_segment"]
    phase: str
    system_sections: list[str] = Field(default_factory=list)
    context_sections: list[dict[str, Any]] = Field(default_factory=list)
    user_instruction: str
    metadata: dict[str, Any] = Field(default_factory=dict)
