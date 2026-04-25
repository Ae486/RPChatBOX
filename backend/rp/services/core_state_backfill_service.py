"""Backfill service for migrating adapter-backed Core State into formal store."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from rp.models.dsl import Layer, ObjectRef

from .core_state_store_repository import CoreStateStoreRepository
from .memory_object_mapper import authoritative_bindings, projection_bindings
from .proposal_repository import ProposalRepository
from .story_session_service import StorySessionService


class CoreStateBackfillService:
    """Backfill current/revision rows from legacy adapter-backed storage."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        proposal_repository: ProposalRepository,
        core_state_store_repository: CoreStateStoreRepository,
    ) -> None:
        self._story_session_service = story_session_service
        self._proposal_repository = proposal_repository
        self._core_state_store_repository = core_state_store_repository

    def backfill_story_session(self, *, session_id: str) -> dict[str, int]:
        authoritative_objects = self.backfill_authoritative_for_session(
            session_id=session_id
        )
        projection_slots = 0
        for chapter in self._story_session_service.list_chapter_workspaces(
            session_id=session_id
        ):
            projection_slots += self.backfill_projection_for_chapter(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
        return {
            "authoritative_objects": authoritative_objects,
            "projection_slots": projection_slots,
        }

    def backfill_authoritative_for_session(self, *, session_id: str) -> int:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")

        payload = dict(session.current_state_json or {})
        count = 0
        for binding in authoritative_bindings():
            current_value = self._clone_json_value(payload.get(binding.backend_field))
            target_ref = ObjectRef(
                object_id=binding.object_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=binding.domain,
                domain_path=binding.domain_path,
                scope="story",
                revision=1,
            )
            apply_receipts = self._proposal_repository.list_apply_receipts_for_target(
                story_id=session.story_id,
                target_ref=target_ref,
                session_id=session.session_id,
            )
            revisions: list[
                tuple[int, Any, str, str | None, str | None, dict[str, Any]]
            ] = []
            if apply_receipts:
                initial_value = self._extract_backfill_value(
                    snapshot=apply_receipts[0].before_snapshot_json,
                    backend_field=binding.backend_field,
                    fallback=current_value,
                )
                revisions.append(
                    (
                        1,
                        initial_value,
                        "migration_backfill",
                        None,
                        None,
                        {"backfilled_from": "apply_receipt.before_snapshot"},
                    )
                )
                for receipt in apply_receipts:
                    revision = int(
                        receipt.revision_after_json.get(binding.object_id) or 1
                    )
                    after_value = self._extract_backfill_value(
                        snapshot=receipt.after_snapshot_json,
                        backend_field=binding.backend_field,
                        fallback=current_value,
                    )
                    revisions.append(
                        (
                            revision,
                            after_value,
                            "proposal_apply",
                            receipt.apply_id,
                            receipt.proposal_id,
                            {"backfilled_from": "apply_receipt.after_snapshot"},
                        )
                    )
            else:
                revisions.append(
                    (
                        1,
                        current_value,
                        "migration_backfill",
                        None,
                        None,
                        {"backfilled_from": "story_session.current_state_json"},
                    )
                )

            latest_revision = max(revision for revision, *_ in revisions)
            latest_apply_id = apply_receipts[-1].apply_id if apply_receipts else None
            current_record = (
                self._core_state_store_repository.upsert_authoritative_object(
                    story_id=session.story_id,
                    session_id=session.session_id,
                    layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                    domain=binding.domain.value,
                    domain_path=binding.domain_path,
                    object_id=binding.object_id,
                    scope="story",
                    current_revision=latest_revision,
                    data_json=self._normalize_authoritative_payload(current_value),
                    metadata_json={"backfilled_from": binding.backend_field},
                    latest_apply_id=latest_apply_id,
                )
            )
            for (
                revision,
                data_json,
                source_kind,
                source_apply_id,
                source_proposal_id,
                metadata,
            ) in revisions:
                revision_record = (
                    self._core_state_store_repository.upsert_authoritative_revision(
                        authoritative_object_id=current_record.authoritative_object_id,
                        story_id=session.story_id,
                        session_id=session.session_id,
                        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                        domain=binding.domain.value,
                        domain_path=binding.domain_path,
                        object_id=binding.object_id,
                        scope="story",
                        revision=revision,
                        data_json=self._normalize_authoritative_payload(data_json),
                        revision_source_kind=source_kind,
                        source_apply_id=source_apply_id,
                        source_proposal_id=source_proposal_id,
                        metadata_json=metadata,
                    )
                )
                if source_apply_id is not None and source_proposal_id is not None:
                    self._proposal_repository.create_apply_target_link(
                        apply_id=source_apply_id,
                        proposal_id=source_proposal_id,
                        story_id=session.story_id,
                        session_id=session.session_id,
                        object_id=binding.object_id,
                        domain=binding.domain.value,
                        domain_path=binding.domain_path,
                        scope="story",
                        revision=revision,
                        authoritative_object_id=current_record.authoritative_object_id,
                        authoritative_revision_id=revision_record.authoritative_revision_id,
                    )
            count += 1
        return count

    def backfill_projection_for_chapter(self, *, chapter_workspace_id: str) -> int:
        chapter = self._story_session_service.get_chapter_workspace(
            chapter_workspace_id
        )
        if chapter is None:
            raise ValueError(f"ChapterWorkspace not found: {chapter_workspace_id}")
        session = self._story_session_service.get_session(chapter.session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {chapter.session_id}")
        snapshot = dict(chapter.builder_snapshot_json or {})
        count = 0
        for binding in projection_bindings():
            existing = self._core_state_store_repository.get_projection_slot(
                chapter_workspace_id=chapter.chapter_workspace_id,
                summary_id=binding.summary_id,
            )
            if existing is not None:
                continue
            items = [
                str(item)
                for item in snapshot.get(binding.slot_name, [])
                if item is not None
            ]
            current_record = self._core_state_store_repository.upsert_projection_slot(
                story_id=session.story_id,
                session_id=session.session_id,
                chapter_workspace_id=chapter.chapter_workspace_id,
                layer=Layer.CORE_STATE_PROJECTION.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                summary_id=binding.summary_id,
                slot_name=binding.slot_name,
                scope="chapter",
                current_revision=1,
                items_json=items,
                metadata_json={
                    "backfilled_from": "chapter_workspace.builder_snapshot_json"
                },
                last_refresh_kind="migration_backfill",
            )
            self._core_state_store_repository.upsert_projection_slot_revision(
                projection_slot_id=current_record.projection_slot_id,
                story_id=session.story_id,
                session_id=session.session_id,
                chapter_workspace_id=chapter.chapter_workspace_id,
                layer=Layer.CORE_STATE_PROJECTION.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                summary_id=binding.summary_id,
                slot_name=binding.slot_name,
                scope="chapter",
                revision=1,
                items_json=items,
                refresh_source_kind="migration_backfill",
                metadata_json={
                    "backfilled_from": "chapter_workspace.builder_snapshot_json"
                },
            )
            count += 1
        return count

    @staticmethod
    def _extract_backfill_value(
        *,
        snapshot: dict[str, Any] | None,
        backend_field: str,
        fallback: Any,
    ) -> Any:
        if snapshot and backend_field in snapshot:
            return CoreStateBackfillService._clone_json_value(
                snapshot.get(backend_field)
            )
        return CoreStateBackfillService._clone_json_value(fallback)

    @staticmethod
    def _clone_json_value(value: Any) -> Any:
        if value is None:
            return {}
        return deepcopy(value)

    @staticmethod
    def _normalize_authoritative_payload(value: Any) -> dict[str, Any] | list[Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        return {"value": value}
