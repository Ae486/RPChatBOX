"""Internal read-only inspection service for current authoritative/projection memory."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .core_state_store_repository import CoreStateStoreRepository
from rp.models.dsl import Layer, ObjectRef

from .builder_projection_context_service import BuilderProjectionContextService
from .memory_object_mapper import authoritative_bindings, normalize_authoritative_ref
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
                        "revision": int(
                            (
                                version_result.current_ref or f"{binding.object_id}@1"
                            ).rsplit("@", 1)[1]
                        ),
                    },
                    "data": deepcopy(
                        store_row.data_json
                        if store_row is not None
                        else payload[binding.backend_field]
                    ),
                    "updated_at": store_row.updated_at
                    if store_row is not None
                    else session.updated_at,
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
            rows = self._core_state_store_repository.list_projection_slots_for_chapter(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            items_by_slot_name = {
                row.slot_name: {
                    "summary_id": row.summary_id,
                    "slot_name": row.slot_name,
                    "items": list(row.items_json),
                    "session_id": session.session_id if session is not None else None,
                    "chapter_workspace_id": chapter.chapter_workspace_id,
                    "updated_at": row.updated_at,
                    "backend": "core_state_store",
                }
                for row in rows
            }
            sections = self._builder_projection_context_service.build_context_sections(
                session_id=session_id
            )
            for section in sections:
                slot_name = str(section["label"])
                if slot_name in items_by_slot_name:
                    continue
                items_by_slot_name[slot_name] = {
                    "summary_id": f"projection.{slot_name}",
                    "slot_name": slot_name,
                    "items": self._section_items(section),
                    "session_id": session.session_id if session is not None else None,
                    "chapter_workspace_id": chapter.chapter_workspace_id,
                    "updated_at": chapter.updated_at,
                    "backend": "compatibility_mirror",
                }
            return [
                items_by_slot_name[slot_name]
                for slot_name in sorted(items_by_slot_name)
            ]
        sections = self._builder_projection_context_service.build_context_sections(
            session_id=session_id
        )
        return [
            {
                "summary_id": f"projection.{section['label']}",
                "slot_name": section["label"],
                "items": self._section_items(section),
                "session_id": session.session_id if session is not None else None,
                "chapter_workspace_id": chapter.chapter_workspace_id
                if chapter is not None
                else None,
                "updated_at": chapter.updated_at if chapter is not None else None,
                "backend": "compatibility_mirror",
            }
            for section in sections
        ]

    @staticmethod
    def _section_items(section: dict[str, object]) -> list[Any]:
        raw_items = section.get("items")
        if isinstance(raw_items, list):
            return deepcopy(raw_items)
        if isinstance(raw_items, tuple):
            return list(raw_items)
        return []

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
            items.append(self._proposal_item(record))
        return items

    def list_proposals_for_authoritative_ref(
        self,
        *,
        story_id: str,
        target_ref: ObjectRef,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """List proposals whose operations target one authoritative Core State ref."""

        target_identity = self._authoritative_ref_identity(target_ref)
        records = self._proposal_repository.list_proposals_for_story(story_id)
        items: list[dict] = []
        for record in records:
            if session_id is not None and record.session_id != session_id:
                continue
            if status is not None and record.status != status:
                continue
            if not self._proposal_targets_authoritative_ref(
                record.operations_json,
                target_identity=target_identity,
            ):
                continue
            items.append(self._proposal_item(record))
        return items

    def get_proposal_for_authoritative_ref(
        self,
        *,
        story_id: str,
        target_ref: ObjectRef,
        proposal_id: str,
        session_id: str | None = None,
    ) -> dict | None:
        """Return one exact-target authoritative proposal detail when it belongs here."""

        record = self._proposal_repository.get_proposal_record(proposal_id)
        if record is None:
            return None
        if record.story_id != story_id:
            return None
        if session_id is not None and record.session_id != session_id:
            return None
        if not self._proposal_targets_authoritative_ref(
            record.operations_json,
            target_identity=self._authoritative_ref_identity(target_ref),
        ):
            return None
        return self._proposal_detail_item(record)

    @staticmethod
    def _proposal_item(record) -> dict:
        return {
            "proposal_id": record.proposal_id,
            "status": record.status,
            "policy_decision": record.policy_decision,
            "domain": record.domain,
            "domain_path": record.domain_path,
            "operation_kinds": [
                item.get("kind", "") for item in record.operations_json
            ],
            "created_at": record.created_at,
            "applied_at": record.applied_at,
        }

    def _proposal_detail_item(self, record) -> dict:
        return {
            **self._proposal_item(record),
            "reason": record.reason,
            "trace_id": record.trace_id,
            "error_message": record.error_message,
            "operations": deepcopy(record.operations_json),
            "base_refs": deepcopy(record.base_refs_json),
            "apply_receipts": [
                self._apply_receipt_item(item)
                for item in self._proposal_repository.list_apply_receipts_for_proposal(
                    record.proposal_id
                )
            ],
        }

    @staticmethod
    def _apply_receipt_item(record) -> dict:
        return {
            "apply_id": record.apply_id,
            "session_id": record.session_id,
            "chapter_workspace_id": record.chapter_workspace_id,
            "target_refs": deepcopy(record.target_refs_json),
            "revision_after": deepcopy(record.revision_after_json),
            "warnings": list(record.warnings_json),
            "apply_backend": record.apply_backend,
            "created_at": record.created_at,
        }

    @classmethod
    def _proposal_targets_authoritative_ref(
        cls,
        operations: list[dict[str, Any]],
        *,
        target_identity: tuple[str, str, str, str, str],
    ) -> bool:
        for operation in operations:
            raw_ref = operation.get("target_ref")
            if not isinstance(raw_ref, dict):
                continue
            try:
                operation_ref = normalize_authoritative_ref(
                    ObjectRef.model_validate(raw_ref)
                )
            except ValueError:
                continue
            if operation_ref.layer != Layer.CORE_STATE_AUTHORITATIVE:
                continue
            if cls._authoritative_ref_identity(operation_ref) == target_identity:
                return True
        return False

    @staticmethod
    def _authoritative_ref_identity(ref: ObjectRef) -> tuple[str, str, str, str, str]:
        normalized = normalize_authoritative_ref(ref)
        return (
            normalized.object_id,
            normalized.layer.value,
            normalized.domain.value,
            normalized.domain_path or normalized.object_id,
            normalized.scope or "story",
        )
