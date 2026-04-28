"""Setup context packets, tool results, and activation handoff models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rp.models.setup_workspace import SetupStepId, StoryMode


class SetupToolResult(BaseModel):
    """Unified setup private tool result payload."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    updated_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SetupContextBuilderInput(BaseModel):
    """Input used to build one stable setup context packet."""

    model_config = ConfigDict(extra="forbid")

    mode: str
    workspace_id: str
    current_step: str
    user_prompt: str
    user_edit_delta_ids: list[str] = Field(default_factory=list)
    token_budget: int | None = None


class SetupStageChunkDescription(BaseModel):
    """Compact retrieval-friendly description for one accepted setup truth unit."""

    model_config = ConfigDict(extra="forbid")

    chunk_ref: str
    block_type: str
    title: str
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SetupStageHandoffSourceBasis(BaseModel):
    """Minimal lineage surface for one accepted prior-stage handoff."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    commit_id: str
    snapshot_block_types: list[str] = Field(default_factory=list)


class SetupStageHandoffPacket(BaseModel):
    """Compact prior-stage truth packet injected into later setup stages."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    from_step: SetupStepId
    to_step: SetupStepId
    step_id: SetupStepId
    commit_id: str
    summary: str
    summary_tier_0: str | None = None
    summary_tier_1: str | None = None
    committed_refs: list[str] = Field(default_factory=list)
    spotlights: list[str] = Field(default_factory=list)
    chunk_descriptions: list[SetupStageChunkDescription] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    retrieval_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_basis: SetupStageHandoffSourceBasis
    created_at: datetime


class SetupContextPacket(BaseModel):
    """Context packet passed into the SetupAgent loop."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    current_step: str
    context_profile: Literal["standard", "compact"] = "standard"
    committed_summaries: list[str] = Field(default_factory=list)
    current_draft_snapshot: dict[str, Any] = Field(default_factory=dict)
    step_asset_preview: list[dict[str, Any]] = Field(default_factory=list)
    user_prompt: str
    user_edit_deltas: list[dict[str, Any]] = Field(default_factory=list)
    spotlights: list[str] = Field(default_factory=list)
    prior_stage_handoffs: list[SetupStageHandoffPacket] = Field(default_factory=list)


class RuntimeStoryConfigSeed(BaseModel):
    """Runtime seed derived from setup truth before activation."""

    model_config = ConfigDict(extra="forbid")

    story_id: str
    mode: StoryMode
    model_profile_ref: str | None = None
    worker_profile_ref: str | None = None
    post_write_policy_preset: str | None = None
    retrieval_embedding_model_id: str | None = None
    retrieval_embedding_provider_id: str | None = None
    retrieval_rerank_model_id: str | None = None
    retrieval_rerank_provider_id: str | None = None


class WriterContractSeed(BaseModel):
    """Writer-facing contract seed derived from setup truth."""

    model_config = ConfigDict(extra="forbid")

    pov_rules: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    writing_constraints: list[str] = Field(default_factory=list)
    task_writing_rules: list[str] = Field(default_factory=list)


class ActivationHandoff(BaseModel):
    """Minimal handoff object built before active runtime starts."""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    story_id: str
    workspace_id: str
    mode: StoryMode
    runtime_story_config: RuntimeStoryConfigSeed
    writer_contract: WriterContractSeed
    foundation_commit_refs: list[str] = Field(default_factory=list)
    blueprint_commit_ref: str | None = None
    archival_ready_refs: list[str] = Field(default_factory=list)
    created_at: datetime


class ActivationCheckResult(BaseModel):
    """Deterministic activation-readiness result returned by the controller/API."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    ready: bool
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    handoff: ActivationHandoff | None = None
