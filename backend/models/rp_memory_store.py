"""SQLModel storage records for Phase E memory proposal/apply persistence."""

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


class MemoryProposalRecord(SQLModel, table=True):
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
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    applied_at: datetime | None = Field(default=None, index=True)
    error_message: str | None = None


class MemoryApplyReceiptRecord(SQLModel, table=True):
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


class MemoryApplyTargetLinkRecord(SQLModel, table=True):
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


def ensure_memory_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight indexes for proposal/apply persistence."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "rp_memory_proposals" not in tables or "rp_memory_apply_receipts" not in tables:
        return

    with engine.begin() as connection:
        receipt_columns = {item["name"] for item in inspector.get_columns("rp_memory_apply_receipts")}
        if "apply_backend" not in receipt_columns:
            connection.execute(
                text(
                    "ALTER TABLE rp_memory_apply_receipts "
                    "ADD COLUMN apply_backend VARCHAR DEFAULT 'adapter_backed' NOT NULL"
                )
            )
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
