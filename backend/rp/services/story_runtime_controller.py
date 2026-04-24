"""Active-story longform read/list/activate facade."""

from __future__ import annotations

from typing import Any

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import ProvenanceResult, VersionListResult
from rp.models.story_runtime import (
    ChapterWorkspaceSnapshot,
    StoryActivationResult,
    StorySession,
)
from .memory_inspection_read_service import MemoryInspectionReadService
from .provenance_read_service import ProvenanceReadService
from .story_activation_service import StoryActivationService
from .story_session_service import StorySessionService
from .version_history_read_service import VersionHistoryReadService


class StoryRuntimeController:
    """Thin facade for activation and read-model access."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        story_activation_service: StoryActivationService,
        version_history_read_service: VersionHistoryReadService,
        provenance_read_service: ProvenanceReadService,
        memory_inspection_read_service: MemoryInspectionReadService,
    ) -> None:
        self._story_session_service = story_session_service
        self._story_activation_service = story_activation_service
        self._version_history_read_service = version_history_read_service
        self._provenance_read_service = provenance_read_service
        self._memory_inspection_read_service = memory_inspection_read_service

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

    def update_runtime_story_config(
        self,
        *,
        session_id: str,
        patch: dict[str, Any],
    ) -> ChapterWorkspaceSnapshot:
        updated_session = self._story_session_service.update_session(
            session_id=session_id,
            runtime_story_config_patch=patch,
        )
        self._story_session_service.commit()
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=updated_session.current_chapter_index,
        )

    def list_memory_authoritative(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        return self._memory_inspection_read_service.list_authoritative_objects(
            session_id=session_id
        )

    def list_memory_projection(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        return self._memory_inspection_read_service.list_projection_slots(
            session_id=session_id
        )

    def list_memory_proposals(
        self,
        *,
        session_id: str,
        status: str | None = None,
    ) -> list[dict]:
        session = self._require_session(session_id)
        return self._memory_inspection_read_service.list_proposals(
            story_id=session.story_id,
            session_id=session_id,
            status=status,
        )

    def read_memory_versions(
        self,
        *,
        session_id: str,
        object_id: str,
        domain: Domain,
        domain_path: str | None = None,
    ) -> VersionListResult:
        self._require_session(session_id)
        return self._version_history_read_service.list_versions(
            self._build_authoritative_ref(
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
            ),
            session_id=session_id,
        )

    def read_memory_provenance(
        self,
        *,
        session_id: str,
        object_id: str,
        domain: Domain,
        domain_path: str | None = None,
    ) -> ProvenanceResult:
        self._require_session(session_id)
        return self._provenance_read_service.read_provenance(
            self._build_authoritative_ref(
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
            ),
            session_id=session_id,
        )

    def _require_session(self, session_id: str) -> StorySession:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return session

    @staticmethod
    def _build_authoritative_ref(
        *,
        object_id: str,
        domain: Domain,
        domain_path: str | None,
    ) -> ObjectRef:
        return ObjectRef(
            object_id=object_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=domain,
            domain_path=domain_path or object_id,
            scope="story",
            revision=1,
        )
