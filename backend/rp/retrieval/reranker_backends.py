"""Backends for hosted or local retrieval rerank models."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from time import perf_counter

from rp.models.memory_crud import RetrievalQuery
from services.litellm_service import LiteLLMService, get_litellm_service
from services.model_registry import ModelRegistryService, get_model_registry_service
from services.provider_registry import ProviderRegistryService, get_provider_registry_service

from .reranker_resolver import (
    HostedRerankerResolver,
    HostedRerankerTarget,
    LocalCrossEncoderResolver,
    LocalCrossEncoderTarget,
)
from .reranker_models import RerankBackendItem, RerankBackendResult, RerankCandidate


def _normalize_scores(scores: object) -> list[float]:
    if scores is None or isinstance(scores, (str, bytes, bytearray)):
        return []
    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    if not isinstance(scores, Iterable):
        return []
    try:
        return [float(score) for score in scores]
    except (TypeError, ValueError):
        return []


class RerankerBackendChain:
    """Try multiple rerank backends in order and return the first useful result."""

    def __init__(self, backends: Sequence[object]) -> None:
        self._backends = list(backends)

    def rerank(
        self,
        *,
        query: RetrievalQuery,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> RerankBackendResult:
        warnings: list[str] = []
        for backend in self._backends:
            result = backend.rerank(query=query, candidates=candidates, top_n=top_n)
            warnings.extend(result.warnings)
            if result.has_usable_items():
                return result.model_copy(update={"warnings": list(dict.fromkeys(warnings))})
        return RerankBackendResult(
            backend_name="chain",
            warnings=list(dict.fromkeys(warnings)),
        )


class HostedRerankerBackend:
    """Use a hosted reranker endpoint via LiteLLM when a capable model exists."""

    def __init__(
        self,
        *,
        litellm_service: LiteLLMService | None = None,
        model_registry_service: ModelRegistryService | None = None,
        provider_registry_service: ProviderRegistryService | None = None,
        model_id: str | None = None,
        provider_id: str | None = None,
        resolver: HostedRerankerResolver | None = None,
    ) -> None:
        self._litellm_service = litellm_service or get_litellm_service()
        self._resolver = resolver or HostedRerankerResolver(
            model_registry_service=model_registry_service or get_model_registry_service(),
            provider_registry_service=provider_registry_service or get_provider_registry_service(),
            model_id=model_id,
            provider_id=provider_id,
        )

    def resolve_target(self) -> HostedRerankerTarget | None:
        return self._resolver.resolve_target()

    def rerank(
        self,
        *,
        query: RetrievalQuery,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> RerankBackendResult:
        expected_count = min(top_n or len(candidates), len(candidates))
        target = self.resolve_target()
        if target is None:
            return RerankBackendResult(
                backend_name="hosted",
                expected_count=expected_count,
                warnings=["rerank_backend_unavailable:no_supported_model"],
            )
        if not candidates:
            return RerankBackendResult(
                backend_name="hosted",
                model_id=target.model_id,
                model_name=target.model_name,
                provider_id=target.provider_id,
                resolution_source=target.resolution_source,
                expected_count=0,
                warnings=["rerank_backend_unavailable:no_candidates"],
            )

        started = perf_counter()
        try:
            response = self._litellm_service.rerank(
                provider=target.provider,
                model=target.model_name,
                query=query.text_query or "",
                documents=[candidate.contextual_text or candidate.excerpt_text for candidate in candidates],
                top_n=top_n or len(candidates),
            )
        except Exception as exc:  # pragma: no cover - network/provider dependent
            return RerankBackendResult(
                backend_name="hosted",
                model_id=target.model_id,
                model_name=target.model_name,
                provider_id=target.provider_id,
                resolution_source=target.resolution_source,
                rerank_ms=(perf_counter() - started) * 1000,
                expected_count=expected_count,
                warnings=[f"rerank_backend_failed:{type(exc).__name__}"],
            )

        results = response.get("results") or []
        items: list[RerankBackendItem] = []
        for rank, raw in enumerate(results, start=1):
            if not isinstance(raw, dict):
                continue
            index = raw.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(candidates):
                continue
            score = raw.get("relevance_score")
            if score is None:
                continue
            items.append(
                RerankBackendItem(
                    hit_id=candidates[index].hit_id,
                    relevance_score=float(score),
                    rank=rank,
                )
            )

        warnings: list[str] = []
        if len(items) < expected_count:
            warnings.append(
                "rerank_backend_incomplete:no_items"
                if not items
                else f"rerank_backend_incomplete:expected_{expected_count}_got_{len(items)}"
            )

        return RerankBackendResult(
            backend_name="hosted",
            model_id=target.model_id,
            model_name=target.model_name,
            provider_id=target.provider_id,
            resolution_source=target.resolution_source,
            rerank_ms=(perf_counter() - started) * 1000,
            expected_count=expected_count,
            items=items,
            warnings=warnings,
        )


class LocalCrossEncoderBackend:
    """Use a local cross-encoder model when one is available."""

    def __init__(
        self,
        *,
        model_registry_service: ModelRegistryService | None = None,
        provider_registry_service: ProviderRegistryService | None = None,
        model_id: str | None = None,
        provider_id: str | None = None,
        resolver: LocalCrossEncoderResolver | None = None,
        cross_encoder_factory=None,
    ) -> None:
        self._resolver = resolver or LocalCrossEncoderResolver(
            model_registry_service=model_registry_service or get_model_registry_service(),
            provider_registry_service=provider_registry_service or get_provider_registry_service(),
            model_id=model_id,
            provider_id=provider_id,
        )
        self._cross_encoder_factory = cross_encoder_factory
        self._model_cache: dict[str, object] = {}

    def resolve_target(self) -> LocalCrossEncoderTarget | None:
        return self._resolver.resolve_target()

    def rerank(
        self,
        *,
        query: RetrievalQuery,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> RerankBackendResult:
        expected_count = min(top_n or len(candidates), len(candidates))
        target = self.resolve_target()
        if target is None:
            return RerankBackendResult(
                backend_name="local_cross_encoder",
                expected_count=expected_count,
                warnings=["rerank_backend_unavailable:no_local_model"],
            )
        if not candidates:
            return RerankBackendResult(
                backend_name="local_cross_encoder",
                model_id=target.model_id,
                model_name=target.model_name,
                provider_id=target.provider_id,
                resolution_source=target.resolution_source,
                expected_count=0,
                warnings=["rerank_backend_unavailable:no_candidates"],
            )

        started = perf_counter()
        try:
            model = self._load_model(target)
            scores = model.predict(
                [
                    (query.text_query or "", candidate.contextual_text or candidate.excerpt_text)
                    for candidate in candidates
                ]
            )
        except ImportError:
            return RerankBackendResult(
                backend_name="local_cross_encoder",
                model_id=target.model_id,
                model_name=target.model_name,
                provider_id=target.provider_id,
                resolution_source=target.resolution_source,
                rerank_ms=(perf_counter() - started) * 1000,
                expected_count=expected_count,
                warnings=["rerank_backend_unavailable:local_dependency_missing"],
            )
        except Exception as exc:  # pragma: no cover - model/runtime dependent
            return RerankBackendResult(
                backend_name="local_cross_encoder",
                model_id=target.model_id,
                model_name=target.model_name,
                provider_id=target.provider_id,
                resolution_source=target.resolution_source,
                rerank_ms=(perf_counter() - started) * 1000,
                expected_count=expected_count,
                warnings=[f"rerank_backend_failed:{type(exc).__name__}"],
            )

        scored = _normalize_scores(scores)
        if len(scored) < expected_count:
            return RerankBackendResult(
                backend_name="local_cross_encoder",
                model_id=target.model_id,
                model_name=target.model_name,
                provider_id=target.provider_id,
                resolution_source=target.resolution_source,
                rerank_ms=(perf_counter() - started) * 1000,
                expected_count=expected_count,
                warnings=[
                    "rerank_backend_incomplete:no_scores"
                    if not scored
                    else f"rerank_backend_incomplete:expected_{expected_count}_got_{len(scored)}"
                ],
            )

        sorted_items = sorted(
            enumerate(scored),
            key=lambda item: float(item[1]),
            reverse=True,
        )[: top_n or len(candidates)]
        items = [
            RerankBackendItem(
                hit_id=candidates[index].hit_id,
                relevance_score=float(score),
                rank=rank,
            )
            for rank, (index, score) in enumerate(sorted_items, start=1)
        ]
        return RerankBackendResult(
            backend_name="local_cross_encoder",
            model_id=target.model_id,
            model_name=target.model_name,
            provider_id=target.provider_id,
            resolution_source=target.resolution_source,
            rerank_ms=(perf_counter() - started) * 1000,
            expected_count=expected_count,
            items=items,
        )

    def _load_model(self, target: LocalCrossEncoderTarget):
        cached = self._model_cache.get(target.model_name)
        if cached is not None:
            return cached

        if self._cross_encoder_factory is not None:
            model = self._cross_encoder_factory(target.model_name)
        else:
            from sentence_transformers import CrossEncoder  # type: ignore

            model = CrossEncoder(target.model_name)
        self._model_cache[target.model_name] = model
        return model
