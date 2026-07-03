"""SQLModel storage records for writing-assistant chat sessions (S6-4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class AssistantSessionRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Story-scoped writing-assistant conversation (REV-028: not story truth).

    messages_json holds display turns plus candidate REFERENCES only; the
    authoritative candidate bodies live in the runtime workspace candidate
    layer, so deleting a session never touches candidates/artifacts/receipts.
    """

    __tablename__ = "rp_assistant_sessions"

    assistant_session_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    title: str = ""
    messages_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
