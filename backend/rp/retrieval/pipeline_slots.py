"""Protocols for the explicit retrieval query pipeline slots."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult


class QueryPreprocessor(Protocol):
    """Normalize retrieval queries before they enter the pipeline."""

    def preprocess(self, query: RetrievalQuery) -> RetrievalQuery: ...


class Retriever(Protocol):
    """Produce retrieval candidates for a normalized query."""

    async def search(self, query: RetrievalQuery) -> RetrievalSearchResult: ...


class FusionStrategy(Protocol):
    """Merge one or more retrieval result sets into a single ranking."""

    def fuse(
        self,
        *,
        query: RetrievalQuery,
        retrieved_results: Sequence[RetrievalSearchResult],
    ) -> RetrievalSearchResult: ...


class Reranker(Protocol):
    """Optionally rerank already-fused retrieval results."""

    async def rerank(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult: ...


class ResultBuilder(Protocol):
    """Build a stable retrieval response view for a given query."""

    def build(
        self,
        *,
        query: RetrievalQuery,
        result: RetrievalSearchResult,
    ) -> RetrievalSearchResult: ...
