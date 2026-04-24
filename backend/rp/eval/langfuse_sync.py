"""Optional Langfuse sync helpers for offline eval artifacts and summaries."""

from __future__ import annotations

from typing import Any

from rp.observability.langfuse_scores import (
    emit_activation_trace_scores,
    emit_comparison_scores,
    emit_retrieval_trace_scores,
    emit_ragas_metric_scores,
    emit_setup_trace_scores,
    emit_suite_summary_scores,
)
from services.langfuse_service import get_langfuse_service


def sync_suite_summary_to_langfuse(
    *,
    suite_payload: dict[str, Any],
    summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    langfuse = get_langfuse_service()
    suite_id = str(suite_payload.get("suite_id") or "offline-suite")
    metadata = {
        "suite_id": suite_id,
        "case_count": int(summary.get("case_count") or 0),
        "run_count": int(summary.get("run_count") or 0),
    }
    with langfuse.propagate_attributes(
        session_id=suite_id,
        tags=["rp", "eval", "suite"],
        metadata=metadata,
        trace_name="rp.eval.suite",
    ):
        with langfuse.start_as_current_observation(
            name="rp.eval.suite",
            as_type="eval",
            input={
                "suite_id": suite_id,
                "case_count": int(summary.get("case_count") or 0),
                "run_count": int(summary.get("run_count") or 0),
            },
        ) as observation:
            observation.update(
                output={
                    "summary": summary,
                    "thresholds": thresholds,
                }
            )
            emit_suite_summary_scores(
                observation,
                summary=summary,
                thresholds=thresholds,
            )


def sync_comparison_to_langfuse(*, comparison: dict[str, Any]) -> None:
    langfuse = get_langfuse_service()
    current = comparison.get("current")
    baseline = comparison.get("baseline")
    if not isinstance(current, dict):
        current = {}
    if not isinstance(baseline, dict):
        baseline = {}
    session_id = str(current.get("suite_id") or baseline.get("suite_id") or "offline-comparison")
    metadata = {
        "current_suite_id": current.get("suite_id"),
        "baseline_suite_id": baseline.get("suite_id"),
    }
    with langfuse.propagate_attributes(
        session_id=session_id,
        tags=["rp", "eval", "compare"],
        metadata=metadata,
        trace_name="rp.eval.compare",
    ):
        with langfuse.start_as_current_observation(
            name="rp.eval.compare",
            as_type="eval",
            input=metadata,
        ) as observation:
            observation.update(output={"comparison": comparison})
            emit_comparison_scores(observation, comparison=comparison)


def sync_replay_to_langfuse(*, replay_payload: dict[str, Any]) -> None:
    langfuse = get_langfuse_service()
    case = replay_payload.get("case")
    if not isinstance(case, dict):
        case = {}
    run = replay_payload.get("run")
    if not isinstance(run, dict):
        run = {}
    report = replay_payload.get("report")
    if not isinstance(report, dict):
        report = {}
    runtime_result = replay_payload.get("runtime_result")
    if not isinstance(runtime_result, dict):
        runtime_result = {}

    failure = run.get("failure")
    if not isinstance(failure, dict):
        failure = {}
    metadata = run.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    session_id = str(
        metadata.get("story_id")
        or metadata.get("workspace_id")
        or metadata.get("session_id")
        or run.get("run_id")
        or "offline-replay"
    )
    scope = str(case.get("scope") or run.get("scope") or "unknown")
    with langfuse.propagate_attributes(
        session_id=session_id,
        tags=["rp", "eval", "replay", scope],
        metadata={
            "case_id": case.get("case_id"),
            "run_id": run.get("run_id"),
            "scope": scope,
        },
        trace_name="rp.eval.replay",
    ):
        with langfuse.start_as_current_observation(
            name="rp.eval.replay",
            as_type="eval",
            input={
                "case_id": case.get("case_id"),
                "run_id": run.get("run_id"),
                "scope": scope,
            },
        ) as observation:
            retrieval_sync_payload = (
                _extract_retrieval_sync_payload(runtime_result)
                if scope == "retrieval"
                else None
            )
            observation.update(
                output={
                    "status": run.get("status"),
                    "finish_reason": report.get("finish_reason"),
                    "retrieval": (
                        {
                            "query_kind": retrieval_sync_payload["query_payload"].get("query_kind"),
                            "route": retrieval_sync_payload["observability_payload"].get("route"),
                            "returned_count": retrieval_sync_payload["observability_payload"].get("returned_count"),
                        }
                        if isinstance(retrieval_sync_payload, dict)
                        else None
                    ),
                },
            )
            failure_layer = (
                str(failure.get("layer"))
                if failure.get("layer") is not None
                else report.get("failure_layer")
            )
            error_code = str(failure.get("code")) if failure.get("code") is not None else None
            if scope == "setup":
                emit_setup_trace_scores(
                    observation,
                    runtime_result=runtime_result,
                    failure_layer=failure_layer,
                    error_code=error_code,
                )
            elif scope == "activation":
                emit_activation_trace_scores(
                    observation,
                    runtime_result=runtime_result,
                    failure_layer=failure_layer,
                    error_code=error_code,
                )
            elif scope == "retrieval" and isinstance(retrieval_sync_payload, dict):
                emit_retrieval_trace_scores(
                    observation,
                    query_payload=retrieval_sync_payload["query_payload"],
                    result_payload=retrieval_sync_payload["result_payload"],
                    observability_payload=retrieval_sync_payload["observability_payload"],
                    failure_layer=failure_layer,
                    error_code=error_code,
                )
            ragas = report.get("ragas")
            if isinstance(ragas, dict):
                emit_ragas_metric_scores(observation, report=ragas)


def _extract_retrieval_sync_payload(
    runtime_result: dict[str, Any],
) -> dict[str, dict[str, Any]] | None:
    query_payload = runtime_result.get("query_input")
    result_payload = runtime_result.get("query_result")
    if not isinstance(query_payload, dict) or not isinstance(result_payload, dict):
        return None

    trace_payload = result_payload.get("trace")
    if not isinstance(trace_payload, dict):
        trace_payload = {}
    warnings = _merge_retrieval_warnings(
        result_warnings=result_payload.get("warnings"),
        trace_warnings=trace_payload.get("warnings"),
    )
    maintenance = runtime_result.get("maintenance")
    maintenance_snapshot = {}
    if isinstance(maintenance, dict) and isinstance(maintenance.get("story_snapshot"), dict):
        maintenance_snapshot = dict(maintenance.get("story_snapshot") or {})

    observability_payload = {
        "query_id": query_payload.get("query_id"),
        "story_id": query_payload.get("story_id"),
        "query_kind": query_payload.get("query_kind"),
        "text_query": query_payload.get("text_query"),
        "top_k": query_payload.get("top_k"),
        "route": trace_payload.get("route"),
        "result_kind": trace_payload.get("result_kind"),
        "retriever_routes": list(trace_payload.get("retriever_routes") or []),
        "pipeline_stages": list(trace_payload.get("pipeline_stages") or []),
        "reranker_name": trace_payload.get("reranker_name"),
        "candidate_count": trace_payload.get("candidate_count"),
        "returned_count": trace_payload.get("returned_count"),
        "filters_applied": dict(trace_payload.get("filters_applied") or {}),
        "timings": dict(trace_payload.get("timings") or {}),
        "warnings": warnings,
        "warning_buckets": _build_warning_buckets(warnings),
        "details": dict(trace_payload.get("details") or {}),
        "maintenance": maintenance_snapshot,
    }
    return {
        "query_payload": dict(query_payload),
        "result_payload": dict(result_payload),
        "observability_payload": observability_payload,
    }


def _merge_retrieval_warnings(*, result_warnings: Any, trace_warnings: Any) -> list[str]:
    merged: list[str] = []
    for value in (result_warnings, trace_warnings):
        if not isinstance(value, list):
            continue
        for item in value:
            warning = str(item or "").strip()
            if warning and warning not in merged:
                merged.append(warning)
    return merged


def _build_warning_buckets(warnings: list[str]) -> list[dict[str, Any]]:
    buckets: dict[str, list[str]] = {}
    for warning in warnings:
        category = str(warning or "").split(":", 1)[0].strip() or "unknown"
        buckets.setdefault(category, []).append(warning)
    return [
        {
            "category": category,
            "count": len(items),
            "warnings": items,
        }
        for category, items in buckets.items()
    ]
