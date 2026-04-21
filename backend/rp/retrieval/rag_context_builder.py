"""Build a compact RAG-oriented view from retrieval hits."""

from __future__ import annotations

from rp.models.memory_crud import RetrievalSearchResult


class RagContextBuilder:
    """Keep Phase B rag context thin and chunk-centric."""

    def build(self, result: RetrievalSearchResult) -> RetrievalSearchResult:
        seen_assets: set[str] = set()
        compact_hits = []
        for hit in result.hits:
            asset_id = str(hit.metadata.get("asset_id") or "")
            key = asset_id or hit.hit_id
            if key in seen_assets:
                continue
            seen_assets.add(key)
            compact_hits.append(
                hit.model_copy(
                    update={
                        "excerpt_text": hit.excerpt_text[:800],
                    }
                )
            )
        return result.model_copy(update={"hits": compact_hits})
