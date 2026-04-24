"""Business-facing authoritative state view service for story runtime."""

from __future__ import annotations

from copy import deepcopy

from .core_state_store_repository import CoreStateStoreRepository
from .memory_object_mapper import authoritative_bindings
from .story_session_core_state_adapter import StorySessionCoreStateAdapter


class AuthoritativeStateViewService:
    """Expose current authoritative state through a stable business-facing boundary."""

    def __init__(
        self,
        *,
        adapter: StorySessionCoreStateAdapter,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        store_read_enabled: bool = False,
    ) -> None:
        self._adapter = adapter
        self._core_state_store_repository = core_state_store_repository
        self._store_read_enabled = store_read_enabled

    def get_state_map(self, *, session_id: str) -> dict:
        if self._store_read_enabled and self._core_state_store_repository is not None:
            rows = self._core_state_store_repository.list_authoritative_objects_for_session(
                session_id=session_id
            )
            if rows:
                binding_by_object_id = {binding.object_id: binding for binding in authoritative_bindings()}
                state_map: dict = {}
                for row in rows:
                    binding = binding_by_object_id.get(row.object_id)
                    if binding is None:
                        continue
                    state_map[binding.backend_field] = deepcopy(row.data_json)
                return state_map
        _, payload = self._adapter.get_state_payload(session_id=session_id)
        return payload

    def get_object_data(self, *, session_id: str, object_id: str) -> dict:
        payload = self.get_state_map(session_id=session_id)
        value = payload.get(object_id) or {}
        if isinstance(value, dict):
            return deepcopy(value)
        return {}

    def get_chapter_digest(self, *, session_id: str) -> dict:
        return self.get_object_data(session_id=session_id, object_id="chapter_digest")

    def get_narrative_progress(self, *, session_id: str) -> dict:
        return self.get_object_data(session_id=session_id, object_id="narrative_progress")
