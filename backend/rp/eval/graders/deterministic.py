"""Generic deterministic assertion engine for eval cases."""

from __future__ import annotations

import re
from typing import Any

from ..models import EvalAssertionSpec, EvalCase, EvalScore


_TOKEN_RE = re.compile(r"([^\[\]]+)|\[(\-?\d+)\]")


def evaluate_deterministic_scores(
    *,
    case: EvalCase,
    run_id: str,
    root_span_id: str | None,
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
) -> list[EvalScore]:
    return [
        _evaluate_assertion(
            run_id=run_id,
            span_id=root_span_id,
            assertion=assertion,
            source_payload=_select_source_payload(
                assertion.source,
                runtime_result=runtime_result,
                workspace_before=workspace_before,
                workspace_after=workspace_after,
                graph_debug=graph_debug,
                runtime_events=runtime_events,
            ),
        )
        for assertion in case.expected.deterministic_assertions
    ]


def evaluate_diagnostic_expectation_scores(
    *,
    case: EvalCase,
    run_id: str,
    root_span_id: str | None,
    report: dict[str, Any],
) -> list[EvalScore]:
    diagnostics = report.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    attribution = diagnostics.get("attribution")
    if not isinstance(attribution, dict):
        attribution = {}

    scores: list[EvalScore] = []
    if case.expected.expected_reason_codes:
        scores.append(
            _evaluate_expected_list_subset(
                run_id=run_id,
                span_id=root_span_id,
                name="diagnostic.reason_code_presence",
                expected=case.expected.expected_reason_codes,
                actual=diagnostics.get("reason_codes") or report.get("reason_codes") or [],
                source="diagnostics.reason_codes",
            )
        )
    if case.expected.expected_primary_suspects:
        scores.append(
            _evaluate_expected_list_subset(
                run_id=run_id,
                span_id=root_span_id,
                name="diagnostic.attribution_primary_suspect_alignment",
                expected=case.expected.expected_primary_suspects,
                actual=attribution.get("primary_suspects") or [],
                source="diagnostics.attribution.primary_suspects",
            )
        )
    if case.expected.expected_outcome_chain:
        scores.append(
            _evaluate_expected_mapping_entries(
                run_id=run_id,
                span_id=root_span_id,
                name="diagnostic.outcome_chain_alignment",
                expected=case.expected.expected_outcome_chain,
                actual=diagnostics.get("outcome_chain") or report.get("outcome_chain") or {},
                source="diagnostics.outcome_chain",
            )
        )
    if case.expected.expected_recommended_next_action is not None:
        scores.append(
            _evaluate_expected_value(
                run_id=run_id,
                span_id=root_span_id,
                name="diagnostic.recommended_next_action_alignment",
                expected=case.expected.expected_recommended_next_action,
                actual=diagnostics.get("recommended_next_action")
                or attribution.get("recommended_next_action")
                or report.get("recommended_next_action"),
                source="diagnostics.recommended_next_action",
            )
        )
    return scores


def _evaluate_assertion(
    *,
    run_id: str,
    span_id: str | None,
    assertion: EvalAssertionSpec,
    source_payload: Any,
) -> EvalScore:
    value, exists = _resolve_path(source_payload, assertion.path)
    passed, explanation = _apply_assertion(assertion, value=value, exists=exists)
    status = "pass" if passed else ("warn" if assertion.severity == "warn" else "fail")
    label = "pass" if passed else "fail"
    return EvalScore(
        score_id=f"{run_id}:score:{assertion.assertion_id}",
        run_id=run_id,
        span_id=span_id,
        name=assertion.assertion_id,
        kind="code",
        status=status,
        value_type="boolean",
        value=passed,
        label=label,
        explanation=explanation,
        severity=assertion.severity,
        metadata={
            "source": assertion.source,
            "path": assertion.path,
            "expected": assertion.expected,
            "actual": value,
        },
    )


def _evaluate_expected_list_subset(
    *,
    run_id: str,
    span_id: str | None,
    name: str,
    expected: list[str],
    actual: Any,
    source: str,
) -> EvalScore:
    expected_values = _normalize_string_list(expected)
    actual_values = _normalize_string_list(actual)
    missing = [item for item in expected_values if item not in actual_values]
    passed = not missing
    explanation = (
        f"expected_present={expected_values!r} actual={actual_values!r} "
        f"missing={missing!r}"
    )
    return _diagnostic_score(
        run_id=run_id,
        span_id=span_id,
        name=name,
        passed=passed,
        explanation=explanation,
        metadata={
            "source": source,
            "expected": expected_values,
            "actual": actual_values,
            "missing": missing,
        },
    )


def _evaluate_expected_mapping_entries(
    *,
    run_id: str,
    span_id: str | None,
    name: str,
    expected: dict[str, str],
    actual: Any,
    source: str,
) -> EvalScore:
    expected_values = {str(key): str(value) for key, value in expected.items()}
    actual_values = (
        {str(key): str(value) for key, value in actual.items()}
        if isinstance(actual, dict)
        else {}
    )
    mismatches = {
        key: {"expected": expected_value, "actual": actual_values.get(key)}
        for key, expected_value in expected_values.items()
        if actual_values.get(key) != expected_value
    }
    passed = not mismatches
    explanation = (
        f"expected_entries={expected_values!r} actual={actual_values!r} "
        f"mismatches={mismatches!r}"
    )
    return _diagnostic_score(
        run_id=run_id,
        span_id=span_id,
        name=name,
        passed=passed,
        explanation=explanation,
        metadata={
            "source": source,
            "expected": expected_values,
            "actual": actual_values,
            "mismatches": mismatches,
        },
    )


def _evaluate_expected_value(
    *,
    run_id: str,
    span_id: str | None,
    name: str,
    expected: str,
    actual: Any,
    source: str,
) -> EvalScore:
    actual_value = None if actual is None else str(actual)
    expected_value = str(expected)
    passed = actual_value == expected_value
    return _diagnostic_score(
        run_id=run_id,
        span_id=span_id,
        name=name,
        passed=passed,
        explanation=f"expected={expected_value!r} actual={actual_value!r}",
        metadata={
            "source": source,
            "expected": expected_value,
            "actual": actual_value,
        },
    )


def _diagnostic_score(
    *,
    run_id: str,
    span_id: str | None,
    name: str,
    passed: bool,
    explanation: str,
    metadata: dict[str, Any],
) -> EvalScore:
    return EvalScore(
        score_id=f"{run_id}:score:{name}",
        run_id=run_id,
        span_id=span_id,
        name=name,
        kind="code",
        status="pass" if passed else "fail",
        value_type="boolean",
        value=passed,
        label="pass" if passed else "fail",
        explanation=explanation,
        severity="error",
        metadata=metadata,
    )


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _apply_assertion(
    assertion: EvalAssertionSpec,
    *,
    value: Any,
    exists: bool,
) -> tuple[bool, str]:
    if assertion.type == "equals":
        passed = value == assertion.expected
        return passed, f"expected={assertion.expected!r} actual={value!r}"
    if assertion.type == "contains":
        passed = _contains(value, assertion.expected)
        return passed, f"contains expected={assertion.expected!r} actual={value!r}"
    if assertion.type == "not_contains":
        passed = not _contains(value, assertion.expected)
        return passed, f"not_contains expected={assertion.expected!r} actual={value!r}"
    if assertion.type == "exists":
        want_exists = bool(assertion.expected)
        passed = exists if want_exists else not exists
        return passed, f"exists={exists!r} expected={want_exists!r}"
    if assertion.type == "count_gte":
        try:
            count = len(value)
        except TypeError:
            count = 0
        passed = count >= int(assertion.expected)
        return passed, f"count={count!r} expected_gte={assertion.expected!r}"
    return False, f"unsupported assertion type={assertion.type!r}"


def _contains(value: Any, expected: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return str(expected) in value
    if isinstance(value, list):
        return expected in value
    if isinstance(value, dict):
        return expected in value or expected in value.values()
    return False


def _select_source_payload(
    source: str,
    *,
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
) -> Any:
    mapping = {
        "runtime_result": runtime_result,
        "runtime_events": runtime_events,
        "workspace_truth": workspace_after or {},
        "workspace_before": workspace_before or {},
        "graph_debug": graph_debug or {},
        "activation_result": runtime_result,
        "retrieval_result": runtime_result,
        "retrieval_truth": workspace_after or {},
        "session_truth": workspace_after or {},
    }
    return mapping.get(source, {})


def _resolve_path(source_payload: Any, path: str) -> tuple[Any, bool]:
    current = source_payload
    for segment in path.split("."):
        if segment == "":
            continue
        for name, index in _iter_segment_tokens(segment):
            if name is not None:
                if isinstance(current, dict) and name in current:
                    current = current[name]
                else:
                    return None, False
            elif index is not None:
                if not isinstance(current, list):
                    return None, False
                try:
                    current = current[index]
                except IndexError:
                    return None, False
    return current, True


def _iter_segment_tokens(segment: str):
    for name, index in _TOKEN_RE.findall(segment):
        if name:
            yield name, None
        else:
            yield None, int(index)
