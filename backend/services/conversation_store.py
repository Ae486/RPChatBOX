"""Conversation/session storage service backed by SQLModel."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, desc
from sqlmodel import Session, select

from models.conversation_store import (
    ConversationAttachmentRecord,
    ConversationCreateRequest,
    ConversationCompactSummaryPayload,
    ConversationCompactSummaryRecord,
    ConversationRecord,
    ConversationSourceGraphRecord,
    ConversationSettingsPayload,
    ConversationSettingsRecord,
    ConversationSourceVisibilityRecord,
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

    def get_source_visibility(
        self,
        conversation_id: UUID,
    ) -> ConversationSourceVisibilityRecord | None:
        return self._session.get(ConversationSourceVisibilityRecord, conversation_id)

    def get_compact_summary(
        self,
        conversation_id: UUID,
    ) -> ConversationCompactSummaryRecord | None:
        return self._session.get(ConversationCompactSummaryRecord, conversation_id)

    def get_source_graph(
        self,
        conversation_id: UUID,
    ) -> ConversationSourceGraphRecord | None:
        return self._session.get(ConversationSourceGraphRecord, conversation_id)

    def upsert_source_graph(
        self,
        conversation_id: UUID,
        *,
        namespace: str,
        thread_state: dict,
        checkpoint_by_message_id: dict[str, str],
        current_message_id: str | None,
    ) -> ConversationSourceGraphRecord | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        record = self.get_source_graph(conversation_id)
        now = _utcnow()
        if record is None:
            record = ConversationSourceGraphRecord(
                conversation_id=conversation_id,
                created_at=now,
            )

        record.namespace = namespace
        record.thread_state = dict(thread_state)
        record.checkpoint_by_message_id = dict(checkpoint_by_message_id)
        record.current_message_id = current_message_id
        record.updated_at = now
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def delete_source_graph(self, conversation_id: UUID) -> bool:
        record = self.get_source_graph(conversation_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.commit()
        return True

    def get_hidden_source_message_ids(self, conversation_id: UUID) -> list[str]:
        record = self.get_source_visibility(conversation_id)
        if record is None:
            return []
        return list(record.hidden_message_ids or [])

    def set_hidden_source_message_ids(
        self,
        conversation_id: UUID,
        hidden_message_ids: list[str],
    ) -> ConversationSourceVisibilityRecord | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        record = self.get_source_visibility(conversation_id)
        now = _utcnow()
        if record is None:
            record = ConversationSourceVisibilityRecord(
                conversation_id=conversation_id,
                created_at=now,
            )

        record.hidden_message_ids = list(hidden_message_ids)
        record.updated_at = now
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def upsert_compact_summary(
        self,
        conversation_id: UUID,
        payload: ConversationCompactSummaryPayload,
    ) -> ConversationCompactSummaryRecord | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        now = _utcnow()
        record = self.get_compact_summary(conversation_id)
        if record is None:
            record = ConversationCompactSummaryRecord(
                conversation_id=conversation_id,
                created_at=now,
            )

        record.summary = payload.summary
        record.range_start_message_id = payload.range_start_message_id
        record.range_end_message_id = payload.range_end_message_id
        record.updated_at = now

        conversation.updated_at = now
        if payload.touch_last_activity:
            conversation.last_activity_at = now

        self._session.add(record)
        self._session.add(conversation)
        self._session.commit()
        self._session.refresh(record)
        return record

    def clear_compact_summary(self, conversation_id: UUID) -> bool:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return False

        record = self.get_compact_summary(conversation_id)
        if record is None:
            return True

        conversation.updated_at = _utcnow()
        self._session.add(conversation)
        self._session.delete(record)
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

    def list_attachments(
        self,
        conversation_id: UUID,
    ) -> list[ConversationAttachmentRecord]:
        statement = (
            select(ConversationAttachmentRecord)
            .where(ConversationAttachmentRecord.conversation_id == conversation_id)
            .order_by(ConversationAttachmentRecord.created_at)
        )
        return list(self._session.exec(statement).all())

    def get_attachment(self, attachment_id: str) -> ConversationAttachmentRecord | None:
        return self._session.get(ConversationAttachmentRecord, attachment_id)

    def upsert_attachment(
        self,
        *,
        attachment_id: str,
        conversation_id: UUID,
        storage_key: str,
        local_path: str,
        original_name: str,
        mime_type: str,
        size_bytes: int,
        kind: str,
        metadata_payload: dict,
    ) -> ConversationAttachmentRecord | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None

        record = self.get_attachment(attachment_id)
        if record is None:
            record = ConversationAttachmentRecord(
                id=attachment_id,
                conversation_id=conversation_id,
                created_at=_utcnow(),
            )

        record.conversation_id = conversation_id
        record.storage_key = storage_key
        record.local_path = local_path
        record.original_name = original_name
        record.mime_type = mime_type
        record.size_bytes = size_bytes
        record.kind = kind
        record.metadata_json = dict(metadata_payload)

        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record
