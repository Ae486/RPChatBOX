"""Conversation/session storage service backed by SQLModel."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, desc
from sqlmodel import Session, select

from models.conversation_store import (
    ConversationCreateRequest,
    ConversationRecord,
    ConversationSettingsPayload,
    ConversationSettingsRecord,
    ConversationUpdateRequest,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_conversation_title() -> str:
    now = datetime.now()
    return f"新对话 {now.month}/{now.day}"


class ConversationStoreService:
    """Database-backed CRUD for conversation metadata and settings."""

    def __init__(self, session: Session):
        self._session = session

    def list_conversations(
        self,
        *,
        include_archived: bool = False,
        include_deleted: bool = False,
        role_id: str | None = None,
    ) -> list[ConversationRecord]:
        pin_sort = case((ConversationRecord.pinned_at.is_(None), 1), else_=0)
        statement = select(ConversationRecord)
        if not include_deleted:
            statement = statement.where(ConversationRecord.deleted_at.is_(None))
        if not include_archived:
            statement = statement.where(ConversationRecord.archived_at.is_(None))
        if role_id:
            statement = statement.where(ConversationRecord.role_id == role_id)
        statement = statement.order_by(
            pin_sort,
            desc(ConversationRecord.pinned_at),
            desc(ConversationRecord.last_activity_at),
            desc(ConversationRecord.created_at),
        )
        return list(self._session.exec(statement).all())

    def get_conversation(
        self,
        conversation_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> ConversationRecord | None:
        record = self._session.get(ConversationRecord, conversation_id)
        if record is None:
            return None
        if record.deleted_at is not None and not include_deleted:
            return None
        return record

    def create_conversation(
        self,
        payload: ConversationCreateRequest,
    ) -> ConversationRecord:
        now = _utcnow()
        title = (payload.title or "").strip() or _default_conversation_title()
        record = ConversationRecord(
            title=title,
            system_prompt=payload.system_prompt,
            role_id=payload.role_id,
            role_type=payload.role_type,
            created_at=now,
            updated_at=now,
            last_activity_at=now,
        )
        self._session.add(record)
        self._session.flush()
        self._session.add(
            ConversationSettingsRecord(
                conversation_id=record.id,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.commit()
        self._session.refresh(record)
        return record

    def update_conversation(
        self,
        conversation_id: UUID,
        payload: ConversationUpdateRequest,
    ) -> ConversationRecord | None:
        record = self.get_conversation(conversation_id)
        if record is None:
            return None

        updates = payload.model_dump(exclude_unset=True)
        now = _utcnow()
        for field_name in (
            "title",
            "system_prompt",
            "role_id",
            "role_type",
            "latest_checkpoint_id",
            "selected_checkpoint_id",
        ):
            if field_name in updates:
                setattr(record, field_name, updates[field_name])

        if "is_pinned" in updates:
            record.pinned_at = now if updates["is_pinned"] else None
        if "is_archived" in updates:
            record.archived_at = now if updates["is_archived"] else None

        should_touch_activity = bool(updates.get("touch_last_activity"))
        should_touch_activity = should_touch_activity or any(
            field_name in updates
            for field_name in (
                "system_prompt",
                "latest_checkpoint_id",
                "selected_checkpoint_id",
            )
        )
        if should_touch_activity:
            record.last_activity_at = now

        record.updated_at = now
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def soft_delete_conversation(self, conversation_id: UUID) -> bool:
        record = self.get_conversation(conversation_id)
        if record is None:
            return False
        now = _utcnow()
        record.deleted_at = now
        record.updated_at = now
        self._session.add(record)
        self._session.commit()
        return True

    def get_or_create_settings(
        self,
        conversation_id: UUID,
    ) -> ConversationSettingsRecord | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        settings = self._session.get(ConversationSettingsRecord, conversation_id)
        if settings is not None:
            return settings

        now = _utcnow()
        settings = ConversationSettingsRecord(
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(settings)
        self._session.commit()
        self._session.refresh(settings)
        return settings

    def upsert_settings(
        self,
        conversation_id: UUID,
        payload: ConversationSettingsPayload,
    ) -> ConversationSettingsRecord | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        settings = self._session.get(ConversationSettingsRecord, conversation_id)
        now = _utcnow()
        if settings is None:
            settings = ConversationSettingsRecord(
                conversation_id=conversation_id,
                created_at=now,
            )

        settings.selected_provider_id = payload.selected_provider_id
        settings.selected_model_id = payload.selected_model_id
        settings.parameters = dict(payload.parameters)
        settings.enable_vision = payload.enable_vision
        settings.enable_tools = payload.enable_tools
        settings.enable_network = payload.enable_network
        settings.enable_experimental_streaming_markdown = (
            payload.enable_experimental_streaming_markdown
        )
        settings.context_length = payload.context_length
        settings.updated_at = now

        conversation.last_activity_at = now
        conversation.updated_at = now

        self._session.add(settings)
        self._session.add(conversation)
        self._session.commit()
        self._session.refresh(settings)
        return settings
