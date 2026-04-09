"""Conversation source-thread models backed by LangGraph checkpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationSourceMessage(BaseModel):
    """Frontend-facing source message payload/read model."""

    id: str
    role: Literal["system", "user", "assistant"]
    content: str
    created_at: datetime = Field(default_factory=_utcnow)
    edited_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_name: str | None = None
    provider_name: str | None = None
    attached_files: list[dict[str, Any]] = Field(default_factory=list)
    thinking_duration_seconds: int | None = None


class ConversationSourceSummary(BaseModel):
    """Selected source-thread snapshot for a conversation."""

    conversation_id: UUID
    checkpoint_id: str | None = None
    latest_checkpoint_id: str | None = None
    selected_checkpoint_id: str | None = None
    messages: list[ConversationSourceMessage] = Field(default_factory=list)


class ConversationSourceCheckpointSummary(BaseModel):
    """A single persisted checkpoint in the source-thread history."""

    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    source: str | None = None
    step: int | None = None
    created_at: datetime | None = None
    message_count: int = 0
    last_message_id: str | None = None
    last_message_role: str | None = None
    last_message_preview: str | None = None


class ConversationSourceWriteRequest(BaseModel):
    """Append/fork source-thread messages from an optional base checkpoint."""

    base_checkpoint_id: str | None = None
    messages: list[ConversationSourceMessage] = Field(min_length=1)
    select_after_write: bool = True
    touch_last_activity: bool = True


class ConversationSourcePatchRequest(BaseModel):
    """Patch a single existing source-thread message in place."""

    base_checkpoint_id: str | None = None
    content: str
    edited_at: datetime | None = None
    select_after_write: bool = True
    touch_last_activity: bool = True


class ConversationSourceSelectionRequest(BaseModel):
    """Switch the selected source-thread checkpoint for a conversation."""

    checkpoint_id: str | None = None
