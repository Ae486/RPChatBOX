"""Runtime Workspace material service with persistent identity-scoped storage."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)
from rp.models.runtime_workspace_material import (
    RUNTIME_WORKSPACE_MATERIAL_LAYER,
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialReceipt,
)
from rp.services.memory_contract_registry import (
    MemoryContractRegistryError,
    MemoryContractRegistryService,
)
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.runtime_memory_persistence_repository import (
    RuntimeWorkspaceMaterialRepository,
    clone_json_value,
    normalize_optional_key,
    utcnow,
)
from services.database import get_engine


RUNTIME_WORKSPACE_TRACE_ROLE = "runtime_workspace_trace_invalidation_skeleton"


@dataclass
class RuntimeWorkspaceMaterialStore:
    """Optional in-process fallback/test seam for Runtime Workspace material."""

    materials_by_identity: dict[
        tuple[str, str, str, str, str],
        dict[str, RuntimeWorkspaceMaterial],
    ] = field(default_factory=dict)
    short_ids_by_identity: dict[tuple[str, str, str, str, str], dict[str, str]] = field(
        default_factory=dict
    )
    events: list[MemoryChangeEvent] = field(default_factory=list)


class RuntimeWorkspaceMaterialServiceError(ValueError):
    """Stable Runtime Workspace material error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RuntimeWorkspaceMaterialService:
    """Identity-scoped Runtime Workspace material service.

    Persistent repository-backed storage is the default truth path. The injected
    in-process store remains available as a fallback/test seam when a caller
    explicitly passes `store=` without a session or repository.
    """

    def __init__(
        self,
        *,
        registry_service: MemoryContractRegistryService | None = None,
        memory_change_event_service: MemoryChangeEventService | None = None,
        session: Session | None = None,
        repository: RuntimeWorkspaceMaterialRepository | None = None,
        store: RuntimeWorkspaceMaterialStore | None = None,
    ) -> None:
        self._registry_service = registry_service or MemoryContractRegistryService()
        self._memory_change_event_service = memory_change_event_service
        self._session = session
        self._repository = repository
        self._store = store or RuntimeWorkspaceMaterialStore()
        self._persistent_enabled = (
            repository is not None or session is not None or store is None
        )

    @property
    def store(self) -> RuntimeWorkspaceMaterialStore:
        return self._store

    def record_material(
        self,
        material: RuntimeWorkspaceMaterial,
    ) -> RuntimeWorkspaceMaterialReceipt:
        resolved_domain = self._require_registered_domain(material.domain)
        normalized_material = material.model_copy(update={"domain": resolved_domain})
        if not self._persistent_enabled:
            return self._record_material_in_store(normalized_material)
        return self._record_material_persistently(normalized_material)

    def get_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
    ) -> RuntimeWorkspaceMaterial | None:
        if not self._persistent_enabled:
            return self._store.materials_by_identity.get(
                _identity_key(identity), {}
            ).get(material_id)

        with self._repository_scope() as (repository, _):
            record = repository.get(identity=identity, material_id=material_id)
            return None if record is None else _record_to_material(record)

    def require_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
    ) -> RuntimeWorkspaceMaterial:
        material = self.get_material(identity=identity, material_id=material_id)
        if material is None:
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_material_not_found",
                material_id,
            )
        return material

    def list_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_kind: RuntimeWorkspaceMaterialKind | None = None,
        domain: str | None = None,
        lifecycle: RuntimeWorkspaceMaterialLifecycle | None = None,
    ) -> list[RuntimeWorkspaceMaterial]:
        resolved_domain = None
        if domain is not None:
            resolved_domain = self._require_registered_domain(domain)

        if not self._persistent_enabled:
            materials = list(
                self._store.materials_by_identity.get(
                    _identity_key(identity), {}
                ).values()
            )
            return [
                material
                for material in materials
                if (material_kind is None or material.material_kind == material_kind)
                and (resolved_domain is None or material.domain == resolved_domain)
                and (lifecycle is None or material.lifecycle == lifecycle)
            ]

        with self._repository_scope() as (repository, _):
            records = repository.list(
                identity=identity,
                material_kind=None if material_kind is None else material_kind.value,
                domain=resolved_domain,
                lifecycle=None if lifecycle is None else lifecycle.value,
            )
            return [_record_to_material(record) for record in records]

    def update_lifecycle(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        lifecycle: RuntimeWorkspaceMaterialLifecycle,
        reason: str,
    ) -> RuntimeWorkspaceMaterialReceipt:
        normalized_reason = _require_non_blank(reason, field_name="reason")
        if not self._persistent_enabled:
            return self._update_lifecycle_in_store(
                identity=identity,
                material_id=material_id,
                lifecycle=lifecycle,
                reason=normalized_reason,
            )
        return self._update_lifecycle_persistently(
            identity=identity,
            material_id=material_id,
            lifecycle=lifecycle,
            reason=normalized_reason,
        )

    def _record_material_in_store(
        self,
        material: RuntimeWorkspaceMaterial,
    ) -> RuntimeWorkspaceMaterialReceipt:
        identity_key = _identity_key(material.identity)
        materials = self._store.materials_by_identity.setdefault(identity_key, {})
        if material.material_id in materials:
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_material_id_conflict",
                material.material_id,
            )

        self._reserve_short_id(identity_key, material=material)
        materials[material.material_id] = material
        event = self._build_event(
            material=material,
            event_kind="runtime_workspace_material_recorded",
            operation_kind="runtime_material.record",
            actor=material.created_by,
            reason="material_recorded",
            extra_metadata={"lifecycle": material.lifecycle.value},
        )
        self._store.events.append(event)
        self._publish_event(event)
        return RuntimeWorkspaceMaterialReceipt(material=material, event=event)

    def _record_material_persistently(
        self,
        material: RuntimeWorkspaceMaterial,
    ) -> RuntimeWorkspaceMaterialReceipt:
        with self._repository_scope() as (repository, managed_session):
            try:
                if repository.get_by_material_id(material.material_id) is not None:
                    raise RuntimeWorkspaceMaterialServiceError(
                        "runtime_workspace_material_id_conflict",
                        material.material_id,
                    )
                self._ensure_short_id_available(repository, material=material)
                record = repository.insert(_material_to_record(material))
                persisted_material = _record_to_material(record)
                event = self._build_event(
                    material=persisted_material,
                    event_kind="runtime_workspace_material_recorded",
                    operation_kind="runtime_material.record",
                    actor=persisted_material.created_by,
                    reason="material_recorded",
                    extra_metadata={"lifecycle": persisted_material.lifecycle.value},
                )
                self._store.events.append(event)
                self._publish_event(event)
                if managed_session is not None:
                    managed_session.commit()
                return RuntimeWorkspaceMaterialReceipt(
                    material=persisted_material,
                    event=event,
                )
            except RuntimeWorkspaceMaterialServiceError:
                _rollback_if_needed(managed_session)
                raise
            except IntegrityError as exc:
                _rollback_if_needed(managed_session)
                self._raise_integrity_error(repository, material=material, exc=exc)
            except Exception:
                _rollback_if_needed(managed_session)
                raise
        raise AssertionError("unreachable")

    def _update_lifecycle_in_store(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        lifecycle: RuntimeWorkspaceMaterialLifecycle,
        reason: str,
    ) -> RuntimeWorkspaceMaterialReceipt:
        identity_key = _identity_key(identity)
        materials = self._store.materials_by_identity.get(identity_key, {})
        material = materials.get(material_id)
        if material is None:
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_material_not_found",
                material_id,
            )

        updated = material.model_copy(update={"lifecycle": lifecycle})
        materials[material_id] = updated
        event = self._build_event(
            material=updated,
            event_kind="runtime_workspace_material_lifecycle_updated",
            operation_kind="runtime_material.lifecycle.update",
            actor=updated.created_by,
            reason=reason,
            extra_metadata={
                "previous_lifecycle": material.lifecycle.value,
                "lifecycle": lifecycle.value,
            },
        )
        self._store.events.append(event)
        self._publish_event(event)
        return RuntimeWorkspaceMaterialReceipt(material=updated, event=event)

    def _update_lifecycle_persistently(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        lifecycle: RuntimeWorkspaceMaterialLifecycle,
        reason: str,
    ) -> RuntimeWorkspaceMaterialReceipt:
        with self._repository_scope() as (repository, managed_session):
            try:
                existing_record = repository.get(
                    identity=identity, material_id=material_id
                )
                if existing_record is None:
                    raise RuntimeWorkspaceMaterialServiceError(
                        "runtime_workspace_material_not_found",
                        material_id,
                    )

                previous_material = _record_to_material(existing_record)
                updated_at = utcnow()
                updated_record = repository.update_lifecycle(
                    identity=identity,
                    material_id=material_id,
                    lifecycle=lifecycle.value,
                    updated_at=updated_at,
                    expired_at=(
                        updated_at
                        if lifecycle == RuntimeWorkspaceMaterialLifecycle.EXPIRED
                        else None
                    ),
                    invalidated_at=(
                        updated_at
                        if lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED
                        else None
                    ),
                )
                if updated_record is None:
                    raise RuntimeWorkspaceMaterialServiceError(
                        "runtime_workspace_material_not_found",
                        material_id,
                    )
                updated_material = _record_to_material(updated_record)
                event = self._build_event(
                    material=updated_material,
                    event_kind="runtime_workspace_material_lifecycle_updated",
                    operation_kind="runtime_material.lifecycle.update",
                    actor=updated_material.created_by,
                    reason=reason,
                    extra_metadata={
                        "previous_lifecycle": previous_material.lifecycle.value,
                        "lifecycle": lifecycle.value,
                    },
                )
                self._store.events.append(event)
                self._publish_event(event)
                if managed_session is not None:
                    managed_session.commit()
                return RuntimeWorkspaceMaterialReceipt(
                    material=updated_material,
                    event=event,
                )
            except RuntimeWorkspaceMaterialServiceError:
                _rollback_if_needed(managed_session)
                raise
            except Exception:
                _rollback_if_needed(managed_session)
                raise

    def _ensure_short_id_available(
        self,
        repository: RuntimeWorkspaceMaterialRepository,
        *,
        material: RuntimeWorkspaceMaterial,
    ) -> None:
        if material.short_id is None:
            return
        previous = repository.get_by_short_id(
            identity=material.identity,
            short_id=material.short_id,
        )
        if previous is not None:
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_short_id_conflict",
                material.short_id,
            )

    def _raise_integrity_error(
        self,
        repository: RuntimeWorkspaceMaterialRepository,
        *,
        material: RuntimeWorkspaceMaterial,
        exc: IntegrityError,
    ) -> None:
        if repository.get_by_material_id(material.material_id) is not None:
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_material_id_conflict",
                material.material_id,
            ) from exc
        if (
            material.short_id is not None
            and repository.get_by_short_id(
                identity=material.identity,
                short_id=material.short_id,
            )
            is not None
        ):
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_short_id_conflict",
                material.short_id,
            ) from exc
        raise

    @contextmanager
    def _repository_scope(
        self,
    ) -> Iterator[tuple[RuntimeWorkspaceMaterialRepository, Session | None]]:
        if not self._persistent_enabled:
            raise RuntimeError("persistent repository scope not available")
        if self._repository is not None:
            yield self._repository, None
            return
        if self._session is not None:
            yield RuntimeWorkspaceMaterialRepository(self._session), None
            return
        with Session(get_engine()) as session:
            yield RuntimeWorkspaceMaterialRepository(session), session

    def _publish_event(self, event: MemoryChangeEvent) -> None:
        if self._memory_change_event_service is None:
            return
        self._memory_change_event_service.record_event(event)

    def _require_registered_domain(self, domain: str) -> str:
        try:
            return self._registry_service.require_domain(domain).domain_id
        except MemoryContractRegistryError as exc:
            if exc.code != "memory_domain_not_registered":
                raise
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_domain_not_registered",
                domain,
            ) from exc

    def _reserve_short_id(
        self,
        identity_key: tuple[str, str, str, str, str],
        *,
        material: RuntimeWorkspaceMaterial,
    ) -> None:
        if material.short_id is None:
            return
        short_ids = self._store.short_ids_by_identity.setdefault(identity_key, {})
        previous_material_id = short_ids.get(_normalize_key(material.short_id))
        if previous_material_id is not None:
            raise RuntimeWorkspaceMaterialServiceError(
                "runtime_workspace_short_id_conflict",
                material.short_id,
            )
        short_ids[_normalize_key(material.short_id)] = material.material_id

    def _build_event(
        self,
        *,
        material: RuntimeWorkspaceMaterial,
        event_kind: str,
        operation_kind: str,
        actor: str,
        reason: str,
        extra_metadata: dict[str, Any],
    ) -> MemoryChangeEvent:
        source_ref = _material_source_ref(material)
        dirty_target = MemoryDirtyTarget(
            target_kind="runtime_workspace_material",
            target_id=material.material_id,
            layer=RUNTIME_WORKSPACE_MATERIAL_LAYER,
            domain=material.domain,
            block_id=_material_block_id(material),
            reason=reason,
            metadata={
                "material_kind": material.material_kind.value,
                "short_id": material.short_id,
                "temporary": True,
                "source_of_truth": False,
            },
        )
        return MemoryChangeEvent(
            event_id=f"runtime_workspace_event_{uuid4().hex}",
            identity=material.identity,
            actor=actor,
            event_kind=event_kind,
            layer=RUNTIME_WORKSPACE_MATERIAL_LAYER,
            domain=material.domain,
            block_id=_material_block_id(material),
            entry_id=material.material_id,
            operation_kind=operation_kind,
            source_refs=[*material.source_refs, source_ref],
            dirty_targets=[dirty_target],
            visibility_effect=material.visibility,
            metadata={
                "trace_role": RUNTIME_WORKSPACE_TRACE_ROLE,
                "material_kind": material.material_kind.value,
                "material_id": material.material_id,
                "short_id": material.short_id,
                "domain_path": material.domain_path,
                "temporary": True,
                "source_of_truth": False,
                "core_state_truth": False,
                "recall_truth": False,
                "archival_truth": False,
                **extra_metadata,
            },
        )


def _material_to_record(
    material: RuntimeWorkspaceMaterial,
) -> RuntimeWorkspaceMaterialRecord:
    lifecycle_timestamp = utcnow()
    return RuntimeWorkspaceMaterialRecord(
        material_id=material.material_id,
        story_id=material.identity.story_id,
        session_id=material.identity.session_id,
        branch_head_id=material.identity.branch_head_id,
        turn_id=material.identity.turn_id,
        runtime_profile_snapshot_id=material.identity.runtime_profile_snapshot_id,
        material_kind=material.material_kind.value,
        domain=material.domain,
        domain_path=material.domain_path,
        short_id=material.short_id,
        short_id_key=normalize_optional_key(material.short_id),
        lifecycle=material.lifecycle.value,
        visibility=material.visibility,
        created_by=material.created_by,
        expiration_ref=material.expiration_ref,
        materialization_ref=material.materialization_ref,
        payload_json=clone_json_value(material.payload),
        source_refs_json=[
            clone_json_value(ref.model_dump(mode="json"))
            for ref in material.source_refs
        ],
        metadata_json=clone_json_value(material.metadata),
        expired_at=(
            lifecycle_timestamp
            if material.lifecycle == RuntimeWorkspaceMaterialLifecycle.EXPIRED
            else None
        ),
        invalidated_at=(
            lifecycle_timestamp
            if material.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED
            else None
        ),
    )


def _record_to_material(
    record: RuntimeWorkspaceMaterialRecord,
) -> RuntimeWorkspaceMaterial:
    metadata = clone_json_value(record.metadata_json)
    if record.expired_at is not None:
        metadata["expired_at"] = _datetime_to_json(record.expired_at)
    if record.invalidated_at is not None:
        metadata["invalidated_at"] = _datetime_to_json(record.invalidated_at)
    return RuntimeWorkspaceMaterial.model_validate(
        {
            "material_id": record.material_id,
            "material_kind": record.material_kind,
            "identity": {
                "story_id": record.story_id,
                "session_id": record.session_id,
                "branch_head_id": record.branch_head_id,
                "turn_id": record.turn_id,
                "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
            },
            "domain": record.domain,
            "domain_path": record.domain_path,
            "source_refs": clone_json_value(record.source_refs_json),
            "short_id": record.short_id,
            "payload": clone_json_value(record.payload_json),
            "lifecycle": record.lifecycle,
            "visibility": record.visibility,
            "created_by": record.created_by,
            "expiration_ref": record.expiration_ref,
            "materialization_ref": record.materialization_ref,
            "metadata": metadata,
        }
    )


def _material_source_ref(material: RuntimeWorkspaceMaterial) -> MemorySourceRef:
    return MemorySourceRef(
        source_type=material.material_kind.value,
        source_id=material.short_id or material.material_id,
        layer=RUNTIME_WORKSPACE_MATERIAL_LAYER,
        domain=material.domain,
        block_id=_material_block_id(material),
        entry_id=material.material_id,
        metadata={
            "material_id": material.material_id,
            "short_id": material.short_id,
            "lifecycle": material.lifecycle.value,
            "visibility": material.visibility,
            "temporary": True,
            "source_of_truth": False,
        },
    )


def _material_block_id(material: RuntimeWorkspaceMaterial) -> str:
    return f"{material.domain}.runtime_workspace"


def _identity_key(identity: MemoryRuntimeIdentity) -> tuple[str, str, str, str, str]:
    return (
        identity.story_id,
        identity.session_id,
        identity.branch_head_id,
        identity.turn_id,
        identity.runtime_profile_snapshot_id,
    )


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _rollback_if_needed(session: Session | None) -> None:
    if session is not None:
        session.rollback()


def _datetime_to_json(value: Any) -> str:
    return value.isoformat()
