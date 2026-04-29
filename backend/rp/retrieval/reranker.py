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


def _filter_values(query: RetrievalQuery, key: str) -> list[str]:
    raw_values = query.filters.get(key)
    if not isinstance(raw_values, list):
        return []
    return [str(item) for item in raw_values if str(item)]


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _policy_context_int(query: RetrievalQuery, key: str) -> int | None:
    direct = _positive_int(query.filters.get(key))
    if direct is not None:
        return direct
    policy = query.filters.get("search_policy")
    if not isinstance(policy, dict):
        return None
    policy_value = _positive_int(policy.get(key))
    if policy_value is not None:
        return policy_value
    context = policy.get("context")
    if isinstance(context, dict):
        return _positive_int(context.get(key))
    return None


def _metadata_values(metadata: dict, *field_names: str) -> list[str]:
    values: list[str] = []
    for field_name in field_names:
        raw_value = metadata.get(field_name)
        if isinstance(raw_value, list | tuple | set):
            values.extend(str(item) for item in raw_value if str(item))
        elif raw_value is not None and str(raw_value):
            values.append(str(raw_value))
    return values


def _matches_filter(metadata: dict, filter_values: list[str], *field_names: str) -> bool:
    if not filter_values:
        return False
    return bool(
        set(filter_values).intersection(set(_metadata_values(metadata, *field_names)))
    )


def _chapter_distance_adjustment(metadata: dict, current_chapter_index: int | None) -> float:
    if current_chapter_index is None:
        return 0.0
    hit_chapter_index = _positive_int(metadata.get("chapter_index"))
    if hit_chapter_index is None:
        return 0.0
    distance = abs(hit_chapter_index - current_chapter_index)
    if distance == 0:
        return 0.08
    if distance == 1:
        return 0.04
    if distance <= 3:
        return 0.02
    return 0.0


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


def _append_narrative_scoring_trace(
    *,
    result: RetrievalSearchResult,
    query: RetrievalQuery,
    rules: list[dict],
) -> RetrievalSearchResult:
    if result.trace is None or not rules:
        return result
    policy = query.filters.get("search_policy")
    profile = "default"
    if isinstance(policy, dict):
        raw_profile = policy.get("profile")
        if isinstance(raw_profile, str) and raw_profile.strip():
            profile = raw_profile.strip().lower()
    details = dict(result.trace.details or {})
    details["narrative_scoring"] = {
        "profile": profile,
        "rules": rules,
    }
    return result.model_copy(
        update={"trace": result.trace.model_copy(update={"details": details})}
    )


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
        domain_path_prefix = (
            str(query.filters.get("domain_path_prefix") or "").strip().lower()
        )

        scored_hits: list[tuple[float, int, RetrievalHit]] = []
        narrative_rules: list[dict] = []
        scene_refs = _filter_values(query, "scene_refs")
        character_refs = _filter_values(query, "character_refs")
        pov_character_refs = _filter_values(query, "pov_character_refs")
        foreshadow_refs = _filter_values(query, "foreshadow_refs")
        foreshadow_statuses = _filter_values(query, "foreshadow_statuses")
        allowed_canon_statuses = set(_filter_values(query, "canon_statuses"))
        allowed_branch_ids = set(_filter_values(query, "branch_ids"))
        current_chapter_index = (
            _policy_context_int(query, "current_chapter_index")
            or _policy_context_int(query, "target_chapter_index")
        )
        for index, hit in enumerate(result.hits):
            metadata = dict(hit.metadata)
            title = str(metadata.get("title") or "").lower()
            domain_path = str(metadata.get("domain_path") or "").lower()
            tags = " ".join(str(item).lower() for item in metadata.get("tags") or [])

            boost = 0.0
            boosts: dict[str, float] = {}
            penalties: dict[str, float] = {}
            if normalized_query and normalized_query in title:
                boost += 0.12
                boosts["title_exact"] = 0.12
            if domain_path_prefix and domain_path.startswith(domain_path_prefix):
                boost += 0.08
                boosts["domain_path_prefix"] = 0.08

            title_matches = sum(1 for token in query_tokens if token in title)
            path_matches = sum(1 for token in query_tokens if token in domain_path)
            tag_matches = sum(1 for token in query_tokens if token in tags)
            if title_matches:
                boosts["title_token_match"] = min(title_matches, 3) * 0.03
                boost += boosts["title_token_match"]
            if path_matches:
                boosts["domain_path_token_match"] = min(path_matches, 3) * 0.02
                boost += boosts["domain_path_token_match"]
            if tag_matches:
                boosts["tag_token_match"] = min(tag_matches, 2) * 0.01
                boost += boosts["tag_token_match"]

            if _matches_filter(metadata, scene_refs, "scene_ref", "scene_refs"):
                boosts["scene_match"] = 0.2
                boost += boosts["scene_match"]
            if _matches_filter(
                metadata,
                character_refs,
                "character_refs",
                "mentioned_character_refs",
                "pov_character_ref",
                "pov_character_refs",
            ):
                boosts["character_match"] = 0.12
                boost += boosts["character_match"]
            if _matches_filter(
                metadata,
                pov_character_refs,
                "pov_character_ref",
                "pov_character_refs",
                "character_refs",
            ):
                boosts["pov_character_match"] = 0.16
                boost += boosts["pov_character_match"]
            if _matches_filter(
                metadata,
                foreshadow_refs,
                "foreshadow_ref",
                "foreshadow_refs",
            ):
                boosts["foreshadow_match"] = 0.12
                boost += boosts["foreshadow_match"]
            if _matches_filter(
                metadata,
                foreshadow_statuses,
                "foreshadow_status",
                "foreshadow_statuses",
            ):
                boosts["foreshadow_status_match"] = 0.08
                boost += boosts["foreshadow_status_match"]

            chapter_distance_boost = _chapter_distance_adjustment(
                metadata,
                current_chapter_index,
            )
            if chapter_distance_boost:
                boosts["chapter_distance"] = chapter_distance_boost
                boost += chapter_distance_boost

            canon_statuses = _metadata_values(
                metadata,
                "canon_status",
                "canon_statuses",
            )
            if (
                any(
                    status in {"superseded", "rejected", "draft"}
                    for status in canon_statuses
                )
                and not allowed_canon_statuses.intersection(canon_statuses)
            ):
                penalties["non_canonical_status"] = -0.25
                boost += penalties["non_canonical_status"]
            branch_ids = _metadata_values(metadata, "branch_id", "branch_ids")
            if (
                allowed_branch_ids
                and branch_ids
                and not allowed_branch_ids.intersection(branch_ids)
            ):
                penalties["branch_mismatch"] = -0.3
                boost += penalties["branch_mismatch"]

            adjusted_score = round(float(hit.score) + boost, 6)
            scored_hits.append((adjusted_score, index, hit))
            if boosts or penalties:
                narrative_rules.append(
                    {
                        "hit_id": hit.hit_id,
                        "boosts": boosts,
                        "penalties": penalties,
                        "final_adjustment": round(boost, 6),
                    }
                )

        reranked_hits = [
            hit.model_copy(update={"score": score, "rank": rank})
            for rank, (score, _, hit) in enumerate(
                sorted(scored_hits, key=lambda item: (-item[0], item[1])),
                start=1,
            )
        ]
        reranked_result = result.model_copy(update={"hits": reranked_hits})
        reranked_result = _append_narrative_scoring_trace(
            result=reranked_result,
            query=query,
            rules=narrative_rules,
        )
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
