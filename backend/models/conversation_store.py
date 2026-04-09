"""Conversation/session persistence models for backend true-source migration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def default_conversation_parameters() -> dict[str, Any]:
    """Return Flutter-compatible default generation parameters."""
    return {
        "temperature": 0.7,
        "maxTokens": 2048,
        "topP": 1.0,
        "frequencyPenalty": 0.0,
        "presencePenalty": 0.0,
        "streamOutput": True,
    }


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class ConversationRecord(SQLModel, table=True):
    """Stable business metadata for a conversation/thread."""

    __tablename__ = "conversations"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    title: str
    system_prompt: str | None = None
    role_id: str | None = Field(default=None, index=True)
    role_type: str | None = None
    latest_checkpoint_id: str | None = None
    selected_checkpoint_id: str | None = None
    pinned_at: datetime | None = Field(default=None, index=True)
    archived_at: datetime | None = Field(default=None, index=True)
    deleted_at: datetime | None = Field(default=None, index=True)
    last_activity_at: datetime = Field(default_factory=_utcnow, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class ConversationSettingsRecord(SQLModel, table=True):
    """Durable generation-affecting settings for a conversation."""

    __tablename__ = "conversation_settings"

    conversation_id: UUID = Field(
        primary_key=True,
        foreign_key="conversations.id",
    )
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    parameters: dict[str, Any] = Field(
        default_factory=default_conversation_parameters,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    enable_vision: bool = False
    enable_tools: bool = False
    enable_network: bool = False
    enable_experimental_streaming_markdown: bool = False
    context_length: int = 10
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConversationCreateRequest(BaseModel):
    """Payload for creating a new backend-owned conversation."""

    title: str | None = None
    system_prompt: str | None = None
    role_id: str | None = None
    role_type: str | None = None


class ConversationUpdateRequest(BaseModel):
    """Partial update payload for conversation metadata."""

    title: str | None = None
    system_prompt: str | None = None
    role_id: str | None = None
    role_type: str | None = None
    latest_checkpoint_id: str | None = None
    selected_checkpoint_id: str | None = None
    is_pinned: bool | None = None
    is_archived: bool | None = None
    touch_last_activity: bool = False


class ConversationSummary(BaseModel):
    """Frontend-facing conversation metadata summary."""

    id: UUID
    title: str
    system_prompt: str | None = None
    role_id: str | None = None
    role_type: str | None = None
    latest_checkpoint_id: str | None = None
    selected_checkpoint_id: str | None = None
    is_pinned: bool = False
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime

    @classmethod
    def from_record(cls, record: ConversationRecord) -> "ConversationSummary":
        return cls(
            id=record.id,
            title=record.title,
            system_prompt=record.system_prompt,
            role_id=record.role_id,
            role_type=record.role_type,
            latest_checkpoint_id=record.latest_checkpoint_id,
            selected_checkpoint_id=record.selected_checkpoint_id,
            is_pinned=record.pinned_at is not None,
            is_archived=record.archived_at is not None,
            created_at=record.created_at,
            updated_at=record.updated_at,
            last_activity_at=record.last_activity_at,
        )


class ConversationSettingsPayload(BaseModel):
    """Frontend-facing conversation settings payload."""

    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    parameters: dict[str, Any] = PydanticField(
        default_factory=default_conversation_parameters
    )
    enable_vision: bool = False
    enable_tools: bool = False
    enable_network: bool = False
    enable_experimental_streaming_markdown: bool = False
    context_length: int = 10


class ConversationSettingsSummary(ConversationSettingsPayload):
    """Conversation settings response including ownership metadata."""

    conversation_id: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: ConversationSettingsRecord,
    ) -> "ConversationSettingsSummary":
        return cls(
            conversation_id=record.conversation_id,
            selected_provider_id=record.selected_provider_id,
            selected_model_id=record.selected_model_id,
            parameters=dict(record.parameters or {}),
            enable_vision=record.enable_vision,
            enable_tools=record.enable_tools,
            enable_network=record.enable_network,
            enable_experimental_streaming_markdown=record.enable_experimental_streaming_markdown,
            context_length=record.context_length,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
