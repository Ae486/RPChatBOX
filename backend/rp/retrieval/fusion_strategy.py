"""Fusion strategies for retrieval rankings."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from .rrf_fusion import reciprocal_rank_fusion
from .search_utils import build_filters_applied


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class RrfFusionStrategy:
    """Fuse keyword and semantic rankings with reciprocal-rank fusion."""

    def fuse(
        self,
        *,
        query: RetrievalQuery,
        retrieved_results: Sequence[RetrievalSearchResult],
    ) -> RetrievalSearchResult:
        started = time.perf_counter()
        warnings = _dedupe_preserve_order(
            [warning for result in retrieved_results for warning in result.warnings]
        )
        timings: dict[str, float] = {}
        rankings: list[list[dict[str, object]]] = []
        non_empty_results: list[RetrievalSearchResult] = []
        retriever_routes: list[str] = []
        pipeline_stages: list[str] = ["retrieve", "fusion"]

        for result in retrieved_results:
            if result.trace is not None:
                timings.update(result.trace.timings)
                retriever_routes.extend(result.trace.retriever_routes or [result.trace.route])
                pipeline_stages.extend(result.trace.pipeline_stages)
            if result.hits:
                rankings.append([hit.model_dump(mode="json") for hit in result.hits])
                non_empty_results.append(result)

        if not rankings:
            route = "retrieval.hybrid.empty"
            hits: list[RetrievalHit] = []
            candidate_count = 0
        elif len(rankings) == 1:
            source = non_empty_results[0]
            route = f"{source.trace.route if source.trace is not None else 'retrieval.hybrid.single'}.degraded"
            hits = [
                hit.model_copy(update={"rank": index})
                for index, hit in enumerate(source.hits[: query.top_k], start=1)
            ]
            candidate_count = len(source.hits)
        else:
            route = "retrieval.hybrid.rrf"
            fused = reciprocal_rank_fusion(rankings)
            hits = [
                RetrievalHit.model_validate({**item, "rank": index})
                for index, item in enumerate(fused[: query.top_k], start=1)
            ]
            candidate_count = len({hit.hit_id for result in non_empty_results for hit in result.hits})

        timings["fusion_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=hits,
            trace=RetrievalTrace(
                trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                query_id=query.query_id,
                route=route,
                result_kind="chunk",
                filters_applied=build_filters_applied(query),
                retriever_routes=_dedupe_preserve_order(retriever_routes),
                pipeline_stages=_dedupe_preserve_order(pipeline_stages),
                candidate_count=candidate_count,
                returned_count=len(hits),
                timings=timings,
                warnings=warnings,
            ),
            warnings=warnings,
        )
