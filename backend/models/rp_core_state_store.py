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


class CoreStateAuthoritativeObjectRecord(SQLModel, table=True):  # type: ignore[call-arg]
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


class CoreStateAuthoritativeRevisionRecord(SQLModel, table=True):  # type: ignore[call-arg]
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
    owning_branch_head_id: str | None = Field(default=None, index=True)
    origin_turn_id: str | None = Field(default=None, index=True)
    runtime_profile_snapshot_id: str | None = Field(default=None, index=True)
    visibility_scope: str = Field(default="story_global", index=True)
    visibility_state: str = Field(default="active", index=True)
    base_revision: int | None = Field(default=None, index=True)
    source_event_id: str | None = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class CoreStateSnapshotManifestRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Turn-bound copy-on-write Core State revision manifest."""

    __tablename__ = "rp_core_state_snapshot_manifests"

    snapshot_id: str = Field(primary_key=True, index=True)
    parent_snapshot_id: str | None = Field(default=None, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    branch_head_id: str = Field(
        foreign_key="rp_story_branch_heads.branch_head_id",
        index=True,
    )
    turn_id: str = Field(foreign_key="rp_story_turns.turn_id", index=True)
    runtime_profile_snapshot_id: str = Field(
        foreign_key="rp_runtime_profile_snapshots.runtime_profile_snapshot_id",
        index=True,
    )
    effective_revision_map_json: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    changed_ref_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    source_event_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    manifest_kind: str = Field(default="runtime", index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class CoreStateProjectionSlotRecord(SQLModel, table=True):  # type: ignore[call-arg]
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


class CoreStateProjectionSlotRevisionRecord(SQLModel, table=True):  # type: ignore[call-arg]
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


def _ensure_column(engine: Engine, table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
        )


def ensure_core_state_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight indexes for formal Core State store tables."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {
        "rp_core_state_authoritative_objects",
        "rp_core_state_authoritative_revisions",
        "rp_core_state_snapshot_manifests",
        "rp_core_state_projection_slots",
        "rp_core_state_projection_slot_revisions",
    }
    if not required_tables <= tables:
        return
    dialect = engine.dialect.name
    json_default_empty_object = (
        "JSONB DEFAULT '{}'::jsonb NOT NULL"
        if dialect == "postgresql"
        else "JSON DEFAULT '{}' NOT NULL"
    )

    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "owning_branch_head_id",
        "VARCHAR",
    )
    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "origin_turn_id",
        "VARCHAR",
    )
    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "runtime_profile_snapshot_id",
        "VARCHAR",
    )
    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "visibility_scope",
        "VARCHAR DEFAULT 'story_global' NOT NULL",
    )
    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "visibility_state",
        "VARCHAR DEFAULT 'active' NOT NULL",
    )
    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "base_revision",
        "INTEGER",
    )
    _ensure_column(
        engine,
        "rp_core_state_authoritative_revisions",
        "source_event_id",
        "VARCHAR",
    )
    _ensure_column(
        engine,
        "rp_core_state_snapshot_manifests",
        "metadata_json",
        json_default_empty_object,
    )

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
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_authoritative_revision_runtime_identity "
                "ON rp_core_state_authoritative_revisions "
                "(story_id, session_id, owning_branch_head_id, origin_turn_id, runtime_profile_snapshot_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_snapshot_manifest_identity "
                "ON rp_core_state_snapshot_manifests "
                "(story_id, session_id, branch_head_id, turn_id, runtime_profile_snapshot_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_core_state_snapshot_manifest_parent "
                "ON rp_core_state_snapshot_manifests (parent_snapshot_id)"
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
