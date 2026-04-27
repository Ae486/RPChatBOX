"""Lazy Block consumer registry for active-story runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from models.rp_story_store import StoryBlockConsumerStateRecord
from rp.models.block_consumer import (
    DEFAULT_BLOCK_CONSUMERS,
    BlockConsumerKey,
    RpBlockConsumerAttachmentView,
    RpBlockConsumerStateView,
)
from rp.models.block_view import RpBlockView

from .rp_block_read_service import RpBlockReadService
from .story_session_service import StorySessionService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StoryBlockConsumerStateService:
    """Track which Block revisions each active-story consumer has consumed."""

    def __init__(
        self,
        *,
        session: Session,
        story_session_service: StorySessionService,
        rp_block_read_service: RpBlockReadService,
    ) -> None:
        self._session = session
        self._story_session_service = story_session_service
        self._rp_block_read_service = rp_block_read_service

    def list_consumers(self, *, session_id: str) -> list[RpBlockConsumerStateView]:
        self._require_session(session_id)
        return [
            self._build_view(session_id=session_id, consumer_key=consumer_key)
            for consumer_key in DEFAULT_BLOCK_CONSUMERS
        ]

    def get_consumer(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockConsumerStateView | None:
        self._require_session(session_id)
        if consumer_key not in DEFAULT_BLOCK_CONSUMERS:
            return None
        return self._build_view(session_id=session_id, consumer_key=consumer_key)

    def mark_consumer_synced(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> RpBlockConsumerStateView | None:
        self._require_session(session_id)
        if consumer_key not in DEFAULT_BLOCK_CONSUMERS:
            return None
        attached_blocks = self._attached_blocks(
            session_id=session_id,
            consumer_key=consumer_key,
        )
        record = self._get_record(session_id=session_id, consumer_key=consumer_key)
        now = _utcnow()
        if record is None:
            record = StoryBlockConsumerStateRecord(
                consumer_state_id=f"consumer_state_{uuid4().hex[:12]}",
                session_id=session_id,
                consumer_key=consumer_key,
                created_at=now,
            )
        current_chapter_workspace_id = self._current_chapter_workspace_id(session_id)
        current_revision_map = {
            block.block_id: block.revision for block in attached_blocks
        }
        snapshot_changed = (
            record.last_synced_at is None
            or record.chapter_workspace_id != current_chapter_workspace_id
            or dict(record.last_synced_revisions_json or {}) != current_revision_map
        )
        record.chapter_workspace_id = current_chapter_workspace_id
        record.last_synced_revisions_json = current_revision_map
        if snapshot_changed:
            record.last_synced_at = now
            record.updated_at = now
            self._session.add(record)
            self._session.flush()
        return self._build_view(
            session_id=session_id,
            consumer_key=consumer_key,
            record=record,
            attached_blocks=attached_blocks,
        )

    def get_consumer_record(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> StoryBlockConsumerStateRecord | None:
        self._require_session(session_id)
        if consumer_key not in DEFAULT_BLOCK_CONSUMERS:
            return None
        return self._get_record(session_id=session_id, consumer_key=consumer_key)

    def mark_consumer_compiled(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
        attached_blocks: list[RpBlockView],
        chapter_workspace_id: str | None,
        prompt_overlay: str,
    ) -> StoryBlockConsumerStateRecord | None:
        self._require_session(session_id)
        if consumer_key not in DEFAULT_BLOCK_CONSUMERS:
            return None
        record = self._get_record(session_id=session_id, consumer_key=consumer_key)
        now = _utcnow()
        if record is None:
            record = StoryBlockConsumerStateRecord(
                consumer_state_id=f"consumer_state_{uuid4().hex[:12]}",
                session_id=session_id,
                consumer_key=consumer_key,
                created_at=now,
            )
        record.last_compiled_revisions_json = {
            block.block_id: int(block.revision) for block in attached_blocks
        }
        record.last_compiled_chapter_workspace_id = chapter_workspace_id
        record.last_compiled_prompt_overlay = prompt_overlay
        record.last_compiled_at = now
        record.updated_at = now
        self._session.add(record)
        self._session.flush()
        return record

    def _build_view(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
        record: StoryBlockConsumerStateRecord | None = None,
        attached_blocks: list[RpBlockView] | None = None,
    ) -> RpBlockConsumerStateView:
        if record is None:
            record = self._get_record(session_id=session_id, consumer_key=consumer_key)
        if attached_blocks is None:
            attached_blocks = self._attached_blocks(
                session_id=session_id,
                consumer_key=consumer_key,
            )
        current_chapter_workspace_id = self._current_chapter_workspace_id(session_id)
        last_synced_revisions = (
            dict(record.last_synced_revisions_json or {}) if record is not None else {}
        )
        current_revision_map = {
            block.block_id: int(block.revision) for block in attached_blocks
        }
        dirty_reasons: list[str] = []
        dirty_block_ids: list[str] = []
        detached_block_ids = sorted(
            block_id
            for block_id in last_synced_revisions
            if block_id not in current_revision_map
        )
        if record is None or record.last_synced_at is None:
            dirty_reasons.append("never_synced")
            dirty_block_ids = [block.block_id for block in attached_blocks]
        else:
            record_chapter_workspace_id = record.chapter_workspace_id
            if current_chapter_workspace_id != record_chapter_workspace_id:
                dirty_reasons.append("chapter_workspace_changed")
            dirty_block_ids = [
                block.block_id
                for block in attached_blocks
                if last_synced_revisions.get(block.block_id) != block.revision
            ]
            if dirty_block_ids:
                dirty_reasons.append("block_revision_changed")
            if detached_block_ids:
                dirty_reasons.append("block_detached")
        return RpBlockConsumerStateView(
            consumer_key=consumer_key,
            session_id=session_id,
            chapter_workspace_id=current_chapter_workspace_id,
            dirty=bool(dirty_reasons),
            dirty_reasons=dirty_reasons,
            dirty_block_ids=dirty_block_ids,
            attached_blocks=[self._attachment_view(block) for block in attached_blocks],
            last_synced_at=record.last_synced_at if record is not None else None,
            metadata={
                "consumer_scope": "chapter",
                "attachment_mode": "session_default",
                "detached_block_ids": detached_block_ids,
            },
        )

    def _attached_blocks(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> list[RpBlockView]:
        if consumer_key == "story.writer_packet":
            return [
                block
                for block in self._rp_block_read_service.list_projection_blocks(
                    session_id=session_id
                )
                if bool(block.items_json)
            ]
        return self._rp_block_read_service.list_core_state_blocks(session_id=session_id)

    def _current_chapter_workspace_id(self, session_id: str) -> str | None:
        chapter = self._story_session_service.get_current_chapter(session_id)
        return chapter.chapter_workspace_id if chapter is not None else None

    def _get_record(
        self,
        *,
        session_id: str,
        consumer_key: BlockConsumerKey,
    ) -> StoryBlockConsumerStateRecord | None:
        stmt = (
            select(StoryBlockConsumerStateRecord)
            .where(StoryBlockConsumerStateRecord.session_id == session_id)
            .where(StoryBlockConsumerStateRecord.consumer_key == consumer_key)
        )
        return self._session.exec(stmt).first()

    def _require_session(self, session_id: str) -> None:
        if self._story_session_service.get_session(session_id) is None:
            raise ValueError(f"StorySession not found: {session_id}")

    @staticmethod
    def _attachment_view(block: RpBlockView) -> RpBlockConsumerAttachmentView:
        return RpBlockConsumerAttachmentView(
            block_id=block.block_id,
            label=block.label,
            layer=block.layer,
            domain=block.domain,
            domain_path=block.domain_path,
            scope=block.scope,
            revision=block.revision,
            source=block.source,
        )
