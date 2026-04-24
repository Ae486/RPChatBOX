"""SQLModel storage records for SetupWorkspace persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class SetupWorkspaceRecord(SQLModel, table=True):
    """Setup workspace aggregate metadata record."""

    __tablename__ = "rp_setup_workspaces"

    workspace_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True, unique=True)
    mode: str = Field(index=True)
    workspace_state: str = Field(index=True)
    current_step: str = Field(index=True)
    version: int = 1
    readiness_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    activated_story_session_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    activated_at: datetime | None = Field(default=None, index=True)


class SetupStepStateRecord(SQLModel, table=True):
    """Per-step lifecycle record for one setup workspace."""

    __tablename__ = "rp_setup_step_states"
    __table_args__ = (UniqueConstraint("workspace_id", "step_id"),)

    id: str = Field(primary_key=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    state: str = Field(index=True)
    discussion_round: int = 0
    review_round: int = 0
    last_proposal_id: str | None = None
    last_commit_id: str | None = None
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class SetupDraftBlockRecord(SQLModel, table=True):
    """Typed setup draft block stored as JSONB payload."""

    __tablename__ = "rp_setup_draft_blocks"
    __table_args__ = (UniqueConstraint("workspace_id", "block_type"),)

    draft_block_id: str = Field(primary_key=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    block_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    current_revision: int = 1
    last_commit_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class SetupImportedAssetRecord(SQLModel, table=True):
    """Setup-stage imported asset record before retrieval authoritative persistence."""

    __tablename__ = "rp_setup_imported_assets"

    asset_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    asset_kind: str = Field(index=True)
    source_ref: str
    title: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    local_path: str | None = None
    parse_status: str = Field(index=True)
    parsed_payload_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(_JSON_VARIANT, nullable=True),
    )
    parse_warnings_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    mapped_targets_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class SetupStepAssetBindingRecord(SQLModel, table=True):
    """Binding between setup step, asset, and target block."""

    __tablename__ = "rp_setup_step_asset_bindings"

    binding_id: str = Field(primary_key=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    asset_id: str = Field(
        foreign_key="rp_setup_imported_assets.asset_id",
        index=True,
    )
    binding_role: str
    target_block: str
    target_path: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class SetupCommitProposalRecord(SQLModel, table=True):
    """Durable setup commit proposal record."""

    __tablename__ = "rp_setup_commit_proposals"

    proposal_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    status: str = Field(index=True)
    target_block_types_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    target_draft_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    review_message: str
    reason: str | None = None
    unresolved_warnings_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    suggested_ingestion_targets_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    reviewed_at: datetime | None = Field(default=None, index=True)


class SetupAcceptedCommitRecord(SQLModel, table=True):
    """Accepted setup commit snapshot record."""

    __tablename__ = "rp_setup_accepted_commits"

    commit_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    proposal_id: str | None = Field(default=None, index=True)
    step_id: str = Field(index=True)
    committed_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    snapshot_payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    summary_tier_0: str | None = None
    summary_tier_1: str | None = None
    summary_tier_2: str | None = None
    spotlights_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class SetupPendingUserEditDeltaRecord(SQLModel, table=True):
    """Durable user edit delta record for setup review/apply workflows."""

    __tablename__ = "rp_setup_pending_user_edit_deltas"

    delta_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    target_block: str = Field(index=True)
    target_ref: str
    changes_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    consumed_at: datetime | None = Field(default=None, index=True)


class SetupAgentRuntimeStateRecord(SQLModel, table=True):
    """Runtime-private cognitive state snapshot for one workspace step."""

    __tablename__ = "rp_setup_agent_runtime_states"
    __table_args__ = (UniqueConstraint("workspace_id", "step_id"),)

    runtime_state_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    state_version: int = 1
    snapshot_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class SetupOpenQuestionRecord(SQLModel, table=True):
    """Open question record owned by SetupWorkspace."""

    __tablename__ = "rp_setup_open_questions"

    question_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    step_id: str = Field(index=True)
    text: str
    severity: str = Field(index=True)
    status: str = Field(index=True)
    resolution_note: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    resolved_at: datetime | None = Field(default=None, index=True)


class SetupRetrievalIngestionJobRecord(SQLModel, table=True):
    """Setup-side view of minimal retrieval ingestion jobs."""

    __tablename__ = "rp_setup_retrieval_ingestion_jobs"

    job_id: str = Field(primary_key=True, index=True)
    workspace_id: str = Field(
        foreign_key="rp_setup_workspaces.workspace_id",
        index=True,
    )
    commit_id: str = Field(index=True)
    step_id: str = Field(index=True)
    target_type: str = Field(index=True)
    target_ref: str
    index_job_id: str | None = Field(default=None, index=True)
    state: str = Field(index=True)
    warnings_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    error_message: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)
    completed_at: datetime | None = Field(default=None, index=True)


def ensure_setup_store_compatible_schema(engine: Engine) -> None:
    """Patch existing setup tables in-place for active-story activation links."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "rp_setup_workspaces" not in tables:
        return

    columns = {item["name"] for item in inspector.get_columns("rp_setup_workspaces")}
    if "activated_story_session_id" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE rp_setup_workspaces "
                "ADD COLUMN activated_story_session_id VARCHAR"
            )
        )
