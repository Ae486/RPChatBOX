"""Hybrid retrieval using an explicit fusion strategy."""

from __future__ import annotations

from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult
from .fusion_strategy import RrfFusionStrategy
from .keyword_retriever import KeywordRetriever
from .pipeline_slots import FusionStrategy
from .pipeline_runner import retrieve_and_fuse
from .semantic_retriever import SemanticRetriever


class HybridRetriever:
    """Convenience composite retriever for keyword + semantic fusion."""

    def __init__(
        self,
        *,
        keyword_retriever: KeywordRetriever,
        semantic_retriever: SemanticRetriever,
        fusion_strategy: FusionStrategy | None = None,
    ) -> None:
        self._keyword_retriever = keyword_retriever
        self._semantic_retriever = semantic_retriever
        self._fusion_strategy = fusion_strategy or RrfFusionStrategy()

    async def search(self, query: RetrievalQuery) -> RetrievalSearchResult:
        return await retrieve_and_fuse(
            query=query,
            retrievers=[self._keyword_retriever, self._semantic_retriever],
            fusion_strategy=self._fusion_strategy,
        )
