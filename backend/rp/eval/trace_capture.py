"""Trace and artifact capture for eval runs."""

from __future__ import annotations

from typing import Any

from rp.agent_runtime.contracts import RpAgentTurnResult
from rp.models.setup_agent import SetupAgentTurnRequest
from rp.models.setup_workspace import SetupWorkspace

from .models import EvalArtifact, EvalEvent, EvalSpan, EvalTrace


def build_setup_trace(
    *,
    trace_id: str,
    run_id: str,
    case_id: str,
    story_id: str,
    request: SetupAgentTurnRequest,
    runtime_result: RpAgentTurnResult | None,
    runtime_events: list[dict[str, Any]],
    workspace_before: SetupWorkspace | None,
    workspace_after: SetupWorkspace | None,
    runtime_debug: dict[str, Any] | None,
    activation_check: dict[str, Any] | None,
    capture_tool_sequence: bool,
    stream_mode: bool,
    started_at,
    finished_at,
) -> tuple[EvalTrace, list[EvalArtifact]]:
    root_span_id = f"{run_id}:root"
    spans = [
        EvalSpan(
            span_id=root_span_id,
            trace_id=trace_id,
            name="setup.turn",
            span_kind="AGENT",
            status=_root_status(runtime_result),
            started_at=started_at,
            finished_at=finished_at,
            input=request.model_dump(mode="json"),
            output=_runtime_result_payload(runtime_result),
            attributes={
                "case_id": case_id,
                "workspace_id": request.workspace_id,
                "story_id": story_id,
                "target_step": (
                    request.target_step.value if request.target_step is not None else None
                ),
                "setup_step": (
                    request.target_step.value if request.target_step is not None else None
                ),
                "model_id": request.model_id,
                "provider_id": request.provider_id,
                "stream_mode": stream_mode,
                "finish_reason": runtime_result.finish_reason if runtime_result else None,
                "repair_route": _structured_payload_value(runtime_result, "repair_route"),
                "continue_reason": _structured_payload_value(runtime_result, "continue_reason"),
                "loop_trace_count": len(_structured_payload_list(runtime_result, "loop_trace")),
                "context_profile": _context_report_value(
                    runtime_result,
                    "context_profile",
                ),
                "context_compacted_history_count": _context_report_value(
                    runtime_result,
                    "compacted_history_count",
                ),
                "context_estimated_input_tokens": _context_report_value(
                    runtime_result,
                    "estimated_input_tokens",
                ),
                "context_previous_prompt_tokens": _context_report_value(
                    runtime_result,
                    "previous_prompt_tokens",
                ),
                "context_previous_total_tokens": _context_report_value(
                    runtime_result,
                    "previous_total_tokens",
                ),
                "context_summary_strategy": _context_report_value(
                    runtime_result,
                    "summary_strategy",
                ),
                "context_summary_action": _context_report_value(
                    runtime_result,
                    "summary_action",
                ),
                "context_fallback_reason": _context_report_value(
                    runtime_result,
                    "fallback_reason",
                ),
                "cognitive_state_invalidated": _cognitive_summary_value(
                    runtime_result,
                    "invalidated",
                ),
                "cognitive_ready_for_review": _cognitive_summary_value(
                    runtime_result,
                    "ready_for_review",
                ),
                "cognitive_remaining_issue_count": len(
                    _cognitive_summary_list(runtime_result, "remaining_open_issues")
                ),
            },
            error=runtime_result.error if runtime_result else None,
        )
    ]
    events = _build_runtime_events(
        root_span_id=root_span_id,
        runtime_events=runtime_events,
    )

    if runtime_result is not None:
        result_by_call_id = {
            item.call_id: item for item in runtime_result.tool_results
        }
        for index, invocation in enumerate(runtime_result.tool_invocations):
            result = result_by_call_id.get(invocation.call_id)
            spans.append(
                EvalSpan(
                    span_id=f"{run_id}:tool:{index}",
                    trace_id=trace_id,
                    parent_span_id=root_span_id,
                    name=_normalize_tool_name(invocation.tool_name),
                    span_kind="TOOL",
                    status="error"
                    if result is not None and not result.success
                    else "ok",
                    started_at=started_at,
                    finished_at=finished_at,
                    input={"arguments": dict(invocation.arguments)},
                    output=_tool_output_payload(result),
                    attributes={
                        "tool_name": _normalize_tool_name(invocation.tool_name),
                        "raw_tool_name": invocation.tool_name,
                        "call_id": invocation.call_id,
                        "source_round": invocation.source_round,
                    },
                    error=_tool_error_payload(result),
                )
            )

    artifacts = [
        EvalArtifact(
            artifact_id=f"{run_id}:artifact:runtime_result",
            run_id=run_id,
            kind="runtime_result",
            name="RpAgentTurnResult",
            payload=_runtime_result_payload(runtime_result),
        )
    ]
    if capture_tool_sequence and runtime_result is not None:
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:tool_sequence",
                run_id=run_id,
                kind="tool_sequence",
                name="SetupToolSequence",
                payload=_tool_sequence_payload(runtime_result),
            )
        )
    cognitive_state_summary = _structured_payload_value(
        runtime_result,
        "cognitive_state_summary",
    )
    if isinstance(cognitive_state_summary, dict):
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:cognitive_state_summary",
                run_id=run_id,
                kind="cognitive_state_summary",
                name="SetupCognitiveStateSummary",
                payload=cognitive_state_summary,
            )
        )
    cognitive_state = _structured_payload_value(runtime_result, "cognitive_state")
    if isinstance(cognitive_state, dict):
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:cognitive_state",
                run_id=run_id,
                kind="cognitive_state",
                name="SetupCognitiveStateSnapshot",
                payload=cognitive_state,
            )
        )
    loop_trace = _structured_payload_value(runtime_result, "loop_trace")
    if isinstance(loop_trace, list):
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:loop_trace",
                run_id=run_id,
                kind="loop_trace",
                name="SetupLoopTrace",
                payload={"frames": list(loop_trace)},
            )
        )
    context_report = _structured_payload_value(runtime_result, "context_report")
    if isinstance(context_report, dict):
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:context_report",
                run_id=run_id,
                kind="context_report",
                name="SetupContextGovernanceReport",
                payload=context_report,
            )
        )
    if workspace_before is not None:
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:workspace_before",
                run_id=run_id,
                kind="workspace_before",
                name="SetupWorkspaceBefore",
                payload=workspace_before.model_dump(mode="json"),
            )
        )
    if workspace_after is not None:
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:workspace_after",
                run_id=run_id,
                kind="workspace_after",
                name="SetupWorkspaceAfter",
                payload=workspace_after.model_dump(mode="json"),
            )
        )
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:readiness_snapshot",
                run_id=run_id,
                kind="readiness_snapshot",
                name="SetupReadinessSnapshot",
                payload=workspace_after.readiness_status.model_dump(mode="json"),
            )
        )
    if runtime_debug is not None:
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:graph_debug",
                run_id=run_id,
                kind="graph_debug",
                name="SetupGraphRuntimeDebug",
                payload=dict(runtime_debug),
            )
        )
    if isinstance(activation_check, dict):
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:activation_check",
                run_id=run_id,
                kind="activation_check",
                name="ActivationCheckResult",
                payload=dict(activation_check),
            )
        )
        handoff = activation_check.get("handoff")
        if isinstance(handoff, dict):
            artifacts.append(
                EvalArtifact(
                    artifact_id=f"{run_id}:artifact:activation_handoff_snapshot",
                    run_id=run_id,
                    kind="activation_handoff_snapshot",
                    name="ActivationHandoffSnapshot",
                    payload=dict(handoff),
                )
            )

    return EvalTrace(trace_id=trace_id, spans=spans, events=events), artifacts


def build_retrieval_trace(
    *,
    trace_id: str,
    run_id: str,
    case_id: str,
    workspace_id: str,
    story_id: str,
    commit_id: str,
    started_at,
    finished_at,
    retrieval_result: dict[str, Any],
    retrieval_truth: dict[str, Any],
) -> tuple[EvalTrace, list[EvalArtifact]]:
    root_span_id = f"{run_id}:root"
    spans = [
        EvalSpan(
            span_id=root_span_id,
            trace_id=trace_id,
            name="retrieval.ingestion",
            span_kind="CHAIN",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            input={
                "workspace_id": workspace_id,
                "story_id": story_id,
                "commit_id": commit_id,
            },
            output=retrieval_result,
            attributes={
                "case_id": case_id,
                "workspace_id": workspace_id,
                "story_id": story_id,
                "commit_id": commit_id,
                "completed_job_count": len(retrieval_result.get("completed_job_ids") or []),
            },
        )
    ]
    query_result = retrieval_result.get("query_result")
    if isinstance(query_result, dict):
        trace_payload = query_result.get("trace")
        spans.append(
            EvalSpan(
                span_id=f"{run_id}:retriever",
                trace_id=trace_id,
                parent_span_id=root_span_id,
                name="retrieval.query",
                span_kind="RETRIEVER",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                input={"query": retrieval_result.get("query_input") or {}},
                output=query_result,
                attributes={
                    "route": trace_payload.get("route") if isinstance(trace_payload, dict) else None,
                    "result_kind": trace_payload.get("result_kind")
                    if isinstance(trace_payload, dict)
                    else None,
                },
            )
        )
    artifacts = [
        EvalArtifact(
            artifact_id=f"{run_id}:artifact:retrieval_result",
            run_id=run_id,
            kind="retrieval_result",
            name="RetrievalRunResult",
            payload=retrieval_result,
        ),
        EvalArtifact(
            artifact_id=f"{run_id}:artifact:retrieval_truth",
            run_id=run_id,
            kind="retrieval_truth",
            name="RetrievalTruth",
            payload=retrieval_truth,
        ),
    ]
    return EvalTrace(trace_id=trace_id, spans=spans, events=[]), artifacts


def build_activation_trace(
    *,
    trace_id: str,
    run_id: str,
    case_id: str,
    workspace_id: str,
    started_at,
    finished_at,
    activation_result: dict[str, Any],
    session_truth: dict[str, Any],
) -> tuple[EvalTrace, list[EvalArtifact]]:
    root_span_id = f"{run_id}:root"
    activation_output = activation_result.get("activation_result")
    if not isinstance(activation_output, dict):
        activation_output = {}
    error_payload = activation_result.get("error")
    if not isinstance(error_payload, dict):
        error_payload = None
    spans = [
        EvalSpan(
            span_id=root_span_id,
            trace_id=trace_id,
            name="activation.bootstrap",
            span_kind="CHAIN",
            status="error" if error_payload is not None else "ok",
            started_at=started_at,
            finished_at=finished_at,
            input={"workspace_id": workspace_id},
            output=activation_result,
            attributes={
                "case_id": case_id,
                "workspace_id": workspace_id,
                "session_id": activation_output.get("session_id"),
                "current_phase": activation_output.get("current_phase"),
                "finish_reason": activation_result.get("finish_reason"),
            },
            error=error_payload,
        )
    ]
    artifacts = [
        EvalArtifact(
            artifact_id=f"{run_id}:artifact:activation_result",
            run_id=run_id,
            kind="activation_result",
            name="StoryActivationResult",
            payload=activation_result,
        ),
        EvalArtifact(
            artifact_id=f"{run_id}:artifact:session_truth",
            run_id=run_id,
            kind="session_truth",
            name="SessionTruth",
            payload=session_truth,
        ),
    ]
    return EvalTrace(trace_id=trace_id, spans=spans, events=[]), artifacts


def _build_runtime_events(
    *,
    root_span_id: str,
    runtime_events: list[dict[str, Any]],
) -> list[EvalEvent]:
    events: list[EvalEvent] = []
    for index, item in enumerate(runtime_events):
        event_type = str(item.get("type") or "unknown")
        payload = dict(item)
        payload.pop("type", None)
        events.append(
            EvalEvent(
                event_id=f"{root_span_id}:event:{index}",
                span_id=root_span_id,
                sequence_no=index + 1,
                type=f"runtime_event.{event_type}",
                payload=payload,
            )
        )
    return events


def _runtime_result_payload(result: RpAgentTurnResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return result.model_dump(mode="json")


def _structured_payload_value(
    result: RpAgentTurnResult | None,
    key: str,
) -> Any | None:
    if result is None:
        return None
    payload = result.structured_payload
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


def _structured_payload_list(
    result: RpAgentTurnResult | None,
    key: str,
) -> list[Any]:
    value = _structured_payload_value(result, key)
    if isinstance(value, list):
        return value
    return []


def _context_report_value(
    result: RpAgentTurnResult | None,
    key: str,
) -> Any | None:
    report = _structured_payload_value(result, "context_report")
    if not isinstance(report, dict):
        return None
    return report.get(key)


def _cognitive_summary_value(
    result: RpAgentTurnResult | None,
    key: str,
) -> Any | None:
    summary = _structured_payload_value(result, "cognitive_state_summary")
    if not isinstance(summary, dict):
        return None
    return summary.get(key)


def _cognitive_summary_list(
    result: RpAgentTurnResult | None,
    key: str,
) -> list[Any]:
    value = _cognitive_summary_value(result, key)
    if isinstance(value, list):
        return value
    return []


def _tool_output_payload(result) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "success": result.success,
        "content_text": result.content_text,
        "error_code": result.error_code,
        "structured_payload": result.structured_payload,
    }


def _tool_error_payload(result) -> dict[str, Any] | None:
    if result is None or result.success:
        return None
    return {
        "error_code": result.error_code,
        "content_text": result.content_text,
    }


def _tool_sequence_payload(result: RpAgentTurnResult) -> dict[str, Any]:
    result_by_call_id = {
        item.call_id: item for item in result.tool_results
    }
    sequence: list[dict[str, Any]] = []
    for index, invocation in enumerate(result.tool_invocations):
        tool_result = result_by_call_id.get(invocation.call_id)
        sequence.append(
            {
                "sequence_no": index + 1,
                "call_id": invocation.call_id,
                "tool_name": _normalize_tool_name(invocation.tool_name),
                "raw_tool_name": invocation.tool_name,
                "arguments": dict(invocation.arguments),
                "source_round": invocation.source_round,
                "success": (
                    bool(tool_result.success) if tool_result is not None else None
                ),
                "error_code": (
                    tool_result.error_code if tool_result is not None else None
                ),
            }
        )
    return {
        "count": len(sequence),
        "items": sequence,
    }


def _root_status(runtime_result: RpAgentTurnResult | None) -> str:
    if runtime_result is None:
        return "error"
    return "error" if runtime_result.status == "failed" else "ok"


def _normalize_tool_name(tool_name: str) -> str:
    if "__" not in tool_name:
        return tool_name
    return tool_name.split("__", 1)[1]
