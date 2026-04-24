"""Build a compact RAG-oriented view from retrieval hits."""

from __future__ import annotations

import time

from rp.models.memory_crud import RetrievalSearchResult

from .context_rendering import build_rag_excerpt


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


class RagContextBuilder:
    """Keep Phase B rag context thin and chunk-centric."""

    def build(self, result: RetrievalSearchResult) -> RetrievalSearchResult:
        started = time.perf_counter()
        seen_assets: set[str] = set()
        compact_hits = []
        for hit in result.hits:
            metadata = dict(hit.metadata)
            asset_id = str(metadata.get("asset_id") or "")
            key = asset_id or hit.hit_id
            if key in seen_assets:
                continue
            seen_assets.add(key)
            excerpt, header_lines, normalized_summary = build_rag_excerpt(
                context_header=str(metadata.get("context_header") or "") or None,
                title=str(metadata.get("title") or metadata.get("document_title") or "") or None,
                domain_path=str(metadata.get("domain_path") or "") or None,
                source_ref=str(metadata.get("source_ref") or "") or None,
                document_summary=str(metadata.get("document_summary") or "") or None,
                page_no=metadata.get("page_no"),
                page_label=metadata.get("page_label"),
                image_caption=str(metadata.get("image_caption") or "") or None,
                snippet=hit.excerpt_text,
            )
            compact_hits.append(
                hit.model_copy(
                    update={
                        "excerpt_text": excerpt,
                        "metadata": {
                            **metadata,
                            "result_kind": "rag",
                            "rag_context_header": " | ".join(header_lines),
                            "rag_document_summary": normalized_summary,
                        },
                    }
                )
            )

        trace = result.trace
        if trace is not None:
            trace = trace.model_copy(
                update={
                    "result_kind": "rag",
                    "returned_count": len(compact_hits),
                    "pipeline_stages": _dedupe_preserve_order(
                        [*(trace.pipeline_stages or []), "rag_context_builder"]
                    ),
                    "timings": {
                        **dict(trace.timings or {}),
                        "rag_context_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                }
            )
        return result.model_copy(update={"hits": compact_hits, "trace": trace})
