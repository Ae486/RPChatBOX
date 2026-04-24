"""Reporting helpers for eval runs."""

from __future__ import annotations

from typing import Any

from .diagnostics import build_diagnostics
from .models import EvalRunResult
from .ragas_reporting import extract_ragas_report


def build_report(result: EvalRunResult) -> dict:
    counts = {
        "pass": 0,
        "fail": 0,
        "warn": 0,
        "skip": 0,
    }
    hard_failures: list[str] = []
    subjective_hook_ids: list[str] = []
    judge_family_counts: dict[str, int] = {}
    rubric_refs: list[str] = []
    subjective_status_counts: dict[str, int] = {}
    subjective_hook_results: list[dict[str, Any]] = []
    subjective_hook_artifact_ids: list[str] = []
    subjective_artifact_id_by_hook: dict[str, str] = {}
    rubric_summaries: dict[str, dict[str, Any]] = {}
    subjective_numeric_scores: list[float] = []
    for artifact in result.artifacts:
        if artifact.kind != "subjective_hook_record":
            continue
        hook_id = str(artifact.payload.get("hook_id") or "").strip()
        if not hook_id:
            continue
        subjective_hook_artifact_ids.append(artifact.artifact_id)
        subjective_artifact_id_by_hook[hook_id] = artifact.artifact_id
    for score in result.scores:
        counts[score.status] = counts.get(score.status, 0) + 1
        if score.status == "fail" and score.severity == "error":
            hard_failures.append(score.name)
        if score.kind in {"llm", "human"}:
            hook_id = str(score.metadata.get("hook_id") or score.name)
            subjective_hook_ids.append(hook_id)
            judge_family = score.metadata.get("judge_family")
            if judge_family:
                key = str(judge_family)
                judge_family_counts[key] = judge_family_counts.get(key, 0) + 1
            rubric_ref = score.metadata.get("rubric_ref")
            if rubric_ref and str(rubric_ref) not in rubric_refs:
                rubric_refs.append(str(rubric_ref))
            subjective_status_counts[score.status] = (
                subjective_status_counts.get(score.status, 0) + 1
            )
            hook_result = _serialize_subjective_hook_result(
                score,
                artifact_id=subjective_artifact_id_by_hook.get(hook_id),
            )
            subjective_hook_results.append(hook_result)
            score_value = _numeric_score_value(score.value)
            if score_value is not None and score.status != "skip":
                subjective_numeric_scores.append(score_value)
            rubric_key = str(rubric_ref or "unknown")
            rubric_entry = rubric_summaries.setdefault(
                rubric_key,
                {
                    "total": 0,
                    "pending": 0,
                    "executed": 0,
                    "status_counts": {},
                    "_numeric_scores": [],
                    "hook_ids": [],
                },
            )
            rubric_entry["total"] += 1
            if score.status == "skip":
                rubric_entry["pending"] += 1
            else:
                rubric_entry["executed"] += 1
            rubric_entry["status_counts"][score.status] = (
                rubric_entry["status_counts"].get(score.status, 0) + 1
            )
            if hook_result["hook_id"] not in rubric_entry["hook_ids"]:
                rubric_entry["hook_ids"].append(hook_result["hook_id"])
            if score_value is not None and score.status != "skip":
                rubric_entry["_numeric_scores"].append(score_value)

    subjective_hook_results.sort(key=lambda item: item["hook_id"])
    subjective_hook_artifact_ids.sort()
    finalized_rubric_summaries = {
        rubric_ref: _finalize_rubric_summary(summary)
        for rubric_ref, summary in sorted(rubric_summaries.items())
    }

    structured_payload = result.runtime_result.get("structured_payload", {})
    if not isinstance(structured_payload, dict):
        structured_payload = {}
    cognitive_state_summary = structured_payload.get("cognitive_state_summary")
    if not isinstance(cognitive_state_summary, dict):
        cognitive_state_summary = {}
    last_failure = structured_payload.get("last_failure")
    if not isinstance(last_failure, dict):
        last_failure = {}
    completion_guard = structured_payload.get("completion_guard")
    if not isinstance(completion_guard, dict):
        completion_guard = {}
    pending_obligation = structured_payload.get("pending_obligation")
    if not isinstance(pending_obligation, dict):
        pending_obligation = {}
    warnings = result.runtime_result.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    repair_route = structured_payload.get("repair_route")
    if repair_route is None and (
        "commit_proposal_blocked" in warnings
        or pending_obligation.get("obligation_type") == "reassess_commit_readiness"
    ):
        repair_route = "block_commit"

    report = {
        "run_id": result.run.run_id,
        "case_id": result.case.case_id,
        "scope": result.case.scope,
        "status": result.run.status,
        "assertion_summary": counts,
        "hard_failures": hard_failures,
        "failure_layer": result.run.failure.layer if result.run.failure else None,
        "finish_reason": result.runtime_result.get("finish_reason"),
        "repair_route": repair_route,
        "completion_guard_reason": completion_guard.get("reason"),
        "last_failure_category": last_failure.get("failure_category"),
        "last_failure_message": last_failure.get("message"),
        "cognitive_state_invalidated": cognitive_state_summary.get("invalidated"),
        "cognitive_ready_for_review": cognitive_state_summary.get("ready_for_review"),
        "cognitive_invalidation_reasons": cognitive_state_summary.get("invalidation_reasons") or [],
        "remaining_open_issues": cognitive_state_summary.get("remaining_open_issues") or [],
        "commit_blocked": (
            repair_route == "block_commit"
            or "commit_proposal_blocked" in warnings
        ),
        "subjective_hook_summary": {
            "total": len(subjective_hook_ids),
            "pending": sum(1 for score in result.scores if score.kind in {"llm", "human"} and score.status == "skip"),
            "executed": sum(1 for score in result.scores if score.kind in {"llm", "human"} and score.status != "skip"),
            "judge_family_counts": dict(sorted(judge_family_counts.items())),
            "rubric_refs": rubric_refs,
            "status_counts": dict(sorted(subjective_status_counts.items())),
            "average_numeric_score": _average(subjective_numeric_scores),
            "rubric_summaries": finalized_rubric_summaries,
            "artifact_count": len(subjective_hook_artifact_ids),
        },
        "subjective_hook_results": subjective_hook_results,
        "subjective_hook_artifact_ids": subjective_hook_artifact_ids,
        "pending_judge_hook_ids": sorted(
            {
                str(score.metadata.get("hook_id") or score.name)
                for score in result.scores
                if score.kind in {"llm", "human"} and score.status == "skip"
            }
        ),
        "end_reason_summary": _derive_end_reason_summary(
            finish_reason=result.runtime_result.get("finish_reason"),
            repair_route=repair_route,
            completion_guard_reason=completion_guard.get("reason"),
            last_failure_category=last_failure.get("failure_category"),
        ),
        "ragas": extract_ragas_report(result.artifacts),
    }
    report["diagnostics"] = build_diagnostics(
        result=result,
        assertion_summary=counts,
        hard_failures=hard_failures,
        repair_route=repair_route,
        completion_guard_reason=completion_guard.get("reason"),
        last_failure_category=last_failure.get("failure_category"),
        cognitive_state_invalidated=cognitive_state_summary.get("invalidated"),
        remaining_open_issues=cognitive_state_summary.get("remaining_open_issues") or [],
        subjective_hook_results=subjective_hook_results,
    )
    diagnostics = report["diagnostics"] if isinstance(report.get("diagnostics"), dict) else {}
    activation_check = result.runtime_result.get("activation_check")
    if not isinstance(activation_check, dict):
        activation_check = {}
    report["reason_codes"] = list(diagnostics.get("reason_codes") or [])
    report["outcome_chain"] = dict(diagnostics.get("outcome_chain") or {})
    report["recommended_next_action"] = (
        diagnostics.get("recommended_next_action")
        or ((diagnostics.get("attribution") or {}).get("recommended_next_action"))
    )
    report["activation_check"] = activation_check
    report["activation_handoff_snapshot"] = (
        dict(activation_check.get("handoff") or {})
        if isinstance(activation_check.get("handoff"), dict)
        else None
    )
    return report


def render_text_summary(result: EvalRunResult) -> str:
    summary = result.report or build_report(result)
    return (
        f"[{summary['status']}] {summary['case_id']} "
        f"pass={summary['assertion_summary']['pass']} "
        f"fail={summary['assertion_summary']['fail']} "
        f"warn={summary['assertion_summary']['warn']} "
        f"finish_reason={summary.get('finish_reason') or 'n/a'} "
        f"repair_route={summary.get('repair_route') or 'n/a'} "
        f"end_reason={summary.get('end_reason_summary') or 'n/a'}"
    )


def render_suite_markdown(
    *,
    summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> str:
    lines = [
        "# RP Eval Suite Summary",
        "",
        f"- run_count: {summary.get('run_count', 0)}",
        f"- case_count: {summary.get('case_count', 0)}",
        f"- failed_run_count: {summary.get('failed_run_count', 0)}",
        f"- assertion_fail_total: {summary.get('assertion_fail_total', 0)}",
        f"- assertion_warn_total: {summary.get('assertion_warn_total', 0)}",
        f"- hard_failure_total: {summary.get('hard_failure_total', 0)}",
        f"- pending_judge_hook_total: {summary.get('pending_judge_hook_total', 0)}",
        f"- executed_judge_hook_total: {summary.get('executed_judge_hook_total', 0)}",
        f"- subjective_average_score: {summary.get('subjective_average_score')}",
        f"- threshold_passed: {thresholds.get('passed')}",
        "",
        "## Finish Reasons",
        "",
    ]

    finish_reason_counts = dict(summary.get("finish_reason_counts") or {})
    if finish_reason_counts:
        for finish_reason, count in finish_reason_counts.items():
            lines.append(f"- {finish_reason}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Failure Layers", ""])
    failure_layer_counts = dict(summary.get("failure_layer_counts") or {})
    if failure_layer_counts:
        for layer, count in failure_layer_counts.items():
            lines.append(f"- {layer}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Judge Hooks", ""])
    judge_family_counts = dict(summary.get("judge_family_counts") or {})
    if judge_family_counts:
        for judge_family, count in judge_family_counts.items():
            lines.append(f"- {judge_family}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Judge Status", ""])
    subjective_status_counts = dict(summary.get("subjective_status_counts") or {})
    if subjective_status_counts:
        for status, count in subjective_status_counts.items():
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Judge Rubrics", ""])
    rubric_summaries = dict(summary.get("rubric_summaries") or {})
    if rubric_summaries:
        for rubric_ref, item in rubric_summaries.items():
            lines.append(
                "- "
                f"{rubric_ref}: total={item.get('total', 0)} "
                f"executed={item.get('executed', 0)} "
                f"pending={item.get('pending', 0)} "
                f"avg_score={item.get('average_numeric_score')} "
                f"cases={item.get('case_count', 0)}"
            )
    else:
        lines.append("- none")

    diagnostics = dict(summary.get("diagnostic_summary") or {})
    lines.extend(["", "## Diagnostics", ""])
    primary_suspects = list(diagnostics.get("primary_suspects") or [])
    if primary_suspects:
        lines.append(f"- primary_suspects: {', '.join(primary_suspects)}")
    else:
        lines.append("- primary_suspects: none")

    ragas_status_counts = dict(summary.get("ragas_status_counts") or {})
    lines.extend(["", "## RAGAS", ""])
    if ragas_status_counts:
        for status, count in ragas_status_counts.items():
            lines.append(f"- status {status}: {count}")
    else:
        lines.append("- status: none")
    ragas_metric_averages = dict(summary.get("ragas_metric_averages") or {})
    if ragas_metric_averages:
        for metric_name, value in ragas_metric_averages.items():
            lines.append(f"- metric {metric_name}: {value}")
    else:
        lines.append("- metric: none")

    repeat_case_ids = list(summary.get("repeat_case_ids") or [])
    lines.extend(["", "## Repeat Cases", ""])
    if repeat_case_ids:
        for case_id in repeat_case_ids:
            lines.append(f"- {case_id}")
    else:
        lines.append("- none")

    breaches = list(thresholds.get("breaches") or [])
    lines.extend(["", "## Thresholds", ""])
    if breaches:
        for breach in breaches:
            lines.append(f"- breach: {breach}")
    else:
        lines.append("- no threshold breaches")

    lines.extend(["", "## Top Cases", ""])
    case_summaries = dict(summary.get("case_summaries") or {})
    sorted_cases = sorted(
        case_summaries.items(),
        key=lambda item: (
            -int(item[1].get("assertion_fail_total", 0)),
            -int(item[1].get("hard_failure_total", 0)),
            item[0],
        ),
    )
    if sorted_cases:
        for case_id, item in sorted_cases[:10]:
            lines.append(
                "- "
                f"{case_id}: runs={item.get('run_count', 0)} "
                f"fails={item.get('assertion_fail_total', 0)} "
                f"warns={item.get('assertion_warn_total', 0)} "
                f"pending_judge_hooks={item.get('pending_judge_hook_count', 0)} "
                f"finish_reasons={', '.join(item.get('finish_reasons') or ['n/a'])}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def render_comparison_markdown(*, comparison: dict[str, Any]) -> str:
    drift = dict(comparison.get("drift_summary") or {})
    lines = [
        "# RP Eval Comparison",
        "",
        f"- added_case_count: {len(comparison.get('added_case_ids') or [])}",
        f"- removed_case_count: {len(comparison.get('removed_case_ids') or [])}",
        f"- changed_case_count: {drift.get('changed_case_count', 0)}",
        "",
        "## Added Cases",
        "",
    ]

    added_case_ids = list(comparison.get("added_case_ids") or [])
    if added_case_ids:
        for case_id in added_case_ids:
            lines.append(f"- {case_id}")
    else:
        lines.append("- none")

    lines.extend(["", "## Removed Cases", ""])
    removed_case_ids = list(comparison.get("removed_case_ids") or [])
    if removed_case_ids:
        for case_id in removed_case_ids:
            lines.append(f"- {case_id}")
    else:
        lines.append("- none")

    lines.extend(["", "## Drift Summary", ""])
    for label, key in (
        ("finish_reason_drifts", "changed_finish_reason_case_ids"),
        ("failure_layer_drifts", "changed_failure_layer_case_ids"),
        ("hard_failure_drifts", "changed_hard_failure_case_ids"),
        ("pending_judge_drifts", "changed_pending_judge_case_ids"),
        ("executed_judge_drifts", "changed_executed_judge_case_ids"),
        ("subjective_status_drifts", "changed_subjective_status_case_ids"),
        ("subjective_score_drifts", "changed_subjective_score_case_ids"),
        ("ragas_drifts", "changed_ragas_case_ids"),
    ):
        values = list(drift.get(key) or [])
        if values:
            lines.append(f"- {label}: {', '.join(values)}")
        else:
            lines.append(f"- {label}: none")

    lines.extend(["", "## Judge Summary", ""])
    current = dict(comparison.get("current") or {})
    baseline = dict(comparison.get("baseline") or {})
    lines.append(
        "- "
        f"executed_hooks current={current.get('executed_judge_hook_total', 0)} "
        f"baseline={baseline.get('executed_judge_hook_total', 0)}"
    )
    lines.append(
        "- "
        f"avg_score current={current.get('subjective_average_score')} "
        f"baseline={baseline.get('subjective_average_score')}"
    )
    current_ragas = dict(current.get("ragas_metric_averages") or {})
    baseline_ragas = dict(baseline.get("ragas_metric_averages") or {})
    if current_ragas or baseline_ragas:
        lines.append(
            "- "
            f"ragas_metrics current={current_ragas or {}} "
            f"baseline={baseline_ragas or {}}"
        )

    lines.extend(["", "## Changed Cases", ""])
    changed_cases = list(comparison.get("changed_cases") or [])
    if changed_cases:
        for item in changed_cases[:20]:
            deltas = dict(item.get("deltas") or {})
            ragas_metric_deltas = dict(deltas.get("ragas_metric_deltas") or {})
            lines.append(
                "- "
                f"{item.get('case_id')}: "
                f"run_delta={deltas.get('run_count', 0)} "
                f"fail_delta={deltas.get('assertion_fail_total', 0)} "
                f"warn_delta={deltas.get('assertion_warn_total', 0)} "
                f"hard_failure_delta={deltas.get('hard_failure_total', 0)} "
                f"pending_judge_delta={deltas.get('pending_judge_hook_count', 0)} "
                f"executed_judge_delta={deltas.get('executed_judge_hook_count', 0)} "
                f"subjective_score_delta={deltas.get('subjective_average_score')} "
                f"ragas_metric_deltas={ragas_metric_deltas or {}}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def _derive_end_reason_summary(
    *,
    finish_reason,
    repair_route,
    completion_guard_reason,
    last_failure_category,
) -> str | None:
    if completion_guard_reason:
        return str(completion_guard_reason)
    if repair_route:
        return f"repair_route:{repair_route}"
    if last_failure_category:
        return f"last_failure:{last_failure_category}"
    if finish_reason:
        return str(finish_reason)
    return None


def _serialize_subjective_hook_result(score, *, artifact_id: str | None = None) -> dict[str, Any]:
    return {
        "hook_id": str(score.metadata.get("hook_id") or score.name),
        "artifact_id": artifact_id,
        "judge_family": score.metadata.get("judge_family"),
        "rubric_ref": score.metadata.get("rubric_ref"),
        "rubric_title": score.metadata.get("rubric_title"),
        "status": score.status,
        "score": _numeric_score_value(score.value),
        "label": score.label,
        "explanation": score.explanation,
        "judge_model_id": score.metadata.get("judge_model_id"),
        "judge_provider_id": score.metadata.get("judge_provider_id"),
        "judge_prompt_version": score.metadata.get("judge_prompt_version"),
        "judge_response_schema_version": score.metadata.get("judge_response_schema_version"),
        "judge_skip_reason": score.metadata.get("judge_skip_reason"),
        "judge_status_source": score.metadata.get("judge_status_source"),
        "judge_score_source": score.metadata.get("judge_score_source"),
        "judge_score_band": score.metadata.get("judge_score_band"),
        "judge_score_band_conflict": bool(score.metadata.get("judge_score_band_conflict")),
        "judge_strengths": list(score.metadata.get("judge_strengths") or []),
        "judge_issues": list(score.metadata.get("judge_issues") or []),
        "target_available": bool(score.metadata.get("target_available")),
        "resolved_source": score.metadata.get("resolved_source"),
        "resolved_path": score.metadata.get("resolved_path"),
    }


def _numeric_score_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _finalize_rubric_summary(summary: dict[str, Any]) -> dict[str, Any]:
    numeric_scores = list(summary.get("_numeric_scores") or [])
    hook_ids = sorted(str(hook_id) for hook_id in summary.get("hook_ids") or [])
    total = int(summary.get("total", 0) or 0)
    return {
        "total": total,
        "pending": int(summary.get("pending", 0) or 0),
        "executed": int(summary.get("executed", 0) or 0),
        "status_counts": dict(sorted(dict(summary.get("status_counts") or {}).items())),
        "average_numeric_score": _average(numeric_scores),
        "hook_ids": hook_ids,
        "case_count": 1 if total > 0 else 0,
    }
