"""Optional Langfuse sync helpers for offline eval artifacts and summaries."""

from __future__ import annotations

from pathlib import Path
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

from .replay import load_replay


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
    replay_metadata = {
        "case_id": case.get("case_id"),
        "run_id": run.get("run_id"),
        "trace_id": run.get("trace_id"),
        "scope": scope,
        "workspace_id": metadata.get("workspace_id"),
        "story_id": metadata.get("story_id"),
        "source_session_id": metadata.get("session_id"),
        "setup_step": metadata.get("setup_step"),
        "model_id": metadata.get("model_id"),
        "provider_id": metadata.get("provider_id"),
    }
    replay_metadata = {
        key: value for key, value in replay_metadata.items() if value is not None
    }
    with langfuse.propagate_attributes(
        session_id=session_id,
        tags=["rp", "eval", "replay", scope],
        metadata=replay_metadata,
        trace_name="rp.eval.replay",
    ):
        with langfuse.start_as_current_observation(
            name="rp.eval.replay",
            as_type="eval",
            input={
                "case_id": case.get("case_id"),
                "run_id": run.get("run_id"),
                "trace_id": run.get("trace_id"),
                "scope": scope,
            },
        ) as observation:
            retrieval_sync_payload = (
                _extract_retrieval_sync_payload(runtime_result)
                if scope == "retrieval"
                else None
            )
            observation.update(
                output=_build_replay_output(
                    scope=scope,
                    run=run,
                    metadata=metadata,
                    report=report,
                    retrieval_sync_payload=retrieval_sync_payload,
                ),
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
                    report=report,
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


def sync_suite_bundle_to_langfuse(
    *,
    suite_payload: dict[str, Any],
    summary: dict[str, Any],
    thresholds: dict[str, Any],
    comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sync the full suite bundle to Langfuse for WebUI drill-down."""
    sync_suite_summary_to_langfuse(
        suite_payload=suite_payload,
        summary=summary,
        thresholds=thresholds,
    )
    replay_payloads = _load_suite_replay_payloads(suite_payload)
    for replay_payload in replay_payloads:
        sync_replay_to_langfuse(replay_payload=replay_payload)
    comparison_synced = isinstance(comparison, dict)
    if isinstance(comparison, dict):
        sync_comparison_to_langfuse(comparison=comparison)
    return {
        "suite_summary_synced": True,
        "suite_replay_sync_count": len(replay_payloads),
        "comparison_synced": comparison_synced,
    }


def _build_replay_output(
    *,
    scope: str,
    run: dict[str, Any],
    metadata: dict[str, Any],
    report: dict[str, Any],
    retrieval_sync_payload: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "status": run.get("status"),
        "finish_reason": report.get("finish_reason"),
        "identifiers": {
            "run_id": run.get("run_id"),
            "trace_id": run.get("trace_id"),
            "workspace_id": metadata.get("workspace_id"),
            "story_id": metadata.get("story_id"),
            "session_id": metadata.get("session_id"),
        },
        "diagnostics": _build_replay_diagnostics_output(scope=scope, report=report),
        "retrieval": (
            {
                "query_kind": retrieval_sync_payload["query_payload"].get("query_kind"),
                "route": retrieval_sync_payload["observability_payload"].get("route"),
                "returned_count": retrieval_sync_payload["observability_payload"].get("returned_count"),
            }
            if isinstance(retrieval_sync_payload, dict)
            else None
        ),
    }


def _build_replay_diagnostics_output(
    *,
    scope: str,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    diagnostics = {
        "scope": scope,
        "failure_layer": report.get("failure_layer"),
        "reason_codes": list(report.get("reason_codes") or []),
        "primary_suspects": list(report.get("primary_suspects") or []),
        "secondary_suspects": list(report.get("secondary_suspects") or []),
        "recommended_next_action": report.get("recommended_next_action"),
        "outcome_chain": dict(report.get("outcome_chain") or {}),
        "evidence_refs": list(report.get("evidence_refs") or []),
    }
    if any(
        value
        for key, value in diagnostics.items()
        if key not in {"scope", "failure_layer", "recommended_next_action"}
    ):
        return diagnostics
    if diagnostics["failure_layer"] is not None or diagnostics["recommended_next_action"] is not None:
        return diagnostics
    return None


def _load_suite_replay_payloads(suite_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = suite_payload.get("items")
    if not isinstance(items, list):
        return []
    replay_payloads: list[dict[str, Any]] = []
    missing_case_ids: list[str] = []
    seen_paths: set[str] = set()
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        case_id = str(raw_item.get("case_id") or "unknown")
        replay_path = raw_item.get("replay_path")
        if not isinstance(replay_path, str) or not replay_path.strip():
            missing_case_ids.append(case_id)
            continue
        normalized_path = str(Path(replay_path).resolve())
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        replay_payloads.append(load_replay(normalized_path))
    if missing_case_ids:
        missing_text = ", ".join(sorted(missing_case_ids))
        raise ValueError(
            "Suite replay sync requires replay bundles for every suite item. "
            f"Missing replay_path for: {missing_text}"
        )
    return replay_payloads


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
