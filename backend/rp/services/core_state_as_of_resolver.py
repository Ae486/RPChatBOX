"""Branch-aware Core State as-of manifest resolver."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Any

from sqlalchemy import asc
from sqlmodel import Session, select

from models.rp_core_state_store import (
    CoreStateAuthoritativeRevisionRecord,
    CoreStateSnapshotManifestRecord,
)
from models.rp_story_store import BranchHeadRecord, StorySessionRecord, StoryTurnRecord
from rp.models.dsl import Layer, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_read_contract import (
    CoreStateSnapshotManifest,
    RuntimeBranchReadScope,
)

from .core_state_store_repository import CoreStateStoreRepository
from .memory_object_mapper import authoritative_bindings, normalize_authoritative_ref
from .runtime_read_manifest_service import BranchVisibilityResolver


class CoreStateAsOfResolverError(ValueError):
    """Stable Core State as-of resolver error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class CoreStateAsOfResolver:
    """Resolve exact Core object revisions for one branch/turn read scope."""

    def __init__(
        self,
        *,
        session: Session,
        repository: CoreStateStoreRepository | None = None,
        branch_visibility_resolver: BranchVisibilityResolver | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or CoreStateStoreRepository(session)
        self._branch_visibility_resolver = (
            branch_visibility_resolver or BranchVisibilityResolver(session)
        )

    def build_scope(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None = None,
    ) -> RuntimeBranchReadScope:
        return self._branch_visibility_resolver.build_scope(
            identity=identity,
            selected_turn_id=selected_turn_id,
        )

    def ensure_manifest_for_identity(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        selected_turn_id: str | None = None,
    ) -> CoreStateSnapshotManifest:
        scope = self.build_scope(identity=identity, selected_turn_id=selected_turn_id)
        return self.resolve_manifest(scope=scope, selected_turn_id=selected_turn_id)

    def resolve_manifest(
        self,
        *,
        scope: RuntimeBranchReadScope,
        selected_turn_id: str | None = None,
    ) -> CoreStateSnapshotManifest:
        turn_id = str(
            selected_turn_id or scope.selected_turn_id or scope.active_turn_id or ""
        ).strip()
        if not turn_id:
            raise CoreStateAsOfResolverError(
                "core_state_as_of_turn_required",
                scope.active_branch_head_id,
            )
        turn = self._require_turn(turn_id)
        bound = self._bound_manifest_for_turn(turn)
        if bound is not None:
            return self._record_to_manifest(bound)

        inherited = self._latest_visible_manifest(scope=scope, selected_turn_id=turn_id)
        if inherited is not None:
            self._bind_turn_to_manifest(turn=turn, snapshot_id=inherited.snapshot_id)
            return self._record_to_manifest(inherited)

        if self._can_seed_compatibility_snapshot(scope=scope, turn=turn):
            manifest_kind = (
                "runtime_initial"
                if self._all_current_rows_are_initial(session_id=turn.session_id)
                else "compatibility_snapshot"
            )
            metadata: dict[str, Any] = (
                {
                    "source_route": "core_state_activation_seed",
                    "historical_as_of_unavailable_before_turn_id": None,
                }
                if manifest_kind == "runtime_initial"
                else {
                    "compatibility_warning": (
                        "historical_core_state_as_of_unavailable_before_this_snapshot"
                    ),
                    "historical_as_of_unavailable_before_turn_id": turn.turn_id,
                    "source_route": "core_state_current_rows_compatibility_seed",
                }
            )
            created = self._create_manifest_from_current_rows(
                turn=turn,
                manifest_kind=manifest_kind,
                metadata=metadata,
            )
            self._bind_turn_to_manifest(turn=turn, snapshot_id=created.snapshot_id)
            return self._record_to_manifest(created)

        created = self._create_empty_unavailable_manifest(turn=turn)
        self._bind_turn_to_manifest(turn=turn, snapshot_id=created.snapshot_id)
        return self._record_to_manifest(created)

    def resolve_object_revision(
        self,
        *,
        manifest: CoreStateSnapshotManifest,
        object_ref: ObjectRef,
    ) -> CoreStateAuthoritativeRevisionRecord:
        normalized = normalize_authoritative_ref(object_ref)
        ref_key = self.object_ref_key(
            layer=normalized.layer.value,
            scope=normalized.scope or "story",
            object_id=normalized.object_id,
        )
        revision_ref = str(manifest.effective_revision_map.get(ref_key) or "").strip()
        if not revision_ref:
            raise CoreStateAsOfResolverError(
                "core_state_as_of_revision_missing",
                f"{manifest.snapshot_id}:{ref_key}",
            )
        record = self._revision_record_from_ref(
            session_id=manifest.session_id,
            layer=normalized.layer.value,
            scope=normalized.scope or "story",
            object_id=normalized.object_id,
            revision_ref=revision_ref,
        )
        if record is None:
            raise CoreStateAsOfResolverError(
                "core_state_as_of_revision_missing",
                f"{manifest.snapshot_id}:{ref_key}:{revision_ref}",
            )
        return record

    def record_core_mutation(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        changed_revisions: Iterable[CoreStateAuthoritativeRevisionRecord],
        source_event_ids: list[str] | None = None,
    ) -> CoreStateSnapshotManifest:
        turn = self._require_turn(identity.turn_id)
        if (
            turn.story_id != identity.story_id
            or turn.session_id != identity.session_id
            or turn.branch_head_id != identity.branch_head_id
            or turn.runtime_profile_snapshot_id != identity.runtime_profile_snapshot_id
        ):
            raise CoreStateAsOfResolverError(
                "core_state_as_of_identity_mismatch",
                identity.turn_id,
            )
        scope = self.build_scope(identity=identity)
        parent = self._latest_visible_manifest_before_turn(
            scope=scope,
            selected_turn_id=identity.turn_id,
        )
        effective_map = (
            dict(parent.effective_revision_map_json)
            if parent is not None
            else self._earliest_revision_map(session_id=identity.session_id)
        )
        changed_ref_ids: list[str] = []
        for revision in changed_revisions:
            ref_key = self.object_ref_key(
                layer=revision.layer,
                scope=revision.scope,
                object_id=revision.object_id,
            )
            effective_map[ref_key] = revision.authoritative_revision_id
            changed_ref_ids.append(ref_key)
        manifest = self._repository.create_core_state_snapshot_manifest(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            turn_id=identity.turn_id,
            runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
            parent_snapshot_id=None if parent is None else parent.snapshot_id,
            effective_revision_map=effective_map,
            changed_ref_ids=list(dict.fromkeys(changed_ref_ids)),
            source_event_ids=list(source_event_ids or []),
            manifest_kind="runtime_mutation",
            metadata_json={
                "copy_on_write": True,
                "source_route": "core_mutation_kernel",
            },
        )
        self._bind_turn_to_manifest(turn=turn, snapshot_id=manifest.snapshot_id)
        return self._record_to_manifest(manifest)

    @staticmethod
    def object_ref_key(*, layer: str, scope: str, object_id: str) -> str:
        return f"{layer}:{scope}:{object_id}"

    def _bound_manifest_for_turn(
        self,
        turn: StoryTurnRecord,
    ) -> CoreStateSnapshotManifestRecord | None:
        snapshot_id = str(turn.core_state_snapshot_id or "").strip()
        if not snapshot_id:
            return None
        manifest = self._repository.get_core_state_snapshot_manifest(snapshot_id)
        if manifest is None:
            return None
        if manifest.session_id != turn.session_id or manifest.story_id != turn.story_id:
            return None
        return manifest

    def _latest_visible_manifest(
        self,
        *,
        scope: RuntimeBranchReadScope,
        selected_turn_id: str,
    ) -> CoreStateSnapshotManifestRecord | None:
        return self._latest_visible_manifest_by_scope(
            scope=scope,
            selected_turn_id=selected_turn_id,
            before_selected_turn=False,
        )

    def _latest_visible_manifest_before_turn(
        self,
        *,
        scope: RuntimeBranchReadScope,
        selected_turn_id: str,
    ) -> CoreStateSnapshotManifestRecord | None:
        return self._latest_visible_manifest_by_scope(
            scope=scope,
            selected_turn_id=selected_turn_id,
            before_selected_turn=True,
        )

    def _latest_visible_manifest_by_scope(
        self,
        *,
        scope: RuntimeBranchReadScope,
        selected_turn_id: str,
        before_selected_turn: bool,
    ) -> CoreStateSnapshotManifestRecord | None:
        for branch_head_id in scope.visible_branch_head_ids:
            cutoff_turn_id = scope.turn_cutoff_by_branch.get(branch_head_id)
            turn_order = self._turn_order(
                session_id=scope.session_id,
                branch_head_id=branch_head_id,
            )
            cutoff_order = turn_order.get(str(cutoff_turn_id or "").strip())
            selected_order = turn_order.get(selected_turn_id)
            allowed_turn_ids: set[str] = set()
            for turn_id, order in turn_order.items():
                if cutoff_order is not None and order > cutoff_order:
                    continue
                if (
                    before_selected_turn
                    and branch_head_id == scope.active_branch_head_id
                    and selected_order is not None
                    and order >= selected_order
                ):
                    continue
                allowed_turn_ids.add(turn_id)
            hidden_turn_ids = set(scope.hidden_turn_ids_by_branch.get(branch_head_id, []))
            allowed_turn_ids.difference_update(hidden_turn_ids)
            if not allowed_turn_ids:
                continue
            manifests = [
                manifest
                for manifest in self._repository.list_core_state_snapshot_manifests_for_branch(
                    session_id=scope.session_id,
                    branch_head_id=branch_head_id,
                )
                if manifest.turn_id in allowed_turn_ids
            ]
            if not manifests:
                continue
            manifests.sort(
                key=lambda item: (
                    turn_order.get(item.turn_id, -1),
                    item.created_at,
                    item.snapshot_id,
                )
            )
            return manifests[-1]
        return None

    def _create_manifest_from_current_rows(
        self,
        *,
        turn: StoryTurnRecord,
        manifest_kind: str,
        metadata: dict[str, Any],
    ) -> CoreStateSnapshotManifestRecord:
        effective_map: dict[str, str] = {}
        warnings: list[str] = []
        rows = self._repository.list_authoritative_objects_for_session(
            session_id=turn.session_id
        )
        if not rows and manifest_kind == "compatibility_snapshot":
            warnings.extend(self._seed_compatibility_rows_from_session_mirror(turn=turn))
            rows = self._repository.list_authoritative_objects_for_session(
                session_id=turn.session_id
            )
        for row in rows:
            revision = self._repository.get_authoritative_revision(
                session_id=turn.session_id,
                layer=row.layer,
                scope=row.scope,
                object_id=row.object_id,
                revision=int(row.current_revision or 1),
            )
            if revision is None:
                warnings.append(f"revision_missing:{row.object_id}@{row.current_revision}")
                continue
            effective_map[
                self.object_ref_key(
                    layer=row.layer,
                    scope=row.scope,
                    object_id=row.object_id,
                )
            ] = revision.authoritative_revision_id
        return self._repository.create_core_state_snapshot_manifest(
            story_id=turn.story_id,
            session_id=turn.session_id,
            branch_head_id=turn.branch_head_id,
            turn_id=turn.turn_id,
            runtime_profile_snapshot_id=turn.runtime_profile_snapshot_id,
            effective_revision_map=effective_map,
            changed_ref_ids=list(effective_map),
            source_event_ids=[],
            manifest_kind=manifest_kind,
            metadata_json={**metadata, "warnings": warnings},
        )

    def _seed_compatibility_rows_from_session_mirror(
        self,
        *,
        turn: StoryTurnRecord,
    ) -> list[str]:
        session_record = self._session.get(StorySessionRecord, turn.session_id)
        if session_record is None:
            return ["compatibility_seed_session_missing"]
        snapshot = dict(session_record.current_state_json or {})
        for binding in authoritative_bindings():
            value = self._normalize_json_payload(snapshot.get(binding.backend_field))
            current_record = self._repository.upsert_authoritative_object(
                story_id=turn.story_id,
                session_id=turn.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope="story",
                current_revision=1,
                data_json=value,
                metadata_json={
                    "compatibility_warning": (
                        "historical_core_state_as_of_unavailable_before_this_snapshot"
                    ),
                    "backfilled_from": "story_session.current_state_json",
                    "source_route": "core_state_current_rows_compatibility_seed",
                },
                latest_apply_id=None,
            )
            self._repository.upsert_authoritative_revision(
                authoritative_object_id=current_record.authoritative_object_id,
                story_id=turn.story_id,
                session_id=turn.session_id,
                layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                domain=binding.domain.value,
                domain_path=binding.domain_path,
                object_id=binding.object_id,
                scope="story",
                revision=1,
                data_json=value,
                revision_source_kind="compatibility_snapshot_seed",
                metadata_json={
                    "compatibility_warning": (
                        "historical_core_state_as_of_unavailable_before_this_snapshot"
                    ),
                    "backfilled_from": "story_session.current_state_json",
                    "runtime_writer_context_must_not_use_latest_current_row": True,
                },
            )
        return ["historical_core_state_as_of_unavailable_before_this_snapshot"]

    def _create_empty_unavailable_manifest(
        self,
        *,
        turn: StoryTurnRecord,
    ) -> CoreStateSnapshotManifestRecord:
        return self._repository.create_core_state_snapshot_manifest(
            story_id=turn.story_id,
            session_id=turn.session_id,
            branch_head_id=turn.branch_head_id,
            turn_id=turn.turn_id,
            runtime_profile_snapshot_id=turn.runtime_profile_snapshot_id,
            effective_revision_map={},
            changed_ref_ids=[],
            source_event_ids=[],
            manifest_kind="historical_as_of_unavailable",
            metadata_json={
                "compatibility_warning": "historical_core_state_as_of_unavailable",
                "runtime_writer_context_must_not_use_latest_current_row": True,
                "source_route": "empty_fail_closed_manifest",
            },
        )

    def _earliest_revision_map(self, *, session_id: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for revision in self._repository.list_authoritative_revisions_for_session(
            session_id=session_id
        ):
            key = self.object_ref_key(
                layer=revision.layer,
                scope=revision.scope,
                object_id=revision.object_id,
            )
            if key in result:
                continue
            result[key] = revision.authoritative_revision_id
        return result

    def _revision_record_from_ref(
        self,
        *,
        session_id: str,
        layer: str,
        scope: str,
        object_id: str,
        revision_ref: str,
    ) -> CoreStateAuthoritativeRevisionRecord | None:
        record = self._repository.get_authoritative_revision_by_id(revision_ref)
        if record is not None:
            return record
        if "@" not in revision_ref:
            return None
        ref_object_id, raw_revision = revision_ref.rsplit("@", 1)
        try:
            revision = int(raw_revision)
        except ValueError:
            return None
        return self._repository.get_authoritative_revision(
            session_id=session_id,
            layer=layer,
            scope=scope,
            object_id=ref_object_id or object_id,
            revision=revision,
        )

    def _can_seed_compatibility_snapshot(
        self,
        *,
        scope: RuntimeBranchReadScope,
        turn: StoryTurnRecord,
    ) -> bool:
        if turn.branch_head_id != scope.active_branch_head_id:
            return False
        if turn.turn_id != (scope.active_turn_id or scope.selected_turn_id):
            return False
        if len(scope.visible_branch_head_ids) != 1:
            return False
        if any(scope.hidden_turn_ids_by_branch.values()):
            return False
        branch = self._session.get(BranchHeadRecord, turn.branch_head_id)
        if branch is None:
            return False
        return not bool(str(branch.parent_branch_head_id or "").strip())

    def _all_current_rows_are_initial(self, *, session_id: str) -> bool:
        rows = self._repository.list_authoritative_objects_for_session(
            session_id=session_id
        )
        return bool(rows) and all(int(row.current_revision or 1) == 1 for row in rows)

    def _bind_turn_to_manifest(
        self,
        *,
        turn: StoryTurnRecord,
        snapshot_id: str,
    ) -> None:
        if turn.core_state_snapshot_id == snapshot_id:
            return
        turn.core_state_snapshot_id = snapshot_id
        self._session.add(turn)
        self._session.flush()

    def _turn_order(self, *, session_id: str, branch_head_id: str) -> dict[str, int]:
        stmt = (
            select(StoryTurnRecord)
            .where(StoryTurnRecord.session_id == session_id)
            .where(StoryTurnRecord.branch_head_id == branch_head_id)
            .order_by(asc(StoryTurnRecord.created_at))
            .order_by(asc(StoryTurnRecord.turn_id))
        )
        return {
            record.turn_id: index
            for index, record in enumerate(self._session.exec(stmt).all())
        }

    def _require_turn(self, turn_id: str) -> StoryTurnRecord:
        turn = self._session.get(StoryTurnRecord, turn_id)
        if turn is None:
            raise CoreStateAsOfResolverError("core_state_as_of_turn_missing", turn_id)
        return turn

    @staticmethod
    def _record_to_manifest(
        record: CoreStateSnapshotManifestRecord,
    ) -> CoreStateSnapshotManifest:
        return CoreStateSnapshotManifest(
            snapshot_id=record.snapshot_id,
            parent_snapshot_id=record.parent_snapshot_id,
            story_id=record.story_id,
            session_id=record.session_id,
            branch_head_id=record.branch_head_id,
            turn_id=record.turn_id,
            runtime_profile_snapshot_id=record.runtime_profile_snapshot_id,
            effective_revision_map=deepcopy(record.effective_revision_map_json or {}),
            changed_ref_ids=list(record.changed_ref_ids_json or []),
            source_event_ids=list(record.source_event_ids_json or []),
            manifest_kind=record.manifest_kind,
            metadata=deepcopy(record.metadata_json or {}),
        )

    @staticmethod
    def _normalize_json_payload(value: Any) -> dict[str, Any] | list[Any]:
        cloned = deepcopy(value)
        if isinstance(cloned, dict):
            return cloned
        if isinstance(cloned, list):
            return cloned
        if cloned is None:
            return {}
        return {"value": cloned}
