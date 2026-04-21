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


class ConversationCompactSummaryRecord(SQLModel, table=True):
    """Durable compact summary state for a conversation."""

    __tablename__ = "conversation_compact_summaries"

    conversation_id: UUID = Field(
        primary_key=True,
        foreign_key="conversations.id",
    )
    summary: str | None = None
    range_start_message_id: str | None = None
    range_end_message_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConversationSourceVisibilityRecord(SQLModel, table=True):
    """Logical visibility state layered on top of immutable source checkpoints."""

    __tablename__ = "conversation_source_visibility"

    conversation_id: UUID = Field(
        primary_key=True,
        foreign_key="conversations.id",
    )
    hidden_message_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConversationSourceGraphRecord(SQLModel, table=True):
    """Backend-owned persisted source tree and checkpoint bindings."""

    __tablename__ = "conversation_source_graph"

    conversation_id: UUID = Field(
        primary_key=True,
        foreign_key="conversations.id",
    )
    namespace: str = ""
    thread_state: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    checkpoint_by_message_id: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    current_message_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConversationAttachmentRecord(SQLModel, table=True):
    """Backend-owned durable attachment metadata."""

    __tablename__ = "conversation_attachments"

    id: str = Field(primary_key=True, index=True)
    conversation_id: UUID = Field(
        foreign_key="conversations.id",
        index=True,
    )
    storage_key: str
    local_path: str
    original_name: str
    mime_type: str
    size_bytes: int
    kind: str
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


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


class ConversationCompactSummaryPayload(BaseModel):
    """Payload for backend-owned compact summary state."""

    summary: str | None = None
    range_start_message_id: str | None = None
    range_end_message_id: str | None = None
    touch_last_activity: bool = False


class ConversationCompactSummary(BaseModel):
    """Frontend-facing compact summary state for a conversation."""

    conversation_id: UUID
    summary: str | None = None
    range_start_message_id: str | None = None
    range_end_message_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def empty(cls, conversation_id: UUID) -> "ConversationCompactSummary":
        return cls(conversation_id=conversation_id)

    @classmethod
    def from_record(
        cls,
        record: ConversationCompactSummaryRecord,
    ) -> "ConversationCompactSummary":
        return cls(
            conversation_id=record.conversation_id,
            summary=record.summary,
            range_start_message_id=record.range_start_message_id,
            range_end_message_id=record.range_end_message_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


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


class ConversationAttachmentUploadItem(BaseModel):
    """Attachment upload payload for durable conversation storage."""

    client_id: str | None = None
    name: str
    mime_type: str
    kind: str | None = None
    path: str | None = None
    data: str | None = None
    metadata: dict[str, Any] = PydanticField(default_factory=dict)

    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def model_post_init(self, __context: Any) -> None:
        self.client_id = self._normalize_text(self.client_id)
        self.path = self._normalize_text(self.path)
        if not self.data and not self.path:
            raise ValueError("At least one of 'data' or 'path' must be provided")


class ConversationAttachmentUploadRequest(BaseModel):
    """Batch upload request for conversation attachments."""

    files: list[ConversationAttachmentUploadItem] = PydanticField(min_length=1)


class ConversationAttachmentSummary(BaseModel):
    """Frontend-facing durable attachment metadata."""

    id: str
    conversation_id: UUID
    storage_key: str
    local_path: str
    original_name: str
    mime_type: str
    size_bytes: int
    kind: str
    metadata: dict[str, Any] = PydanticField(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_record(
        cls,
        record: ConversationAttachmentRecord,
    ) -> "ConversationAttachmentSummary":
        return cls(
            id=record.id,
            conversation_id=record.conversation_id,
            storage_key=record.storage_key,
            local_path=record.local_path,
            original_name=record.original_name,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            kind=record.kind,
            metadata=dict(record.metadata_json or {}),
            created_at=record.created_at,
        )
