"""Business-facing settled projection service for story runtime."""

from __future__ import annotations

from .chapter_workspace_projection_adapter import ChapterWorkspaceProjectionAdapter
from .core_state_dual_write_service import CoreStateDualWriteService
from .core_state_store_repository import CoreStateStoreRepository
from .projection_compatibility_mirror_service import ProjectionCompatibilityMirrorService
from .settled_projection_mapper import settled_projection_slots
from .story_session_service import StorySessionService


class ProjectionStateService:
    """Read and mutate settled projection slots behind a stable boundary."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        adapter: ChapterWorkspaceProjectionAdapter,
        core_state_dual_write_service: CoreStateDualWriteService | None = None,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        store_read_enabled: bool = False,
        core_state_store_write_switch_enabled: bool = False,
        projection_compatibility_mirror_service: ProjectionCompatibilityMirrorService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._adapter = adapter
        self._core_state_dual_write_service = core_state_dual_write_service
        self._core_state_store_repository = core_state_store_repository
        self._store_read_enabled = store_read_enabled
        self._core_state_store_write_switch_enabled = core_state_store_write_switch_enabled
        self._projection_compatibility_mirror_service = (
            projection_compatibility_mirror_service
            or ProjectionCompatibilityMirrorService(
                story_session_service=story_session_service
            )
        )

    def get_slot_items(self, *, session_id: str, slot_name: str) -> list[str]:
        if self._store_read_enabled and self._core_state_store_repository is not None:
            _, chapter = self._adapter.get_current_chapter(session_id=session_id)
            if chapter is not None:
                for row in self._core_state_store_repository.list_projection_slots_for_chapter(
                    chapter_workspace_id=chapter.chapter_workspace_id
                ):
                    if row.slot_name == slot_name:
                        return [str(item) for item in row.items_json if item is not None]
        _, _, payload = self._adapter.get_projection_payload(session_id=session_id)
        raw_items = payload.get(slot_name) or []
        return [str(item) for item in raw_items if item is not None]

    def get_slot_map(self, *, session_id: str) -> dict[str, list[str]]:
        return {
            slot_name: self.get_slot_items(session_id=session_id, slot_name=slot_name)
            for slot_name in settled_projection_slots()
        }

    def build_planner_projection(self, *, session_id: str) -> dict[str, object]:
        session, chapter, _ = self._adapter.get_projection_payload(session_id=session_id)
        projection = {
            "chapter_index": chapter.chapter_index if chapter is not None else None,
            "phase": chapter.phase.value if chapter is not None else None,
        }
        projection.update(self.get_slot_map(session_id=session_id))
        if session is not None:
            projection["session_id"] = session.session_id
        if chapter is not None:
            projection["chapter_workspace_id"] = chapter.chapter_workspace_id
        return projection

    def build_context_sections(self, *, session_id: str) -> list[dict[str, object]]:
        return [
            {"label": slot_name, "items": items}
            for slot_name, items in self.get_slot_map(session_id=session_id).items()
            if items
        ]

    def set_current_outline(self, *, chapter_workspace_id: str, outline_text: str) -> None:
        snapshot = self._load_snapshot(chapter_workspace_id=chapter_workspace_id)
        snapshot["current_outline_digest"] = [outline_text[:400]] if outline_text else []
        self._persist_snapshot(
            chapter_workspace_id=chapter_workspace_id,
            snapshot=snapshot,
            refresh_source_kind="outline_accept",
        )

    def append_recent_segment(
        self,
        *,
        chapter_workspace_id: str,
        excerpt: str,
        keep_last: int = 3,
    ) -> None:
        snapshot = self._load_snapshot(chapter_workspace_id=chapter_workspace_id)
        existing = [str(item) for item in snapshot.get("recent_segment_digest", []) if item is not None]
        trimmed_excerpt = excerpt[:400]
        if keep_last <= 1:
            next_items = [trimmed_excerpt]
        else:
            next_items = [*existing[-(keep_last - 1) :], trimmed_excerpt]
        snapshot["recent_segment_digest"] = next_items
        self._persist_snapshot(
            chapter_workspace_id=chapter_workspace_id,
            snapshot=snapshot,
            refresh_source_kind="segment_append",
        )

    def seed_next_chapter(
        self,
        *,
        previous_chapter_workspace_id: str,
        next_chapter_workspace_id: str,
        next_chapter_index: int,
    ) -> None:
        previous = self._require_chapter(previous_chapter_workspace_id)
        next_chapter = self._require_chapter(next_chapter_workspace_id)
        snapshot = self._materialize_snapshot(chapter=previous)
        snapshot.update(
            {
                "chapter_index": next_chapter_index,
                "phase": next_chapter.phase.value,
                "current_outline_digest": [],
                "recent_segment_digest": [],
            }
        )
        self._persist_snapshot(
            chapter_workspace_id=next_chapter_workspace_id,
            snapshot=snapshot,
            refresh_source_kind="chapter_seed",
        )

    def _load_snapshot(self, *, chapter_workspace_id: str) -> dict:
        chapter = self._require_chapter(chapter_workspace_id)
        snapshot = self._materialize_snapshot(chapter=chapter)
        snapshot.setdefault("chapter_index", chapter.chapter_index)
        snapshot.setdefault("phase", chapter.phase.value)
        for slot_name in settled_projection_slots():
            snapshot.setdefault(slot_name, [])
        return snapshot

    def _persist_snapshot(
        self,
        *,
        chapter_workspace_id: str,
        snapshot: dict,
        refresh_source_kind: str,
    ) -> None:
        store_primary = (
            self._core_state_store_write_switch_enabled
            and self._core_state_dual_write_service is not None
        )
        if store_primary:
            chapter = self._require_chapter(chapter_workspace_id)
            session = self._story_session_service.get_session(chapter.session_id)
            if session is not None:
                self._core_state_dual_write_service.sync_projection_snapshot(
                    session=session,
                    chapter=chapter,
                    snapshot=dict(snapshot),
                    refresh_source_kind=refresh_source_kind,
                )
            self._projection_compatibility_mirror_service.sync_mirror_snapshot(
                chapter_workspace_id=chapter_workspace_id,
                snapshot=snapshot,
            )
            return
        updated_chapter = self._projection_compatibility_mirror_service.sync_mirror_snapshot(
            chapter_workspace_id=chapter_workspace_id,
            snapshot=snapshot,
        )
        if self._core_state_dual_write_service is not None:
            session = self._story_session_service.get_session(updated_chapter.session_id)
            if session is not None:
                self._core_state_dual_write_service.sync_projection_snapshot(
                    session=session,
                    chapter=updated_chapter,
                    snapshot=dict(snapshot),
                    refresh_source_kind=refresh_source_kind,
                )

    def _materialize_snapshot(self, *, chapter) -> dict:
        if (
            self._core_state_store_write_switch_enabled
            and self._core_state_dual_write_service is not None
        ):
            session = self._story_session_service.get_session(chapter.session_id)
            if session is not None:
                return self._core_state_dual_write_service.materialize_projection_snapshot(
                    session=session,
                    chapter=chapter,
                    fallback_snapshot=self._projection_compatibility_mirror_service.read_mirror_snapshot(
                        chapter=chapter
                    ),
                )
        snapshot = self._projection_compatibility_mirror_service.read_mirror_snapshot(
            chapter=chapter
        )
        snapshot.pop("writer_hints", None)
        return snapshot

    def _require_chapter(self, chapter_workspace_id: str):
        chapter = self._story_session_service.get_chapter_workspace(chapter_workspace_id)
        if chapter is None:
            raise ValueError(f"ChapterWorkspace not found: {chapter_workspace_id}")
        return chapter
