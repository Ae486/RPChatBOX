"""Refresh settled projection slots into the current chapter workspace backend."""

from __future__ import annotations

from rp.models.story_runtime import ChapterWorkspace, SpecialistResultBundle

from .core_state_dual_write_service import CoreStateDualWriteService
from .projection_compatibility_mirror_service import ProjectionCompatibilityMirrorService
from .story_session_service import StorySessionService


class ProjectionRefreshService:
    """Persist settled projection slots without redefining the builder contract."""

    def __init__(
        self,
        story_session_service: StorySessionService,
        core_state_dual_write_service: CoreStateDualWriteService | None = None,
        core_state_store_write_switch_enabled: bool = False,
        projection_compatibility_mirror_service: ProjectionCompatibilityMirrorService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._core_state_dual_write_service = core_state_dual_write_service
        self._core_state_store_write_switch_enabled = core_state_store_write_switch_enabled
        self._projection_compatibility_mirror_service = (
            projection_compatibility_mirror_service
            or ProjectionCompatibilityMirrorService(
                story_session_service=story_session_service
            )
        )

    def refresh_from_bundle(
        self,
        *,
        chapter: ChapterWorkspace,
        bundle: SpecialistResultBundle,
    ) -> ChapterWorkspace:
        snapshot = self._projection_compatibility_mirror_service.read_mirror_snapshot(
            chapter=chapter
        )
        snapshot.pop("writer_hints", None)
        snapshot.update(
            {
                "chapter_index": chapter.chapter_index,
                "phase": chapter.phase.value,
                "foundation_digest": list(bundle.foundation_digest),
                "blueprint_digest": list(bundle.blueprint_digest),
                "current_outline_digest": list(bundle.current_outline_digest),
                "recent_segment_digest": list(bundle.recent_segment_digest),
                "current_state_digest": list(bundle.current_state_digest),
            }
        )
        store_primary = (
            self._core_state_store_write_switch_enabled
            and self._core_state_dual_write_service is not None
        )
        if store_primary:
            session = self._story_session_service.get_session(chapter.session_id)
            if session is not None:
                self._core_state_dual_write_service.sync_projection_snapshot(
                    session=session,
                    chapter=chapter,
                    snapshot=dict(snapshot),
                    refresh_source_kind="bundle_refresh",
                )
        updated_chapter = self._projection_compatibility_mirror_service.sync_mirror_snapshot(
            chapter_workspace_id=chapter.chapter_workspace_id,
            snapshot=snapshot,
        )
        if self._core_state_dual_write_service is not None and not store_primary:
            session = self._story_session_service.get_session(updated_chapter.session_id)
            if session is not None:
                self._core_state_dual_write_service.sync_projection_snapshot(
                    session=session,
                    chapter=updated_chapter,
                    snapshot=dict(snapshot),
                    refresh_source_kind="bundle_refresh",
                )
        return updated_chapter
