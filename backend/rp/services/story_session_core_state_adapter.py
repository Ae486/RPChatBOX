"""Adapter over StorySession compatibility mirror persistence for fallback reads."""

from __future__ import annotations

from copy import deepcopy

from rp.models.story_runtime import StorySession

from .story_session_service import StorySessionService


class StorySessionCoreStateAdapter:
    """Read legacy authoritative mirror state through StorySessionService."""

    def __init__(
        self,
        story_session_service: StorySessionService,
        *,
        default_story_id: str | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._default_story_id = default_story_id

    def _get_story_session(
        self,
        *,
        story_id: str | None = None,
        session_id: str | None = None,
    ) -> StorySession | None:
        if session_id:
            return self._story_session_service.get_session(session_id)
        resolved_story_id = story_id or self._default_story_id
        if not resolved_story_id:
            return None
        return self._story_session_service.get_latest_session_for_story(resolved_story_id)

    def get_story_session(
        self,
        *,
        story_id: str | None = None,
        session_id: str | None = None,
    ) -> StorySession | None:
        return self._get_story_session(story_id=story_id, session_id=session_id)

    def get_state_payload(
        self,
        *,
        story_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[StorySession | None, dict]:
        session = self.get_story_session(story_id=story_id, session_id=session_id)
        if session is None:
            return None, {}
        return session, deepcopy(session.current_state_json)
