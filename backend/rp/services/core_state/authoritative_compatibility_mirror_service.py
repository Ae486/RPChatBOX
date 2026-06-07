"""Compatibility mirror access for legacy authoritative session state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from rp.models.story.runtime import StorySession

from ..story.session_service import StorySessionService


@dataclass(frozen=True)
class MirrorStateReadResult:
    present: bool
    state: dict


class AuthoritativeCompatibilityMirrorService:
    """Read/write the legacy authoritative mirror without treating it as truth source."""

    def __init__(self, *, story_session_service: StorySessionService) -> None:
        self._story_session_service = story_session_service

    def read_mirror_state(
        self,
        *,
        session: StorySession | None = None,
        session_id: str | None = None,
    ) -> dict:
        resolved = session
        if resolved is None and session_id is not None:
            resolved = self._story_session_service.get_session(session_id)
        if resolved is None:
            return {}
        return deepcopy(resolved.current_state_json or {})

    def read_mirror_state_with_presence(
        self,
        *,
        session: StorySession | None = None,
        session_id: str | None = None,
    ) -> MirrorStateReadResult:
        resolved = session
        if resolved is None and session_id is not None:
            resolved = self._story_session_service.get_session(session_id)
        if resolved is None:
            return MirrorStateReadResult(present=False, state={})
        return MirrorStateReadResult(
            present=True,
            state=deepcopy(resolved.current_state_json or {}),
        )

    def sync_mirror_state(
        self,
        *,
        session_id: str,
        state_map: dict,
    ) -> StorySession:
        return self._story_session_service.update_session(
            session_id=session_id,
            current_state_json=state_map,
        )
