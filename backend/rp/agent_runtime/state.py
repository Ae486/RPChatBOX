"""Execution-state schema for the RP agent runtime graph."""
from __future__ import annotations

from typing import Any, TypedDict


class RpAgentRunState(TypedDict, total=False):
    run_id: str
    profile_id: str
    run_kind: str
    status: str
    round_no: int
    stream_mode: bool
    turn_input: dict[str, Any]
    normalized_messages: list[dict[str, Any]]
    tool_definitions: list[dict[str, Any]]
    latest_request: dict[str, Any]
    latest_response: dict[str, Any]
    pending_tool_calls: list[dict[str, Any]]
    tool_invocations: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    latest_tool_batch: list[dict[str, Any]]
    assistant_text: str
    warnings: list[str]
    finish_reason: str | None
    error: dict[str, Any] | None
    turn_goal: dict[str, Any] | None
    working_plan: dict[str, Any] | None
    pending_obligation: dict[str, Any] | None
    last_failure: dict[str, Any] | None
    reflection_ticket: dict[str, Any] | None
    completion_guard: dict[str, Any] | None
    cognitive_state: dict[str, Any] | None
    cognitive_state_summary: dict[str, Any] | None
    working_digest: dict[str, Any] | None
    tool_outcomes: list[dict[str, Any]]
    compact_summary: dict[str, Any] | None
    repair_route: str | None
    next_action: str
    schema_retry_count: int
    error_event_emitted: bool
