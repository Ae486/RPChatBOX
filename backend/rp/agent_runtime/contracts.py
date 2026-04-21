"""Runtime-internal contracts for RP agent execution."""
from __future__ import annotations

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


class SetupTurnGoal(BaseModel):
    """Setup-only per-turn goal derived from step state and runtime obligations."""

    model_config = ConfigDict(extra="forbid")

    current_step: str
    goal_type: Literal[
        "clarify_user_intent",
        "fill_missing_step_fields",
        "patch_draft",
        "prepare_commit_intent",
        "recover_from_tool_failure",
    ]
    goal_summary: str
    success_criteria: list[str] = Field(default_factory=list)


class SetupWorkingPlan(BaseModel):
    """Setup-only working plan for the current step slice."""

    model_config = ConfigDict(extra="forbid")

    missing_information: list[str] = Field(default_factory=list)
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
        "reassess_commit_readiness",
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
