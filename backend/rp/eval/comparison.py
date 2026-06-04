"""Helpers for suite comparison, repeat summaries, and threshold checks."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_suite_payload(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Eval suite path does not exist: {source_path}")

    if source_path.is_dir():
        summary_path = source_path / "suite-summary.json"
        if summary_path.exists():
            return _load_json(summary_path)
        reports_dir = source_path / "reports"
        if reports_dir.exists():
            return _suite_payload_from_reports_dir(reports_dir)
        replays_dir = source_path / "replays"
        if replays_dir.exists():
            return _suite_payload_from_replays_dir(replays_dir)
        return _suite_payload_from_replays_dir(source_path)

    payload = _load_json(source_path)
    if source_path.name == "suite-summary.json":
        return payload
    return {
        "suite_id": None,
        "case_count": 1,
        "run_count": 1,
        "pass_count": 0,
        "fail_count": 0,
        "output_dir": str(source_path.parent),
        "items": [
            {
                "case_id": str(payload.get("case_id") or source_path.stem),
                "run_id": str(payload.get("run_id") or source_path.stem),
                "scope": payload.get("scope"),
                "status": payload.get("status"),
                "report_path": str(source_path),
                "report": payload,
            }
        ],
    }


def summarize_suite(path_or_payload: str | Path | dict[str, Any]) -> dict[str, Any]:
    payload = (
        load_suite_payload(path_or_payload)
        if not isinstance(path_or_payload, dict)
        else path_or_payload
    )
    report_items = _collect_report_items(payload)
    suite_totals = _new_suite_totals()
    for item in report_items:
        _accumulate_suite_report_item(suite_totals, item)

    return _build_suite_summary(payload, report_items, suite_totals)


def compare_suite_outputs(
    current_path: str | Path | dict[str, Any],
    baseline_path: str | Path | dict[str, Any],
) -> dict[str, Any]:
    current_payload = (
        load_suite_payload(current_path)
        if not isinstance(current_path, dict)
        else current_path
    )
    baseline_payload = (
        load_suite_payload(baseline_path)
        if not isinstance(baseline_path, dict)
        else baseline_path
    )
    current_cases = _aggregate_cases(current_payload)
    baseline_cases = _aggregate_cases(baseline_payload)

    current_case_ids = set(current_cases)
    baseline_case_ids = set(baseline_cases)
    changed_cases: list[dict[str, Any]] = []
    unchanged_case_count = 0

    for case_id in sorted(current_case_ids & baseline_case_ids):
        current_signature = current_cases[case_id]
        baseline_signature = baseline_cases[case_id]
        if current_signature == baseline_signature:
            unchanged_case_count += 1
            continue
        changed_cases.append(
            {
                "case_id": case_id,
                "current": current_signature,
                "baseline": baseline_signature,
                "deltas": {
                    "run_count": current_signature["run_count"]
                    - baseline_signature["run_count"],
                    "assertion_fail_total": current_signature["assertion_fail_total"]
                    - baseline_signature["assertion_fail_total"],
                    "assertion_warn_total": current_signature["assertion_warn_total"]
                    - baseline_signature["assertion_warn_total"],
                    "hard_failure_total": current_signature["hard_failure_total"]
                    - baseline_signature["hard_failure_total"],
                    "pending_judge_hook_count": current_signature["pending_judge_hook_count"]
                    - baseline_signature["pending_judge_hook_count"],
                    "executed_judge_hook_count": current_signature["executed_judge_hook_count"]
                    - baseline_signature["executed_judge_hook_count"],
                    "subjective_average_score": _delta_float(
                        current_signature.get("subjective_average_score"),
                        baseline_signature.get("subjective_average_score"),
                    ),
                    "reason_code_deltas": _list_membership_delta(
                        current_signature.get("reason_codes"),
                        baseline_signature.get("reason_codes"),
                    ),
                    "primary_suspect_deltas": _list_membership_delta(
                        current_signature.get("primary_suspects"),
                        baseline_signature.get("primary_suspects"),
                    ),
                    "outcome_chain_deltas": _changed_map_entries(
                        current_signature.get("outcome_chain"),
                        baseline_signature.get("outcome_chain"),
                    ),
                    "recommended_next_action_deltas": _list_membership_delta(
                        current_signature.get("recommended_next_actions"),
                        baseline_signature.get("recommended_next_actions"),
                    ),
                    "diagnostic_expectation_failure_deltas": _list_membership_delta(
                        current_signature.get("diagnostic_expectation_failures"),
                        baseline_signature.get("diagnostic_expectation_failures"),
                    ),
                    "ragas_metric_deltas": _delta_metric_map(
                        current_signature.get("ragas_metric_averages"),
                        baseline_signature.get("ragas_metric_averages"),
                    ),
                },
            }
        )

    changed_finish_reason_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["finish_reasons"] != item["baseline"]["finish_reasons"]
    )
    changed_failure_layer_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["failure_layers"] != item["baseline"]["failure_layers"]
    )
    changed_hard_failure_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["hard_failures"] != item["baseline"]["hard_failures"]
    )
    changed_pending_judge_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["pending_judge_hook_count"]
        != item["baseline"]["pending_judge_hook_count"]
    )
    changed_executed_judge_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["executed_judge_hook_count"]
        != item["baseline"]["executed_judge_hook_count"]
    )
    changed_subjective_status_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["subjective_hook_statuses"]
        != item["baseline"]["subjective_hook_statuses"]
    )
    changed_subjective_score_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["subjective_rubric_scores"]
        != item["baseline"]["subjective_rubric_scores"]
        or item["current"]["subjective_average_score"]
        != item["baseline"]["subjective_average_score"]
    )
    changed_ragas_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["ragas_statuses"] != item["baseline"]["ragas_statuses"]
        or item["current"]["ragas_metric_averages"] != item["baseline"]["ragas_metric_averages"]
    )
    changed_reason_code_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["reason_codes"] != item["baseline"]["reason_codes"]
    )
    changed_primary_suspect_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["primary_suspects"] != item["baseline"]["primary_suspects"]
    )
    changed_outcome_chain_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["outcome_chain"] != item["baseline"]["outcome_chain"]
    )
    changed_recommended_next_action_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["recommended_next_actions"]
        != item["baseline"]["recommended_next_actions"]
    )
    changed_diagnostic_expectation_case_ids = sorted(
        item["case_id"]
        for item in changed_cases
        if item["current"]["diagnostic_expectation_failures"]
        != item["baseline"]["diagnostic_expectation_failures"]
    )

    return {
        "current": summarize_suite(current_payload),
        "baseline": summarize_suite(baseline_payload),
        "added_case_ids": sorted(current_case_ids - baseline_case_ids),
        "removed_case_ids": sorted(baseline_case_ids - current_case_ids),
        "changed_cases": changed_cases,
        "unchanged_case_count": unchanged_case_count,
        "drift_summary": {
            "changed_case_count": len(changed_cases),
            "changed_finish_reason_case_ids": changed_finish_reason_case_ids,
            "changed_failure_layer_case_ids": changed_failure_layer_case_ids,
            "changed_hard_failure_case_ids": changed_hard_failure_case_ids,
            "changed_pending_judge_case_ids": changed_pending_judge_case_ids,
            "changed_executed_judge_case_ids": changed_executed_judge_case_ids,
            "changed_subjective_status_case_ids": changed_subjective_status_case_ids,
            "changed_subjective_score_case_ids": changed_subjective_score_case_ids,
            "changed_ragas_case_ids": changed_ragas_case_ids,
            "changed_reason_code_case_ids": changed_reason_code_case_ids,
            "changed_primary_suspect_case_ids": changed_primary_suspect_case_ids,
            "changed_outcome_chain_case_ids": changed_outcome_chain_case_ids,
            "changed_recommended_next_action_case_ids": changed_recommended_next_action_case_ids,
            "changed_diagnostic_expectation_case_ids": changed_diagnostic_expectation_case_ids,
        },
    }


def evaluate_suite_thresholds(
    path_or_payload: str | Path | dict[str, Any],
    *,
    max_fail: int = 0,
    max_warn: int | None = None,
    allowed_soft_fail_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    payload = (
        load_suite_payload(path_or_payload)
        if not isinstance(path_or_payload, dict)
        else path_or_payload
    )
    allowed_soft_fail_case_ids = set(allowed_soft_fail_case_ids or set())
    report_items = _collect_report_items(payload)

    effective_fail_total = 0
    warn_total = 0
    failed_run_count = 0
    soft_failed_cases: set[str] = set()
    soft_failed_assertions = 0

    for item in report_items:
        case_id = item["case_id"]
        report = item["report"]
        counts = _assertion_summary(report)
        warn_total += int(counts["warn"])
        if str(report.get("status") or "") == "failed":
            failed_run_count += 1
        if case_id in allowed_soft_fail_case_ids:
            if int(counts["fail"]) > 0:
                soft_failed_cases.add(case_id)
                soft_failed_assertions += int(counts["fail"])
            continue
        effective_fail_total += int(counts["fail"])

    breaches: list[str] = []
    if effective_fail_total > max_fail:
        breaches.append(
            f"assertion_fail_total>{max_fail} (actual={effective_fail_total})"
        )
    if max_warn is not None and warn_total > max_warn:
        breaches.append(f"assertion_warn_total>{max_warn} (actual={warn_total})")

    return {
        "passed": not breaches,
        "max_fail": max_fail,
        "max_warn": max_warn,
        "effective_fail_total": effective_fail_total,
        "warn_total": warn_total,
        "failed_run_count": failed_run_count,
        "soft_failed_case_ids": sorted(soft_failed_cases),
        "soft_failed_assertions": soft_failed_assertions,
        "breaches": breaches,
    }


def _new_suite_totals() -> dict[str, Any]:
    return {
        "finish_reason_counts": defaultdict(int),
        "failure_layer_counts": defaultdict(int),
        "case_run_counts": defaultdict(int),
        "hard_failure_total": 0,
        "assertion_fail_total": 0,
        "assertion_warn_total": 0,
        "failed_run_count": 0,
        "pending_judge_hook_total": 0,
        "executed_judge_hook_total": 0,
        "judge_family_counts": defaultdict(int),
        "subjective_status_counts": defaultdict(int),
        "subjective_numeric_scores": [],
        "rubric_summaries": {},
        "primary_suspect_counts": defaultdict(int),
        "reason_code_counts": defaultdict(int),
        "recommended_next_action_counts": defaultdict(int),
        "diagnostic_expectation_failure_counts": defaultdict(int),
        "outcome_chain_status_counts": defaultdict(lambda: defaultdict(int)),
        "ragas_status_counts": defaultdict(int),
        "ragas_metric_values": defaultdict(list),
    }


def _accumulate_suite_report_item(
    suite_totals: dict[str, Any],
    item: dict[str, Any],
) -> None:
    report = item["report"]
    case_id = item["case_id"]
    counts = _assertion_summary(report)
    suite_totals["case_run_counts"][case_id] += 1
    suite_totals["assertion_fail_total"] += int(counts["fail"])
    suite_totals["assertion_warn_total"] += int(counts["warn"])
    suite_totals["hard_failure_total"] += len(report.get("hard_failures") or [])
    if str(report.get("status") or "") == "failed":
        suite_totals["failed_run_count"] += 1

    _accumulate_suite_finish_and_failure_counts(suite_totals, report)
    _accumulate_suite_subjective_summary(suite_totals, report)
    _accumulate_suite_diagnostics(suite_totals, report)
    _accumulate_suite_ragas_metrics(suite_totals, report)
    _accumulate_suite_subjective_hooks(suite_totals, report, case_id)


def _accumulate_suite_finish_and_failure_counts(
    suite_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    finish_reason = str(report.get("finish_reason") or "n/a")
    suite_totals["finish_reason_counts"][finish_reason] += 1
    failure_layer = report.get("failure_layer")
    if failure_layer:
        suite_totals["failure_layer_counts"][str(failure_layer)] += 1
    suite_totals["pending_judge_hook_total"] += len(
        report.get("pending_judge_hook_ids") or []
    )


def _accumulate_suite_subjective_summary(
    suite_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    subjective_hook_summary = report.get("subjective_hook_summary") or {}
    suite_totals["executed_judge_hook_total"] += int(
        subjective_hook_summary.get("executed", 0) or 0
    )
    for judge_family, count in dict(
        subjective_hook_summary.get("judge_family_counts") or {}
    ).items():
        suite_totals["judge_family_counts"][str(judge_family)] += int(count or 0)
    for status, count in dict(subjective_hook_summary.get("status_counts") or {}).items():
        suite_totals["subjective_status_counts"][str(status)] += int(count or 0)


def _accumulate_suite_diagnostics(
    suite_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    for suspect in _report_primary_suspects(report):
        suite_totals["primary_suspect_counts"][suspect] += 1
    for reason_code in _report_reason_codes(report):
        suite_totals["reason_code_counts"][str(reason_code)] += 1
    recommended_next_action = _report_recommended_next_action(report)
    if recommended_next_action:
        suite_totals["recommended_next_action_counts"][
            str(recommended_next_action)
        ] += 1
    outcome_chain = _report_outcome_chain(report)
    if isinstance(outcome_chain, dict):
        for stage, status in outcome_chain.items():
            suite_totals["outcome_chain_status_counts"][str(stage)][
                str(status or "unknown")
            ] += 1
    for score_name in _report_diagnostic_expectation_failures(report):
        suite_totals["diagnostic_expectation_failure_counts"][score_name] += 1


def _accumulate_suite_ragas_metrics(
    suite_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    ragas_status = _report_ragas_status(report)
    if ragas_status:
        suite_totals["ragas_status_counts"][str(ragas_status)] += 1
    for metric_name, numeric_value in _report_ragas_metric_values(report):
        suite_totals["ragas_metric_values"][metric_name].append(numeric_value)


def _accumulate_suite_subjective_hooks(
    suite_totals: dict[str, Any],
    report: dict[str, Any],
    case_id: str,
) -> None:
    for hook_result in report.get("subjective_hook_results") or []:
        if not isinstance(hook_result, dict):
            continue
        rubric_ref = str(hook_result.get("rubric_ref") or "unknown")
        rubric_entry = suite_totals["rubric_summaries"].setdefault(
            rubric_ref,
            _new_suite_rubric_entry(),
        )
        rubric_entry["total"] += 1
        status = str(hook_result.get("status") or "skip")
        if status == "skip":
            rubric_entry["pending"] += 1
        else:
            rubric_entry["executed"] += 1
        rubric_entry["status_counts"][status] += 1
        rubric_entry["case_ids"].add(case_id)
        rubric_entry["hook_ids"].add(str(hook_result.get("hook_id") or "unknown"))
        numeric_score = _numeric_score(hook_result.get("score"))
        if numeric_score is not None and status != "skip":
            suite_totals["subjective_numeric_scores"].append(numeric_score)
            rubric_entry["_numeric_scores"].append(numeric_score)


def _new_suite_rubric_entry() -> dict[str, Any]:
    return {
        "total": 0,
        "pending": 0,
        "executed": 0,
        "status_counts": defaultdict(int),
        "_numeric_scores": [],
        "case_ids": set(),
        "hook_ids": set(),
    }


def _build_suite_summary(
    payload: dict[str, Any],
    report_items: list[dict[str, Any]],
    suite_totals: dict[str, Any],
) -> dict[str, Any]:
    case_run_counts = suite_totals["case_run_counts"]
    return {
        "suite_id": payload.get("suite_id"),
        "case_count": len(case_run_counts),
        "run_count": len(report_items),
        "failed_run_count": suite_totals["failed_run_count"],
        "assertion_fail_total": suite_totals["assertion_fail_total"],
        "assertion_warn_total": suite_totals["assertion_warn_total"],
        "hard_failure_total": suite_totals["hard_failure_total"],
        "repeat_case_ids": sorted(
            case_id for case_id, run_count in case_run_counts.items() if run_count > 1
        ),
        "finish_reason_counts": dict(
            sorted(suite_totals["finish_reason_counts"].items())
        ),
        "failure_layer_counts": dict(
            sorted(suite_totals["failure_layer_counts"].items())
        ),
        "pending_judge_hook_total": suite_totals["pending_judge_hook_total"],
        "executed_judge_hook_total": suite_totals["executed_judge_hook_total"],
        "judge_family_counts": dict(
            sorted(suite_totals["judge_family_counts"].items())
        ),
        "subjective_status_counts": dict(
            sorted(suite_totals["subjective_status_counts"].items())
        ),
        "subjective_average_score": _average(
            suite_totals["subjective_numeric_scores"]
        ),
        "rubric_summaries": _finalize_suite_rubric_summaries(
            suite_totals["rubric_summaries"]
        ),
        "ragas_status_counts": dict(sorted(suite_totals["ragas_status_counts"].items())),
        "ragas_metric_averages": {
            metric_name: _average(values)
            for metric_name, values in sorted(suite_totals["ragas_metric_values"].items())
        },
        "diagnostic_summary": _build_suite_diagnostic_summary(suite_totals),
        "case_summaries": _aggregate_cases(payload),
    }


def _build_suite_diagnostic_summary(suite_totals: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_suspects": dict(sorted(suite_totals["primary_suspect_counts"].items())),
        "reason_codes": dict(sorted(suite_totals["reason_code_counts"].items())),
        "recommended_next_actions": dict(
            sorted(suite_totals["recommended_next_action_counts"].items())
        ),
        "diagnostic_expectation_failures": dict(
            sorted(suite_totals["diagnostic_expectation_failure_counts"].items())
        ),
        "outcome_chain": {
            stage: dict(sorted(statuses.items()))
            for stage, statuses in sorted(
                suite_totals["outcome_chain_status_counts"].items()
            )
        },
    }


def _aggregate_cases(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_case = _group_reports_by_case(payload)
    aggregated: dict[str, dict[str, Any]] = {}
    for case_id, reports in by_case.items():
        aggregated[case_id] = _build_case_summary(reports)
    return aggregated


def _group_reports_by_case(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _collect_report_items(payload):
        by_case[item["case_id"]].append(item["report"])
    return by_case


def _build_case_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    case_totals = _new_case_totals()
    for report in reports:
        _accumulate_case_report(case_totals, report)
    hard_failures = _case_hard_failures(reports)
    return {
        "run_count": len(reports),
        "statuses": _case_statuses(reports),
        "finish_reasons": _case_finish_reasons(reports),
        "failure_layers": _case_failure_layers(reports),
        "assertion_fail_total": _case_assertion_total(reports, "fail"),
        "assertion_warn_total": _case_assertion_total(reports, "warn"),
        "hard_failure_total": len(hard_failures),
        "hard_failures": hard_failures,
        "pending_judge_hook_count": _case_pending_judge_hook_count(reports),
        "executed_judge_hook_count": case_totals["executed_judge_hook_count"],
        "subjective_hook_statuses": {
            hook_id: sorted(statuses)
            for hook_id, statuses in sorted(
                case_totals["subjective_hook_statuses"].items()
            )
        },
        "subjective_hook_score_averages": {
            hook_id: _average(scores)
            for hook_id, scores in sorted(
                case_totals["subjective_hook_scores"].items()
            )
        },
        "subjective_rubric_scores": {
            rubric_ref: _average(scores)
            for rubric_ref, scores in sorted(
                case_totals["subjective_rubric_scores"].items()
            )
        },
        "subjective_average_score": _average(case_totals["all_subjective_scores"]),
        "primary_suspects": sorted(case_totals["primary_suspects"]),
        "reason_codes": sorted(case_totals["reason_codes"]),
        "recommended_next_actions": sorted(case_totals["recommended_next_actions"]),
        "outcome_chain": {
            stage: sorted(statuses)
            for stage, statuses in sorted(case_totals["outcome_chain_values"].items())
        },
        "diagnostic_expectation_failures": sorted(
            case_totals["diagnostic_expectation_failures"]
        ),
        "ragas_statuses": sorted(case_totals["ragas_statuses"]),
        "ragas_metric_averages": {
            metric_name: _average(values)
            for metric_name, values in sorted(case_totals["ragas_metric_values"].items())
        },
    }


def _new_case_totals() -> dict[str, Any]:
    return {
        "primary_suspects": set(),
        "reason_codes": set(),
        "recommended_next_actions": set(),
        "outcome_chain_values": defaultdict(set),
        "diagnostic_expectation_failures": set(),
        "subjective_hook_statuses": defaultdict(set),
        "subjective_hook_scores": defaultdict(list),
        "subjective_rubric_scores": defaultdict(list),
        "all_subjective_scores": [],
        "executed_judge_hook_count": 0,
        "ragas_statuses": set(),
        "ragas_metric_values": defaultdict(list),
    }


def _accumulate_case_report(
    case_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    subjective_summary = report.get("subjective_hook_summary") or {}
    case_totals["executed_judge_hook_count"] += int(
        subjective_summary.get("executed", 0) or 0
    )
    _accumulate_case_diagnostics(case_totals, report)
    _accumulate_case_ragas_metrics(case_totals, report)
    _accumulate_case_subjective_hooks(case_totals, report)


def _accumulate_case_diagnostics(
    case_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    case_totals["primary_suspects"].update(_report_primary_suspects(report))
    for reason_code in _report_reason_codes(report):
        case_totals["reason_codes"].add(str(reason_code))
    recommended_next_action = _report_recommended_next_action(report)
    if recommended_next_action:
        case_totals["recommended_next_actions"].add(str(recommended_next_action))
    outcome_chain = _report_outcome_chain(report)
    if isinstance(outcome_chain, dict):
        for stage, status in outcome_chain.items():
            case_totals["outcome_chain_values"][str(stage)].add(
                str(status or "unknown")
            )
    case_totals["diagnostic_expectation_failures"].update(
        _report_diagnostic_expectation_failures(report)
    )


def _accumulate_case_ragas_metrics(
    case_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    ragas_status = _report_ragas_status(report)
    if ragas_status:
        case_totals["ragas_statuses"].add(str(ragas_status))
    for metric_name, numeric_value in _report_ragas_metric_values(report):
        case_totals["ragas_metric_values"][metric_name].append(numeric_value)


def _accumulate_case_subjective_hooks(
    case_totals: dict[str, Any],
    report: dict[str, Any],
) -> None:
    for hook_result in report.get("subjective_hook_results") or []:
        if not isinstance(hook_result, dict):
            continue
        hook_id = str(hook_result.get("hook_id") or "unknown")
        status = str(hook_result.get("status") or "skip")
        case_totals["subjective_hook_statuses"][hook_id].add(status)
        numeric_score = _numeric_score(hook_result.get("score"))
        if numeric_score is None or status == "skip":
            continue
        case_totals["all_subjective_scores"].append(numeric_score)
        case_totals["subjective_hook_scores"][hook_id].append(numeric_score)
        case_totals["subjective_rubric_scores"][
            str(hook_result.get("rubric_ref") or "unknown")
        ].append(numeric_score)


def _case_statuses(reports: list[dict[str, Any]]) -> list[str]:
    return sorted({str(report.get("status") or "unknown") for report in reports})


def _case_finish_reasons(reports: list[dict[str, Any]]) -> list[str]:
    return sorted({str(report.get("finish_reason") or "n/a") for report in reports})


def _case_failure_layers(reports: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(report.get("failure_layer"))
            for report in reports
            if report.get("failure_layer")
        }
    )


def _case_hard_failures(reports: list[dict[str, Any]]) -> list[Any]:
    return sorted(
        {
            hard_failure
            for report in reports
            for hard_failure in (report.get("hard_failures") or [])
        }
    )


def _case_assertion_total(reports: list[dict[str, Any]], status: str) -> int:
    return sum(int(_assertion_summary(report)[status]) for report in reports)


def _case_pending_judge_hook_count(reports: list[dict[str, Any]]) -> int:
    return sum(len(report.get("pending_judge_hook_ids") or []) for report in reports)


def _report_diagnostics(report: dict[str, Any]) -> Any:
    return report.get("diagnostics") or {}


def _report_attribution(diagnostics: Any) -> Any:
    return diagnostics.get("attribution") if isinstance(diagnostics, dict) else {}


def _report_primary_suspects(report: dict[str, Any]) -> set[str]:
    diagnostics = _report_diagnostics(report)
    attribution = _report_attribution(diagnostics)
    primary_suspects: set[str] = set()
    top_level_suspects = report.get("primary_suspects")
    if isinstance(top_level_suspects, list):
        primary_suspects.update(str(suspect) for suspect in top_level_suspects)
    if isinstance(attribution, dict):
        primary_suspects.update(
            str(suspect) for suspect in attribution.get("primary_suspects") or []
        )
    return primary_suspects


def _report_reason_codes(report: dict[str, Any]) -> Any:
    diagnostics = _report_diagnostics(report)
    return report.get("reason_codes") or diagnostics.get("reason_codes") or []


def _report_recommended_next_action(report: dict[str, Any]) -> Any:
    diagnostics = _report_diagnostics(report)
    attribution = _report_attribution(diagnostics)
    return (
        report.get("recommended_next_action")
        or diagnostics.get("recommended_next_action")
        or (
            attribution.get("recommended_next_action")
            if isinstance(attribution, dict)
            else None
        )
    )


def _report_outcome_chain(report: dict[str, Any]) -> Any:
    diagnostics = _report_diagnostics(report)
    return report.get("outcome_chain") or diagnostics.get("outcome_chain") or {}


def _report_diagnostic_expectation_failures(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for expectation in report.get("diagnostic_expectation_results") or []:
        if not isinstance(expectation, dict):
            continue
        if str(expectation.get("status") or "") == "fail":
            failures.append(str(expectation.get("score_name") or "unknown"))
    return failures


def _report_ragas_status(report: dict[str, Any]) -> Any:
    ragas = report.get("ragas") or {}
    if isinstance(ragas, dict):
        return ragas.get("status")
    return None


def _report_ragas_metric_values(report: dict[str, Any]) -> list[tuple[str, float]]:
    metric_values: list[tuple[str, float]] = []
    ragas = report.get("ragas") or {}
    if isinstance(ragas, dict):
        metric_summary = ragas.get("metric_summary") or {}
        if isinstance(metric_summary, dict):
            for metric_name, value in metric_summary.items():
                numeric_value = _numeric_score(value)
                if numeric_value is None:
                    continue
                metric_values.append((str(metric_name), numeric_value))
    return metric_values


def _collect_report_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items") or []
    report_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        report = item.get("report")
        report_path = item.get("report_path")
        if not isinstance(report, dict) and report_path:
            report = _load_json(Path(report_path))
        if not isinstance(report, dict):
            continue
        case_id = str(item.get("case_id") or report.get("case_id") or "unknown")
        report_items.append({"case_id": case_id, "report": report})
    return report_items


def _suite_payload_from_reports_dir(reports_dir: Path) -> dict[str, Any]:
    if not reports_dir.exists():
        raise FileNotFoundError(
            f"Eval suite summary and reports directory are both missing: {reports_dir.parent}"
        )
    items = []
    for report_path in sorted(reports_dir.glob("*.json")):
        report = _load_json(report_path)
        items.append(
            {
                "case_id": str(report.get("case_id") or report_path.stem),
                "run_id": str(report.get("run_id") or report_path.stem),
                "scope": report.get("scope"),
                "status": report.get("status"),
                "report_path": str(report_path),
                "report": report,
            }
        )
    return {
        "suite_id": None,
        "case_count": len({item["case_id"] for item in items}),
        "run_count": len(items),
        "pass_count": 0,
        "fail_count": 0,
        "output_dir": str(reports_dir.parent),
        "items": items,
    }


def _suite_payload_from_replays_dir(replays_dir: Path) -> dict[str, Any]:
    if not replays_dir.exists():
        raise FileNotFoundError(
            f"Eval suite summary, reports directory, and replays directory are all missing: {replays_dir.parent}"
        )
    items = []
    for replay_path in sorted(replays_dir.glob("*.json")):
        replay_payload = _load_json(replay_path)
        case = replay_payload.get("case")
        run = replay_payload.get("run")
        report = replay_payload.get("report")
        if not isinstance(case, dict) or not isinstance(run, dict) or not isinstance(report, dict):
            continue
        items.append(
            {
                "case_id": str(case.get("case_id") or replay_path.stem),
                "run_id": str(run.get("run_id") or replay_path.stem),
                "scope": case.get("scope") or run.get("scope"),
                "status": run.get("status") or report.get("status"),
                "report_path": str(replay_path),
                "replay_path": str(replay_path),
                "report": report,
            }
        )
    return {
        "suite_id": None,
        "case_count": len({item["case_id"] for item in items}),
        "run_count": len(items),
        "pass_count": 0,
        "fail_count": 0,
        "output_dir": str(replays_dir.parent),
        "items": items,
    }


def _assertion_summary(report: dict[str, Any]) -> dict[str, int]:
    raw = report.get("assertion_summary") or {}
    return {
        "pass": int(raw.get("pass", 0) or 0),
        "fail": int(raw.get("fail", 0) or 0),
        "warn": int(raw.get("warn", 0) or 0),
        "skip": int(raw.get("skip", 0) or 0),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Eval JSON must deserialize to an object: {path}")
    return payload


def _numeric_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _delta_float(current: Any, baseline: Any) -> float | None:
    current_value = _numeric_score(current)
    baseline_value = _numeric_score(baseline)
    if current_value is None and baseline_value is None:
        return None
    return round((current_value or 0.0) - (baseline_value or 0.0), 4)


def _delta_metric_map(
    current: Any,
    baseline: Any,
) -> dict[str, float | None]:
    current_map = dict(current or {}) if isinstance(current, dict) else {}
    baseline_map = dict(baseline or {}) if isinstance(baseline, dict) else {}
    metric_names = sorted(set(current_map) | set(baseline_map))
    return {
        metric_name: _delta_float(current_map.get(metric_name), baseline_map.get(metric_name))
        for metric_name in metric_names
    }


def _list_membership_delta(current: Any, baseline: Any) -> dict[str, list[str]]:
    current_values = sorted({str(item) for item in (current or [])})
    baseline_values = sorted({str(item) for item in (baseline or [])})
    return {
        "added": sorted(set(current_values) - set(baseline_values)),
        "removed": sorted(set(baseline_values) - set(current_values)),
    }


def _changed_map_entries(current: Any, baseline: Any) -> dict[str, dict[str, list[str]]]:
    current_map = dict(current or {}) if isinstance(current, dict) else {}
    baseline_map = dict(baseline or {}) if isinstance(baseline, dict) else {}
    keys = sorted(set(current_map) | set(baseline_map))
    changed: dict[str, dict[str, list[str]]] = {}
    for key in keys:
        current_values = current_map.get(key) or []
        baseline_values = baseline_map.get(key) or []
        if current_values == baseline_values:
            continue
        changed[key] = _list_membership_delta(current_values, baseline_values)
    return changed


def _finalize_suite_rubric_summaries(
    rubric_summaries: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    finalized: dict[str, dict[str, Any]] = {}
    for rubric_ref, item in sorted(rubric_summaries.items()):
        finalized[rubric_ref] = {
            "total": int(item.get("total", 0) or 0),
            "pending": int(item.get("pending", 0) or 0),
            "executed": int(item.get("executed", 0) or 0),
            "status_counts": dict(sorted(dict(item.get("status_counts") or {}).items())),
            "average_numeric_score": _average(list(item.get("_numeric_scores") or [])),
            "case_count": len(item.get("case_ids") or set()),
            "hook_ids": sorted(str(hook_id) for hook_id in item.get("hook_ids") or set()),
        }
    return finalized
