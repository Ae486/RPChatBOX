"""Reporting helpers for retrieval-side RAGAS evaluation."""

from __future__ import annotations

from typing import Any

from .models import EvalArtifact
from .ragas_adapter import parse_ragas_metrics
from .ragas_samples import RagasRetrievalSample


def build_ragas_report(
    *,
    enabled: bool,
    available: bool,
    status: str,
    metric_names: tuple[str, ...] | list[str],
    samples: list[RagasRetrievalSample],
    records: list[dict[str, Any]],
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_metric_names = list(parse_ragas_metrics(metric_names))
    metric_summary = summarize_ragas_records(
        records=records,
        metric_names=normalized_metric_names,
    )
    return {
        "enabled": enabled,
        "available": available,
        "status": status,
        "metric_names": normalized_metric_names,
        "sample_count": len(samples),
        "record_count": len(records),
        "metric_summary": metric_summary,
        "sample_overview": [
            {
                "sample_id": sample.sample_id,
                "case_id": sample.case_id,
                "query": sample.query,
                "retrieved_context_count": len(sample.retrieved_contexts),
                "has_response": bool(sample.response),
                "has_reference": bool(sample.reference),
                "metadata": dict(sample.metadata),
            }
            for sample in samples
        ],
        "error": error,
    }


def build_ragas_artifacts(
    *,
    run_id: str,
    samples: list[RagasRetrievalSample],
    records: list[dict[str, Any]],
    report: dict[str, Any],
) -> list[EvalArtifact]:
    artifacts = [
        EvalArtifact(
            artifact_id=f"{run_id}:artifact:ragas_report",
            run_id=run_id,
            kind="ragas_report",
            name="RagasReport",
            payload=report,
        )
    ]
    if samples:
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:ragas_samples",
                run_id=run_id,
                kind="ragas_samples",
                name="RagasSamples",
                payload={
                    "samples": [sample.model_dump(mode="json") for sample in samples],
                },
            )
        )
    if records:
        artifacts.append(
            EvalArtifact(
                artifact_id=f"{run_id}:artifact:ragas_records",
                run_id=run_id,
                kind="ragas_records",
                name="RagasRecords",
                payload={"records": records},
            )
        )
    return artifacts


def summarize_ragas_records(
    *,
    records: list[dict[str, Any]],
    metric_names: list[str] | tuple[str, ...],
) -> dict[str, float | None]:
    summary: dict[str, float | None] = {}
    for metric_name in metric_names:
        candidate_keys = _candidate_metric_keys(str(metric_name))
        values = [
            float(value)
            for record in records
            for key in candidate_keys
            for value in [record.get(key)]
            if _is_numeric_metric_value(value)
        ]
        summary[str(metric_name)] = _average(values)
    return summary


def extract_ragas_report(artifacts: list[EvalArtifact]) -> dict[str, Any] | None:
    artifact = next((item for item in artifacts if item.kind == "ragas_report"), None)
    if artifact is None:
        return None
    return dict(artifact.payload)


def _is_numeric_metric_value(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _candidate_metric_keys(metric_name: str) -> list[str]:
    if metric_name == "response_relevancy":
        return ["response_relevancy", "answer_relevancy"]
    return [metric_name]
