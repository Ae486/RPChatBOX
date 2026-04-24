"""Shared helpers for running retrieval pipeline stages."""

from __future__ import annotations

from collections.abc import Sequence

from rp.models.memory_crud import RetrievalQuery, RetrievalSearchResult

from .pipeline_slots import FusionStrategy, Retriever


async def retrieve_and_fuse(
    *,
    query: RetrievalQuery,
    retrievers: Sequence[Retriever],
    fusion_strategy: FusionStrategy,
) -> RetrievalSearchResult:
    retrieved_results = [await retriever.search(query) for retriever in retrievers]
    return fusion_strategy.fuse(
        query=query,
        retrieved_results=retrieved_results,
    )
