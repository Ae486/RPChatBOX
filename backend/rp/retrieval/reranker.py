"""Reranker slot implementations for retrieval results."""

from __future__ import annotations

import json
import re
import time

from models.chat import ChatMessage
from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult
from rp.services.story_llm_gateway import StoryLlmGateway
from services.model_registry import ModelRegistryService, get_model_registry_service
from .reranker_backends import HostedRerankerBackend, LocalCrossEncoderBackend, RerankerBackendChain
from .reranker_models import RerankBackendItem, RerankCandidate, RerankBackendResult

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_LLM_RERANK_TEXT_MAX_CHARS = 900


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token]


def _append_trace_metadata(
    *,
    query: RetrievalQuery,
    result: RetrievalSearchResult,
    reranker_name: str,
    rerank_ms: float,
) -> RetrievalSearchResult:
    if result.trace is None:
        return result
    trace = result.trace.model_copy(
        update={
            "filters_applied": {
                **dict(result.trace.filters_applied or {}),
                "rerank": query.rerank,
            },
            "pipeline_stages": _dedupe_preserve_order(
                [*(result.trace.pipeline_stages or []), "rerank"]
            ),
            "reranker_name": reranker_name,
            "timings": {
                **dict(result.trace.timings or {}),
                "rerank_ms": round(rerank_ms, 3),
            },
        }
    )
    return result.model_copy(update={"trace": trace})


def _append_warnings(
    *,
    result: RetrievalSearchResult,
    warnings: list[str],
) -> RetrievalSearchResult:
    if not warnings:
        return result
    combined = _dedupe_preserve_order([*result.warnings, *warnings])
    trace = result.trace
    if trace is not None:
        trace = trace.model_copy(
            update={
                "warnings": _dedupe_preserve_order([*(trace.warnings or []), *warnings]),
            }
        )
    return result.model_copy(update={"warnings": combined, "trace": trace})


def _append_backend_trace_details(
    *,
    result: RetrievalSearchResult,
    backend_result: RerankBackendResult,
    input_candidate_count: int,
) -> RetrievalSearchResult:
    if result.trace is None:
        return result
    details = dict(result.trace.details or {})
    details["rerank"] = {
        "backend_name": backend_result.backend_name,
        "model_id": backend_result.model_id,
        "model_name": backend_result.model_name,
        "provider_id": backend_result.provider_id,
        "resolution_source": backend_result.resolution_source,
        "input_candidate_count": input_candidate_count,
        "expected_count": backend_result.expected_count,
        "returned_item_count": len(backend_result.items),
        "used_backend_result": backend_result.has_usable_items(),
    }
    trace = result.trace.model_copy(update={"details": details})
    return result.model_copy(update={"trace": trace})


class NoOpReranker:
    """Default reranker that preserves the fused ranking unchanged."""

    async def rerank(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        if not query.rerank:
            return result
        return _append_trace_metadata(
            query=query,
            result=result,
            reranker_name="noop",
            rerank_ms=0.0,
        )


class SimpleMetadataReranker:
    """Deterministic reranker that lightly boosts metadata-aligned hits."""

    async def rerank(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        if not query.rerank or len(result.hits) <= 1:
            return result

        started = time.perf_counter()
        normalized_query = (query.text_query or "").strip().lower()
        query_tokens = _tokens(normalized_query)
        domain_path_prefix = str(query.filters.get("domain_path_prefix") or "").strip().lower()

        scored_hits: list[tuple[float, int, RetrievalHit]] = []
        for index, hit in enumerate(result.hits):
            metadata = dict(hit.metadata)
            title = str(metadata.get("title") or "").lower()
            domain_path = str(metadata.get("domain_path") or "").lower()
            tags = " ".join(str(item).lower() for item in metadata.get("tags") or [])

            boost = 0.0
            if normalized_query and normalized_query in title:
                boost += 0.12
            if domain_path_prefix and domain_path.startswith(domain_path_prefix):
                boost += 0.08

            title_matches = sum(1 for token in query_tokens if token in title)
            path_matches = sum(1 for token in query_tokens if token in domain_path)
            tag_matches = sum(1 for token in query_tokens if token in tags)
            boost += min(title_matches, 3) * 0.03
            boost += min(path_matches, 3) * 0.02
            boost += min(tag_matches, 2) * 0.01

            adjusted_score = round(float(hit.score) + boost, 6)
            scored_hits.append((adjusted_score, index, hit))

        reranked_hits = [
            hit.model_copy(update={"score": score, "rank": rank})
            for rank, (score, _, hit) in enumerate(
                sorted(scored_hits, key=lambda item: (-item[0], item[1])),
                start=1,
            )
        ]
        reranked_result = result.model_copy(update={"hits": reranked_hits})
        return _append_trace_metadata(
            query=query,
            result=reranked_result,
            reranker_name="simple_metadata",
            rerank_ms=(time.perf_counter() - started) * 1000,
        )


class CrossEncoderReranker:
    """Model-backed reranker with stable fallback to metadata reranking."""

    def __init__(
        self,
        *,
        backend: object | None = None,
        fallback_reranker: SimpleMetadataReranker | None = None,
    ) -> None:
        self._backend = backend or RerankerBackendChain(
            [
                HostedRerankerBackend(),
                LocalCrossEncoderBackend(),
            ]
        )
        self._fallback_reranker = fallback_reranker or SimpleMetadataReranker()

    async def rerank(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        if not query.rerank or len(result.hits) <= 1:
            return result

        candidates = self.build_candidates(result)
        backend_result = self._backend.rerank(
            query=query,
            candidates=candidates,
            top_n=len(candidates),
        )
        if not backend_result.has_usable_items():
            fallback_result = await self._fallback_reranker.rerank(query=query, result=result)
            fallback_result = _append_backend_trace_details(
                result=fallback_result,
                backend_result=backend_result,
                input_candidate_count=len(candidates),
            )
            return _append_warnings(result=fallback_result, warnings=backend_result.warnings)

        reranked_hits = self._apply_backend_ranking(result=result, backend_result=backend_result)
        reranked_result = result.model_copy(update={"hits": reranked_hits})
        reranked_result = _append_trace_metadata(
            query=query,
            result=reranked_result,
            reranker_name=f"cross_encoder_{backend_result.backend_name}",
            rerank_ms=backend_result.rerank_ms,
        )
        reranked_result = _append_backend_trace_details(
            result=reranked_result,
            backend_result=backend_result,
            input_candidate_count=len(candidates),
        )
        return _append_warnings(result=reranked_result, warnings=backend_result.warnings)

    @staticmethod
    def build_candidates(result: RetrievalSearchResult) -> list[RerankCandidate]:
        return [RerankCandidate.from_hit(hit) for hit in result.hits]

    @staticmethod
    def _apply_backend_ranking(
        *,
        result: RetrievalSearchResult,
        backend_result: RerankBackendResult,
    ) -> list[RetrievalHit]:
        hit_by_id = {hit.hit_id: hit for hit in result.hits}
        ordered_hit_ids = [item.hit_id for item in backend_result.items]
        ordered_hits: list[RetrievalHit] = []

        for item in backend_result.items:
            hit = hit_by_id.get(item.hit_id)
            if hit is None:
                continue
            ordered_hits.append(
                hit.model_copy(
                    update={
                        "score": round(float(item.relevance_score), 6),
                        "rank": item.rank,
                    }
                )
            )

        for hit in result.hits:
            if hit.hit_id in ordered_hit_ids:
                continue
            ordered_hits.append(hit)

        return [
            hit.model_copy(update={"rank": index})
            for index, hit in enumerate(ordered_hits, start=1)
        ]


class LLMReranker:
    """High-cost enhancement reranker using a general-purpose LLM."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        provider_id: str | None = None,
        gateway: StoryLlmGateway | None = None,
        model_registry_service: ModelRegistryService | None = None,
        fallback_reranker: SimpleMetadataReranker | None = None,
        max_candidates: int = 8,
        temperature: float = 0.0,
        max_tokens: int = 400,
    ) -> None:
        self._model_id = model_id
        self._provider_id = provider_id
        self._gateway = gateway or StoryLlmGateway()
        self._model_registry_service = model_registry_service or get_model_registry_service()
        self._fallback_reranker = fallback_reranker or SimpleMetadataReranker()
        self._max_candidates = max(2, max_candidates)
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def rerank(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        if not query.rerank or len(result.hits) <= 1:
            return result

        candidates = CrossEncoderReranker.build_candidates(result)[: self._max_candidates]
        truncated = len(result.hits) > len(candidates)
        if self._model_id is None:
            backend_result = RerankBackendResult(
                backend_name="llm",
                provider_id=self._provider_id,
                expected_count=len(candidates),
                warnings=["llm_rerank_unconfigured:no_model_id"],
            )
            fallback_result = await self._fallback_reranker.rerank(query=query, result=result)
            fallback_result = _append_backend_trace_details(
                result=fallback_result,
                backend_result=backend_result,
                input_candidate_count=len(candidates),
            )
            return _append_warnings(result=fallback_result, warnings=backend_result.warnings)

        warnings: list[str] = []
        if truncated:
            warnings.append(
                f"llm_rerank_truncated:top_{len(candidates)}_of_{len(result.hits)}"
            )

        model_name = self._resolve_model_name()
        started = time.perf_counter()
        try:
            response_text = await self._gateway.complete_text(
                model_id=self._model_id,
                provider_id=self._provider_id,
                messages=self._build_messages(query=query, candidates=candidates),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                include_reasoning=False,
            )
            backend_result = self._backend_result_from_response(
                response_text=response_text,
                candidates=candidates,
                model_name=model_name,
                rerank_ms=(time.perf_counter() - started) * 1000,
                extra_warnings=warnings,
            )
        except Exception as exc:
            backend_result = RerankBackendResult(
                backend_name="llm",
                model_id=self._model_id,
                model_name=model_name,
                provider_id=self._provider_id,
                resolution_source="explicit_model",
                rerank_ms=(time.perf_counter() - started) * 1000,
                expected_count=len(candidates),
                warnings=[*warnings, f"llm_rerank_failed:{type(exc).__name__}"],
            )

        if not backend_result.has_usable_items():
            fallback_result = await self._fallback_reranker.rerank(query=query, result=result)
            fallback_result = _append_backend_trace_details(
                result=fallback_result,
                backend_result=backend_result,
                input_candidate_count=len(candidates),
            )
            return _append_warnings(result=fallback_result, warnings=backend_result.warnings)

        reranked_hits = CrossEncoderReranker._apply_backend_ranking(
            result=result,
            backend_result=backend_result,
        )
        reranked_result = result.model_copy(update={"hits": reranked_hits})
        reranked_result = _append_trace_metadata(
            query=query,
            result=reranked_result,
            reranker_name="llm",
            rerank_ms=backend_result.rerank_ms,
        )
        reranked_result = _append_backend_trace_details(
            result=reranked_result,
            backend_result=backend_result,
            input_candidate_count=len(candidates),
        )
        return _append_warnings(result=reranked_result, warnings=backend_result.warnings)

    def _resolve_model_name(self) -> str | None:
        if self._model_id is None:
            return None
        entry = self._model_registry_service.get_entry(self._model_id)
        if entry is None:
            return None
        return entry.model_name

    def _build_messages(
        self,
        *,
        query: RetrievalQuery,
        candidates: list[RerankCandidate],
    ) -> list[ChatMessage]:
        candidate_lines = []
        for candidate in candidates:
            payload = {
                "hit_id": candidate.hit_id,
                "title": candidate.title,
                "domain_path": candidate.domain_path,
                "page_ref": candidate.page_ref,
                "document_title": candidate.document_title,
                "document_summary": candidate.document_summary,
                "image_caption": candidate.image_caption,
                "text": self._candidate_text(candidate),
            }
            candidate_lines.append(json.dumps(payload, ensure_ascii=False))

        return [
            ChatMessage(
                role="system",
                content=(
                    "You are a reranking engine. Reorder retrieval candidates for the query. "
                    "Return only strict JSON with the shape "
                    '{"ordered_hit_ids":["hit_id_1","hit_id_2"]}. '
                    "Include every candidate hit_id exactly once and do not invent ids."
                ),
            ),
            ChatMessage(
                role="user",
                content="\n".join(
                    [
                        f"Query: {query.text_query or ''}",
                        "Candidates:",
                        *candidate_lines,
                    ]
                ),
            ),
        ]

    @staticmethod
    def _candidate_text(candidate: RerankCandidate) -> str:
        text = candidate.contextual_text or candidate.excerpt_text
        return text[:_LLM_RERANK_TEXT_MAX_CHARS]

    def _backend_result_from_response(
        self,
        *,
        response_text: str,
        candidates: list[RerankCandidate],
        model_name: str | None,
        rerank_ms: float,
        extra_warnings: list[str],
    ) -> RerankBackendResult:
        try:
            payload = StoryLlmGateway.extract_json_object(response_text)
        except Exception:
            return RerankBackendResult(
                backend_name="llm",
                model_id=self._model_id,
                model_name=model_name,
                provider_id=self._provider_id,
                resolution_source="explicit_model",
                rerank_ms=rerank_ms,
                expected_count=len(candidates),
                warnings=[*extra_warnings, "llm_rerank_failed:invalid_json"],
            )

        ordered_hit_ids = payload.get("ordered_hit_ids")
        if not isinstance(ordered_hit_ids, list):
            return RerankBackendResult(
                backend_name="llm",
                model_id=self._model_id,
                model_name=model_name,
                provider_id=self._provider_id,
                resolution_source="explicit_model",
                rerank_ms=rerank_ms,
                expected_count=len(candidates),
                warnings=[*extra_warnings, "llm_rerank_failed:missing_ordered_hit_ids"],
            )

        allowed_hit_ids = [candidate.hit_id for candidate in candidates]
        deduped_hit_ids = []
        seen: set[str] = set()
        for item in ordered_hit_ids:
            hit_id = str(item or "").strip()
            if not hit_id or hit_id in seen or hit_id not in allowed_hit_ids:
                continue
            seen.add(hit_id)
            deduped_hit_ids.append(hit_id)

        if len(deduped_hit_ids) < len(candidates):
            return RerankBackendResult(
                backend_name="llm",
                model_id=self._model_id,
                model_name=model_name,
                provider_id=self._provider_id,
                resolution_source="explicit_model",
                rerank_ms=rerank_ms,
                expected_count=len(candidates),
                items=[
                    RerankBackendItem(
                        hit_id=hit_id,
                        relevance_score=round(1.0 - ((rank - 1) / max(len(candidates), 1)), 6),
                        rank=rank,
                    )
                    for rank, hit_id in enumerate(deduped_hit_ids, start=1)
                ],
                warnings=[
                    *extra_warnings,
                    f"llm_rerank_incomplete:expected_{len(candidates)}_got_{len(deduped_hit_ids)}",
                ],
            )

        return RerankBackendResult(
            backend_name="llm",
            model_id=self._model_id,
            model_name=model_name,
            provider_id=self._provider_id,
            resolution_source="explicit_model",
            rerank_ms=rerank_ms,
            expected_count=len(candidates),
            items=[
                RerankBackendItem(
                    hit_id=hit_id,
                    relevance_score=round(1.0 - ((rank - 1) / max(len(candidates), 1)), 6),
                    rank=rank,
                )
                for rank, hit_id in enumerate(deduped_hit_ids, start=1)
            ],
            warnings=extra_warnings,
        )
