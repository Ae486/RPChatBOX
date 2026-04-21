"""Top-level retrieval search service."""

from __future__ import annotations

import time
import uuid

from rp.models.memory_crud import RetrievalHit, RetrievalQuery, RetrievalSearchResult, RetrievalTrace
from rp.retrieval.embedder import Embedder
from rp.retrieval.hybrid_retriever import HybridRetriever
from rp.retrieval.keyword_retriever import KeywordRetriever
from rp.retrieval.rag_context_builder import RagContextBuilder
from rp.retrieval.semantic_retriever import SemanticRetriever
from rp.retrieval.search_utils import build_filters_applied


class RetrievalService:
    """Provide chunk, document, and RAG retrieval views over the same store."""

    def __init__(self, session, *, embedder: Embedder | None = None) -> None:
        self._session = session
        self._embedder = embedder or Embedder()
        self._keyword = KeywordRetriever(session)
        self._semantic = SemanticRetriever(session, embedder=self._embedder)
        self._hybrid = HybridRetriever(
            keyword_retriever=self._keyword,
            semantic_retriever=self._semantic,
        )
        self._rag_builder = RagContextBuilder()

    async def search_chunks(self, query: RetrievalQuery) -> RetrievalSearchResult:
        return await self._hybrid.search(query)

    async def search_documents(self, query: RetrievalQuery) -> RetrievalSearchResult:
        started = time.perf_counter()
        chunk_result = await self.search_chunks(query)
        grouped: dict[str, RetrievalHit] = {}
        for hit in chunk_result.hits:
            asset_id = str(hit.metadata.get("asset_id") or hit.hit_id)
            current = grouped.get(asset_id)
            if current is None or hit.score > current.score:
                grouped[asset_id] = hit
        document_hits = [
            item.model_copy(
                update={
                    "hit_id": f"doc:{index}:{item.metadata.get('asset_id')}",
                    "rank": index,
                    "metadata": {**dict(item.metadata), "result_kind": "document"},
                }
            )
            for index, item in enumerate(
                sorted(grouped.values(), key=lambda hit: hit.score, reverse=True)[: query.top_k],
                start=1,
            )
        ]
        warnings = list(chunk_result.warnings)
        return RetrievalSearchResult(
            query=query.text_query or "",
            hits=document_hits,
            trace=RetrievalTrace(
                trace_id=f"trace_{uuid.uuid4().hex[:10]}",
                query_id=query.query_id,
                route="retrieval.documents",
                filters_applied=build_filters_applied(query),
                candidate_count=len(grouped),
                returned_count=len(document_hits),
                timings={"document_ms": round((time.perf_counter() - started) * 1000, 3)},
                warnings=warnings,
            ),
            warnings=warnings,
        )

    async def rag_context(self, query: RetrievalQuery) -> RetrievalSearchResult:
        chunk_result = await self.search_chunks(query)
        return self._rag_builder.build(chunk_result)
