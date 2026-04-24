"""Subjective hook materialization and optional LLM judge execution."""

from __future__ import annotations

import json
import re
from typing import Any

from models.chat import ChatMessage
from pydantic import BaseModel, ConfigDict, Field
from rp.services.story_llm_gateway import StoryLlmGateway

from ..models import EvalArtifact, EvalCase, EvalScore, EvalSubjectiveHook
from .judge_registry import JudgeRubricSpec, get_judge_rubric

_TOKEN_RE = re.compile(r"([^\[\]]+)|\[(\-?\d+)\]")
_SUPPORTED_SOURCES = {
    "runtime_result",
    "runtime_events",
    "workspace_truth",
    "workspace_before",
    "graph_debug",
    "activation_result",
    "retrieval_result",
    "retrieval_truth",
    "session_truth",
}
_TARGET_ALIASES = {
    "assistant_text": ("runtime_result", "assistant_text"),
    "query_text": ("retrieval_result", "query_input.text_query"),
    "query_input": ("retrieval_result", "query_input"),
    "retrieval_hits": ("retrieval_result", "query_result.hits"),
    "activation_handoff": ("activation_result", "activation_check.handoff"),
}


class _JudgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="skip")
    label: str | None = None
    score: float | int | None = None
    explanation: str | None = None
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


def materialize_subjective_hook_scores(
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
        _materialize_hook_score(
            hook=hook,
            run_id=run_id,
            span_id=root_span_id,
            runtime_result=runtime_result,
            workspace_before=workspace_before,
            workspace_after=workspace_after,
            graph_debug=graph_debug,
            runtime_events=runtime_events,
        )
        for hook in case.expected.subjective_hooks
    ]


async def evaluate_subjective_hook_scores(
    *,
    case: EvalCase,
    run_id: str,
    root_span_id: str | None,
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
    judge_enabled: bool,
    judge_model_id: str | None,
    judge_provider_id: str | None,
    gateway: StoryLlmGateway | None = None,
) -> list[EvalScore]:
    resolved_hooks = [
        (
            hook,
            _resolve_hook_target(
                hook.target,
                runtime_result=runtime_result,
                workspace_before=workspace_before,
                workspace_after=workspace_after,
                graph_debug=graph_debug,
                runtime_events=runtime_events,
            ),
        )
        for hook in case.expected.subjective_hooks
    ]
    if not judge_enabled:
        return [
            _materialize_resolved_hook_score(
                hook=hook,
                resolved=resolved,
                run_id=run_id,
                span_id=root_span_id,
            )
            for hook, resolved in resolved_hooks
        ]

    llm_gateway = gateway or StoryLlmGateway()
    scores: list[EvalScore] = []
    for hook, resolved in resolved_hooks:
        if hook.judge_family != "llm_judge":
            scores.append(
                _skip_hook_score(
                    hook=hook,
                    resolved=resolved,
                    run_id=run_id,
                    span_id=root_span_id,
                    reason="unsupported_judge_family",
                )
            )
            continue
        if not resolved["exists"]:
            scores.append(
                _skip_hook_score(
                    hook=hook,
                    resolved=resolved,
                    run_id=run_id,
                    span_id=root_span_id,
                    reason="target_missing",
                )
            )
            continue
        if not judge_model_id:
            scores.append(
                _skip_hook_score(
                    hook=hook,
                    resolved=resolved,
                    run_id=run_id,
                    span_id=root_span_id,
                    reason="judge_model_missing",
                )
            )
            continue
        rubric = get_judge_rubric(hook.rubric_ref)
        if rubric is None:
            scores.append(
                _skip_hook_score(
                    hook=hook,
                    resolved=resolved,
                    run_id=run_id,
                    span_id=root_span_id,
                    reason="unsupported_rubric",
                )
            )
            continue
        try:
            score = await _run_llm_judge(
                hook=hook,
                resolved=resolved,
                run_id=run_id,
                span_id=root_span_id,
                judge_model_id=judge_model_id,
                judge_provider_id=judge_provider_id,
                gateway=llm_gateway,
                rubric=rubric,
                judge_context=_build_judge_context(
                    case=case,
                    hook=hook,
                    resolved=resolved,
                    runtime_result=runtime_result,
                    workspace_before=workspace_before,
                    workspace_after=workspace_after,
                    graph_debug=graph_debug,
                    runtime_events=runtime_events,
                ),
            )
        except Exception as exc:
            score = _skip_hook_score(
                hook=hook,
                resolved=resolved,
                run_id=run_id,
                span_id=root_span_id,
                reason=f"judge_execution_failed:{type(exc).__name__}",
            )
        scores.append(score)
    return scores


def build_subjective_hook_artifacts(*, scores: list[EvalScore]) -> list[EvalArtifact]:
    artifacts: list[EvalArtifact] = []
    for score in scores:
        if score.kind not in {"llm", "human"}:
            continue
        hook_id = str(score.metadata.get("hook_id") or "").strip()
        if not hook_id:
            continue
        artifacts.append(
            EvalArtifact(
                artifact_id=_subjective_hook_artifact_id(
                    run_id=score.run_id,
                    hook_id=hook_id,
                ),
                run_id=score.run_id,
                kind="subjective_hook_record",
                name=f"SubjectiveHookRecord:{hook_id}",
                payload={
                    "hook_id": hook_id,
                    "name": score.name,
                    "kind": score.kind,
                    "status": score.status,
                    "label": score.label,
                    "score": _coerce_numeric_score(score.value),
                    "explanation": score.explanation,
                    "severity": score.severity,
                    "judge_family": score.metadata.get("judge_family"),
                    "rubric_ref": score.metadata.get("rubric_ref"),
                    "rubric_title": score.metadata.get("rubric_title"),
                    "target": {
                        "name": score.metadata.get("target"),
                        "available": bool(score.metadata.get("target_available")),
                        "source": score.metadata.get("resolved_source"),
                        "path": score.metadata.get("resolved_path"),
                        "preview": score.metadata.get("target_preview"),
                    },
                    "judge": {
                        "model_id": score.metadata.get("judge_model_id"),
                        "provider_id": score.metadata.get("judge_provider_id"),
                        "prompt_version": score.metadata.get("judge_prompt_version"),
                        "response_schema_version": score.metadata.get(
                            "judge_response_schema_version"
                        ),
                        "status_source": score.metadata.get("judge_status_source"),
                        "score_source": score.metadata.get("judge_score_source"),
                        "score_band": score.metadata.get("judge_score_band"),
                        "score_band_conflict": bool(
                            score.metadata.get("judge_score_band_conflict")
                        ),
                        "skip_reason": score.metadata.get("judge_skip_reason"),
                    },
                    "request": score.metadata.get("judge_request_payload"),
                    "response": score.metadata.get("judge_output"),
                    "strengths": list(score.metadata.get("judge_strengths") or []),
                    "issues": list(score.metadata.get("judge_issues") or []),
                },
            )
        )
    return artifacts


def _materialize_hook_score(
    *,
    hook: EvalSubjectiveHook,
    run_id: str,
    span_id: str | None,
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
) -> EvalScore:
    resolved = _resolve_hook_target(
        hook.target,
        runtime_result=runtime_result,
        workspace_before=workspace_before,
        workspace_after=workspace_after,
        graph_debug=graph_debug,
        runtime_events=runtime_events,
    )
    return _materialize_resolved_hook_score(
        hook=hook,
        resolved=resolved,
        run_id=run_id,
        span_id=span_id,
    )


def _materialize_resolved_hook_score(
    *,
    hook: EvalSubjectiveHook,
    resolved: dict[str, Any],
    run_id: str,
    span_id: str | None,
) -> EvalScore:
    return EvalScore(
        score_id=f"{run_id}:score:hook:{hook.hook_id}",
        run_id=run_id,
        span_id=span_id,
        name=f"hook:{hook.hook_id}",
        kind="llm",
        status="skip",
        value_type="categorical",
        value="pending",
        label="pending",
        explanation="Subjective hook prepared but no judge executor is configured yet",
        severity="warn",
        metadata=_hook_metadata(hook=hook, resolved=resolved),
    )


def _skip_hook_score(
    *,
    hook: EvalSubjectiveHook,
    resolved: dict[str, Any],
    run_id: str,
    span_id: str | None,
    reason: str,
) -> EvalScore:
    return EvalScore(
        score_id=f"{run_id}:score:hook:{hook.hook_id}",
        run_id=run_id,
        span_id=span_id,
        name=f"hook:{hook.hook_id}",
        kind="llm",
        status="skip",
        value_type="categorical",
        value="pending",
        label="pending",
        explanation=f"Subjective judge skipped: {reason}",
        severity="warn",
        metadata={
            **_hook_metadata(hook=hook, resolved=resolved),
            "judge_skip_reason": reason,
        },
    )


async def _run_llm_judge(
    *,
    hook: EvalSubjectiveHook,
    resolved: dict[str, Any],
    run_id: str,
    span_id: str | None,
    judge_model_id: str,
    judge_provider_id: str | None,
    gateway: StoryLlmGateway,
    rubric: JudgeRubricSpec,
    judge_context: dict[str, Any],
) -> EvalScore:
    prompt_payload = {
        "judge_prompt_version": rubric.prompt_version,
        "response_schema_version": rubric.response_schema_version,
        "rubric": {
            "ref": rubric.rubric_ref,
            "title": rubric.title,
            "task": rubric.task,
            "criteria": rubric.criteria,
            "anchors": {
                "pass": rubric.pass_anchor,
                "warn": rubric.warn_anchor,
                "fail": rubric.fail_anchor,
            },
            "score_bands": rubric.score_bands,
        },
        "target": {
            "source": resolved["source"],
            "path": resolved["path"],
            "preview": resolved["preview"],
            "content": _serialize_for_judge(resolved.get("value")),
        },
        "context": judge_context,
        "evidence_refs": [
            {"kind": "run", "run_id": run_id},
            {"kind": "span", "span_id": span_id},
            {
                "kind": "target",
                "source": resolved["source"],
                "path": resolved["path"],
            },
        ],
        "output_contract": {
            "return_json_only": True,
            "keys": ["status", "label", "score", "explanation", "strengths", "issues"],
            "allowed_status": ["pass", "warn", "fail"],
            "score_range": [0.0, 1.0],
            "strengths_max_items": 3,
            "issues_max_items": 3,
        },
    }
    messages = [
        ChatMessage(
            role="system",
            content=(
                "You are a strict evaluation judge for RP agent systems. "
                "Evaluate only against the provided rubric and target evidence. "
                "Return exactly one JSON object and no extra prose."
            ),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(prompt_payload, ensure_ascii=False),
        ),
    ]
    response_text = await gateway.complete_text(
        model_id=judge_model_id,
        provider_id=judge_provider_id,
        messages=messages,
        temperature=0.0,
        max_tokens=240,
        include_reasoning=False,
    )
    payload = StoryLlmGateway.extract_json_object(response_text)
    normalized = _JudgeResponse.model_validate(payload)
    numeric_score = _coerce_numeric_score(normalized.score)
    status, status_source = _normalize_status(
        raw_status=normalized.status,
        numeric_score=numeric_score,
        rubric=rubric,
    )
    if numeric_score is None and status in {"pass", "warn", "fail"}:
        numeric_score = _default_numeric_score(status=status, rubric=rubric)
        score_source = "status_default"
    else:
        score_source = "model"
    score_band = _resolve_score_band(numeric_score, rubric=rubric)
    label = str(normalized.label or ("pending" if status == "skip" else status))
    explanation = str(normalized.explanation or "").strip() or None
    return EvalScore(
        score_id=f"{run_id}:score:hook:{hook.hook_id}",
        run_id=run_id,
        span_id=span_id,
        name=f"hook:{hook.hook_id}",
        kind="llm",
        status=status,
        value_type="numeric",
        value=numeric_score,
        label=label,
        explanation=explanation,
        severity="warn",
        metadata={
            **_hook_metadata(hook=hook, resolved=resolved),
            "judge_model_id": judge_model_id,
            "judge_provider_id": judge_provider_id,
            "judge_request_payload": prompt_payload,
            "judge_output": normalized.model_dump(mode="json", exclude_none=True),
            "judge_prompt_version": rubric.prompt_version,
            "judge_response_schema_version": rubric.response_schema_version,
            "judge_status_source": status_source,
            "judge_score_source": score_source,
            "judge_score_band": score_band,
            "judge_score_band_conflict": (
                status in {"pass", "warn", "fail"}
                and score_band is not None
                and score_band != status
            ),
            "judge_strengths": list(normalized.strengths),
            "judge_issues": list(normalized.issues),
        },
    )


def _hook_metadata(*, hook: EvalSubjectiveHook, resolved: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "hook_id": hook.hook_id,
        "judge_family": hook.judge_family,
        "rubric_ref": hook.rubric_ref,
        "target": hook.target,
        "resolved_source": resolved["source"],
        "resolved_path": resolved["path"],
        "target_available": resolved["exists"],
        "target_preview": resolved["preview"],
    }
    rubric = get_judge_rubric(hook.rubric_ref)
    if rubric is not None:
        metadata.update(
            {
                "rubric_title": rubric.title,
                "judge_prompt_version": rubric.prompt_version,
                "judge_response_schema_version": rubric.response_schema_version,
            }
        )
    return metadata


def _resolve_hook_target(
    target: str,
    *,
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
) -> dict[str, Any]:
    source_name: str
    path: str

    if target in _TARGET_ALIASES:
        source_name, path = _TARGET_ALIASES[target]
    elif ":" in target:
        maybe_source, path = target.split(":", 1)
        if maybe_source in _SUPPORTED_SOURCES:
            source_name = maybe_source
        else:
            source_name = "runtime_result"
            path = target
    else:
        source_name = "runtime_result"
        path = target

    payload = _select_source_payload(
        source=source_name,
        runtime_result=runtime_result,
        workspace_before=workspace_before,
        workspace_after=workspace_after,
        graph_debug=graph_debug,
        runtime_events=runtime_events,
    )
    value, exists = _resolve_path(payload, path)
    return {
        "source": source_name,
        "path": path,
        "exists": exists,
        "preview": _preview(value),
        "value": value,
    }


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


def _preview(value: Any, *, max_chars: int = 280) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= max_chars else f"{text[: max_chars - 3]}..."


def _coerce_numeric_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None

def _build_judge_context(
    *,
    case: EvalCase,
    hook: EvalSubjectiveHook,
    resolved: dict[str, Any],
    runtime_result: dict[str, Any],
    workspace_before: dict[str, Any] | None,
    workspace_after: dict[str, Any] | None,
    graph_debug: dict[str, Any] | None,
    runtime_events: list[dict[str, Any]],
) -> dict[str, Any]:
    structured_payload = runtime_result.get("structured_payload")
    if not isinstance(structured_payload, dict):
        structured_payload = {}
    warnings = runtime_result.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    return {
        "case": {
            "case_id": case.case_id,
            "scope": case.scope,
            "category": case.category,
            "tags": case.tags,
        },
        "hook": {
            "hook_id": hook.hook_id,
            "judge_family": hook.judge_family,
            "rubric_ref": hook.rubric_ref,
            "target": hook.target,
        },
        "runtime": {
            "finish_reason": runtime_result.get("finish_reason"),
            "warnings": warnings[:5],
            "repair_route": structured_payload.get("repair_route"),
            "completion_guard_reason": _dict_get(structured_payload, "completion_guard", "reason"),
            "last_failure_category": _dict_get(
                structured_payload,
                "last_failure",
                "failure_category",
            ),
        },
        "evidence": {
            "target_available": resolved["exists"],
            "workspace_before_keys": _top_level_keys(workspace_before),
            "workspace_after_keys": _top_level_keys(workspace_after),
            "graph_debug_keys": _top_level_keys(graph_debug),
            "runtime_event_count": len(runtime_events),
        },
    }


def _serialize_for_judge(value: Any, *, max_chars: int = 3200) -> str | None:
    return _preview(value, max_chars=max_chars)


def _normalize_status(
    *,
    raw_status: str | None,
    numeric_score: float | None,
    rubric: JudgeRubricSpec,
) -> tuple[str, str]:
    status = str(raw_status or "").strip().lower()
    if status in {"pass", "warn", "fail"}:
        return status, "model_status"
    fallback = _resolve_score_band(numeric_score, rubric=rubric)
    if fallback in {"pass", "warn", "fail"}:
        return fallback, "score_band_fallback"
    return "skip", "unresolved"


def _default_numeric_score(*, status: str, rubric: JudgeRubricSpec) -> float | None:
    band = rubric.score_bands.get(status)
    if not isinstance(band, list) or len(band) != 2:
        return None
    try:
        low = float(band[0])
        high = float(band[1])
    except (TypeError, ValueError):
        return None
    return round((low + high) / 2, 4)


def _resolve_score_band(
    numeric_score: float | None,
    *,
    rubric: JudgeRubricSpec,
) -> str | None:
    if numeric_score is None:
        return None
    for status in ("pass", "warn", "fail"):
        band = rubric.score_bands.get(status)
        if not isinstance(band, list) or len(band) != 2:
            continue
        try:
            low = float(band[0])
            high = float(band[1])
        except (TypeError, ValueError):
            continue
        if low <= numeric_score <= high:
            return status
    return None


def _top_level_keys(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return sorted(str(key) for key in payload.keys())


def _dict_get(payload: dict[str, Any], key: str, nested_key: str) -> Any:
    candidate = payload.get(key)
    if not isinstance(candidate, dict):
        return None
    return candidate.get(nested_key)


def _subjective_hook_artifact_id(*, run_id: str, hook_id: str) -> str:
    return f"{run_id}:artifact:subjective_hook:{hook_id}"
