"""SQLModel storage records for active-story longform MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class StorySessionRecord(SQLModel, table=True):
    __tablename__ = "rp_story_sessions"

    session_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    source_workspace_id: str = Field(index=True)
    mode: str = Field(index=True)
    session_state: str = Field(index=True)
    current_chapter_index: int = 1
    current_phase: str = Field(index=True)
    runtime_story_config_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    writer_contract_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    current_state_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    activated_at: datetime = Field(default_factory=_utcnow, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class ChapterWorkspaceRecord(SQLModel, table=True):
    __tablename__ = "rp_chapter_workspaces"

    chapter_workspace_id: str = Field(primary_key=True, index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    chapter_index: int = Field(index=True)
    phase: str = Field(index=True)
    chapter_goal: str | None = None
    outline_draft_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(_JSON_VARIANT, nullable=True),
    )
    accepted_outline_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(_JSON_VARIANT, nullable=True),
    )
    builder_snapshot_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    review_notes_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    accepted_segment_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    pending_segment_artifact_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class StoryArtifactRecord(SQLModel, table=True):
    __tablename__ = "rp_story_artifacts"

    artifact_id: str = Field(primary_key=True, index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    chapter_workspace_id: str = Field(
        foreign_key="rp_chapter_workspaces.chapter_workspace_id",
        index=True,
    )
    artifact_kind: str = Field(index=True)
    status: str = Field(index=True)
    revision: int = 1
    content_text: str
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class StoryDiscussionEntryRecord(SQLModel, table=True):
    __tablename__ = "rp_story_discussion_entries"

    entry_id: str = Field(primary_key=True, index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    chapter_workspace_id: str = Field(
        foreign_key="rp_chapter_workspaces.chapter_workspace_id",
        index=True,
    )
    role: str = Field(index=True)
    content_text: str
    linked_artifact_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)


def ensure_story_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight story-store indexes for MVP."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {"rp_story_sessions", "rp_chapter_workspaces", "rp_story_artifacts"} <= tables:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_story_sessions_story_state "
                "ON rp_story_sessions (story_id, session_state)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_chapter_workspaces_session_chapter "
                "ON rp_chapter_workspaces (session_id, chapter_index)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_story_artifacts_chapter_kind_status "
                "ON rp_story_artifacts (chapter_workspace_id, artifact_kind, status)"
            )
        )
