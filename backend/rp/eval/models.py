"""Contracts for RP eval cases, traces, scores, and reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


EvalScope = Literal["setup", "retrieval", "activation"]
EvalRunStatus = Literal["completed", "failed", "aborted"]
EvalSource = Literal[
    "runtime_result",
    "runtime_events",
    "workspace_truth",
    "workspace_before",
    "graph_debug",
    "activation_result",
    "retrieval_result",
    "retrieval_truth",
    "session_truth",
]
EvalAssertionType = Literal[
    "equals",
    "contains",
    "not_contains",
    "exists",
    "count_gte",
    "custom",
]
EvalSeverity = Literal["error", "warn"]
EvalScoreKind = Literal["code", "llm", "human"]
EvalScoreStatus = Literal["pass", "fail", "warn", "skip"]
EvalFailureLayer = Literal["agent", "deterministic", "infra"]
EvalValueType = Literal["boolean", "numeric", "categorical"]
EvalSpanKind = Literal["AGENT", "CHAIN", "LLM", "TOOL", "RETRIEVER", "EVALUATOR"]


class EvalRuntimeTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["in_process", "http"] = "in_process"
    entrypoint: str
    graph_id: str
    stream: bool = False


class EvalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: dict[str, Any] = Field(default_factory=dict)
    workspace_seed: dict[str, Any] = Field(default_factory=dict)
    env_overrides: dict[str, Any] = Field(default_factory=dict)
    diagnostic_profile: str | None = None


class EvalAssertionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assertion_id: str
    source: EvalSource
    type: EvalAssertionType
    path: str
    expected: Any = None
    severity: EvalSeverity = "error"


class EvalSubjectiveHook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_id: str
    judge_family: str
    rubric_ref: str
    target: str


class EvalExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deterministic_assertions: list[EvalAssertionSpec] = Field(default_factory=list)
    subjective_hooks: list[EvalSubjectiveHook] = Field(default_factory=list)
    expected_reason_codes: list[str] = Field(
        default_factory=list,
        description=(
            "Stable diagnostic reason codes that must be present in the generated "
            "setup diagnostics for this case."
        ),
    )
    expected_primary_suspects: list[str] = Field(
        default_factory=list,
        description=(
            "Primary attribution suspects that must be present in diagnostics."
        ),
    )
    expected_outcome_chain: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Expected setup outcome-chain stage statuses, keyed by stage name."
        ),
    )
    expected_recommended_next_action: str | None = Field(
        default=None,
        description="Expected diagnostics remediation action when the case asserts one.",
    )


class EvalTraceHooks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_runtime_events: bool = True
    capture_graph_debug: bool = True
    capture_workspace_before_after: bool = True
    capture_activation_snapshot: bool = True
    capture_tool_sequence: bool = True


class EvalRepeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 1
    stop_on_first_hard_failure: bool = False


class EvalBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compare_by: list[str] = Field(default_factory=list)
    baseline_tags: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    title: str
    scope: EvalScope
    category: str
    tags: list[str] = Field(default_factory=list)
    runtime_target: EvalRuntimeTarget
    input: EvalInput = Field(default_factory=EvalInput)
    preconditions: dict[str, Any] = Field(default_factory=dict)
    expected: EvalExpected = Field(default_factory=EvalExpected)
    trace_hooks: EvalTraceHooks = Field(default_factory=EvalTraceHooks)
    repeat: EvalRepeat = Field(default_factory=EvalRepeat)
    baseline: EvalBaseline = Field(default_factory=EvalBaseline)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: EvalFailureLayer
    code: str
    message: str
    retryable: bool = False
    source: str | None = None


class EvalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    case_id: str
    scope: EvalScope
    status: EvalRunStatus
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    runtime_target: str
    baseline_tags: list[str] = Field(default_factory=list)
    trace_id: str
    failure: EvalFailure | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    span_id: str
    sequence_no: int
    type: str
    timestamp: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)


class EvalSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    name: str
    span_kind: EvalSpanKind
    status: Literal["ok", "error"] = "ok"
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class EvalArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    run_id: str
    kind: str
    name: str
    content_type: str = "application/json"
    payload: dict[str, Any] = Field(default_factory=dict)


class EvalScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_id: str
    run_id: str
    span_id: str | None = None
    name: str
    kind: EvalScoreKind
    status: EvalScoreStatus
    value_type: EvalValueType
    value: bool | float | str | None = None
    label: str | None = None
    explanation: str | None = None
    severity: EvalSeverity = "error"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    spans: list[EvalSpan] = Field(default_factory=list)
    events: list[EvalEvent] = Field(default_factory=list)


class EvalRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: EvalCase
    run: EvalRun
    trace: EvalTrace
    artifacts: list[EvalArtifact] = Field(default_factory=list)
    scores: list[EvalScore] = Field(default_factory=list)
    runtime_result: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] = Field(default_factory=dict)


class EvalSuiteCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    run_id: str
    scope: EvalScope
    status: EvalRunStatus
    attempt_index: int | None = None
    replay_path: str | None = None
    report_path: str | None = None
    report: dict[str, Any] = Field(default_factory=dict)


class EvalSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str
    case_count: int
    run_count: int
    pass_count: int
    fail_count: int
    output_dir: str | None = None
    items: list[EvalSuiteCaseResult] = Field(default_factory=list)
