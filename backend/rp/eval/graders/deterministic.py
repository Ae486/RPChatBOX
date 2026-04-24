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
