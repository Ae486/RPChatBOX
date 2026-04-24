"""Adapter over ChapterWorkspace compatibility mirror persistence for fallback reads."""

from __future__ import annotations

from copy import deepcopy

from rp.models.story_runtime import ChapterWorkspace, StorySession

from .story_session_service import StorySessionService


class ChapterWorkspaceProjectionAdapter:
    """Read legacy projection mirror state through StorySessionService."""

    def __init__(
        self,
        story_session_service: StorySessionService,
        *,
        default_story_id: str | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._default_story_id = default_story_id

    def get_current_chapter(
        self,
        *,
        story_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StorySession | None, ChapterWorkspace | None]:
        if session_id:
            session = self._story_session_service.get_session(session_id)
            if session is None:
                return None, None
            chapter = self._story_session_service.get_current_chapter(session.session_id)
            return session, chapter
        resolved_story_id = story_id or self._default_story_id
        if not resolved_story_id:
            return None, None
        session = self._story_session_service.get_latest_session_for_story(resolved_story_id)
        if session is None:
            return None, None
        chapter = self._story_session_service.get_current_chapter(session.session_id)
        return session, chapter

    def get_projection_payload(
        self,
        *,
        story_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StorySession | None, ChapterWorkspace | None, dict]:
        session, chapter = self.get_current_chapter(story_id=story_id, session_id=session_id)
        if chapter is None:
            return session, None, {}
        return session, chapter, deepcopy(chapter.builder_snapshot_json)
