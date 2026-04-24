"""SQLModel storage records for formal Core State store."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class CoreStateAuthoritativeObjectRecord(SQLModel, table=True):
    __tablename__ = "rp_core_state_authoritative_objects"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "layer",
            "scope",
            "object_id",
            name="uq_rp_core_state_authoritative_object_ref",
        ),
        UniqueConstraint(
            "session_id",
            "layer",
            "scope",
            "domain",
            "domain_path",
            name="uq_rp_core_state_authoritative_domain_path",
        ),
    )

    authoritative_object_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    layer: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str = Field(index=True)
    object_id: str = Field(index=True)
    scope: str = Field(index=True)
    payload_schema_ref: str | None = None
    current_revision: int = Field(default=1, index=True)
    data_json: dict[str, Any] | list[Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    latest_apply_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class CoreStateAuthoritativeRevisionRecord(SQLModel, table=True):
    __tablename__ = "rp_core_state_authoritative_revisions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "layer",
            "scope",
            "object_id",
            "revision",
            name="uq_rp_core_state_authoritative_revision_ref",
        ),
    )

    authoritative_revision_id: str = Field(primary_key=True, index=True)
    authoritative_object_id: str = Field(
        foreign_key="rp_core_state_authoritative_objects.authoritative_object_id",
        index=True,
    )
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    layer: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str = Field(index=True)
    object_id: str = Field(index=True)
    scope: str = Field(index=True)
    revision: int = Field(index=True)
    data_json: dict[str, Any] | list[Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    revision_source_kind: str = Field(index=True)
    source_apply_id: str | None = Field(default=None, index=True)
    source_proposal_id: str | None = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class CoreStateProjectionSlotRecord(SQLModel, table=True):
    __tablename__ = "rp_core_state_projection_slots"
    __table_args__ = (
        UniqueConstraint(
            "chapter_workspace_id",
            "summary_id",
            name="uq_rp_core_state_projection_slot_ref",
        ),
    )

    projection_slot_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    chapter_workspace_id: str = Field(
        foreign_key="rp_chapter_workspaces.chapter_workspace_id",
        index=True,
    )
    layer: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str = Field(index=True)
    summary_id: str = Field(index=True)
    slot_name: str = Field(index=True)
    scope: str = Field(index=True)
    payload_schema_ref: str | None = None
    current_revision: int = Field(default=1, index=True)
    items_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    last_refresh_kind: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class CoreStateProjectionSlotRevisionRecord(SQLModel, table=True):
    __tablename__ = "rp_core_state_projection_slot_revisions"
    __table_args__ = (
        UniqueConstraint(
            "chapter_workspace_id",
            "summary_id",
            "revision",
            name="uq_rp_core_state_projection_slot_revision_ref",
        ),
    )

    projection_slot_revision_id: str = Field(primary_key=True, index=True)
    projection_slot_id: str = Field(
        foreign_key="rp_core_state_projection_slots.projection_slot_id",
        index=True,
    )
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    chapter_workspace_id: str = Field(
        foreign_key="rp_chapter_workspaces.chapter_workspace_id",
        index=True,
    )
    layer: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str = Field(index=True)
    summary_id: str = Field(index=True)
    slot_name: str = Field(index=True)
    scope: str = Field(index=True)
    revision: int = Field(index=True)
    items_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    refresh_source_kind: str = Field(index=True)
    refresh_source_ref: str | None = None
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


def ensure_core_state_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight indexes for formal Core State store tables."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "rp_core_state_authoritative_objects",
        "rp_core_state_authoritative_revisions",
        "rp_core_state_projection_slots",
        "rp_core_state_projection_slot_revisions",
    }
    if not required_tables <= tables:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_authoritative_story_session "
                "ON rp_core_state_authoritative_objects (story_id, session_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_authoritative_revision_story_object "
                "ON rp_core_state_authoritative_revisions (story_id, session_id, object_id, revision)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_projection_story_session "
                "ON rp_core_state_projection_slots (story_id, session_id, chapter_workspace_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_projection_revision_story_slot "
                "ON rp_core_state_projection_slot_revisions "
                "(story_id, session_id, chapter_workspace_id, summary_id, revision)"
            )
        )
