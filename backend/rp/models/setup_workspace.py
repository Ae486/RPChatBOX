"""SetupWorkspace aggregate models for the SetupAgent MVP."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.setup_drafts import (
    FoundationDraft,
    LongformBlueprintDraft,
    StoryConfigDraft,
    WritingContractDraft,
)


class StoryMode(StrEnum):
    LONGFORM = "longform"
    ROLEPLAY = "roleplay"
    TRPG = "trpg"


class SetupWorkspaceState(StrEnum):
    DRAFTING = "drafting"
    READY_TO_ACTIVATE = "ready_to_activate"
    ACTIVATED = "activated"
    ACTIVATION_FAILED = "activation_failed"
    ARCHIVED = "archived"


class SetupStepId(StrEnum):
    STORY_CONFIG = "story_config"
    WRITING_CONTRACT = "writing_contract"
    FOUNDATION = "foundation"
    LONGFORM_BLUEPRINT = "longform_blueprint"


class SetupStepLifecycleState(StrEnum):
    DISCUSSING = "discussing"
    REVIEW_PENDING = "review_pending"
    FROZEN = "frozen"


class ImportedAssetParseStatus(StrEnum):
    STAGED = "staged"
    PARSED = "parsed"
    FAILED = "failed"


class RetrievalIngestionState(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class CommitProposalStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class QuestionSeverity(StrEnum):
    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"


class QuestionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class SetupStepReadiness(StrEnum):
    NOT_READY = "not_ready"
    READY_FOR_REVIEW = "ready_for_review"
    READY_FOR_COMMIT = "ready_for_commit"
    FROZEN = "frozen"


class SetupStepState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: SetupStepId
    state: SetupStepLifecycleState
    discussion_round: int = 0
    review_round: int = 0
    last_proposal_id: str | None = None
    last_commit_id: str | None = None
    updated_at: datetime


class ImportedAssetRaw(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    step_id: SetupStepId
    asset_kind: str
    source_ref: str
    title: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    parse_status: ImportedAssetParseStatus = ImportedAssetParseStatus.STAGED
    parsed_payload: dict[str, Any] | None = None
    parse_warnings: list[str] = Field(default_factory=list)
    mapped_targets: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class StepAssetBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_id: str
    step_id: SetupStepId
    asset_id: str
    binding_role: Literal["primary", "reference", "supplement"]
    target_block: str
    target_path: str | None = None


class RetrievalIngestionJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    commit_id: str
    step_id: SetupStepId
    target_type: Literal["foundation_entry", "writing_contract", "blueprint", "asset"]
    target_ref: str
    index_job_id: str | None = None
    state: RetrievalIngestionState
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class CommitProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    step_id: SetupStepId
    status: CommitProposalStatus = CommitProposalStatus.PENDING_REVIEW
    target_block_types: list[str] = Field(default_factory=list)
    target_draft_refs: list[str] = Field(default_factory=list)
    review_message: str
    reason: str | None = None
    unresolved_warnings: list[str] = Field(default_factory=list)
    suggested_ingestion_targets: list[str] = Field(default_factory=list)
    created_at: datetime
    reviewed_at: datetime | None = None


class AcceptedCommitSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_type: str
    source_draft_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AcceptedCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_id: str
    proposal_id: str | None = None
    step_id: SetupStepId
    committed_refs: list[str] = Field(default_factory=list)
    snapshots: list[AcceptedCommitSnapshot] = Field(default_factory=list)
    summary_tier_0: str | None = None
    summary_tier_1: str | None = None
    summary_tier_2: str | None = None
    spotlights: list[str] = Field(default_factory=list)
    created_at: datetime


class UserEditChangeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    change_kind: Literal["add", "remove", "replace"]
    before_value: Any | None = None
    after_value: Any | None = None
    text_diff: str | None = None


class PendingUserEditDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta_id: str
    step_id: SetupStepId
    target_block: str
    target_ref: str
    changes: list[UserEditChangeItem] = Field(default_factory=list)
    created_at: datetime
    consumed_at: datetime | None = None


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    step_id: SetupStepId
    text: str
    severity: QuestionSeverity = QuestionSeverity.NON_BLOCKING
    status: QuestionStatus = QuestionStatus.OPEN
    resolution_note: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ReadinessStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_readiness: dict[str, SetupStepReadiness] = Field(default_factory=dict)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SetupWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    story_id: str
    mode: StoryMode
    workspace_state: SetupWorkspaceState
    current_step: SetupStepId
    step_states: list[SetupStepState] = Field(default_factory=list)
    story_config_draft: StoryConfigDraft | None = None
    writing_contract_draft: WritingContractDraft | None = None
    foundation_draft: FoundationDraft | None = None
    longform_blueprint_draft: LongformBlueprintDraft | None = None
    imported_assets: list[ImportedAssetRaw] = Field(default_factory=list)
    step_asset_bindings: list[StepAssetBinding] = Field(default_factory=list)
    retrieval_ingestion_jobs: list[RetrievalIngestionJob] = Field(default_factory=list)
    commit_proposals: list[CommitProposal] = Field(default_factory=list)
    accepted_commits: list[AcceptedCommit] = Field(default_factory=list)
    pending_user_edit_deltas: list[PendingUserEditDelta] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    readiness_status: ReadinessStatus
    version: int
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None
    activated_story_session_id: str | None = None
