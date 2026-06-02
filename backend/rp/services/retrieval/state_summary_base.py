"""Shared block-fallback read infra for retrieval state and summary brokers."""

from __future__ import annotations

from sqlmodel import Session

from config import get_settings
from rp.services.projection.builder_context_service import (
    BuilderProjectionContextService,
)
from rp.services.projection.chapter_workspace_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.memory.inspection_read_service import MemoryInspectionReadService
from rp.services.projection.state_service import ProjectionStateService
from rp.services.proposal.repository import ProposalRepository
from rp.services.memory.rp_block_read_service import RpBlockReadService
from rp.services.story.session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story.session_service import StorySessionService
from rp.services.memory.version_history_read_service import VersionHistoryReadService

from .context import RetrievalBrokerContext


class StateSummaryReadBase:
    """Own block-fallback helpers shared by state and summary read paths."""

    def __init__(self, *, context: RetrievalBrokerContext) -> None:
        self._context = context

    def _build_rp_block_read_service(self, session: Session) -> RpBlockReadService:
        story_session_service = StorySessionService(session)
        proposal_repository = ProposalRepository(session)
        core_state_store_repository = CoreStateStoreRepository(session)
        store_read_enabled = bool(
            get_settings().rp_memory_core_state_store_read_enabled
        )
        projection_state_service = ProjectionStateService(
            story_session_service=story_session_service,
            adapter=ChapterWorkspaceProjectionAdapter(
                story_session_service,
                default_story_id=self._context.default_story_id,
            ),
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
        )
        builder_projection_context_service = BuilderProjectionContextService(
            projection_state_service
        )
        core_state_adapter = StorySessionCoreStateAdapter(
            story_session_service,
            default_story_id=self._context.default_story_id,
        )
        version_history_read_service = VersionHistoryReadService(
            adapter=core_state_adapter,
            proposal_repository=proposal_repository,
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
        )
        memory_inspection_read_service = MemoryInspectionReadService(
            story_session_service=story_session_service,
            builder_projection_context_service=builder_projection_context_service,
            proposal_repository=proposal_repository,
            version_history_read_service=version_history_read_service,
            core_state_store_repository=core_state_store_repository,
            store_read_enabled=store_read_enabled,
        )
        return RpBlockReadService(
            story_session_service=story_session_service,
            builder_projection_context_service=builder_projection_context_service,
            core_state_store_repository=core_state_store_repository,
            memory_inspection_read_service=memory_inspection_read_service,
            store_read_enabled=store_read_enabled,
        )

    def _current_session_id(self, session: Session) -> str | None:
        if self._context.runtime_identity is not None:
            return self._context.runtime_identity.session_id
        if not self._context.default_story_id:
            return None
        current_session = StorySessionService(session).get_latest_session_for_story(
            self._context.default_story_id
        )
        if current_session is None:
            return None
        return current_session.session_id
