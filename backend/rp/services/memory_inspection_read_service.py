"""Internal read-only inspection service for current authoritative/projection memory."""

from __future__ import annotations

from copy import deepcopy

from .core_state_store_repository import CoreStateStoreRepository
from rp.models.dsl import Layer, ObjectRef

from .builder_projection_context_service import BuilderProjectionContextService
from .memory_object_mapper import authoritative_bindings
from .proposal_repository import ProposalRepository
from .story_session_service import StorySessionService
from .version_history_read_service import VersionHistoryReadService


class MemoryInspectionReadService:
    """Expose current authoritative objects, projection slots, and proposals."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        builder_projection_context_service: BuilderProjectionContextService,
        proposal_repository: ProposalRepository,
        version_history_read_service: VersionHistoryReadService,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        store_read_enabled: bool = False,
    ) -> None:
        self._story_session_service = story_session_service
        self._builder_projection_context_service = builder_projection_context_service
        self._proposal_repository = proposal_repository
        self._version_history_read_service = version_history_read_service
        self._core_state_store_repository = core_state_store_repository
        self._store_read_enabled = store_read_enabled

    def list_authoritative_objects(self, *, session_id: str) -> list[dict]:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            return []
        payload = dict(session.current_state_json or {})
        store_rows = {}
        if self._store_read_enabled and self._core_state_store_repository is not None:
            store_rows = {
                row.object_id: row
                for row in self._core_state_store_repository.list_authoritative_objects_for_session(
                    session_id=session_id
                )
            }
        items: list[dict] = []
        for binding in authoritative_bindings():
            store_row = store_rows.get(binding.object_id)
            if store_row is None and binding.backend_field not in payload:
                continue
            version_result = self._version_history_read_service.list_versions(
                ObjectRef(
                    object_id=binding.object_id,
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=binding.domain,
                    domain_path=binding.domain_path,
                    scope="story",
                    revision=1,
                ),
                session_id=session_id,
            )
            items.append(
                {
                    "object_ref": {
                        "object_id": binding.object_id,
                        "layer": Layer.CORE_STATE_AUTHORITATIVE.value,
                        "domain": binding.domain.value,
                        "domain_path": binding.domain_path,
                        "scope": "story",
                        "revision": int((version_result.current_ref or f"{binding.object_id}@1").rsplit("@", 1)[1]),
                    },
                    "data": deepcopy(store_row.data_json if store_row is not None else payload[binding.backend_field]),
                    "updated_at": store_row.updated_at if store_row is not None else session.updated_at,
                }
            )
        return items

    def list_projection_slots(self, *, session_id: str) -> list[dict]:
        session = self._story_session_service.get_session(session_id)
        chapter = self._story_session_service.get_current_chapter(session_id)
        if (
            self._store_read_enabled
            and self._core_state_store_repository is not None
            and chapter is not None
        ):
            return [
                {
                    "summary_id": row.summary_id,
                    "slot_name": row.slot_name,
                    "items": list(row.items_json),
                    "session_id": session.session_id if session is not None else None,
                    "chapter_workspace_id": chapter.chapter_workspace_id,
                    "updated_at": row.updated_at,
                }
                for row in self._core_state_store_repository.list_projection_slots_for_chapter(
                    chapter_workspace_id=chapter.chapter_workspace_id
                )
            ]
        sections = self._builder_projection_context_service.build_context_sections(session_id=session_id)
        return [
            {
                "summary_id": f"projection.{section['label']}",
                "slot_name": section["label"],
                "items": list(section["items"]),
                "session_id": session.session_id if session is not None else None,
                "chapter_workspace_id": chapter.chapter_workspace_id if chapter is not None else None,
                "updated_at": chapter.updated_at if chapter is not None else None,
            }
            for section in sections
        ]

    def list_proposals(
        self,
        *,
        story_id: str,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        records = self._proposal_repository.list_proposals_for_story(story_id)
        items: list[dict] = []
        for record in records:
            if session_id is not None and record.session_id != session_id:
                continue
            if status is not None and record.status != status:
                continue
            items.append(
                {
                    "proposal_id": record.proposal_id,
                    "status": record.status,
                    "policy_decision": record.policy_decision,
                    "domain": record.domain,
                    "domain_path": record.domain_path,
                    "operation_kinds": [item.get("kind", "") for item in record.operations_json],
                    "created_at": record.created_at,
                    "applied_at": record.applied_at,
                }
            )
        return items
