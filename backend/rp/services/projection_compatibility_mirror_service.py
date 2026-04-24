"""Compatibility mirror access for legacy projection chapter snapshots."""

from __future__ import annotations

from copy import deepcopy

from rp.models.story_runtime import ChapterWorkspace

from .story_session_service import StorySessionService


class ProjectionCompatibilityMirrorService:
    """Read/write the legacy builder snapshot mirror without treating it as truth source."""

    def __init__(self, *, story_session_service: StorySessionService) -> None:
        self._story_session_service = story_session_service

    def read_mirror_snapshot(
        self,
        *,
        chapter: ChapterWorkspace | None = None,
        chapter_workspace_id: str | None = None,
    ) -> dict:
        resolved = chapter
        if resolved is None and chapter_workspace_id is not None:
            resolved = self._story_session_service.get_chapter_workspace(chapter_workspace_id)
        if resolved is None:
            return {}
        return deepcopy(resolved.builder_snapshot_json or {})

    def sync_mirror_snapshot(
        self,
        *,
        chapter_workspace_id: str,
        snapshot: dict,
    ) -> ChapterWorkspace:
        return self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter_workspace_id,
            builder_snapshot_json=snapshot,
        )
