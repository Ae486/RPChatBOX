"""Dual-write bridge from legacy adapter backends to formal Core State store."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from models.rp_core_state_store import (
    CoreStateAuthoritativeObjectRecord,
    CoreStateAuthoritativeRevisionRecord,
)
from rp.models.dsl import Layer, ObjectRef
from rp.models.projection_refresh import (
    ProjectionRefreshRequest,
    ProjectionRefreshServiceError,
)
from rp.models.story_runtime import ChapterWorkspace, StorySession

from .core_state_store_repository import CoreStateStoreRepository
from .memory_object_mapper import (
    authoritative_bindings,
    normalize_authoritative_ref,
    projection_bindings,
    resolve_authoritative_binding,
)


class CoreStateDualWriteService:
    """Persist formal Core State rows while legacy JSON backends remain active."""

    def __init__(self, *, repository: CoreStateStoreRepository) -> None:
        self._repository = repository

    def seed_activation_state(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
    ) -> None:
        self.ensure_authoritative_seed(
            session=session,
            snapshot=dict(session.current_state_json or {}),
            source_kind="activation_seed",
        )
        self.sync_projection_snapshot(
            session=session,
            chapter=chapter,
            snapshot=dict(chapter.builder_snapshot_json or {}),
            refresh_source_kind="activation_seed",
        )

    def ensure_authoritative_seed(
        self,
        *,
        session: StorySession,
        snapshot: dict[str, Any],
        source_kind: str,
    ) -> None:
        for binding in authoritative_bindings():
            value = self._extract_payload(
                snapshot=snapshot, field_name=binding.backend_field
            )
            current_record = self._repository.upsert_authoritative_object(
                story_id=session.story_id,
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope="story",
                current_revision=1,
                data_json=value,
                metadata_json={"dual_write_source": source_kind},
                latest_apply_id=None,
            )
            self._repository.upsert_authoritative_revision(
                authoritative_object_id=current_record.authoritative_object_id,
                story_id=session.story_id,
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope="story",
                revision=1,
                data_json=value,
                revision_source_kind=source_kind,
                metadata_json={"dual_write_source": source_kind},
            )

    def ensure_authoritative_targets_seed(
        self,
        *,
        session: StorySession,
        snapshot: dict[str, Any],
        target_refs: list[ObjectRef],
        source_kind: str = "write_switch_seed",
    ) -> None:
        for raw_ref in target_refs:
            target_ref = normalize_authoritative_ref(raw_ref)
            binding = resolve_authoritative_binding(target_ref)
            if binding is None:
                continue
            scope = target_ref.scope or "story"
            current_record = self._repository.get_authoritative_object(
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                scope=scope,
                object_id=binding.object_id,
            )
            if current_record is not None:
                continue
            value = self._extract_payload(
                snapshot=snapshot,
                field_name=binding.backend_field,
            )
            current_record = self._repository.upsert_authoritative_object(
                story_id=session.story_id,
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope=scope,
                current_revision=1,
                data_json=value,
                metadata_json={"dual_write_source": source_kind},
                latest_apply_id=None,
            )
            self._repository.upsert_authoritative_revision(
                authoritative_object_id=current_record.authoritative_object_id,
                story_id=session.story_id,
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope=scope,
                revision=1,
                data_json=value,
                revision_source_kind=source_kind,
                metadata_json={"dual_write_source": source_kind},
            )

    def current_authoritative_revision(
        self,
        *,
        session_id: str,
        target_ref: ObjectRef,
    ) -> int:
        normalized = normalize_authoritative_ref(target_ref)
        row = self._repository.get_authoritative_object(
            session_id=session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            scope=normalized.scope or "story",
            object_id=normalized.object_id,
        )
        if row is None:
            return 0
        return int(row.current_revision or 0)

    def materialize_authoritative_snapshot(
        self,
        *,
        session: StorySession,
        fallback_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = dict(fallback_snapshot or {})
        rows = {
            row.object_id: row
            for row in self._repository.list_authoritative_objects_for_session(
                session_id=session.session_id
            )
        }
        materialized: dict[str, Any] = deepcopy(fallback)
        for binding in authoritative_bindings():
            row = rows.get(binding.object_id)
            if row is not None:
                materialized[binding.backend_field] = deepcopy(row.data_json)
                continue
            materialized[binding.backend_field] = self._extract_payload(
                snapshot=fallback,
                field_name=binding.backend_field,
            )
        return materialized

    def apply_authoritative_mutation(
        self,
        *,
        session: StorySession,
        before_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
        target_refs: list[ObjectRef],
        revision_after: dict[str, int],
        apply_id: str,
        proposal_id: str,
    ) -> dict[
        str,
        tuple[CoreStateAuthoritativeObjectRecord, CoreStateAuthoritativeRevisionRecord],
    ]:
        written: dict[
            str,
            tuple[
                CoreStateAuthoritativeObjectRecord, CoreStateAuthoritativeRevisionRecord
            ],
        ] = {}
        for raw_ref in target_refs:
            target_ref = normalize_authoritative_ref(raw_ref)
            binding = resolve_authoritative_binding(target_ref)
            if binding is None:
                continue
            scope = target_ref.scope or "story"
            desired_revision = int(revision_after.get(target_ref.object_id) or 1)
            if desired_revision > 1:
                self._ensure_authoritative_revision_one(
                    session=session,
                    binding=binding,
                    scope=scope,
                    value=self._extract_payload(
                        snapshot=before_snapshot,
                        field_name=binding.backend_field,
                    ),
                )

            after_value = self._extract_payload(
                snapshot=after_snapshot,
                field_name=binding.backend_field,
            )
            current_record = self._repository.upsert_authoritative_object(
                story_id=session.story_id,
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope=scope,
                current_revision=desired_revision,
                data_json=after_value,
                metadata_json={"dual_write_source": "proposal_apply"},
                latest_apply_id=apply_id,
            )
            revision_record = self._repository.upsert_authoritative_revision(
                authoritative_object_id=current_record.authoritative_object_id,
                story_id=session.story_id,
                session_id=session.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope=scope,
                revision=desired_revision,
                data_json=after_value,
                revision_source_kind="proposal_apply",
                source_apply_id=apply_id,
                source_proposal_id=proposal_id,
                metadata_json={"dual_write_source": "proposal_apply"},
            )
            written[binding.object_id] = (current_record, revision_record)
        return written

    def materialize_projection_snapshot(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        fallback_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = dict(fallback_snapshot or {})
        fallback.pop("writer_hints", None)
        rows = {
            row.summary_id: row
            for row in self._repository.list_projection_slots_for_chapter(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
        }
        materialized = deepcopy(fallback)
        materialized["chapter_index"] = chapter.chapter_index
        materialized["phase"] = chapter.phase.value
        for binding in projection_bindings():
            row = rows.get(binding.summary_id)
            if row is not None:
                materialized[binding.slot_name] = [
                    str(item) for item in list(row.items_json or []) if item is not None
                ]
                continue
            materialized[binding.slot_name] = [
                str(item)
                for item in list(fallback.get(binding.slot_name) or [])
                if item is not None
            ]
        return materialized

    def sync_projection_snapshot(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        snapshot: dict[str, Any],
        refresh_source_kind: str,
        refresh_source_ref: str | None = None,
        refresh_request: ProjectionRefreshRequest | None = None,
    ) -> None:
        request = refresh_request or ProjectionRefreshRequest(
            refresh_source_kind=refresh_source_kind,
            refresh_source_ref=refresh_source_ref,
        )
        self.validate_projection_refresh_request(
            session_id=session.session_id,
            chapter=chapter,
            refresh_request=request,
        )
        for binding in projection_bindings():
            items = [
                str(item)
                for item in snapshot.get(binding.slot_name, [])
                if item is not None
            ]
            existing = self._repository.get_projection_slot(
                chapter_workspace_id=chapter.chapter_workspace_id,
                summary_id=binding.summary_id,
            )
            metadata = self._projection_refresh_metadata(
                refresh_source_kind=request.refresh_source_kind,
                refresh_source_ref=request.refresh_source_ref,
                refresh_request=request,
            )
            if (
                existing is not None
                and list(existing.items_json or []) == items
                and existing.last_refresh_kind == request.refresh_source_kind
                and dict(existing.metadata_json or {}) == metadata
            ):
                continue
            next_revision = 1 if existing is None else existing.current_revision + 1
            current_record = self._repository.upsert_projection_slot(
                story_id=session.story_id,
                session_id=session.session_id,
                chapter_workspace_id=chapter.chapter_workspace_id,
                layer=Layer.CORE_STATE_PROJECTION.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                summary_id=binding.summary_id,
                slot_name=binding.slot_name,
                scope="chapter",
                current_revision=next_revision,
                items_json=items,
                metadata_json=metadata,
                last_refresh_kind=request.refresh_source_kind,
            )
            self._repository.upsert_projection_slot_revision(
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
                revision=next_revision,
                items_json=items,
                refresh_source_kind=request.refresh_source_kind,
                refresh_source_ref=request.refresh_source_ref,
                metadata_json=metadata,
            )

    def validate_projection_refresh_request(
        self,
        *,
        session_id: str,
        chapter: ChapterWorkspace,
        refresh_request: ProjectionRefreshRequest,
    ) -> None:
        self._validate_projection_source_refs(
            session_id=session_id,
            refresh_request=refresh_request,
        )
        self._validate_projection_base_revision(
            chapter=chapter,
            refresh_request=refresh_request,
        )

    @staticmethod
    def _projection_refresh_metadata(
        *,
        refresh_source_kind: str,
        refresh_source_ref: str | None,
        refresh_request: ProjectionRefreshRequest | None = None,
    ) -> dict[str, Any]:
        request = refresh_request or ProjectionRefreshRequest(
            refresh_source_kind=refresh_source_kind,
            refresh_source_ref=refresh_source_ref,
        )
        metadata: dict[str, Any] = {
            "dual_write_source": request.refresh_source_kind,
            "layer_family": "core_state.derived_projection",
            "semantic_layer": "Core State.derived_projection",
            "projection_role": "current_projection",
            "materialization_event": "projection_refresh",
            "maintenance_event": request.refresh_source_kind,
            "authoritative_mutation": False,
            "refresh_actor": request.refresh_actor,
            "refresh_reason": request.refresh_reason,
            "base_revision": request.base_revision,
            "projection_dirty_state": request.projection_dirty_state,
            "source_authoritative_refs": [
                ref.model_dump(mode="json") for ref in request.source_authoritative_refs
            ],
            "source_refs": [ref.model_dump(mode="json") for ref in request.source_refs],
            "dirty_targets": [
                target.model_dump(mode="json") for target in request.dirty_targets
            ],
        }
        if request.identity is not None:
            metadata["identity"] = request.identity.model_dump(mode="json")
        if request.refresh_source_ref:
            metadata["maintenance_source_ref"] = request.refresh_source_ref
        return metadata

    def _validate_projection_source_refs(
        self,
        *,
        session_id: str,
        refresh_request: ProjectionRefreshRequest,
    ) -> None:
        for source_ref in refresh_request.source_authoritative_refs:
            if source_ref.revision is None:
                raise ProjectionRefreshServiceError(
                    "projection_refresh_source_revision_missing",
                    source_ref.object_id,
                )
            current_revision = self.current_authoritative_revision(
                session_id=session_id,
                target_ref=source_ref,
            )
            if current_revision != source_ref.revision:
                raise ProjectionRefreshServiceError(
                    "projection_refresh_source_revision_conflict",
                    f"{source_ref.object_id}:base={source_ref.revision}:current={current_revision}",
                )

    def _validate_projection_base_revision(
        self,
        *,
        chapter: ChapterWorkspace,
        refresh_request: ProjectionRefreshRequest,
    ) -> None:
        if refresh_request.base_revision is None:
            return
        for binding in projection_bindings():
            existing = self._repository.get_projection_slot(
                chapter_workspace_id=chapter.chapter_workspace_id,
                summary_id=binding.summary_id,
            )
            if existing is None:
                continue
            if int(existing.current_revision or 0) != refresh_request.base_revision:
                raise ProjectionRefreshServiceError(
                    "projection_refresh_base_revision_conflict",
                    f"{binding.summary_id}:base={refresh_request.base_revision}:current={existing.current_revision}",
                )

    def _ensure_authoritative_revision_one(
        self,
        *,
        session: StorySession,
        binding,
        scope: str,
        value: dict[str, Any] | list[Any],
    ) -> None:
        existing_revision = self._repository.get_authoritative_revision(
            session_id=session.session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            scope=scope,
            object_id=binding.object_id,
            revision=1,
        )
        if existing_revision is not None:
            return
        current_record = self._repository.upsert_authoritative_object(
            story_id=session.story_id,
            session_id=session.session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=binding.domain.value,
            domain_path=binding.domain_path,
            object_id=binding.object_id,
            scope=scope,
            current_revision=1,
            data_json=value,
            metadata_json={"dual_write_source": "repair_seed"},
            latest_apply_id=None,
        )
        self._repository.upsert_authoritative_revision(
            authoritative_object_id=current_record.authoritative_object_id,
            story_id=session.story_id,
            session_id=session.session_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=binding.domain.value,
            domain_path=binding.domain_path,
            object_id=binding.object_id,
            scope=scope,
            revision=1,
            data_json=value,
            revision_source_kind="repair",
            metadata_json={"dual_write_source": "proposal_apply.before_snapshot"},
        )

    @staticmethod
    def _extract_payload(
        *,
        snapshot: dict[str, Any],
        field_name: str,
    ) -> dict[str, Any] | list[Any]:
        value = deepcopy(snapshot.get(field_name))
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        if value is None:
            return {}
        return {"value": value}
