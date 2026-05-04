"""Refresh settled projection slots into the current chapter workspace backend."""

from __future__ import annotations

from uuid import uuid4

from rp.models.dsl import Layer
from rp.models.memory_contract_registry import MemoryChangeEvent, MemoryDirtyTarget
from rp.models.projection_refresh import ProjectionRefreshRequest
from rp.models.story_runtime import ChapterWorkspace, SpecialistResultBundle

from .core_state_dual_write_service import CoreStateDualWriteService
from .memory_change_event_service import MemoryChangeEventService
from .projection_compatibility_mirror_service import (
    ProjectionCompatibilityMirrorService,
)
from .story_session_service import StorySessionService


class ProjectionRefreshService:
    """Persist settled projection slots without redefining the builder contract."""

    def __init__(
        self,
        story_session_service: StorySessionService,
        core_state_dual_write_service: CoreStateDualWriteService | None = None,
        core_state_store_write_switch_enabled: bool = False,
        projection_compatibility_mirror_service: ProjectionCompatibilityMirrorService
        | None = None,
        memory_change_event_service: MemoryChangeEventService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._core_state_dual_write_service = core_state_dual_write_service
        self._core_state_store_write_switch_enabled = (
            core_state_store_write_switch_enabled
        )
        self._memory_change_event_service = memory_change_event_service
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
        refresh_request: ProjectionRefreshRequest | None = None,
    ) -> ChapterWorkspace:
        request = refresh_request or ProjectionRefreshRequest()
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
        self._validate_refresh_before_writing(chapter=chapter, refresh_request=request)
        if store_primary:
            session = self._story_session_service.get_session(chapter.session_id)
            if session is not None:
                core_state_dual_write_service = self._core_state_dual_write_service
                assert core_state_dual_write_service is not None
                core_state_dual_write_service.sync_projection_snapshot(
                    session=session,
                    chapter=chapter,
                    snapshot=dict(snapshot),
                    refresh_source_kind=request.refresh_source_kind,
                    refresh_source_ref=request.refresh_source_ref,
                    refresh_request=request,
                )
        updated_chapter = (
            self._projection_compatibility_mirror_service.sync_mirror_snapshot(
                chapter_workspace_id=chapter.chapter_workspace_id,
                snapshot=snapshot,
            )
        )
        if self._core_state_dual_write_service is not None and not store_primary:
            session = self._story_session_service.get_session(
                updated_chapter.session_id
            )
            if session is not None:
                self._core_state_dual_write_service.sync_projection_snapshot(
                    session=session,
                    chapter=updated_chapter,
                    snapshot=dict(snapshot),
                    refresh_source_kind=request.refresh_source_kind,
                    refresh_source_ref=request.refresh_source_ref,
                    refresh_request=request,
                )
        self._publish_refresh_event(chapter=updated_chapter, refresh_request=request)
        return updated_chapter

    def _validate_refresh_before_writing(
        self,
        *,
        chapter: ChapterWorkspace,
        refresh_request: ProjectionRefreshRequest,
    ) -> None:
        if self._core_state_dual_write_service is None:
            return
        session = self._story_session_service.get_session(chapter.session_id)
        if session is None:
            return
        self._core_state_dual_write_service.validate_projection_refresh_request(
            session_id=session.session_id,
            chapter=chapter,
            refresh_request=refresh_request,
        )

    def _publish_refresh_event(
        self,
        *,
        chapter: ChapterWorkspace,
        refresh_request: ProjectionRefreshRequest,
    ) -> None:
        if (
            self._memory_change_event_service is None
            or refresh_request.identity is None
        ):
            return
        dirty_targets = list(refresh_request.dirty_targets)
        if not dirty_targets:
            dirty_targets = [
                MemoryDirtyTarget(
                    target_kind="projection_slot",
                    target_id=chapter.chapter_workspace_id,
                    layer=Layer.CORE_STATE_PROJECTION.value,
                    reason=refresh_request.refresh_reason,
                    metadata={"chapter_workspace_id": chapter.chapter_workspace_id},
                )
            ]
        self._memory_change_event_service.record_event(
            MemoryChangeEvent(
                event_id=(
                    f"{chapter.chapter_workspace_id}:projection.refresh:"
                    f"{refresh_request.refresh_source_kind}:"
                    f"{refresh_request.identity.session_id}:"
                    f"{refresh_request.identity.turn_id}:"
                    f"{uuid4().hex}"
                ),
                identity=refresh_request.identity,
                actor=refresh_request.refresh_actor,
                event_kind="projection_refreshed",
                layer=Layer.CORE_STATE_PROJECTION.value,
                domain=dirty_targets[0].domain or "chapter",
                block_id=f"{chapter.chapter_workspace_id}:projection",
                entry_id=chapter.chapter_workspace_id,
                operation_kind="projection.refresh",
                source_refs=list(refresh_request.source_refs),
                dirty_targets=dirty_targets,
                visibility_effect="active",
                metadata={
                    "refresh_reason": refresh_request.refresh_reason,
                    "refresh_source_kind": refresh_request.refresh_source_kind,
                    "base_revision": refresh_request.base_revision,
                    "projection_dirty_state": refresh_request.projection_dirty_state,
                },
            )
        )
