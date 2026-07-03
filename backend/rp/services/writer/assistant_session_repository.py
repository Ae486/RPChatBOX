"""Persistence repository for writing-assistant chat sessions (S6-4).

Story-scoped agent conversations with switch/resume support. Sessions are
NOT story truth (REV-028): turns carry display text plus candidate
references; deleting a session leaves candidates/artifacts/receipts intact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc
from sqlmodel import Session, select

from models.rp_assistant_store import AssistantSessionRecord
from rp.errors import RPError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssistantSessionRepositoryError(RPError, ValueError):
    """Stable assistant-session repository error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class AssistantSessionRepository:
    """CRUD for story-scoped assistant sessions (list/load/upsert/delete)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_sessions(self, story_id: str) -> list[AssistantSessionRecord]:
        stmt = (
            select(AssistantSessionRecord)
            .where(AssistantSessionRecord.story_id == story_id)
            .order_by(
                desc(AssistantSessionRecord.updated_at),
                desc(AssistantSessionRecord.created_at),
            )
        )
        return list(self._session.exec(stmt).all())

    def load_session(self, assistant_session_id: str) -> AssistantSessionRecord | None:
        return self._session.get(AssistantSessionRecord, assistant_session_id)

    def save_session(
        self,
        *,
        assistant_session_id: str | None = None,
        story_id: str,
        title: str | None = None,
        messages: list[dict[str, Any]],
    ) -> AssistantSessionRecord:
        record = (
            self._session.get(AssistantSessionRecord, assistant_session_id)
            if assistant_session_id is not None
            else None
        )
        now = _utcnow()
        if record is None:
            record = AssistantSessionRecord(
                assistant_session_id=(
                    assistant_session_id or f"assistant_session_{uuid4().hex[:12]}"
                ),
                story_id=story_id,
                title=title or "",
                messages_json=list(messages),
                created_at=now,
                updated_at=now,
            )
        else:
            if record.story_id != story_id:
                raise AssistantSessionRepositoryError(
                    "assistant_session_story_mismatch",
                    record.story_id,
                )
            if title is not None:
                record.title = title
            record.messages_json = list(messages)
            record.updated_at = now
        self._session.add(record)
        self._session.flush()
        return record

    def delete_session(self, assistant_session_id: str) -> bool:
        record = self._session.get(AssistantSessionRecord, assistant_session_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True
