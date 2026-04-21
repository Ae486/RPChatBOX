"""Facade over RetrievalBroker for RP Phase A."""
from __future__ import annotations

from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    ProvenanceResult,
    RetrievalSearchResult,
    StateReadResult,
    SummaryReadResult,
    VersionListResult,
)
from rp.services.retrieval_broker import RetrievalBroker


class MemoryOsService:
    """Thin facade that keeps a stable entry point for tool providers."""

    def __init__(self, *, retrieval_broker: RetrievalBroker | None = None):
        self._retrieval_broker = retrieval_broker or RetrievalBroker()

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        return await self._retrieval_broker.get_state(input_model)

    async def get_summary(self, input_model: MemoryGetSummaryInput) -> SummaryReadResult:
        return await self._retrieval_broker.get_summary(input_model)

    async def search_recall(
        self,
        input_model: MemorySearchRecallInput,
    ) -> RetrievalSearchResult:
        return await self._retrieval_broker.search_recall(input_model)

    async def search_archival(
        self,
        input_model: MemorySearchArchivalInput,
    ) -> RetrievalSearchResult:
        return await self._retrieval_broker.search_archival(input_model)

    async def list_versions(
        self,
        input_model: MemoryListVersionsInput,
    ) -> VersionListResult:
        return await self._retrieval_broker.list_versions(input_model)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        return await self._retrieval_broker.read_provenance(input_model)

