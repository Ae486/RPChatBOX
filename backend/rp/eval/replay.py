"""Replay serialization for eval evidence bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    EvalBaseline,
    EvalCase,
    EvalExpected,
    EvalInput,
    EvalRepeat,
    EvalRun,
    EvalRunResult,
    EvalRuntimeTarget,
    EvalTrace,
    EvalTraceHooks,
)


class SampledRetrievalTrace(BaseModel):
    """Normalized sampled retrieval trace for replay import."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    source_ref: str | None = None
    query: str
    retrieved_contexts: list[str] = Field(default_factory=list)
    response: str | None = None
    reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ragas_report: dict[str, Any] | None = None


def save_replay(path: str | Path, result: EvalRunResult) -> Path:
    replay_path = Path(path)
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "case": result.case.model_dump(mode="json"),
        "run": result.run.model_dump(mode="json"),
        "trace": result.trace.model_dump(mode="json"),
        "artifacts": [item.model_dump(mode="json") for item in result.artifacts],
        "scores": [item.model_dump(mode="json") for item in result.scores],
        "runtime_result": result.runtime_result,
        "report": result.report,
        "source": {
            "kind": "offline_eval_case",
        },
    }
    replay_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return replay_path


def build_sampled_retrieval_replay_payload(
    sample: SampledRetrievalTrace,
) -> dict[str, Any]:
    resolved_sample_id = str(sample.sample_id or f"sampled-{uuid4().hex[:12]}")
    case_id = f"retrieval.sampled.{resolved_sample_id}"
    run_id = f"run-{resolved_sample_id}"
    trace_id = f"trace-{resolved_sample_id}"
    ragas_report = (
        dict(sample.ragas_report)
        if isinstance(sample.ragas_report, dict)
        else {
            "enabled": False,
            "available": True,
            "status": "not_requested",
            "metric_names": [],
            "sample_count": 1,
            "record_count": 0,
            "metric_summary": {},
            "sample_overview": [
                {
                    "sample_id": resolved_sample_id,
                    "case_id": case_id,
                    "query": sample.query,
                    "retrieved_context_count": len(sample.retrieved_contexts),
                    "has_response": bool(sample.response),
                    "has_reference": bool(sample.reference),
                    "metadata": dict(sample.metadata),
                }
            ],
            "error": None,
        }
    )
    report = {
        "run_id": run_id,
        "case_id": case_id,
        "scope": "retrieval",
        "status": "completed",
        "assertion_summary": {
            "pass": 0,
            "fail": 0,
            "warn": 0,
            "skip": 0,
        },
        "hard_failures": [],
        "failure_layer": None,
        "finish_reason": "sampled_trace_loaded",
        "subjective_hook_summary": {
            "total": 0,
            "pending": 0,
            "executed": 0,
            "judge_family_counts": {},
            "rubric_refs": [],
            "status_counts": {},
            "average_numeric_score": None,
            "rubric_summaries": {},
            "artifact_count": 0,
        },
        "subjective_hook_results": [],
        "subjective_hook_artifact_ids": [],
        "pending_judge_hook_ids": [],
        "end_reason_summary": "sampled_trace_loaded",
        "ragas": ragas_report,
        "diagnostics": {
            "diagnostic_version": "v1",
            "capabilities": {},
            "attribution": {
                "primary_suspects": [],
                "optimization_candidates": [],
                "dimensions": {},
            },
            "observability": {
                "supported_scope": "retrieval",
                "diagnostic_mode": "sampled_trace_only",
            },
        },
    }
    return {
        "source": {
            "kind": "sampled_retrieval_trace",
            "source_ref": sample.source_ref,
            "sample_id": resolved_sample_id,
        },
        "sampled_trace": sample.model_dump(mode="json"),
        "case": EvalCase(
            case_id=case_id,
            title=f"Sampled retrieval trace {resolved_sample_id}",
            scope="retrieval",
            category="sampled_trace",
            runtime_target=EvalRuntimeTarget(
                mode="in_process",
                entrypoint="sampled_trace",
                graph_id="sampled_trace",
                stream=False,
            ),
            input=EvalInput(),
            expected=EvalExpected(),
            trace_hooks=EvalTraceHooks(),
            repeat=EvalRepeat(),
            baseline=EvalBaseline(),
        ).model_dump(mode="json"),
        "run": EvalRun(
            run_id=run_id,
            case_id=case_id,
            scope="retrieval",
            status="completed",
            runtime_target="sampled_trace",
            trace_id=trace_id,
            metadata=dict(sample.metadata),
        ).model_dump(mode="json"),
        "trace": EvalTrace(trace_id=trace_id).model_dump(mode="json"),
        "artifacts": [],
        "scores": [],
        "runtime_result": {
            "finish_reason": "sampled_trace_loaded",
            "sampled_trace": sample.model_dump(mode="json"),
        },
        "report": report,
    }


def save_sampled_retrieval_replay(
    path: str | Path,
    sample: SampledRetrievalTrace,
) -> Path:
    replay_path = Path(path)
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_sampled_retrieval_replay_payload(sample)
    replay_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return replay_path


def load_replay(path: str | Path) -> dict[str, Any]:
    replay_path = Path(path)
    if not replay_path.exists():
        raise FileNotFoundError(f"Eval replay file does not exist: {replay_path}")
    return json.loads(replay_path.read_text(encoding="utf-8"))


def load_replay_case(path: str | Path) -> EvalCase:
    payload = load_replay(path)
    return EvalCase.model_validate(payload["case"])
