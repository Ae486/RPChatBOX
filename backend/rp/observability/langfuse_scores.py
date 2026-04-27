"""Langfuse score emission helpers for RP runtime traces."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency path
    from langfuse.api import ScoreDataType
except ImportError:  # pragma: no cover - optional dependency path
    ScoreDataType = None


def emit_setup_trace_scores(
    observation: Any,
    *,
    runtime_result: dict[str, Any],
    failure_layer: str | None = None,
    error_code: str | None = None,
    report: dict[str, Any] | None = None,
) -> None:
    """Attach coarse setup scores to the current Langfuse trace."""
    if observation is None:
        return
    from rp.eval.diagnostics import build_setup_diagnostic_projection

    diagnostics = build_setup_diagnostic_projection(
        runtime_result=runtime_result,
        failure_layer=failure_layer,
        error_code=error_code,
    )
    if not isinstance(report, dict):
        report = {}
    report_diagnostics = _first_dict(report.get("diagnostics"))
    report_attribution = _first_dict(report_diagnostics.get("attribution"))
    finish_reason = runtime_result.get("finish_reason")
    warnings = _first_list(runtime_result.get("warnings"))
    structured_payload = _first_dict(runtime_result.get("structured_payload"))
    repair_route = structured_payload.get("repair_route")
    completion_guard = _first_dict(structured_payload.get("completion_guard"))
    pending_obligation = _first_dict(structured_payload.get("pending_obligation"))
    if repair_route is None and (
        "commit_proposal_blocked" in warnings
        or pending_obligation.get("obligation_type") == "reassess_commit_readiness"
    ):
        repair_route = "block_commit"
    last_failure = _first_dict(structured_payload.get("last_failure"))
    usage = (
        structured_payload.get("latest_response", {}).get("usage")
        if isinstance(structured_payload.get("latest_response"), dict)
        else None
    )
    usage = _first_dict(usage)
    tool_invocations = runtime_result.get("tool_invocations")
    if not isinstance(tool_invocations, list):
        tool_invocations = []
    tool_results = runtime_result.get("tool_results")
    if not isinstance(tool_results, list):
        tool_results = []
    assistant_text = str(runtime_result.get("assistant_text") or "")
    turn_goal = _first_dict(structured_payload.get("turn_goal"))
    working_plan = _first_dict(structured_payload.get("working_plan"))
    request_context = _first_dict(structured_payload.get("request_context"))
    round_no = int(structured_payload.get("round_no") or 0)
    total_tokens = int(usage.get("total_tokens") or 0)
    capabilities = diagnostics.get("capabilities") or {}
    attribution = diagnostics.get("attribution") or {}
    if not isinstance(attribution, dict):
        attribution = {}
    attribution_dimensions = _first_dict(
        report_attribution.get("dimensions"),
        attribution.get("dimensions"),
    )
    outcome_chain = _first_dict(
        report.get("outcome_chain"),
        report_diagnostics.get("outcome_chain"),
        diagnostics.get("outcome_chain"),
    )
    reason_codes = _first_list(
        report.get("reason_codes"),
        report_diagnostics.get("reason_codes"),
        diagnostics.get("reason_codes"),
    )
    primary_suspects = _first_list(
        report.get("primary_suspects"),
        report_attribution.get("primary_suspects"),
        attribution.get("primary_suspects"),
    )
    secondary_suspects = _first_list(
        report.get("secondary_suspects"),
        report_attribution.get("secondary_suspects"),
        attribution.get("secondary_suspects"),
    )
    evidence_refs = _first_list(
        report.get("evidence_refs"),
        report_attribution.get("evidence_refs"),
        attribution.get("evidence_refs"),
    )
    optimization_candidates = _first_list(
        report_attribution.get("optimization_candidates"),
        attribution.get("optimization_candidates"),
    )
    recommended_next_action = _first_scalar(
        report.get("recommended_next_action"),
        report_diagnostics.get("recommended_next_action"),
        report_attribution.get("recommended_next_action"),
        diagnostics.get("recommended_next_action"),
        attribution.get("recommended_next_action"),
    )
    effective_failure_layer = _first_scalar(
        report.get("failure_layer"),
        report_diagnostics.get("failure_layer"),
        diagnostics.get("failure_layer"),
        failure_layer,
    )

    _score_trace(
        observation,
        name="setup.finish_reason",
        value=str(finish_reason or "unknown"),
        data_type=_categorical_type(),
        comment="Setup turn terminal finish reason",
    )
    if repair_route:
        _score_trace(
            observation,
            name="setup.repair_route",
            value=str(repair_route),
            data_type=_categorical_type(),
            comment="Setup recovery route selected by runtime",
        )
    _score_trace(
        observation,
        name="setup.commit_blocked",
        value=bool(
            repair_route == "block_commit"
            or "commit_proposal_blocked" in warnings
        ),
        data_type=_boolean_type(),
        comment="Whether runtime blocked commit proposal in this turn",
    )
    _score_trace(
        observation,
        name="setup.pending_obligation",
        value=str(pending_obligation.get("obligation_type") or "none"),
        data_type=_categorical_type(),
        comment="Pending obligation left by runtime after the turn",
    )
    if completion_guard.get("reason"):
        _score_trace(
            observation,
            name="setup.completion_guard_reason",
            value=str(completion_guard.get("reason")),
            data_type=_categorical_type(),
            comment="Completion guard reason for finalization decision",
        )
    if last_failure.get("failure_category"):
        _score_trace(
            observation,
            name="setup.last_failure_category",
            value=str(last_failure.get("failure_category")),
            data_type=_categorical_type(),
            comment="Last failure category interpreted by runtime",
        )
    _score_trace(
        observation,
        name="setup.task_completion",
        value=bool(finish_reason and finish_reason != "runtime_failed"),
        data_type=_boolean_type(),
        comment="Coarse online success signal for one setup turn",
    )
    _score_trace(
        observation,
        name="setup.failure_layer",
        value=str(effective_failure_layer or "none"),
        data_type=_categorical_type(),
        comment="Top-level setup failure layer used by offline/online diagnostics",
    )
    _score_trace(
        observation,
        name="setup.metric.total_tokens",
        value=total_tokens,
        data_type=_numeric_type(),
        comment="Total tokens reported by the latest setup model response",
    )
    _score_trace(
        observation,
        name="setup.metric.round_no",
        value=round_no,
        data_type=_numeric_type(),
        comment="Runtime round count for this setup turn",
    )
    _score_trace(
        observation,
        name="setup.metric.tool_invocation_count",
        value=len(tool_invocations),
        data_type=_numeric_type(),
        comment="Tool invocation count for this setup turn",
    )
    if tool_invocations:
        _score_trace(
            observation,
            name="setup.metric.tokens_per_tool_invocation",
            value=round(total_tokens / len(tool_invocations), 2),
            data_type=_numeric_type(),
            comment="Average tokens spent per tool invocation in this setup turn",
        )
    _emit_diagnostic_score_group(
        observation,
        prefix="setup",
        name="tool_selection_correct",
        entry=_build_setup_tool_selection_entry(
            tool_invocations=tool_invocations,
            tool_results=tool_results,
            turn_goal=turn_goal,
            working_plan=working_plan,
            request_context=request_context,
            pending_obligation=pending_obligation,
            completion_guard_reason=str(completion_guard.get("reason") or ""),
            finish_reason=str(finish_reason or ""),
        ),
    )
    _emit_diagnostic_score_group(
        observation,
        prefix="setup",
        name="tool_result_value",
        entry=_build_setup_tool_result_value_entry(
            tool_invocations=tool_invocations,
            tool_results=tool_results,
            finish_reason=str(finish_reason or ""),
            assistant_text=assistant_text,
            request_context=request_context,
            pending_obligation=pending_obligation,
            completion_guard_reason=str(completion_guard.get("reason") or ""),
            repair_route=str(repair_route or ""),
        ),
    )
    _emit_diagnostic_score_group(
        observation,
        prefix="setup.loop",
        name="noop_or_repeated_question",
        entry=_build_setup_loop_health_entry(
            round_no=round_no,
            tool_invocations=tool_invocations,
            tool_results=tool_results,
            finish_reason=str(finish_reason or ""),
            request_context=request_context,
            pending_obligation=pending_obligation,
            completion_guard_reason=str(completion_guard.get("reason") or ""),
            assistant_text=assistant_text,
        ),
    )
    for name, entry in capabilities.items():
        _emit_diagnostic_score_group(
            observation,
            prefix="setup.capability",
            name=str(name),
            entry=entry if isinstance(entry, dict) else {},
        )
    for name, entry in attribution_dimensions.items():
        _emit_diagnostic_score_group(
            observation,
            prefix="setup.attribution",
            name=str(name),
            entry=entry if isinstance(entry, dict) else {},
        )
    _score_trace(
        observation,
        name="setup.attribution.primary_suspects",
        value=_list_score_value(primary_suspects),
        data_type=_categorical_type(),
        comment="Top attribution suspects derived from setup diagnostics",
    )
    _score_trace(
        observation,
        name="setup.attribution.secondary_suspects",
        value=_list_score_value(secondary_suspects),
        data_type=_categorical_type(),
        comment="Secondary attribution suspects derived from setup diagnostics",
    )
    _score_trace(
        observation,
        name="setup.attribution.optimization_candidates",
        value=_list_score_value(optimization_candidates),
        data_type=_categorical_type(),
        comment="Suggested optimization actions derived from setup diagnostics",
    )
    _score_trace(
        observation,
        name="setup.recommended_next_action",
        value=str(recommended_next_action or "none"),
        data_type=_categorical_type(),
        comment="Primary recommended next action derived from setup diagnostics",
    )
    _score_trace(
        observation,
        name="setup.reason_codes",
        value=_list_score_value(reason_codes),
        data_type=_categorical_type(),
        comment="Stable setup reason codes derived from offline/online diagnostics",
    )
    _score_trace(
        observation,
        name="setup.evidence_refs",
        value=_list_score_value(evidence_refs),
        data_type=_categorical_type(),
        comment="Evidence artifact refs backing setup diagnostics",
    )
    for chain_name, status in dict(outcome_chain).items():
        _score_trace(
            observation,
            name=f"setup.outcome_chain.{chain_name}",
            value=str(status),
            data_type=_categorical_type(),
            comment="Outcome-chain status derived from setup diagnostics",
        )


def emit_activation_trace_scores(
    observation: Any,
    *,
    runtime_result: dict[str, Any],
    failure_layer: str | None = None,
    error_code: str | None = None,
) -> None:
    """Attach activation diagnostics to the current Langfuse trace."""
    if observation is None:
        return
    from rp.eval.diagnostics import build_activation_diagnostic_projection

    diagnostics = build_activation_diagnostic_projection(
        runtime_result=runtime_result,
        failure_layer=failure_layer,
        error_code=error_code,
    )
    activation_check = runtime_result.get("activation_check")
    if not isinstance(activation_check, dict):
        activation_check = {}
    activation_result = runtime_result.get("activation_result")
    if not isinstance(activation_result, dict):
        activation_result = {}
    capabilities = diagnostics.get("capabilities") or {}
    attribution = diagnostics.get("attribution") or {}
    attribution_dimensions = attribution.get("dimensions") or {}

    _score_trace(
        observation,
        name="activation.finish_reason",
        value=str(runtime_result.get("finish_reason") or "unknown"),
        data_type=_categorical_type(),
        comment="Activation terminal finish reason",
    )
    _score_trace(
        observation,
        name="activation.ready",
        value=bool(activation_check.get("ready")),
        data_type=_boolean_type(),
        comment="Whether the activation readiness gate passed",
    )
    _score_trace(
        observation,
        name="activation.metric.blocking_issue_count",
        value=len(activation_check.get("blocking_issues") or []),
        data_type=_numeric_type(),
        comment="Blocking issue count returned by activation-check",
    )
    _score_trace(
        observation,
        name="activation.metric.warning_count",
        value=len(activation_check.get("warnings") or []),
        data_type=_numeric_type(),
        comment="Warning count returned by activation-check",
    )
    _score_trace(
        observation,
        name="activation.metric.foundation_commit_ref_count",
        value=len(((activation_check.get("handoff") or {}).get("foundation_commit_refs") or [])),
        data_type=_numeric_type(),
        comment="Foundation commit refs carried in the activation handoff",
    )
    _score_trace(
        observation,
        name="activation.metric.archival_ready_ref_count",
        value=len(((activation_check.get("handoff") or {}).get("archival_ready_refs") or [])),
        data_type=_numeric_type(),
        comment="Archival-ready refs carried in the activation handoff",
    )
    if activation_result.get("session_id"):
        _score_trace(
            observation,
            name="activation.session_id",
            value=str(activation_result.get("session_id")),
            data_type=_categorical_type(),
            comment="Activated StorySession identifier",
        )
    if activation_result.get("current_phase") is not None:
        _score_trace(
            observation,
            name="activation.current_phase",
            value=str(activation_result.get("current_phase")),
            data_type=_categorical_type(),
            comment="Current phase immediately after activation bootstrap",
        )
    for name, entry in capabilities.items():
        _emit_diagnostic_score_group(
            observation,
            prefix="activation.capability",
            name=str(name),
            entry=entry if isinstance(entry, dict) else {},
        )
    for name, entry in attribution_dimensions.items():
        _emit_diagnostic_score_group(
            observation,
            prefix="activation.attribution",
            name=str(name),
            entry=entry if isinstance(entry, dict) else {},
        )
    _score_trace(
        observation,
        name="activation.attribution.primary_suspects",
        value=_list_score_value(attribution.get("primary_suspects")),
        data_type=_categorical_type(),
        comment="Top attribution suspects derived from activation diagnostics",
    )
    _score_trace(
        observation,
        name="activation.attribution.optimization_candidates",
        value=_list_score_value(attribution.get("optimization_candidates")),
        data_type=_categorical_type(),
        comment="Suggested optimization actions derived from activation diagnostics",
    )


def emit_retrieval_trace_scores(
    observation: Any,
    *,
    query_payload: dict[str, Any],
    result_payload: dict[str, Any],
    observability_payload: dict[str, Any] | None = None,
    failure_layer: str | None = None,
    error_code: str | None = None,
) -> None:
    """Attach coarse retrieval observability signals to the current Langfuse trace."""
    if observation is None:
        return

    if not isinstance(query_payload, dict):
        query_payload = {}
    if not isinstance(result_payload, dict):
        result_payload = {}
    if not isinstance(observability_payload, dict):
        observability_payload = {}

    trace = result_payload.get("trace")
    if not isinstance(trace, dict):
        trace = {}
    warnings = observability_payload.get("warnings")
    if not isinstance(warnings, list):
        warnings = result_payload.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warning_buckets = observability_payload.get("warning_buckets")
    if not isinstance(warning_buckets, list):
        warning_buckets = []
    warning_categories = [
        str(item.get("category")).strip()
        for item in warning_buckets
        if isinstance(item, dict) and str(item.get("category") or "").strip()
    ]
    if not warning_categories and warnings:
        warning_categories = _warning_categories_from_warnings(warnings)
    timings = observability_payload.get("timings")
    if not isinstance(timings, dict):
        timings = trace.get("timings")
    if not isinstance(timings, dict):
        timings = {}
    maintenance = observability_payload.get("maintenance")
    if not isinstance(maintenance, dict):
        maintenance = {}
    route = str(observability_payload.get("route") or trace.get("route") or "").strip()
    result_kind = str(
        observability_payload.get("result_kind") or trace.get("result_kind") or ""
    ).strip()
    reranker_name = str(
        observability_payload.get("reranker_name") or trace.get("reranker_name") or ""
    ).strip()
    returned_count = _coerce_int(
        observability_payload.get("returned_count"),
        fallback=_coerce_int(trace.get("returned_count"), fallback=len(result_payload.get("hits") or [])),
    )
    candidate_count = _coerce_int(
        observability_payload.get("candidate_count"),
        fallback=_coerce_int(trace.get("candidate_count"), fallback=returned_count),
    )
    query_kind = str(query_payload.get("query_kind") or "unknown")
    scope = str(query_payload.get("scope") or "none")
    top_k = _coerce_int(query_payload.get("top_k"), fallback=0)
    pipeline_stages = observability_payload.get("pipeline_stages")
    if not isinstance(pipeline_stages, list):
        pipeline_stages = trace.get("pipeline_stages")
    if not isinstance(pipeline_stages, list):
        pipeline_stages = []
    retriever_routes = observability_payload.get("retriever_routes")
    if not isinstance(retriever_routes, list):
        retriever_routes = trace.get("retriever_routes")
    if not isinstance(retriever_routes, list):
        retriever_routes = []
    failed_job_count = _coerce_int(maintenance.get("failed_job_count"), fallback=0)
    backfill_candidate_count = len(maintenance.get("backfill_candidate_asset_ids") or [])
    latency_ms = _resolve_retrieval_latency_ms(timings)
    execution_status = "failed" if failure_layer or error_code else "ok"
    pipeline_health = "fail" if failure_layer or error_code else ("warn" if warnings else "pass")

    _score_trace(
        observation,
        name="retrieval.query_kind",
        value=query_kind,
        data_type=_categorical_type(),
        comment="Retrieval query kind",
    )
    _score_trace(
        observation,
        name="retrieval.scope",
        value=scope,
        data_type=_categorical_type(),
        comment="Retrieval scope",
    )
    _score_trace(
        observation,
        name="retrieval.execution_status",
        value=execution_status,
        data_type=_categorical_type(),
        comment="Retrieval execution status",
    )
    if failure_layer:
        _score_trace(
            observation,
            name="retrieval.failure_layer",
            value=str(failure_layer),
            data_type=_categorical_type(),
            comment="Failure layer reported for retrieval execution",
        )
    if error_code:
        _score_trace(
            observation,
            name="retrieval.error_code",
            value=str(error_code),
            data_type=_categorical_type(),
            comment="Error code reported for retrieval execution",
        )
    if route:
        _score_trace(
            observation,
            name="retrieval.route",
            value=route,
            data_type=_categorical_type(),
            comment="Resolved retrieval route",
        )
    if result_kind:
        _score_trace(
            observation,
            name="retrieval.result_kind",
            value=result_kind,
            data_type=_categorical_type(),
            comment="Retrieval result kind",
        )
    if reranker_name:
        _score_trace(
            observation,
            name="retrieval.reranker_name",
            value=reranker_name,
            data_type=_categorical_type(),
            comment="Resolved reranker name when available",
        )
    _score_trace(
        observation,
        name="retrieval.hit_found",
        value=bool(returned_count > 0),
        data_type=_boolean_type(),
        comment="Whether retrieval returned at least one hit",
    )
    _score_trace(
        observation,
        name="retrieval.pipeline_health",
        value=pipeline_health,
        data_type=_categorical_type(),
        comment="pass=no warnings, warn=warnings present, fail=execution failure",
    )
    numeric_health = _status_to_numeric(pipeline_health)
    if numeric_health is not None:
        _score_trace(
            observation,
            name="retrieval.pipeline_health.numeric",
            value=numeric_health,
            data_type=_numeric_type(),
            comment="Numeric retrieval pipeline health signal",
        )
    _score_trace(
        observation,
        name="retrieval.warning_categories",
        value=_list_score_value(warning_categories),
        data_type=_categorical_type(),
        comment="Warning bucket categories observed during retrieval",
    )
    _score_trace(
        observation,
        name="retrieval.metric.top_k",
        value=top_k,
        data_type=_numeric_type(),
        comment="Requested retrieval top_k",
    )
    _score_trace(
        observation,
        name="retrieval.metric.candidate_count",
        value=candidate_count,
        data_type=_numeric_type(),
        comment="Candidate count before final truncation",
    )
    _score_trace(
        observation,
        name="retrieval.metric.returned_count",
        value=returned_count,
        data_type=_numeric_type(),
        comment="Returned hit count",
    )
    _score_trace(
        observation,
        name="retrieval.metric.warning_count",
        value=len(warnings),
        data_type=_numeric_type(),
        comment="Total retrieval warning count",
    )
    _score_trace(
        observation,
        name="retrieval.metric.warning_bucket_count",
        value=len(warning_categories),
        data_type=_numeric_type(),
        comment="Unique retrieval warning bucket count",
    )
    _score_trace(
        observation,
        name="retrieval.metric.pipeline_stage_count",
        value=len(pipeline_stages),
        data_type=_numeric_type(),
        comment="Pipeline stage count surfaced by retrieval trace",
    )
    _score_trace(
        observation,
        name="retrieval.metric.retriever_route_count",
        value=len(retriever_routes),
        data_type=_numeric_type(),
        comment="Retriever route fan-out count",
    )
    _score_trace(
        observation,
        name="retrieval.metric.failed_job_count",
        value=failed_job_count,
        data_type=_numeric_type(),
        comment="Failed retrieval maintenance jobs for the story snapshot",
    )
    _score_trace(
        observation,
        name="retrieval.metric.backfill_candidate_count",
        value=backfill_candidate_count,
        data_type=_numeric_type(),
        comment="Backfill candidate assets for the story snapshot",
    )
    if latency_ms is not None:
        _score_trace(
            observation,
            name="retrieval.metric.latency_ms",
            value=latency_ms,
            data_type=_numeric_type(),
            comment="End-to-end retrieval latency from trace timings",
        )


def emit_ragas_metric_scores(
    observation: Any,
    *,
    report: dict[str, Any],
) -> None:
    """Attach retrieval/RAGAS metrics to the current Langfuse trace."""
    if observation is None:
        return
    metric_summary = report.get("metric_summary")
    if not isinstance(metric_summary, dict):
        metric_summary = {}
    _score_trace(
        observation,
        name="retrieval.ragas.status",
        value=str(report.get("status") or "unknown"),
        data_type=_categorical_type(),
        comment="RAGAS execution status for retrieval evaluation",
    )
    _score_trace(
        observation,
        name="retrieval.ragas.sample_count",
        value=int(report.get("sample_count") or 0),
        data_type=_numeric_type(),
        comment="RAGAS sample count",
    )
    for metric_name, value in metric_summary.items():
        if value is None:
            continue
        _score_trace(
            observation,
            name=f"retrieval.ragas.{metric_name}",
            value=float(value),
            data_type=_numeric_type(),
            comment=f"RAGAS metric {metric_name}",
        )


def emit_suite_summary_scores(
    observation: Any,
    *,
    summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> None:
    """Attach offline eval suite summary and threshold signals to Langfuse."""
    if observation is None:
        return
    numeric_fields = {
        "run_count": summary.get("run_count"),
        "case_count": summary.get("case_count"),
        "failed_run_count": summary.get("failed_run_count"),
        "assertion_fail_total": summary.get("assertion_fail_total"),
        "assertion_warn_total": summary.get("assertion_warn_total"),
        "hard_failure_total": summary.get("hard_failure_total"),
        "pending_judge_hook_total": summary.get("pending_judge_hook_total"),
        "executed_judge_hook_total": summary.get("executed_judge_hook_total"),
    }
    for field_name, value in numeric_fields.items():
        _score_trace(
            observation,
            name=f"eval.suite.{field_name}",
            value=int(value or 0),
            data_type=_numeric_type(),
            comment=f"Offline eval suite summary field {field_name}",
        )
    _score_trace(
        observation,
        name="eval.suite.threshold_passed",
        value=bool(thresholds.get("passed")),
        data_type=_boolean_type(),
        comment="Whether suite thresholds passed",
    )
    _score_trace(
        observation,
        name="eval.suite.threshold_breaches",
        value=_list_score_value(thresholds.get("breaches")),
        data_type=_categorical_type(),
        comment="Threshold breach summary",
    )
    _score_trace(
        observation,
        name="eval.suite.repeat_case_ids",
        value=_list_score_value(summary.get("repeat_case_ids")),
        data_type=_categorical_type(),
        comment="Case ids executed multiple times in the suite",
    )
    ragas_metric_averages = summary.get("ragas_metric_averages")
    if isinstance(ragas_metric_averages, dict):
        for metric_name, value in ragas_metric_averages.items():
            if value is None:
                continue
            _score_trace(
                observation,
                name=f"eval.suite.ragas.{metric_name}",
                value=float(value),
                data_type=_numeric_type(),
                comment=f"Average suite RAGAS metric {metric_name}",
            )
    diagnostic_summary = summary.get("diagnostic_summary")
    if not isinstance(diagnostic_summary, dict):
        diagnostic_summary = {}
    diagnostic_counters = {
        "reason_codes": diagnostic_summary.get("reason_codes"),
        "primary_suspects": diagnostic_summary.get("primary_suspects"),
        "recommended_next_actions": diagnostic_summary.get("recommended_next_actions"),
    }
    for field_name, counter in diagnostic_counters.items():
        _score_trace(
            observation,
            name=f"eval.suite.diagnostic.{field_name}.top",
            value=_top_counter_score_value(counter),
            data_type=_categorical_type(),
            comment=f"Top suite diagnostic values for {field_name}",
        )
    expectation_failures = diagnostic_summary.get("diagnostic_expectation_failures")
    _score_trace(
        observation,
        name="eval.suite.diagnostic.expectation_fail_total",
        value=_counter_total(expectation_failures),
        data_type=_numeric_type(),
        comment="Total failed diagnostic expectation assertions across the suite",
    )


def emit_comparison_scores(
    observation: Any,
    *,
    comparison: dict[str, Any],
) -> None:
    """Attach suite comparison / drift summary to Langfuse."""
    if observation is None:
        return
    drift_summary = comparison.get("drift_summary")
    if not isinstance(drift_summary, dict):
        drift_summary = {}
    _score_trace(
        observation,
        name="eval.compare.changed_case_count",
        value=int(drift_summary.get("changed_case_count") or 0),
        data_type=_numeric_type(),
        comment="Changed case count in suite comparison",
    )
    for field_name in (
        "changed_finish_reason_case_ids",
        "changed_failure_layer_case_ids",
        "changed_hard_failure_case_ids",
        "changed_pending_judge_case_ids",
        "changed_executed_judge_case_ids",
        "changed_subjective_status_case_ids",
        "changed_subjective_score_case_ids",
        "changed_ragas_case_ids",
        "changed_reason_code_case_ids",
        "changed_primary_suspect_case_ids",
        "changed_outcome_chain_case_ids",
        "changed_recommended_next_action_case_ids",
        "changed_diagnostic_expectation_case_ids",
    ):
        value = drift_summary.get(field_name)
        items = value if isinstance(value, list) else []
        _score_trace(
            observation,
            name=f"eval.compare.{field_name}",
            value=_list_score_value(items),
            data_type=_categorical_type(),
            comment=f"Drift list for {field_name}",
        )
        _score_trace(
            observation,
            name=f"eval.compare.{field_name}.count",
            value=len(items),
            data_type=_numeric_type(),
            comment=f"Drift count for {field_name}",
        )
    current = comparison.get("current")
    baseline = comparison.get("baseline")
    if not isinstance(current, dict):
        current = {}
    if not isinstance(baseline, dict):
        baseline = {}
    for side_name, payload in (("current", current), ("baseline", baseline)):
        ragas_metric_averages = payload.get("ragas_metric_averages")
        if not isinstance(ragas_metric_averages, dict):
            continue
        for metric_name, value in ragas_metric_averages.items():
            if value is None:
                continue
            _score_trace(
                observation,
                name=f"eval.compare.{side_name}.ragas.{metric_name}",
                value=float(value),
                data_type=_numeric_type(),
                comment=f"{side_name} suite RAGAS average for {metric_name}",
            )


def _score_trace(
    observation: Any,
    *,
    name: str,
    value: Any,
    data_type: Any = None,
    comment: str | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "name": name,
        "value": value,
    }
    if data_type is not None:
        kwargs["data_type"] = data_type
    if comment:
        kwargs["comment"] = comment
    try:
        observation.score_trace(**kwargs)
    except Exception:  # pragma: no cover - defensive fallback
        return


def _categorical_type():
    return getattr(ScoreDataType, "CATEGORICAL", None)


def _boolean_type():
    return getattr(ScoreDataType, "BOOLEAN", None)


def _numeric_type():
    return getattr(ScoreDataType, "NUMERIC", None)


def _emit_diagnostic_score_group(
    observation: Any,
    *,
    prefix: str,
    name: str,
    entry: dict[str, Any],
) -> None:
    status = str(entry.get("status") or "unknown")
    comment = _entry_comment(entry)
    _score_trace(
        observation,
        name=f"{prefix}.{name}",
        value=status,
        data_type=_categorical_type(),
        comment=comment,
    )
    numeric_score = _status_to_numeric(status)
    if numeric_score is not None:
        _score_trace(
            observation,
            name=f"{prefix}.{name}.numeric",
            value=numeric_score,
            data_type=_numeric_type(),
            comment=comment,
        )


def _entry_comment(entry: dict[str, Any]) -> str | None:
    summary = str(entry.get("summary") or "").strip()
    evidence = entry.get("evidence")
    evidence_text = ""
    if isinstance(evidence, list):
        evidence_items = [str(item).strip() for item in evidence if str(item).strip()]
        if evidence_items:
            evidence_text = "evidence: " + "; ".join(evidence_items)
    parts = [item for item in (summary, evidence_text) if item]
    return " | ".join(parts) if parts else None


def _status_to_numeric(status: str) -> float | None:
    normalized = str(status or "").strip().lower()
    if normalized == "pass":
        return 1.0
    if normalized == "warn":
        return 0.5
    if normalized == "fail":
        return 0.0
    return None


def _list_score_value(value: Any) -> str:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(items) if items else "none"
    return "none"


def _build_setup_tool_selection_entry(
    *,
    tool_invocations: list[Any],
    tool_results: list[Any],
    turn_goal: dict[str, Any],
    working_plan: dict[str, Any],
    request_context: dict[str, Any],
    pending_obligation: dict[str, Any],
    completion_guard_reason: str,
    finish_reason: str,
) -> dict[str, Any]:
    tool_names = _normalized_runtime_tool_names(tool_invocations)
    success_count = _setup_tool_success_count(tool_results)
    failure_count = _setup_tool_failure_count(tool_results)
    expected_prefixes = _expected_setup_tool_prefixes(
        turn_goal=turn_goal,
        working_plan=working_plan,
        pending_obligation=pending_obligation,
    )
    question_mode = _setup_question_mode_expected(
        working_plan=working_plan,
        request_context=request_context,
        pending_obligation=pending_obligation,
        finish_reason=finish_reason,
    )
    blocking_open_question_count = int(request_context.get("blocking_open_question_count") or 0)
    last_proposal_status = str(request_context.get("last_proposal_status") or "").strip()
    cognitive_state_invalidated = bool(request_context.get("cognitive_state_invalidated"))
    commit_tool_selected = any(name.startswith("setup.proposal.commit") for name in tool_names)
    evidence = [
        _fmt("goal_type", turn_goal.get("goal_type")),
        _fmt("expected_tool_prefixes", expected_prefixes or ["none"]),
        _fmt("selected_tools", tool_names or ["none"]),
        _fmt("question_mode", question_mode),
        _fmt("success_count", success_count),
        _fmt("failure_count", failure_count),
        _fmt("blocking_open_question_count", blocking_open_question_count),
        _fmt("last_proposal_status", last_proposal_status or "none"),
        _fmt("cognitive_state_invalidated", cognitive_state_invalidated),
        _fmt("completion_guard_reason", completion_guard_reason or "none"),
    ]

    if not tool_names:
        if question_mode:
            return _status_entry(
                status="pass",
                summary="Runtime stayed in clarification mode instead of selecting a setup tool.",
                evidence=evidence,
            )
        if expected_prefixes:
            return _status_entry(
                status="fail",
                summary="Turn goal implied a tool action, but the model did not select any setup tool.",
                evidence=evidence,
            )
        if finish_reason in {"awaiting_user_input", "continue_discussion", "completed_text"}:
            return _status_entry(
                status="fail",
                summary="Turn produced no setup tool selection even though the runtime did not expose a strong clarification-only reason to skip tools.",
                evidence=evidence,
            )
        return _status_entry(
            status="warn",
            summary="No setup tool was selected, and the current turn does not expose a strong expected tool family.",
            evidence=evidence,
        )

    if commit_tool_selected and (
        blocking_open_question_count > 0
        or last_proposal_status == "rejected"
        or cognitive_state_invalidated
        or completion_guard_reason
        in {"truth_write_not_ready_for_review", "repair_obligation_unresolved"}
    ):
        return _status_entry(
            status="fail",
            summary="Commit tool was selected even though setup context still required clarification, fresh cognition, or readiness repair.",
            evidence=evidence,
        )

    matched = [
        name
        for name in tool_names
        if any(name.startswith(prefix) for prefix in expected_prefixes)
    ]
    if matched:
        return _status_entry(
            status="pass",
            summary="Selected setup tool family matches the current turn goal or working plan.",
            evidence=evidence + [_fmt("matched_tools", matched)],
        )
    if not expected_prefixes and success_count > 0:
        return _status_entry(
            status="pass",
            summary="Setup tool selection produced usable progress even though the runtime plan did not expose a narrow expected tool family.",
            evidence=evidence,
        )
    if question_mode:
        return _status_entry(
            status="warn",
            summary="A setup tool was selected even though the runtime appears to be in clarification mode.",
            evidence=evidence,
        )
    if failure_count > 0 and success_count == 0:
        return _status_entry(
            status="warn",
            summary="A plausible setup tool family was selected, but only failed tool results were observed.",
            evidence=evidence,
        )
    if expected_prefixes:
        return _status_entry(
            status="fail",
            summary="Selected setup tool family does not match the expected tool family for this turn.",
            evidence=evidence,
        )
    return _status_entry(
        status="warn",
        summary="A setup tool was selected, but the runtime plan does not provide a strong expectation for which family should have been used.",
        evidence=evidence,
    )


def _build_setup_tool_result_value_entry(
    *,
    tool_invocations: list[Any],
    tool_results: list[Any],
    finish_reason: str,
    assistant_text: str,
    request_context: dict[str, Any],
    pending_obligation: dict[str, Any],
    completion_guard_reason: str,
    repair_route: str,
) -> dict[str, Any]:
    blocking_open_question_count = int(request_context.get("blocking_open_question_count") or 0)
    obligation_type = str(pending_obligation.get("obligation_type") or "")
    if not tool_invocations:
        if finish_reason == "awaiting_user_input" and (
            blocking_open_question_count > 0
            or obligation_type == "ask_user_for_missing_info"
        ):
            return _status_entry(
                status="not_applicable",
                summary="Turn stayed in clarification mode, so tool-result value was not expected yet.",
                evidence=[
                    _fmt("tool_invocation_count", 0),
                    _fmt("blocking_open_question_count", blocking_open_question_count),
                    _fmt("pending_obligation", obligation_type or "none"),
                ],
            )
        return _status_entry(
            status="fail",
            summary="Turn produced no setup tool result value and did not show a clear clarification-only reason for skipping tools.",
            evidence=[
                _fmt("tool_invocation_count", 0),
                _fmt("blocking_open_question_count", blocking_open_question_count),
                _fmt("pending_obligation", obligation_type or "none"),
                _fmt("finish_reason", finish_reason or "unknown"),
            ],
        )

    success_count = _setup_tool_success_count(tool_results)
    failure_count = _setup_tool_failure_count(tool_results)
    structured_payload_count = _setup_structured_tool_payload_count(tool_results)
    final_user_visible_progress = bool(assistant_text.strip()) and finish_reason in {
        "awaiting_user_input",
        "completed_text",
        "continue_discussion",
    }
    unresolved_repair = completion_guard_reason == "repair_obligation_unresolved"
    evidence = [
        _fmt("success_count", success_count),
        _fmt("failure_count", failure_count),
        _fmt("structured_payload_count", structured_payload_count),
        _fmt("finish_reason", finish_reason or "unknown"),
        _fmt("pending_obligation", obligation_type or "none"),
        _fmt("repair_route", repair_route or "none"),
        _fmt("assistant_text_chars", len(assistant_text)),
        _fmt("blocking_open_question_count", blocking_open_question_count),
    ]

    if success_count > 0:
        if (
            structured_payload_count > 0
            or repair_route in {"continue_discussion", "completed"}
        ) and not unresolved_repair:
            return _status_entry(
                status="pass",
                summary="At least one tool result produced usable state or clearly helped the turn progress.",
                evidence=evidence,
            )
        return _status_entry(
            status="warn",
            summary="Tool execution succeeded, but the turn exposes only a weak signal that the result materially advanced state or output quality.",
            evidence=evidence,
        )

    if failure_count > 0 and (
        final_user_visible_progress
        or repair_route in {"ask_user", "continue_discussion", "auto_repair", "block_commit"}
    ) and obligation_type in {
        "ask_user_for_missing_info",
        "continue_after_tool_failure",
        "repair_tool_call",
    }:
        return _status_entry(
            status="warn",
            summary="Tool results were not successful, but they still surfaced useful failure information that the agent converted into a follow-up or clarification.",
            evidence=evidence,
        )

    return _status_entry(
        status="fail",
        summary="Tool execution consumed budget without producing a successful result or a clearly valuable recovery signal.",
        evidence=evidence,
    )


def _build_setup_loop_health_entry(
    *,
    round_no: int,
    tool_invocations: list[Any],
    tool_results: list[Any],
    finish_reason: str,
    request_context: dict[str, Any],
    pending_obligation: dict[str, Any],
    completion_guard_reason: str,
    assistant_text: str,
) -> dict[str, Any]:
    success_count = _setup_tool_success_count(tool_results)
    failure_count = _setup_tool_failure_count(tool_results)
    structured_payload_count = _setup_structured_tool_payload_count(tool_results)
    obligation_type = str(pending_obligation.get("obligation_type") or "")
    blocking_open_question_count = int(request_context.get("blocking_open_question_count") or 0)
    cognitive_state_invalidated = bool(request_context.get("cognitive_state_invalidated"))
    evidence = [
        _fmt("round_no", round_no),
        _fmt("tool_invocation_count", len(tool_invocations)),
        _fmt("successful_tool_count", success_count),
        _fmt("failed_tool_count", failure_count),
        _fmt("structured_payload_count", structured_payload_count),
        _fmt("finish_reason", finish_reason or "unknown"),
        _fmt("pending_obligation", obligation_type or "none"),
        _fmt("completion_guard_reason", completion_guard_reason or "none"),
        _fmt("blocking_open_question_count", blocking_open_question_count),
        _fmt("cognitive_state_invalidated", cognitive_state_invalidated),
    ]

    if round_no >= 4 and success_count == 0:
        return _status_entry(
            status="fail",
            summary="High round count without successful tool progress is a strong signal of a noop loop or repeated question pattern.",
            evidence=evidence + [_fmt("assistant_text_chars", len(assistant_text))],
        )

    if success_count > 0:
        return _status_entry(
            status="pass",
            summary="Turn materially advanced through successful tool progress instead of stalling on another user-facing follow-up.",
            evidence=evidence,
        )

    if finish_reason == "awaiting_user_input" and (
        blocking_open_question_count > 0
        or obligation_type == "ask_user_for_missing_info"
    ):
        return _status_entry(
            status="pass",
            summary="Another user-facing question was justified by explicit blocking questions or a declared ask-user obligation.",
            evidence=evidence,
        )

    if failure_count > 0 and (
        finish_reason in {"awaiting_user_input", "continue_discussion", "repair_obligation_unfulfilled"}
        or obligation_type in {"repair_tool_call", "continue_after_tool_failure"}
        or completion_guard_reason
    ):
        return _status_entry(
            status="warn",
            summary="Tool activity happened, but the turn still looks like an in-flight repair or failed-progress loop rather than a clean advance.",
            evidence=evidence + [_fmt("assistant_text_chars", len(assistant_text))],
        )

    if (
        finish_reason in {"awaiting_user_input", "continue_discussion"}
        and (
            completion_guard_reason
            or obligation_type in {
                "repair_tool_call",
                "continue_after_tool_failure",
            }
            or cognitive_state_invalidated
            or round_no >= 3
        )
    ):
        return _status_entry(
            status="warn",
            summary="Turn stayed in discussion mode without tool progress, but runtime exposed a concrete guard or repair reason instead of a silent loop.",
            evidence=evidence + [_fmt("assistant_text_chars", len(assistant_text))],
        )

    if finish_reason in {"awaiting_user_input", "continue_discussion", "completed_text"}:
        return _status_entry(
            status="fail",
            summary="Turn looks like a noop or repeated-question loop: no tool progress and no explicit blocking context justified another follow-up.",
            evidence=evidence + [_fmt("assistant_text_chars", len(assistant_text))],
        )

    return _status_entry(
        status="warn",
        summary="Loop risk could not be strongly classified, but the turn also did not show durable setup progress.",
        evidence=evidence + [_fmt("assistant_text_chars", len(assistant_text))],
    )


def _status_entry(
    *,
    status: str,
    summary: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": [item for item in evidence if item],
    }


def _fmt(key: str, value: Any) -> str:
    return f"{key}={value}"


def _normalized_runtime_tool_names(tool_invocations: list[Any]) -> list[str]:
    names: list[str] = []
    for item in tool_invocations:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("tool_name") or "").strip()
        if not raw_name:
            continue
        if raw_name.startswith("rp_setup__"):
            raw_name = raw_name[len("rp_setup__") :]
        names.append(raw_name)
    return names


def _expected_setup_tool_prefixes(
    *,
    turn_goal: dict[str, Any],
    working_plan: dict[str, Any],
    pending_obligation: dict[str, Any],
) -> list[str]:
    prefixes: set[str] = set()
    goal_type = str(turn_goal.get("goal_type") or "").strip()
    has_patch_targets = bool(_first_list(working_plan.get("patch_targets")))
    has_draft_write_targets = bool(_first_list(working_plan.get("draft_write_targets")))
    has_candidate_targets = bool(_first_list(working_plan.get("candidate_targets")))
    has_missing_information = bool(
        _first_list(working_plan.get("missing_information"))
        or _first_list(working_plan.get("question_targets"))
    )

    if goal_type in {"patch_draft", "fill_missing_step_fields", "brainstorm_and_clarify"} and has_patch_targets:
        prefixes.add("setup.patch.")
    if goal_type == "write_draft_truth" and has_draft_write_targets:
        prefixes.add("setup.truth.write")
    if goal_type == "refine_chunk_candidate" and has_candidate_targets:
        prefixes.add("setup.chunk.upsert")
    if goal_type in {"prepare_commit_intent"}:
        prefixes.add("setup.proposal.commit")
    if goal_type in {
        "reconcile_after_user_edit",
        "brainstorm_and_clarify",
        "clarify_user_intent",
        "fill_missing_step_fields",
    }:
        prefixes.add("setup.discussion.update_state")
    if goal_type == "recover_from_tool_failure" and has_missing_information:
        prefixes.add("setup.discussion.update_state")

    pending_tool_name = str(pending_obligation.get("tool_name") or "").strip()
    if pending_tool_name.startswith("rp_setup__"):
        pending_tool_name = pending_tool_name[len("rp_setup__") :]
    if pending_tool_name.startswith("setup."):
        prefixes.add(pending_tool_name)

    return sorted(prefixes)


def _setup_question_mode_expected(
    *,
    working_plan: dict[str, Any],
    request_context: dict[str, Any],
    pending_obligation: dict[str, Any],
    finish_reason: str,
) -> bool:
    blocking_open_question_count = int(
        request_context.get("blocking_open_question_count") or 0
    )
    return bool(
        _first_list(working_plan.get("question_targets"))
        or _first_list(working_plan.get("missing_information"))
        or pending_obligation.get("obligation_type") == "ask_user_for_missing_info"
        or (
            finish_reason == "awaiting_user_input"
            and blocking_open_question_count > 0
        )
    )


def _setup_tool_success_count(tool_results: list[Any]) -> int:
    return sum(
        1
        for item in tool_results
        if isinstance(item, dict) and bool(item.get("success"))
    )


def _setup_tool_failure_count(tool_results: list[Any]) -> int:
    return sum(
        1
        for item in tool_results
        if isinstance(item, dict) and not bool(item.get("success"))
    )


def _setup_structured_tool_payload_count(tool_results: list[Any]) -> int:
    count = 0
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        structured_payload = item.get("structured_payload")
        if not isinstance(structured_payload, dict):
            continue
        if isinstance(structured_payload.get("content_payload"), dict) or isinstance(
            structured_payload.get("result_payload"), dict
        ):
            count += 1
    return count


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return list(value)
    return []


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return dict(value)
    return {}


def _first_scalar(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _top_counter_score_value(counter: Any, *, limit: int = 3) -> str:
    if not isinstance(counter, dict):
        return "none"
    items: list[tuple[str, int]] = []
    for key, value in counter.items():
        name = str(key).strip()
        if not name:
            continue
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0
        items.append((name, count))
    if not items:
        return "none"
    return ",".join(
        name for name, _ in sorted(items, key=lambda item: (-item[1], item[0]))[:limit]
    )


def _counter_total(counter: Any) -> int:
    if not isinstance(counter, dict):
        return 0
    total = 0
    for value in counter.values():
        try:
            total += int(value or 0)
        except (TypeError, ValueError):
            continue
    return total


def _coerce_int(value: Any, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _resolve_retrieval_latency_ms(timings: dict[str, Any]) -> float | None:
    if not isinstance(timings, dict) or not timings:
        return None
    for preferred_key in ("broker_ms", "total_ms", "elapsed_ms"):
        value = timings.get(preferred_key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue

    numeric_values: list[float] = []
    for value in timings.values():
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numeric_values:
        return None
    return round(sum(numeric_values), 3)


def _warning_categories_from_warnings(warnings: list[str]) -> list[str]:
    categories: list[str] = []
    for item in warnings:
        category = str(item or "").split(":", 1)[0].strip()
        if category and category not in categories:
            categories.append(category)
    return categories
