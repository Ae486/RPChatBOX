"""SQLModel storage records for active-story longform MVP."""

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


class StorySessionRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_story_sessions"

    session_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    source_workspace_id: str = Field(index=True)
    mode: str = Field(index=True)
    session_state: str = Field(index=True)
    active_branch_head_id: str | None = Field(default=None, index=True)
    active_runtime_profile_snapshot_id: str | None = Field(default=None, index=True)
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


class ChapterWorkspaceRecord(SQLModel, table=True):  # type: ignore[call-arg]
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
    current_scene_ref: str | None = None
    next_scene_index: int = 2
    last_closed_scene_ref: str | None = None
    closed_scene_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class StoryArtifactRecord(SQLModel, table=True):  # type: ignore[call-arg]
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
    scene_ref: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class StoryDiscussionEntryRecord(SQLModel, table=True):  # type: ignore[call-arg]
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
    scene_ref: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class StoryBlockConsumerStateRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Persist the last-synced Block revision snapshot for one story consumer."""

    __tablename__ = "rp_story_block_consumer_states"
    __table_args__ = (UniqueConstraint("session_id", "consumer_key"),)

    consumer_state_id: str = Field(primary_key=True, index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    consumer_key: str = Field(index=True)
    chapter_workspace_id: str | None = Field(
        default=None,
        foreign_key="rp_chapter_workspaces.chapter_workspace_id",
        index=True,
    )
    last_synced_revisions_json: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    last_compiled_revisions_json: dict[str, int] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    last_compiled_chapter_workspace_id: str | None = Field(
        default=None,
        foreign_key="rp_chapter_workspaces.chapter_workspace_id",
        index=True,
    )
    last_compiled_prompt_overlay: str | None = None
    last_synced_at: datetime | None = Field(default=None, index=True)
    last_compiled_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class BranchHeadRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_story_branch_heads"

    branch_head_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    branch_name: str = Field(index=True)
    parent_branch_head_id: str | None = Field(default=None, index=True)
    forked_from_turn_id: str | None = Field(default=None, index=True)
    fork_origin_turn_id: str | None = Field(default=None, index=True)
    fork_base_turn_id: str | None = Field(default=None, index=True)
    head_turn_id: str | None = Field(default=None, index=True)
    last_settled_turn_id: str | None = Field(default=None, index=True)
    status: str = Field(index=True)
    visibility_scope: str = Field(index=True)
    visibility_state: str = Field(default="visible", index=True)
    created_by_control_receipt_id: str | None = Field(default=None, index=True)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class BranchControlReceiptRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Control-plane branch action receipt that stays outside story-turn timeline."""

    __tablename__ = "rp_story_branch_control_receipts"

    receipt_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    branch_head_id: str = Field(
        foreign_key="rp_story_branch_heads.branch_head_id",
        index=True,
    )
    control_kind: str = Field(index=True)
    actor: str = Field(index=True)
    fork_origin_turn_id: str | None = Field(default=None, index=True)
    fork_base_turn_id: str | None = Field(default=None, index=True)
    from_branch_head_id: str | None = Field(default=None, index=True)
    to_branch_head_id: str | None = Field(default=None, index=True)
    target_turn_id: str | None = Field(default=None, index=True)
    source_ref_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    result_ref_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    trace_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class RuntimeProfileSnapshotRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_runtime_profile_snapshots"

    runtime_profile_snapshot_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    mode: str = Field(index=True)
    source_config_revision: str | None = Field(default=None, index=True)
    compiled_profile_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_from: str = Field(index=True)
    status: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    activated_at: datetime | None = Field(default=None, index=True)
    superseded_at: datetime | None = Field(default=None, index=True)


class RuntimeConfigControlReceiptRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Control-plane runtime config receipt outside the story-turn timeline."""

    __tablename__ = "rp_runtime_config_control_receipts"

    receipt_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    previous_snapshot_id: str | None = Field(default=None, index=True)
    published_snapshot_id: str = Field(
        foreign_key="rp_runtime_profile_snapshots.runtime_profile_snapshot_id",
        index=True,
    )
    changed_fields_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    actor_id: str | None = Field(default=None, index=True)
    source: str = Field(index=True)
    reason: str | None = None
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class StoryTurnRecord(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "rp_story_turns"

    turn_id: str = Field(primary_key=True, index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    branch_head_id: str = Field(
        foreign_key="rp_story_branch_heads.branch_head_id",
        index=True,
    )
    runtime_profile_snapshot_id: str = Field(
        foreign_key="rp_runtime_profile_snapshots.runtime_profile_snapshot_id",
        index=True,
    )
    turn_kind: str = Field(index=True)
    command_kind: str = Field(index=True)
    actor: str = Field(index=True)
    status: str = Field(index=True)
    acceptance_state: str = Field(default="auto_accepted", index=True)
    settlement_reason: str | None = Field(default=None, index=True)
    failure_reason: str | None = None
    visible_output_ref: str | None = Field(default=None, index=True)
    selected_output_ref: str | None = Field(default=None, index=True)
    visibility_state: str = Field(default="active", index=True)
    hidden_by_control_receipt_id: str | None = Field(default=None, index=True)
    hidden_after_turn_id: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: datetime | None = Field(default=None, index=True)
    writer_completed_at: datetime | None = Field(default=None, index=True)
    post_write_started_at: datetime | None = Field(default=None, index=True)
    settled_at: datetime | None = Field(default=None, index=True)
    failed_at: datetime | None = Field(default=None, index=True)
    completed_at: datetime | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class RuntimeWorkflowJobRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Turn-scoped workflow job ledger for post-write obligations."""

    __tablename__ = "rp_runtime_workflow_jobs"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_rp_runtime_workflow_jobs_idempotency_key",
        ),
    )

    job_id: str = Field(primary_key=True, index=True)
    turn_id: str = Field(foreign_key="rp_story_turns.turn_id", index=True)
    story_id: str = Field(index=True)
    session_id: str = Field(foreign_key="rp_story_sessions.session_id", index=True)
    branch_head_id: str = Field(
        foreign_key="rp_story_branch_heads.branch_head_id",
        index=True,
    )
    runtime_profile_snapshot_id: str = Field(
        foreign_key="rp_runtime_profile_snapshots.runtime_profile_snapshot_id",
        index=True,
    )
    job_kind: str = Field(index=True)
    job_category: str = Field(index=True)
    status: str = Field(index=True)
    creation_mode: str = Field(index=True)
    required_for_turn_completion: bool = Field(default=False, index=True)
    worker_id: str | None = Field(default=None, index=True)
    parent_job_id: str | None = Field(default=None, index=True)
    idempotency_key: str = Field(index=True)
    source_ref_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    result_ref_ids_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    trace_refs_json: list[str] = Field(
        default_factory=list,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    attempt_count: int = 0
    completion_reason: str | None = None
    failure_reason: str | None = None
    last_error_json: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(_JSON_VARIANT, nullable=True),
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_VARIANT, nullable=False),
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: datetime | None = Field(default=None, index=True)
    completed_at: datetime | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


def _ensure_column(engine: Engine, table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
        )


def ensure_story_store_compatible_schema(engine: Engine) -> None:
    """Apply lightweight story-store indexes for MVP."""

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if (
        not {"rp_story_sessions", "rp_chapter_workspaces", "rp_story_artifacts"}
        <= tables
    ):
        return

    dialect = engine.dialect.name

    if "rp_story_sessions" in tables:
        _ensure_column(
            engine,
            "rp_story_sessions",
            "active_branch_head_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_sessions",
            "active_runtime_profile_snapshot_id",
            "VARCHAR",
        )

    if "rp_story_turns" in tables:
        _ensure_column(
            engine,
            "rp_story_turns",
            "acceptance_state",
            "VARCHAR DEFAULT 'auto_accepted' NOT NULL",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "settlement_reason",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "failure_reason",
            "TEXT",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "visible_output_ref",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "selected_output_ref",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "visibility_state",
            "VARCHAR DEFAULT 'active' NOT NULL",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "hidden_by_control_receipt_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "hidden_after_turn_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "writer_completed_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "post_write_started_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "settled_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "failed_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )
        _ensure_column(
            engine,
            "rp_story_turns",
            "updated_at",
            "TIMESTAMP WITH TIME ZONE"
            if dialect == "postgresql"
            else "DATETIME",
        )

    if "rp_story_branch_heads" in tables:
        _ensure_column(
            engine,
            "rp_story_branch_heads",
            "fork_origin_turn_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_branch_heads",
            "fork_base_turn_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_branch_heads",
            "last_settled_turn_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_branch_heads",
            "visibility_state",
            "VARCHAR DEFAULT 'visible' NOT NULL",
        )
        _ensure_column(
            engine,
            "rp_story_branch_heads",
            "created_by_control_receipt_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_branch_heads",
            "metadata_json",
            (
                "JSONB DEFAULT '{}'::jsonb NOT NULL"
                if dialect == "postgresql"
                else "JSON DEFAULT '{}' NOT NULL"
            ),
        )

    if "rp_chapter_workspaces" in tables:
        _ensure_column(
            engine,
            "rp_chapter_workspaces",
            "current_scene_ref",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_chapter_workspaces",
            "next_scene_index",
            "INTEGER DEFAULT 2 NOT NULL",
        )
        _ensure_column(
            engine,
            "rp_chapter_workspaces",
            "last_closed_scene_ref",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_chapter_workspaces",
            "closed_scene_refs_json",
            (
                "JSONB DEFAULT '[]'::jsonb NOT NULL"
                if dialect == "postgresql"
                else "JSON DEFAULT '[]' NOT NULL"
            ),
        )

    if "rp_story_artifacts" in tables:
        _ensure_column(engine, "rp_story_artifacts", "scene_ref", "VARCHAR")

    if "rp_story_discussion_entries" in tables:
        _ensure_column(
            engine,
            "rp_story_discussion_entries",
            "scene_ref",
            "VARCHAR",
        )

    if "rp_story_block_consumer_states" in tables:
        _ensure_column(
            engine,
            "rp_story_block_consumer_states",
            "last_compiled_revisions_json",
            (
                "JSONB DEFAULT '{}'::jsonb NOT NULL"
                if dialect == "postgresql"
                else "JSON DEFAULT '{}' NOT NULL"
            ),
        )
        _ensure_column(
            engine,
            "rp_story_block_consumer_states",
            "last_compiled_chapter_workspace_id",
            "VARCHAR",
        )
        _ensure_column(
            engine,
            "rp_story_block_consumer_states",
            "last_compiled_prompt_overlay",
            "TEXT",
        )
        _ensure_column(
            engine,
            "rp_story_block_consumer_states",
            "last_compiled_at",
            "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME",
        )

    empty_json_array_literal = "'[]'::jsonb" if dialect == "postgresql" else "'[]'"

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE rp_story_sessions "
                "SET active_branch_head_id = "
                "(:branch_prefix || session_id || :branch_suffix) "
                "WHERE active_branch_head_id IS NULL"
            ),
            {
                "branch_prefix": "branch:",
                "branch_suffix": ":main",
            },
        )
        if "rp_runtime_profile_snapshots" in tables:
            connection.execute(
                text(
                    "UPDATE rp_story_sessions "
                    "SET active_runtime_profile_snapshot_id = ("
                    "SELECT rp_runtime_profile_snapshots.runtime_profile_snapshot_id "
                    "FROM rp_runtime_profile_snapshots "
                    "WHERE rp_runtime_profile_snapshots.session_id = "
                    "rp_story_sessions.session_id "
                    "AND rp_runtime_profile_snapshots.status = 'active' "
                    "ORDER BY rp_runtime_profile_snapshots.activated_at DESC, "
                    "rp_runtime_profile_snapshots.created_at DESC "
                    "LIMIT 1"
                    ") "
                    "WHERE active_runtime_profile_snapshot_id IS NULL"
                )
            )
        connection.execute(
            text(
                "UPDATE rp_chapter_workspaces "
                "SET current_scene_ref = ('chapter:' || chapter_index || ':scene:1') "
                "WHERE current_scene_ref IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE rp_chapter_workspaces "
                "SET next_scene_index = 2 "
                "WHERE next_scene_index IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE rp_chapter_workspaces "
                f"SET closed_scene_refs_json = {empty_json_array_literal} "
                "WHERE closed_scene_refs_json IS NULL"
            )
        )
        # Legacy runtime rows predate explicit scene lifecycle, so they always
        # belong to the deterministic first scene scaffold for their chapter.
        connection.execute(
            text(
                "UPDATE rp_story_artifacts "
                "SET scene_ref = ("
                "SELECT ('chapter:' || rp_chapter_workspaces.chapter_index || ':scene:1') "
                "FROM rp_chapter_workspaces "
                "WHERE rp_chapter_workspaces.chapter_workspace_id = "
                "rp_story_artifacts.chapter_workspace_id"
                ") "
                "WHERE scene_ref IS NULL "
                "AND artifact_kind = 'story_segment'"
            )
        )
        if "rp_story_discussion_entries" in tables:
            connection.execute(
                text(
                    "UPDATE rp_story_discussion_entries "
                    "SET scene_ref = ("
                    "SELECT ('chapter:' || rp_chapter_workspaces.chapter_index || ':scene:1') "
                    "FROM rp_chapter_workspaces "
                    "WHERE rp_chapter_workspaces.chapter_workspace_id = "
                    "rp_story_discussion_entries.chapter_workspace_id"
                    ") "
                    "WHERE scene_ref IS NULL"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_story_sessions_story_state "
                "ON rp_story_sessions (story_id, session_state)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_story_sessions_active_branch "
                "ON rp_story_sessions (active_branch_head_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rp_story_sessions_active_snapshot "
                "ON rp_story_sessions (active_runtime_profile_snapshot_id)"
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
        if "rp_story_block_consumer_states" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_story_block_consumer_states_session_consumer "
                    "ON rp_story_block_consumer_states (session_id, consumer_key)"
                )
            )
        if "rp_story_branch_heads" in tables:
            connection.execute(
                text(
                    "UPDATE rp_story_branch_heads "
                    "SET visibility_state = 'visible' "
                    "WHERE visibility_state IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE rp_story_branch_heads "
                    "SET fork_origin_turn_id = forked_from_turn_id "
                    "WHERE fork_origin_turn_id IS NULL "
                    "AND forked_from_turn_id IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE rp_story_branch_heads "
                    "SET fork_base_turn_id = forked_from_turn_id "
                    "WHERE fork_base_turn_id IS NULL "
                    "AND forked_from_turn_id IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE rp_story_branch_heads "
                    "SET last_settled_turn_id = head_turn_id "
                    "WHERE last_settled_turn_id IS NULL "
                    "AND head_turn_id IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_story_branch_heads_session_status "
                    "ON rp_story_branch_heads (session_id, status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_story_branch_heads_story_branch "
                    "ON rp_story_branch_heads (story_id, branch_name)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_story_branch_heads_session_visibility "
                    "ON rp_story_branch_heads (session_id, visibility_state)"
                )
            )
        if "rp_story_branch_control_receipts" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_story_branch_control_receipts_session_kind "
                    "ON rp_story_branch_control_receipts (session_id, control_kind)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_story_branch_control_receipts_branch_created "
                    "ON rp_story_branch_control_receipts "
                    "(branch_head_id, created_at)"
                )
            )
        if "rp_runtime_profile_snapshots" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_profile_snapshots_session_status "
                    "ON rp_runtime_profile_snapshots (session_id, status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_profile_snapshots_story_created "
                    "ON rp_runtime_profile_snapshots (story_id, created_at)"
                )
            )
        if "rp_runtime_config_control_receipts" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_config_receipts_session_created "
                    "ON rp_runtime_config_control_receipts (session_id, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_config_receipts_snapshot "
                    "ON rp_runtime_config_control_receipts (published_snapshot_id)"
                )
            )
        if "rp_story_turns" in tables:
            connection.execute(
                text(
                    "UPDATE rp_story_turns "
                    "SET visibility_state = 'active' "
                    "WHERE visibility_state IS NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_story_turns_branch_created "
                    "ON rp_story_turns (branch_head_id, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rp_story_turns_branch_visibility "
                    "ON rp_story_turns (branch_head_id, visibility_state)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_story_turns_session_snapshot_status "
                    "ON rp_story_turns (session_id, runtime_profile_snapshot_id, status)"
                )
            )
        if "rp_runtime_workflow_jobs" in tables:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ux_rp_runtime_workflow_jobs_idempotency_key "
                    "ON rp_runtime_workflow_jobs (idempotency_key)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_workflow_jobs_turn_status "
                    "ON rp_runtime_workflow_jobs (turn_id, status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_rp_runtime_workflow_jobs_identity_kind "
                    "ON rp_runtime_workflow_jobs "
                    "(session_id, branch_head_id, turn_id, "
                    "runtime_profile_snapshot_id, job_kind)"
                )
            )
