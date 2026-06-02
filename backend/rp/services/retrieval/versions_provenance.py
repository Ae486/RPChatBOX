"""Versions and provenance layer dispatch for retrieval reads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlmodel import Session

from rp.models.dsl import Layer
from rp.models.memory_crud import (
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProvenanceResult,
    VersionListResult,
)

from .context import RetrievalBrokerContext


class _VersionsProvenanceReadService(Protocol):
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


_ReadServiceFactory = Callable[[Session], _VersionsProvenanceReadService]


class VersionsProvenanceBroker:
    """Route version/provenance reads to the read service for the target layer."""

    def __init__(
        self,
        *,
        context: RetrievalBrokerContext,
        core_state_read_service_factory: _ReadServiceFactory,
        projection_read_service_factory: _ReadServiceFactory,
    ) -> None:
        self._context = context
        self._core_state_read_service_factory = core_state_read_service_factory
        self._projection_read_service_factory = projection_read_service_factory

    async def list_versions(
        self,
        input_model: MemoryListVersionsInput,
    ) -> VersionListResult:
        with self._context.session_scope() as session:
            service = (
                self._projection_read_service_factory(session)
                if (input_model.target_ref.layer == Layer.CORE_STATE_PROJECTION)
                else self._core_state_read_service_factory(session)
            )
            return await service.list_versions(input_model)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        with self._context.session_scope() as session:
            service = (
                self._projection_read_service_factory(session)
                if (input_model.target_ref.layer == Layer.CORE_STATE_PROJECTION)
                else self._core_state_read_service_factory(session)
            )
            return await service.read_provenance(input_model)
