"""Active-story longform read/list/activate facade."""

from __future__ import annotations

from rp.models.story_runtime import (
    ChapterWorkspaceSnapshot,
    StoryActivationResult,
    StorySession,
)
from .story_activation_service import StoryActivationService
from .story_session_service import StorySessionService


class StoryRuntimeController:
    """Thin facade for activation and read-model access."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        story_activation_service: StoryActivationService,
    ) -> None:
        self._story_session_service = story_session_service
        self._story_activation_service = story_activation_service

    def activate_workspace(self, *, workspace_id: str) -> StoryActivationResult:
        return self._story_activation_service.activate_workspace(workspace_id=workspace_id)

    def list_sessions(self) -> list[StorySession]:
        return self._story_session_service.list_sessions()

    def read_session(self, *, session_id: str) -> ChapterWorkspaceSnapshot:
        session = self._require_session(session_id)
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=session.current_chapter_index,
        )

    def read_chapter(self, *, session_id: str, chapter_index: int) -> ChapterWorkspaceSnapshot:
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=chapter_index,
        )

    def _require_session(self, session_id: str) -> StorySession:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return session
