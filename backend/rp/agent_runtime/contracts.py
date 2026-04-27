"""Runtime-internal contracts for RP agent execution."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeProfile(BaseModel):
    """Fixed runtime behavior for one agent profile."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    supports_tools: bool = True
    visible_tool_names: list[str] = Field(default_factory=list)
    max_rounds: int = 8
    allow_stream: bool = True
    recovery_policy: str = "default"
    finish_policy: str = "default"


class RpAgentTurnInput(BaseModel):
    """Unified runtime input after project-specific adapter mapping."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    run_kind: str
    story_id: str | None = None
    workspace_id: str | None = None
    session_id: str | None = None
    model_id: str
    provider_id: str | None = None
    stream: bool = False
    user_visible_request: str | None = None
    conversation_messages: list[dict[str, Any]] = Field(default_factory=list)
    context_bundle: dict[str, Any] = Field(default_factory=dict)
    tool_scope: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeToolCall(BaseModel):
    """Normalized model-declared tool call."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    source_round: int


class RuntimeToolResult(BaseModel):
    """Normalized tool execution outcome."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    success: bool
    content_text: str
    error_code: str | None = None
    structured_payload: dict[str, Any] | None = None


class RuntimeWorkingNote(BaseModel):
    """Internal-only runtime note."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscussionCandidateDirection(BaseModel):
    """One candidate direction still under discussion in the current step."""

    model_config = ConfigDict(extra="forbid")

    direction_id: str
    label: str
    summary: str
    supporting_points: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    status: Literal["active", "selected", "discarded"] = "active"


class DiscussionState(BaseModel):
    """Runtime-private discussion map for the current setup step."""

    model_config = ConfigDict(extra="forbid")

    current_step: str
    discussion_topic: str
    confirmed_points: list[str] = Field(default_factory=list)
    candidate_directions: list[DiscussionCandidateDirection] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    user_preference_signals: list[str] = Field(default_factory=list)
    next_focus: str | None = None
    convergence_score: float | None = None


class ChunkCandidate(BaseModel):
    """Structured truth candidate distilled from discussion."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    current_step: str
    block_type: Literal[
        "story_config",
        "writing_contract",
        "foundation_entry",
        "longform_blueprint",
    ]
    target_ref: str | None = None
    title: str
    content: str
    detail_level: Literal["rough", "usable", "truth_candidate"]
    tags: list[str] = Field(default_factory=list)
    source_turn_refs: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DraftTruthWrite(BaseModel):
    """Runtime-private structured write intent before commit proposal."""

    model_config = ConfigDict(extra="forbid")

    write_id: str
    current_step: str
    block_type: Literal[
        "story_config",
        "writing_contract",
        "foundation_entry",
        "longform_blueprint",
    ]
    target_ref: str | None = None
    operation: Literal["create", "merge", "replace"]
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    remaining_open_issues: list[str] = Field(default_factory=list)
    ready_for_review: bool = False


class SetupCognitiveSourceBasis(BaseModel):
    """Workspace-side source basis used to validate cross-turn cognitive state."""

    model_config = ConfigDict(extra="forbid")

    workspace_version: int
    draft_fingerprint: str | None = None
    pending_user_edit_delta_ids: list[str] = Field(default_factory=list)
    last_proposal_status: str | None = None
    current_step: str


class SetupWorkingDigest(BaseModel):
    """Thin stage-local control state carried across setup turns."""

    model_config = ConfigDict(extra="forbid")

    current_goal: str | None = None
    next_focus: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    rejected_directions: list[str] = Field(default_factory=list)
    draft_refs: list[str] = Field(default_factory=list)
    pending_obligation: str | None = None
    commit_blockers: list[str] = Field(default_factory=list)


class SetupToolOutcome(BaseModel):
    """Final tool outcome retained as thin cross-turn context."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    success: bool
    summary: str
    updated_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None
    relevance: Literal[
        "cognitive",
        "draft",
        "question",
        "proposal",
        "read",
        "asset",
        "failure",
        "other",
    ] = "other"
    recorded_at: datetime


class SetupContextCompactSummary(BaseModel):
    """Compacted carry-forward summary for trimmed older current-step history."""

    model_config = ConfigDict(extra="forbid")

    source_fingerprint: str
    source_message_count: int = 0
    summary_lines: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    draft_refs: list[str] = Field(default_factory=list)


class SetupCognitiveStateSnapshot(BaseModel):
    """Cross-turn runtime-private cognitive snapshot for one setup step."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    current_step: str
    state_version: int = 1
    discussion_state: DiscussionState | None = None
    chunk_candidates: list[ChunkCandidate] = Field(default_factory=list)
    active_truth_write: DraftTruthWrite | None = None
    working_digest: SetupWorkingDigest | None = None
    tool_outcomes: list[SetupToolOutcome] = Field(default_factory=list)
    compact_summary: SetupContextCompactSummary | None = None
    invalidated: bool = False
    invalidation_reasons: list[str] = Field(default_factory=list)
    source_basis: SetupCognitiveSourceBasis


class SetupCognitiveStateSummary(BaseModel):
    """Prompt-sized summary view of the current cognitive snapshot."""

    model_config = ConfigDict(extra="forbid")

    current_step: str
    invalidated: bool = False
    invalidation_reasons: list[str] = Field(default_factory=list)
    discussion_topic: str | None = None
    confirmed_points: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    candidate_titles: list[str] = Field(default_factory=list)
    truth_write_status: str | None = None
    ready_for_review: bool = False
    remaining_open_issues: list[str] = Field(default_factory=list)
    working_digest: SetupWorkingDigest | None = None
    tool_outcomes: list[SetupToolOutcome] = Field(default_factory=list)
    compact_summary: SetupContextCompactSummary | None = None


class SetupTurnGoal(BaseModel):
    """Setup-only per-turn goal derived from step state and runtime obligations."""

    model_config = ConfigDict(extra="forbid")

    current_step: str
    goal_type: Literal[
        "brainstorm_and_clarify",
        "clarify_user_intent",
        "fill_missing_step_fields",
        "patch_draft",
        "reconcile_after_user_edit",
        "refine_chunk_candidate",
        "write_draft_truth",
        "prepare_commit_intent",
        "recover_from_tool_failure",
    ]
    goal_summary: str
    success_criteria: list[str] = Field(default_factory=list)


class SetupWorkingPlan(BaseModel):
    """Setup-only working plan for the current step slice."""

    model_config = ConfigDict(extra="forbid")

    missing_information: list[str] = Field(default_factory=list)
    discussion_actions: list[str] = Field(default_factory=list)
    candidate_targets: list[str] = Field(default_factory=list)
    draft_write_targets: list[str] = Field(default_factory=list)
    patch_targets: list[str] = Field(default_factory=list)
    question_targets: list[str] = Field(default_factory=list)
    commit_readiness_checks: list[str] = Field(default_factory=list)
    current_priority: str | None = None


class SetupPendingObligation(BaseModel):
    """Runtime-only unresolved work that blocks successful completion."""

    model_config = ConfigDict(extra="forbid")

    obligation_type: Literal[
        "repair_tool_call",
        "ask_user_for_missing_info",
        "continue_after_tool_failure",
        "reassess_commit_readiness",
        "reconcile_after_user_edit",
    ]
    reason: str
    tool_name: str | None = None
    required_fields: list[str] = Field(default_factory=list)
    unresolved: bool = True


class SetupLastFailure(BaseModel):
    """Most recent setup runtime failure interpreted into agent semantics."""

    model_config = ConfigDict(extra="forbid")

    failure_category: Literal[
        "auto_repair",
        "ask_user",
        "continue_discussion",
        "block_commit",
        "unrecoverable",
    ]
    message: str
    error_code: str | None = None
    tool_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SetupReflectionTicket(BaseModel):
    """Lightweight reflection request inserted by runtime policies."""

    model_config = ConfigDict(extra="forbid")

    trigger: Literal[
        "tool_failure",
        "before_commit_proposal",
        "proposal_rejected",
    ]
    summary: str
    required_decision: Literal[
        "retry",
        "ask_user",
        "continue_discussion",
        "block_commit",
    ]


class SetupCompletionGuard(BaseModel):
    """Finalization guard result computed inside runtime only."""

    model_config = ConfigDict(extra="forbid")

    allow_finalize: bool
    reason: str
    required_action: Literal[
        "finalize_success",
        "execute_tools",
        "ask_user",
        "continue_discussion",
        "retry",
        "reflect",
        "finalize_failure",
    ]
    finish_reason: str | None = None


class RpAgentTurnResult(BaseModel):
    """Final runtime outcome exposed back to the project layer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed", "stopped"]
    finish_reason: str
    assistant_text: str = ""
    tool_invocations: list[RuntimeToolCall] = Field(default_factory=list)
    tool_results: list[RuntimeToolResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
