"""SQLModel storage records for Phase E memory proposal/apply persistence."""

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


class MemoryProposalRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_memory_proposals"

    proposal_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str | None = Field(default=None, index=True)
    chapter_workspace_id: str | None = Field(default=None, index=True)
    mode: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str | None = Field(default=None, index=True)
    status: str = Field(index=True)
    policy_decision: str | None = Field(default=None, index=True)
    submit_source: str = Field(index=True)
    operations_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    base_refs_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    reason: str | None = None
    trace_id: str | None = Field(default=None, index=True)
    governance_metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    applied_at: datetime | None = Field(default=None, index=True)
    error_message: str | None = None


class MemoryApplyReceiptRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_memory_apply_receipts"

    apply_id: str = Field(primary_key=True, index=True)
    proposal_id: str = Field(index=True)
    story_id: str = Field(index=True)
    session_id: str | None = Field(default=None, index=True)
    chapter_workspace_id: str | None = Field(default=None, index=True)
    target_refs_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    revision_after_json: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    before_snapshot_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    after_snapshot_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    warnings_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    apply_backend: str = Field(default="adapter_backed", index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class MemoryApplyTargetLinkRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_memory_apply_target_links"

    apply_target_link_id: str = Field(primary_key=True, index=True)
    apply_id: str = Field(
        foreign_key="rp_memory_apply_receipts.apply_id",
        index=True,
    )
    proposal_id: str = Field(index=True)
    story_id: str = Field(index=True)
    session_id: str | None = Field(default=None, index=True)
    object_id: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str = Field(index=True)
    scope: str = Field(index=True)
    revision: int = Field(index=True)
    authoritative_object_id: str = Field(
        foreign_key="rp_core_state_authoritative_objects.authoritative_object_id",
        index=True,
    )
    authoritative_revision_id: str = Field(
        foreign_key="rp_core_state_authoritative_revisions.authoritative_revision_id",
        index=True,
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class RuntimeWorkspaceMaterialRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Persistent Runtime Workspace turn-material row keyed by full identity."""

    __tablename__ = "rp_runtime_workspace_materials"
    __table_args__ = (
        UniqueConstraint(
            "story_id",
            "session_id",
            "branch_head_id",
            "turn_id",
            "runtime_profile_snapshot_id",
            "short_id_key",
            name="uq_rp_runtime_workspace_materials_identity_short_id_key",
        ),
    )

    material_id: str = Field(primary_key=True, index=True)
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
    material_kind: str = Field(index=True)
    domain: str = Field(index=True)
    domain_path: str | None = Field(default=None, index=True)
    short_id: str | None = Field(default=None, index=True)
    short_id_key: str | None = Field(default=None, index=True)
    lifecycle: str = Field(index=True)
    visibility: str = Field(index=True)
    created_by: str = Field(index=True)
    expiration_ref: str | None = Field(default=None, index=True)
    materialization_ref: str | None = Field(default=None, index=True)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    source_refs_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    expired_at: datetime | None = Field(default=None, index=True)
    invalidated_at: datetime | None = Field(default=None, index=True)


class MemoryChangeEventRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Persistent lightweight event row for trace and invalidation queries."""

    __tablename__ = "rp_memory_change_events"

    event_id: str = Field(primary_key=True, index=True)
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
    actor: str = Field(index=True)
    event_kind: str = Field(index=True)
    layer: str = Field(index=True)
    domain: str = Field(index=True)
    block_id: str | None = Field(default=None, index=True)
    entry_id: str | None = Field(default=None, index=True)
    operation_kind: str = Field(index=True)
    visibility_effect: str = Field(index=True)
    source_refs_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    dirty_targets_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
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


def ensure_memory_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight indexes for proposal/apply persistence."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.dialect.name

    if "rp_runtime_workspace_materials" in tables:
        _ensure_column(
            engine,
            "rp_runtime_workspace_materials",
            "short_id_key",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_runtime_workspace_materials",
            "expired_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )
        _ensure_column(
            engine,
            "rp_runtime_workspace_materials",
            "invalidated_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )

    if "rp_memory_proposals" in tables:
        _ensure_column(
            engine,
            "rp_memory_proposals",
            "governance_metadata_json",
            "JSONB DEFAULT '{}'::jsonb NOT NULL"
            if dialect == "postgresql"
            else "JSON DEFAULT '{}' NOT NULL",
        )

    with engine.begin() as connection:
        if "rp_memory_apply_receipts" in tables:
            receipt_columns = {
                item["name"]
                for item in inspector.get_columns("rp_memory_apply_receipts")
            }
            if "apply_backend" not in receipt_columns:
                connection.execute(
                    text(
                        "ALTER TABLE rp_memory_apply_receipts "
                        "ADD COLUMN apply_backend VARCHAR DEFAULT 'adapter_backed' NOT NULL"
                    )
                )
        if "rp_memory_proposals" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_memory_proposals_story_status "
                    "ON rp_memory_proposals (story_id, status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_memory_proposals_story_session "
                    "ON rp_memory_proposals (story_id, session_id)"
                )
            )
        if "rp_memory_apply_receipts" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_memory_apply_receipts_story_proposal "
                    "ON rp_memory_apply_receipts (story_id, proposal_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_memory_apply_receipts_story_backend "
                    "ON rp_memory_apply_receipts (story_id, apply_backend)"
                )
            )
        if "rp_memory_apply_target_links" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_memory_apply_target_links_story_object_revision "
                    "ON rp_memory_apply_target_links (story_id, session_id, object_id, revision)"
                )
            )
        if "rp_runtime_workspace_materials" in tables:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ux_rp_runtime_workspace_materials_identity_short_id_key_present "
                    "ON rp_runtime_workspace_materials "
                    "(story_id, session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, short_id_key) "
                    "WHERE short_id_key IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_workspace_materials_identity_created "
                    "ON rp_runtime_workspace_materials "
                    "(story_id, session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_workspace_materials_identity_kind_domain "
                    "ON rp_runtime_workspace_materials "
                    "(story_id, session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, material_kind, domain)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_workspace_materials_identity_lifecycle "
                    "ON rp_runtime_workspace_materials "
                    "(story_id, session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, lifecycle)"
                )
            )
        if "rp_memory_change_events" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_memory_change_events_identity_created "
                    "ON rp_memory_change_events "
                    "(story_id, session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_memory_change_events_identity_domain_layer "
                    "ON rp_memory_change_events "
                    "(story_id, session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, domain, layer)"
                )
            )
