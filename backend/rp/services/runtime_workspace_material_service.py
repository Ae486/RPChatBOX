"""In-process Runtime Workspace material service skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field

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


RUNTIME_WORKSPACE_TRACE_ROLE = "runtime_workspace_trace_invalidation_skeleton"


@dataclass
class RuntimeWorkspaceMaterialStore:
    """Injected in-process store used until a later slice proves persistence."""

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

    The service deliberately keeps material in an injected process-local store.
    It validates memory domains through the registry and emits lightweight
    trace/invalidation events, but it is not Core State, Recall, or Archival
    truth storage.
    """

    def __init__(
        self,
        *,
        registry_service: MemoryContractRegistryService | None = None,
        memory_change_event_service: MemoryChangeEventService | None = None,
        store: RuntimeWorkspaceMaterialStore | None = None,
    ) -> None:
        self._registry_service = registry_service or MemoryContractRegistryService()
        self._memory_change_event_service = memory_change_event_service
        self._store = store or RuntimeWorkspaceMaterialStore()

    @property
    def store(self) -> RuntimeWorkspaceMaterialStore:
        return self._store

    def record_material(
        self,
        material: RuntimeWorkspaceMaterial,
    ) -> RuntimeWorkspaceMaterialReceipt:
        resolved_domain = self._require_registered_domain(material.domain)
        material = material.model_copy(update={"domain": resolved_domain})
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

    def get_material(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
    ) -> RuntimeWorkspaceMaterial | None:
        return self._store.materials_by_identity.get(_identity_key(identity), {}).get(
            material_id
        )

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

        materials = list(
            self._store.materials_by_identity.get(_identity_key(identity), {}).values()
        )
        return [
            material
            for material in materials
            if (material_kind is None or material.material_kind == material_kind)
            and (resolved_domain is None or material.domain == resolved_domain)
            and (lifecycle is None or material.lifecycle == lifecycle)
        ]

    def update_lifecycle(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        lifecycle: RuntimeWorkspaceMaterialLifecycle,
        reason: str,
    ) -> RuntimeWorkspaceMaterialReceipt:
        normalized_reason = _require_non_blank(reason, field_name="reason")
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
            reason=normalized_reason,
            extra_metadata={
                "previous_lifecycle": material.lifecycle.value,
                "lifecycle": lifecycle.value,
            },
        )
        self._store.events.append(event)
        self._publish_event(event)
        return RuntimeWorkspaceMaterialReceipt(material=updated, event=event)

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
        extra_metadata: dict[str, str],
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
            event_id=f"{material.material_id}:{operation_kind}:{len(self._store.events) + 1}",
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
