"""Hybrid retrieval using reciprocal-rank fusion."""

from __future__ import annotations

import time
import uuid

from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from .keyword_retriever import KeywordRetriever
from .rrf_fusion import reciprocal_rank_fusion
from .semantic_retriever import SemanticRetriever
from .search_utils import build_filters_applied


class HybridRetriever:
    """Combine keyword and semantic retrieval with graceful degradation."""

    def __init__(
        self,
        *,
        keyword_retriever: KeywordRetriever,
        semantic_retriever: SemanticRetriever,
    ) -> None:
        self._keyword_retriever = keyword_retriever
        self._semantic_retriever = semantic_retriever

    async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
        started = time.perf_counter()
        keyword_result = await self._keyword_retriever.search(query)
        semantic_result = await self._semantic_retriever.search(query)

        warnings = [*keyword_result.warnings, *semantic_result.warnings]
        rankings = []
        if keyword_result.hits:
            rankings.append([hit.model_dump(mode="json") for hit in keyword_result.hits])
        if semantic_result.hits:
            rankings.append([hit.model_dump(mode="json") for hit in semantic_result.hits])

        if not rankings:
            route = "retrieval.hybrid.empty"
            hits: list[RetrievalHit] = []
        elif len(rankings) == 1:
            source = keyword_result if keyword_result.hits else semantic_result
            route = f"{source.trace.route}.degraded"
            hits = source.hits[: query.top_k]
        else:
            route = "retrieval.hybrid.rrf"
            fused = reciprocal_rank_fusion(rankings)
            hits = [
                RetrievalHit.model_validate({**item, "rank": index})
                for index, item in enumerate(fused[: query.top_k], start=1)
            ]

        candidate_count = len({hit.hit_id for hit in [*keyword_result.hits, *semantic_result.hits]})
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=hits,
            trace=RetrievalTrace(
                trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                query_id=query.query_id,
                route=route,
                filters_applied=build_filters_applied(query),
                candidate_count=candidate_count,
                returned_count=len(hits),
                timings={
                    "hybrid_ms": round((time.perf_counter() - started) * 1000, 3),
                },
                warnings=warnings,
            ),
            warnings=warnings,
        )
