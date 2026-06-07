"""Unified retrieval broker for RP memory reads."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from config import get_settings
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.memory.crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    ProvenanceResult,
    RetrievalHit,
    RetrievalSearchResult,
    StateReadResult,
    SummaryReadResult,
    VersionListResult,
)
from rp.services.projection.chapter_workspace_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state.backfill_service import CoreStateBackfillService
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state.read_service import CoreStateReadService
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.proposal.repository import ProposalRepository
from rp.services.memory.provenance_read_service import ProvenanceReadService
from rp.services.projection.read_service import ProjectionReadService
from .context import RetrievalBrokerContext
from .search import SearchBroker
from .state import StateBroker
from .summary import SummaryBroker
from .versions_provenance import VersionsProvenanceBroker
from rp.services.story.session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story.session_service import StorySessionService
from rp.services.memory.version_history_read_service import VersionHistoryReadService


class RetrievalBroker:
    """Route memory.search_* to the retrieval-core while keeping other surfaces stable."""

    # Pure composition facade (post-T6 decomposition): builds the shared
    # RetrievalBrokerContext and the 4 sub-brokers (search / state / summary /
    # versions-provenance), then one-line-delegates all 7 public methods.
    # The two read-service builders remain here as the factory-default providers
    # injected into the read brokers (Route A); the context-compat shims at the
    # bottom are retained for historical callers/tests.

    def __init__(
        self,
        *,
        default_story_id: str | None = None,
        runtime_identity: MemoryRuntimeIdentity | dict[str, Any] | None = None,
        session: Session | None = None,
        retrieval_service_factory=None,
        core_state_read_service_factory=None,
        projection_read_service_factory=None,
        langfuse_service=None,
    ) -> None:
        self._ctx = RetrievalBrokerContext(
            default_story_id=default_story_id,
            runtime_identity=runtime_identity,
            session=session,
        )
        self._default_story_id = self._ctx.default_story_id
        self._runtime_identity = self._ctx.runtime_identity
        self._session = self._ctx.session
        self._core_state_read_service_factory = core_state_read_service_factory or (
            lambda session: self._build_core_state_read_service(session)
        )
        self._projection_read_service_factory = projection_read_service_factory or (
            lambda session: self._build_projection_read_service(session)
        )
        self._state = StateBroker(
            context=self._ctx,
            core_state_read_service_factory=self._core_state_read_service_factory,
        )
        self._summary = SummaryBroker(
            context=self._ctx,
            projection_read_service_factory=self._projection_read_service_factory,
        )
        self._versions_provenance = VersionsProvenanceBroker(
            context=self._ctx,
            core_state_read_service_factory=self._core_state_read_service_factory,
            projection_read_service_factory=self._projection_read_service_factory,
        )
        self._search = SearchBroker(
            context=self._ctx,
            retrieval_service_factory=retrieval_service_factory,
            langfuse_service=langfuse_service,
        )

    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult:
        return await self._state.get_state(input_model)

    async def get_summary(
        self, input_model: MemoryGetSummaryInput
    ) -> SummaryReadResult:
        return await self._summary.get_summary(input_model)

    async def search_recall(
        self,
        input_model: MemorySearchRecallInput,
    ) -> RetrievalSearchResult:
        return await self._search.search_recall(input_model)

    def expand_hit(self, hit: RetrievalHit) -> dict[str, Any]:
        return self._search.expand_hit(hit)

    async def search_archival(
        self,
        input_model: MemorySearchArchivalInput,
    ) -> RetrievalSearchResult:
        return await self._search.search_archival(input_model)

    async def list_versions(
        self,
        input_model: MemoryListVersionsInput,
    ) -> VersionListResult:
        return await self._versions_provenance.list_versions(input_model)

    async def read_provenance(
        self,
        input_model: MemoryReadProvenanceInput,
    ) -> ProvenanceResult:
        return await self._versions_provenance.read_provenance(input_model)

    def _build_core_state_read_service(self, session: Session) -> CoreStateReadService:
        story_session_service = StorySessionService(session)
        adapter = StorySessionCoreStateAdapter(
            story_session_service,
            default_story_id=self._default_story_id,
        )
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        store_read_enabled = bool(
            get_settings().rp_memory_core_state_store_read_enabled
        )
        runtime_owned_read = self._runtime_identity is not None
        core_state_as_of_resolver = (
            CoreStateAsOfResolver(
                session=session,
                repository=core_state_store_repository,
            )
            if runtime_owned_read
            else None
        )
        backfill_service = CoreStateBackfillService(
            story_session_service=story_session_service,
            proposal_repository=proposal_repository,
            core_state_store_repository=core_state_store_repository,
        )
        return CoreStateReadService(
            adapter=adapter,
            version_history_read_service=VersionHistoryReadService(
                adapter=adapter,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
                store_read_enabled=store_read_enabled,
            ),
            provenance_read_service=ProvenanceReadService(
                adapter=adapter,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
                store_read_enabled=store_read_enabled,
            ),
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled or runtime_owned_read,
            core_state_backfill_service=backfill_service,
            runtime_identity=self._runtime_identity,
            core_state_as_of_resolver=core_state_as_of_resolver,
        )

    def _build_projection_read_service(self, session: Session) -> ProjectionReadService:
        story_session_service = StorySessionService(session)
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        return ProjectionReadService(
            adapter=ChapterWorkspaceProjectionAdapter(
                story_session_service,
                default_story_id=self._default_story_id,
            ),
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=bool(
                get_settings().rp_memory_core_state_store_read_enabled
            ),
            core_state_backfill_service=CoreStateBackfillService(
                story_session_service=story_session_service,
                proposal_repository=proposal_repository,
                core_state_store_repository=core_state_store_repository,
            ),
            runtime_identity=self._runtime_identity,
        )

    @staticmethod
    def _normalize_runtime_identity(
        runtime_identity: object | None,
    ) -> MemoryRuntimeIdentity | None:
        return RetrievalBrokerContext.normalize_runtime_identity(runtime_identity)

    def _effective_runtime_identity(
        self,
        filters: dict[str, object],
    ) -> MemoryRuntimeIdentity | None:
        return self._ctx.effective_runtime_identity(filters)

    def _session_scope(self):
        return self._ctx.session_scope()

