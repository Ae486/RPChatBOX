"""Optional RAGAS integration for retrieval/RAG specialized metrics."""

from __future__ import annotations

import inspect
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .ragas_samples import (
    RagasRetrievalSample,
    build_ragas_dataset_payload,
)

DEFAULT_RAGAS_METRICS: tuple[str, ...] = (
    "context_precision",
    "context_recall",
    "response_relevancy",
    "faithfulness",
)

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "context_precision": (
        "context_precision",
        "ContextPrecision",
        "LLMContextPrecisionWithReference",
        "LLMContextPrecisionWithoutReference",
    ),
    "context_recall": (
        "context_recall",
        "ContextRecall",
        "LLMContextRecall",
    ),
    "response_relevancy": (
        "response_relevancy",
        "answer_relevancy",
        "ResponseRelevancy",
        "AnswerRelevancy",
    ),
    "answer_relevancy": (
        "answer_relevancy",
        "response_relevancy",
        "AnswerRelevancy",
        "ResponseRelevancy",
    ),
    "faithfulness": (
        "faithfulness",
        "Faithfulness",
    ),
}

try:  # pragma: no cover - optional dependency path
    from ragas import evaluate
except ImportError:  # pragma: no cover - optional dependency path
    evaluate = None

try:  # pragma: no cover - optional dependency path
    from ragas.dataset_schema import EvaluationDataset
except ImportError:  # pragma: no cover - optional dependency path
    try:
        from ragas import EvaluationDataset
    except ImportError:  # pragma: no cover - optional dependency path
        EvaluationDataset = None

try:  # pragma: no cover - optional dependency path
    from ragas import metrics as ragas_metrics_module
except ImportError:  # pragma: no cover - optional dependency path
    ragas_metrics_module = None


@dataclass(frozen=True)
class RagasRunConfig:
    enabled: bool = False
    metrics: tuple[str, ...] = DEFAULT_RAGAS_METRICS
    response: str | None = None
    reference: str | None = None
    llm_model_id: str | None = None
    llm_provider_id: str | None = None
    embedding_model_id: str | None = None
    embedding_provider_id: str | None = None


def ragas_available() -> bool:
    return (
        EvaluationDataset is not None
        and evaluate is not None
        and ragas_metrics_module is not None
    )


def parse_ragas_metrics(value: Any) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_RAGAS_METRICS
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(item).strip() for item in value]
    else:
        raw_items = [str(value).strip()]

    canonical: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if not item:
            continue
        normalized = item.lower().replace("-", "_")
        canonical_name = _canonical_metric_name(normalized)
        if canonical_name in seen:
            continue
        canonical.append(canonical_name)
        seen.add(canonical_name)
    return tuple(canonical or DEFAULT_RAGAS_METRICS)


def build_ragas_dataset(samples: list[RagasRetrievalSample]):
    if EvaluationDataset is None:
        raise RuntimeError(
            "RAGAS is not installed. Install 'ragas' to build retrieval evaluation datasets."
        )
    payload = build_ragas_dataset_payload(samples)
    return EvaluationDataset.from_list(payload)


def resolve_metric_objects(
    metric_names: tuple[str, ...] | list[str],
    *,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> list[Any]:
    if ragas_metrics_module is None:
        raise RuntimeError(
            "RAGAS metrics module is not installed. Install 'ragas' to resolve metric objects."
        )

    metric_objects: list[Any] = []
    for metric_name in parse_ragas_metrics(metric_names):
        metric_objects.append(
            _resolve_metric_object(
                metric_name,
                llm=llm,
                embeddings=embeddings,
            )
        )
    return metric_objects


def run_ragas_evaluation(
    *,
    samples: list[RagasRetrievalSample],
    metric_objects: list[Any],
    llm: Any | None = None,
    embeddings: Any | None = None,
):
    if evaluate is None:
        raise RuntimeError(
            "RAGAS is not installed. Install 'ragas' to run retrieval evaluation."
        )
    dataset = build_ragas_dataset(samples)
    return evaluate(
        dataset=dataset,
        metrics=metric_objects,
        llm=llm,
        embeddings=embeddings,
        show_progress=False,
        raise_exceptions=True,
    )


def result_to_records(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    scores = getattr(result, "scores", None)
    if isinstance(scores, list):
        return [_normalize_record(item) for item in scores if isinstance(item, dict)]
    if isinstance(result, list):
        return [_normalize_record(item) for item in result if isinstance(item, dict)]
    to_pandas = getattr(result, "to_pandas", None)
    if callable(to_pandas):
        frame = to_pandas()
        try:
            raw_records = frame.to_dict(orient="records")
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError(f"Failed to serialize RAGAS pandas result: {exc}") from exc
        return [_normalize_record(item) for item in raw_records if isinstance(item, dict)]
    raise TypeError(f"Unsupported RAGAS result type: {type(result)!r}")


def _canonical_metric_name(metric_name: str) -> str:
    if metric_name in _METRIC_ALIASES:
        if metric_name == "answer_relevancy":
            return "response_relevancy"
        return metric_name
    raise ValueError(f"Unsupported RAGAS metric name: {metric_name}")


def _resolve_metric_object(
    metric_name: str,
    *,
    llm: Any | None,
    embeddings: Any | None,
) -> Any:
    if ragas_metrics_module is None:
        raise RuntimeError("RAGAS metrics module is unavailable")

    candidates = _METRIC_ALIASES.get(metric_name)
    if candidates is None:
        raise ValueError(f"Unsupported RAGAS metric name: {metric_name}")

    for attr_name in candidates:
        candidate = getattr(ragas_metrics_module, attr_name, None)
        if candidate is None:
            continue
        if inspect.ismodule(candidate):
            exported_names = list(getattr(candidate, "__all__", []) or [])
            for exported_name in exported_names:
                exported = getattr(candidate, exported_name, None)
                if isinstance(exported, type):
                    return _instantiate_metric_class(
                        metric_name=metric_name,
                        attr_name=f"{attr_name}.{exported_name}",
                        metric_class=exported,
                        llm=llm,
                        embeddings=embeddings,
                    )
        if isinstance(candidate, type):
            return _instantiate_metric_class(
                metric_name=metric_name,
                attr_name=attr_name,
                metric_class=candidate,
                llm=llm,
                embeddings=embeddings,
            )
        return deepcopy(candidate)
    raise RuntimeError(
        f"RAGAS metric '{metric_name}' is not exposed by the installed ragas.metrics module."
    )


def _instantiate_metric_class(
    *,
    metric_name: str,
    attr_name: str,
    metric_class: type,
    llm: Any | None,
    embeddings: Any | None,
) -> Any:
    signature = inspect.signature(metric_class)
    kwargs: dict[str, Any] = {}
    if "llm" in signature.parameters:
        if llm is None:
            raise RuntimeError(
                f"RAGAS metric '{metric_name}' requires an evaluator llm, but none was resolved."
            )
        kwargs["llm"] = llm
    if "embeddings" in signature.parameters:
        if embeddings is None:
            raise RuntimeError(
                f"RAGAS metric '{metric_name}' requires embeddings, but none were resolved."
            )
        kwargs["embeddings"] = embeddings
    try:
        return metric_class(**kwargs)
    except TypeError as exc:
        raise RuntimeError(
            f"RAGAS metric '{metric_name}' requires explicit dependencies and "
            f"cannot be auto-instantiated from '{attr_name}'."
        ) from exc


def _normalize_record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): _normalize_value(value)
        for key, value in payload.items()
    }


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
