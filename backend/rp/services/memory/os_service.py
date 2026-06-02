"""Facade over RetrievalBroker for RP Phase A."""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol, TypeVar

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
from rp.services.retrieval.broker import RetrievalBroker


_In = TypeVar("_In")
_Out = TypeVar("_Out")


class RetrievalBrokerProtocol(Protocol):
    """Structural contract for the broker operations exposed by this facade."""

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        ...

    async def get_summary(
        self,
        input_model: MemoryGetSummaryInput,
    ) -> SummaryReadResult:
        ...

    async def search_recall(
        self,
        input_model: MemorySearchRecallInput,
    ) -> RetrievalSearchResult:
        ...

    async def search_archival(
        self,
        input_model: MemorySearchArchivalInput,
    ) -> RetrievalSearchResult:
        ...

    async def list_versions(
        self,
        input_model: MemoryListVersionsInput,
    ) -> VersionListResult:
        ...

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        ...


class MemoryOsService:
    """Thin facade that keeps a stable entry point for tool providers."""

    def __init__(self, *, retrieval_broker: RetrievalBrokerProtocol | None = None):
        self._retrieval_broker = retrieval_broker or RetrievalBroker()

    async def _delegate(
        self,
        broker_method: Callable[[_In], Awaitable[_Out]],
        input_model: _In,
    ) -> _Out:
        return await broker_method(input_model)

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        """Expose memory.get_state by delegating to the retrieval broker."""
        return await self._delegate(self._retrieval_broker.get_state, input_model)

    async def get_summary(
        self,
        input_model: MemoryGetSummaryInput,
    ) -> SummaryReadResult:
        """Expose memory.get_summary by delegating to the retrieval broker."""
        return await self._delegate(self._retrieval_broker.get_summary, input_model)

    async def search_recall(
        self,
        input_model: MemorySearchRecallInput,
    ) -> RetrievalSearchResult:
        """Expose memory.search_recall by delegating to the retrieval broker."""
        return await self._delegate(self._retrieval_broker.search_recall, input_model)

    async def search_archival(
        self,
        input_model: MemorySearchArchivalInput,
    ) -> RetrievalSearchResult:
        """Expose memory.search_archival by delegating to the retrieval broker."""
        return await self._delegate(
            self._retrieval_broker.search_archival,
            input_model,
        )

    async def list_versions(
        self,
        input_model: MemoryListVersionsInput,
    ) -> VersionListResult:
        """Expose memory.list_versions by delegating to the retrieval broker."""
        return await self._delegate(self._retrieval_broker.list_versions, input_model)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        """Expose memory.read_provenance by delegating to the retrieval broker."""
        return await self._delegate(
            self._retrieval_broker.read_provenance,
            input_model,
        )

