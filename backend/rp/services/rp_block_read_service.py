"""Read-only Block envelope adapter over Core State stores and mirrors."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from rp.models.block_view import RpBlockView
from rp.models.dsl import Domain, Layer

from .builder_projection_context_service import BuilderProjectionContextService
from .core_state_store_repository import CoreStateStoreRepository
from .memory_inspection_read_service import MemoryInspectionReadService
from .memory_object_mapper import (
    authoritative_bindings,
    normalize_projection_summary_id,
    resolve_projection_binding,
)
from .story_session_service import StorySessionService


class RpBlockReadService:
    """Present current Core State rows and mirrors as read-only Block views."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        builder_projection_context_service: BuilderProjectionContextService,
        core_state_store_repository: CoreStateStoreRepository | None = None,
        memory_inspection_read_service: MemoryInspectionReadService | None = None,
        store_read_enabled: bool = False,
    ) -> None:
        self._story_session_service = story_session_service
        self._builder_projection_context_service = builder_projection_context_service
        self._core_state_store_repository = core_state_store_repository
        self._memory_inspection_read_service = memory_inspection_read_service
        self._store_read_enabled = store_read_enabled

    def list_blocks(self, *, session_id: str) -> list[RpBlockView]:
        """List authoritative and projection Core State blocks for a session."""

        return [
            *self.list_authoritative_blocks(session_id=session_id),
            *self.list_projection_blocks(session_id=session_id),
        ]

    def get_block(self, *, session_id: str, block_id: str) -> RpBlockView | None:
        """Read one Block envelope by the formal or deterministic mirror id."""

        for block in self.list_blocks(session_id=session_id):
            if block.block_id == block_id:
                return block
        return None

    def list_authoritative_blocks(self, *, session_id: str) -> list[RpBlockView]:
        """List Core State authoritative objects, preserving mirror fallback."""

        session = self._story_session_service.get_session(session_id)
        if session is None:
            return []

        store_rows_by_object_id = {}
        if self._store_read_enabled and self._core_state_store_repository is not None:
            store_rows_by_object_id = {
                row.object_id: row
                for row in self._core_state_store_repository.list_authoritative_objects_for_session(
                    session_id=session_id
                )
            }

        mirror_payload = dict(session.current_state_json or {})
        inspection_by_object_id = self._inspection_authoritative_by_object_id(
            session_id=session_id
        )
        blocks = [
            self._authoritative_store_block(row)
            for row in store_rows_by_object_id.values()
        ]
        for binding in authoritative_bindings():
            if binding.object_id in store_rows_by_object_id:
                continue

            inspection_item = inspection_by_object_id.get(binding.object_id)
            if inspection_item is not None:
                object_ref = dict(inspection_item.get("object_ref") or {})
                data_json = deepcopy(inspection_item.get("data"))
                revision = int(object_ref.get("revision") or 1)
                updated_at = inspection_item.get("updated_at", session.updated_at)
            elif binding.backend_field in mirror_payload:
                data_json = deepcopy(mirror_payload[binding.backend_field])
                revision = 1
                updated_at = session.updated_at
            else:
                continue

            blocks.append(
                RpBlockView(
                    block_id=self._compat_authoritative_block_id(
                        session_id=session.session_id,
                        object_id=binding.object_id,
                    ),
                    label=binding.object_id,
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=binding.domain,
                    domain_path=binding.domain_path,
                    scope="story",
                    revision=revision,
                    source="compatibility_mirror",
                    data_json=data_json,
                    metadata={
                        "route": "story_session.current_state_json",
                        "source": "compatibility_mirror",
                        "source_field": binding.backend_field,
                        "source_row_id": None,
                        "story_id": session.story_id,
                        "session_id": session.session_id,
                        "updated_at": updated_at,
                    },
                )
            )
        return sorted(blocks, key=lambda block: (block.layer.value, block.label))

    def list_projection_blocks(self, *, session_id: str) -> list[RpBlockView]:
        """List Core State projection slots, preserving mirror fallback."""

        session = self._story_session_service.get_session(session_id)
        if session is None:
            return []
        chapter = self._story_session_service.get_current_chapter(session_id)

        store_rows_by_summary_id = {}
        if (
            self._store_read_enabled
            and self._core_state_store_repository is not None
            and chapter is not None
        ):
            store_rows_by_summary_id = {
                row.summary_id: row
                for row in self._core_state_store_repository.list_projection_slots_for_chapter(
                    chapter_workspace_id=chapter.chapter_workspace_id
                )
            }

        blocks = [
            self._projection_store_block(row)
            for row in store_rows_by_summary_id.values()
        ]
        for mirror_item in self._inspection_projection_items(session_id=session_id):
            slot_name = str(
                mirror_item.get("slot_name") or mirror_item.get("label") or ""
            )
            summary_id = normalize_projection_summary_id(
                str(mirror_item.get("summary_id") or f"projection.{slot_name}")
            )
            if summary_id in store_rows_by_summary_id:
                continue
            binding = resolve_projection_binding(summary_id)
            if binding is None:
                continue
            blocks.append(
                RpBlockView(
                    block_id=self._compat_projection_block_id(
                        session_id=session.session_id,
                        chapter_workspace_id=(
                            str(mirror_item.get("chapter_workspace_id") or "")
                            or (
                                chapter.chapter_workspace_id
                                if chapter is not None
                                else None
                            )
                        ),
                        summary_id=binding.summary_id,
                    ),
                    label=binding.summary_id,
                    layer=Layer.CORE_STATE_PROJECTION,
                    domain=binding.domain,
                    domain_path=binding.domain_path,
                    scope="chapter",
                    revision=1,
                    source="compatibility_mirror",
                    items_json=deepcopy(mirror_item.get("items") or []),
                    metadata={
                        "route": "chapter_workspace.builder_snapshot_json",
                        "source": "compatibility_mirror",
                        "source_field": binding.slot_name,
                        "source_row_id": None,
                        "story_id": session.story_id,
                        "session_id": session.session_id,
                        "chapter_workspace_id": mirror_item.get("chapter_workspace_id")
                        or (
                            chapter.chapter_workspace_id
                            if chapter is not None
                            else None
                        ),
                        "updated_at": mirror_item.get(
                            "updated_at",
                            chapter.updated_at if chapter is not None else None,
                        ),
                    },
                )
            )
        return sorted(blocks, key=lambda block: (block.layer.value, block.label))

    def _inspection_authoritative_by_object_id(
        self,
        *,
        session_id: str,
    ) -> dict[str, dict[str, Any]]:
        if self._memory_inspection_read_service is None:
            return {}
        return {
            str(item.get("object_ref", {}).get("object_id")): item
            for item in self._memory_inspection_read_service.list_authoritative_objects(
                session_id=session_id
            )
        }

    def _inspection_projection_items(self, *, session_id: str) -> list[dict[str, Any]]:
        if self._memory_inspection_read_service is not None:
            return self._memory_inspection_read_service.list_projection_slots(
                session_id=session_id
            )
        return [
            {
                "summary_id": f"projection.{section['label']}",
                "slot_name": section["label"],
                "items": self._section_items(section),
            }
            for section in self._builder_projection_context_service.build_context_sections(
                session_id=session_id
            )
        ]

    @staticmethod
    def _authoritative_store_block(row) -> RpBlockView:
        return RpBlockView(
            block_id=row.authoritative_object_id,
            label=row.object_id,
            layer=Layer(row.layer),
            domain=Domain(row.domain),
            domain_path=row.domain_path,
            scope=row.scope,
            revision=int(row.current_revision or 1),
            source="core_state_store",
            payload_schema_ref=row.payload_schema_ref,
            data_json=deepcopy(row.data_json),
            metadata={
                **deepcopy(row.metadata_json or {}),
                "route": "core_state_store",
                "source": "core_state_store",
                "source_table": "rp_core_state_authoritative_objects",
                "source_row_id": row.authoritative_object_id,
                "story_id": row.story_id,
                "session_id": row.session_id,
                "latest_apply_id": row.latest_apply_id,
                "updated_at": row.updated_at,
            },
        )

    @staticmethod
    def _projection_store_block(row) -> RpBlockView:
        return RpBlockView(
            block_id=row.projection_slot_id,
            label=row.summary_id,
            layer=Layer(row.layer),
            domain=Domain(row.domain),
            domain_path=row.domain_path,
            scope=row.scope,
            revision=int(row.current_revision or 1),
            source="core_state_store",
            payload_schema_ref=row.payload_schema_ref,
            items_json=deepcopy(row.items_json or []),
            metadata={
                **deepcopy(row.metadata_json or {}),
                "route": "core_state_store",
                "source": "core_state_store",
                "source_table": "rp_core_state_projection_slots",
                "source_row_id": row.projection_slot_id,
                "story_id": row.story_id,
                "session_id": row.session_id,
                "chapter_workspace_id": row.chapter_workspace_id,
                "last_refresh_kind": row.last_refresh_kind,
                "updated_at": row.updated_at,
            },
        )

    @staticmethod
    def _section_items(section: dict[str, object]) -> list[Any]:
        raw_items = section.get("items")
        if isinstance(raw_items, list):
            return deepcopy(raw_items)
        if isinstance(raw_items, tuple):
            return list(raw_items)
        return []

    @staticmethod
    def _compat_authoritative_block_id(*, session_id: str, object_id: str) -> str:
        return f"compatibility_mirror:core_state.authoritative:{session_id}:{object_id}"

    @staticmethod
    def _compat_projection_block_id(
        *,
        session_id: str,
        chapter_workspace_id: str | None,
        summary_id: str,
    ) -> str:
        owner_id = chapter_workspace_id or session_id
        return f"compatibility_mirror:core_state.projection:{owner_id}:{summary_id}"
