"""Stable response builders for retrieval result views."""

from __future__ import annotations

import time
import uuid

from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from .search_utils import build_filters_applied


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _stable_hit_metadata(
    *,
    hit: RetrievalHit,
    result_kind: str,
) -> dict[str, object]:
    metadata = dict(hit.metadata)
    metadata["title"] = metadata.get("title")
    metadata["domain"] = metadata.get("domain") or hit.domain.value
    metadata["domain_path"] = metadata.get("domain_path") or hit.domain_path
    metadata["section_id"] = metadata.get("section_id")
    metadata["section_part"] = int(metadata.get("section_part") or 0)
    metadata["parent_section_part"] = int(metadata.get("parent_section_part") or metadata["section_part"])
    metadata["view_part"] = int(metadata.get("view_part") or metadata["section_part"])
    metadata["chunk_view"] = str(metadata.get("chunk_view") or "primary")
    metadata["chunk_size"] = str(metadata.get("chunk_size") or "default")
    metadata["chunk_pass"] = int(metadata.get("chunk_pass") or 0)
    metadata["chunk_view_priority"] = int(metadata.get("chunk_view_priority") or 0)
    metadata["chunk_family_id"] = metadata.get("chunk_family_id") or (
        f"{metadata['section_id']}:{metadata['parent_section_part']}"
        if metadata.get("section_id") is not None
        else hit.hit_id
    )
    metadata["char_start"] = metadata.get("char_start")
    metadata["char_end"] = metadata.get("char_end")
    metadata["asset_id"] = metadata.get("asset_id")
    metadata["collection_id"] = metadata.get("collection_id")
    metadata["source_ref"] = metadata.get("source_ref")
    metadata["commit_id"] = metadata.get("commit_id")
    metadata["document_title"] = metadata.get("document_title") or metadata.get("title")
    metadata["document_summary"] = metadata.get("document_summary")
    metadata["page_no"] = metadata.get("page_no")
    metadata["page_label"] = metadata.get("page_label")
    metadata["page_ref"] = metadata.get("page_ref")
    metadata["image_caption"] = metadata.get("image_caption")
    metadata["context_header"] = metadata.get("context_header")
    metadata["contextual_text_version"] = metadata.get("contextual_text_version")
    metadata["result_kind"] = result_kind
    return metadata


class ChunkResultBuilder:
    """Normalize chunk hits into a stable retrieval response."""

    def build(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        started = time.perf_counter()
        trace = result.trace
        warnings = _dedupe_preserve_order(
            [*list(result.warnings), *(list(trace.warnings) if trace is not None else [])]
        )
        hits = [
            hit.model_copy(
                update={
                    "rank": index,
                    "metadata": _stable_hit_metadata(hit=hit, result_kind="chunk"),
                }
            )
            for index, hit in enumerate(result.hits[: query.top_k], start=1)
        ]

        if trace is not None:
            trace = trace.model_copy(
                update={
                    "result_kind": "chunk",
                    "filters_applied": build_filters_applied(query),
                    "pipeline_stages": _dedupe_preserve_order(
                        [*(trace.pipeline_stages or []), "chunk_result_builder"]
                    ),
                    "returned_count": len(hits),
                    "timings": {
                        **dict(trace.timings or {}),
                        "chunk_builder_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                    "warnings": warnings,
                }
            )

        return result.model_copy(
            update={
                "query": query.text_query or "",
                "hits": hits,
                "trace": trace,
                "warnings": warnings,
            }
        )


class DocumentResultBuilder:
    """Collapse chunk hits into one best hit per asset/document."""

    def build(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult:
        started = time.perf_counter()
        grouped: dict[str, RetrievalHit] = {}
        for hit in result.hits:
            asset_id = str(hit.metadata.get("asset_id") or hit.hit_id)
            current = grouped.get(asset_id)
            if current is None or hit.score > current.score:
                grouped[asset_id] = hit

        warnings = _dedupe_preserve_order(list(result.warnings))
        document_hits = []
        for index, item in enumerate(
            sorted(grouped.values(), key=lambda hit: hit.score, reverse=True)[: query.top_k],
            start=1,
        ):
            asset_id = str(item.metadata.get("asset_id") or item.hit_id)
            document_hits.append(
                item.model_copy(
                    update={
                        "hit_id": f"doc:{asset_id}",
                        "rank": index,
                        "metadata": _stable_hit_metadata(hit=item, result_kind="document"),
                    }
                )
            )

        timings = dict(result.trace.timings if result.trace is not None else {})
        timings["document_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=document_hits,
            trace=RetrievalTrace(
                trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                query_id=query.query_id,
                route="retrieval.documents",
                result_kind="document",
                filters_applied=build_filters_applied(query),
                retriever_routes=list(result.trace.retriever_routes if result.trace is not None else []),
                pipeline_stages=_dedupe_preserve_order(
                    [*(result.trace.pipeline_stages if result.trace is not None else []), "document_result_builder"]
                ),
                reranker_name=result.trace.reranker_name if result.trace is not None else None,
                candidate_count=len(grouped),
                returned_count=len(document_hits),
                timings=timings,
                warnings=warnings,
                details=dict(result.trace.details if result.trace is not None else {}),
            ),
            warnings=warnings,
        )
