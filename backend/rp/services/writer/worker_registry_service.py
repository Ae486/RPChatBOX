"""Runtime-centric worker registry bootstrap built on memory registry + snapshot truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from rp.models.memory_contract_registry import MemoryDomainContract
from rp.models.runtime_identity import (
    RuntimeProfileSnapshotCompiledProfile,
    RuntimeWorkerActivation,
)
from rp.models.mode_extension_contracts import (
    CHARACTER_MEMORY_WORKER_ID,
    RULE_STATE_WORKER_ID,
    SCENE_INTERACTION_WORKER_ID,
)
from rp.models.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    RuntimeWorkerRegistry,
    WorkerDescriptor,
    WorkerExecutionClass,
    WorkerExecutionPolicy,
)
from rp.services.memory_contract_registry import MemoryContractRegistryService
from rp.services.memory_registry_management_service import (
    MemoryRegistryManagementService,
)
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService

LONGFORM_MEMORY_WORKER_ID = "LongformMemoryWorker"
WRITING_WORKER_ID = "WritingWorker"
ROLEPLAY_EXTENSION_SOURCE_WORKER_ID = "specialist"
TRPG_EXTENSION_SOURCE_WORKER_ID = "specialist"


@dataclass(frozen=True)
class _BootstrapRuntimeWorkerSpec:
    runtime_worker_id: str
    source_worker_id: str
    display_name: str
    applicable_modes: tuple[str, ...]
    owned_domains: tuple[str, ...]
    read_domains: tuple[str, ...]
    tool_allowlist: tuple[str, ...]
    supported_phases: tuple[str, ...]
    execution_policy: WorkerExecutionPolicy
    context_slot_policy: dict[str, Any]
    metadata: dict[str, Any]
    use_source_activation_fallback: bool = True


class WorkerRegistryServiceError(ValueError):
    """Stable runtime worker-registry error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class WorkerRegistryService:
    """Resolve the runtime bootstrap registry from snapshot-pinned worker activation."""

    def __init__(
        self,
        session: Session,
        *,
        registry_service: MemoryContractRegistryService | None = None,
        registry_management_service: MemoryRegistryManagementService | None = None,
        runtime_profile_snapshot_service: RuntimeProfileSnapshotService | None = None,
    ) -> None:
        self._session = session
        self._registry_service = registry_service
        self._registry_management_service = (
            registry_management_service
            if registry_management_service is not None
            else MemoryRegistryManagementService(session)
        )
        self._runtime_profile_snapshot_service = (
            runtime_profile_snapshot_service
            if runtime_profile_snapshot_service is not None
            else RuntimeProfileSnapshotService(session)
        )

    def build_registry_for_snapshot(self, *, snapshot_id: str) -> RuntimeWorkerRegistry:
        snapshot = self._runtime_profile_snapshot_service.require_snapshot(snapshot_id)
        compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(
            snapshot.compiled_profile_json or {}
        )
        return self.build_registry(
            compiled_profile=compiled,
            snapshot_id=snapshot.runtime_profile_snapshot_id,
        )

    def build_registry(
        self,
        *,
        compiled_profile: RuntimeProfileSnapshotCompiledProfile | dict[str, Any],
        snapshot_id: str | None = None,
    ) -> RuntimeWorkerRegistry:
        compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(compiled_profile)
        registry_service = self._effective_registry_service()
        domains_by_id = {
            domain.domain_id: domain
            for domain in registry_service.list_domains(include_hidden=True)
        }
        registrations = [
            self._build_registration(
                spec=spec,
                compiled=compiled,
                domains_by_id=domains_by_id,
                registry_service=registry_service,
            )
            for spec in _BOOTSTRAP_RUNTIME_WORKERS
            if compiled.mode_profile.mode in spec.applicable_modes
        ]
        return RuntimeWorkerRegistry(
            snapshot_id=snapshot_id,
            mode=compiled.mode_profile.mode,
            registry_version=compiled.mode_profile.registry_version,
            workers=registrations,
            metadata={
                "bootstrap": True,
                "source": "memory_registry_plus_runtime_profile_snapshot",
            },
        )

    def list_workers(
        self,
        *,
        snapshot_id: str,
        include_inactive: bool = False,
    ) -> list[RuntimeWorkerRegistration]:
        registry = self.build_registry_for_snapshot(snapshot_id=snapshot_id)
        if include_inactive:
            return list(registry.workers)
        return [worker for worker in registry.workers if worker.active]

    def get_worker(
        self,
        worker_id: str,
        *,
        snapshot_id: str,
        include_inactive: bool = False,
    ) -> RuntimeWorkerRegistration | None:
        normalized_id = _normalize_key(worker_id)
        for worker in self.list_workers(
            snapshot_id=snapshot_id,
            include_inactive=include_inactive,
        ):
            if _normalize_key(worker.descriptor.worker_id) == normalized_id:
                return worker
        return None

    def require_worker(
        self,
        worker_id: str,
        *,
        snapshot_id: str,
        include_inactive: bool = False,
    ) -> RuntimeWorkerRegistration:
        worker = self.get_worker(
            worker_id,
            snapshot_id=snapshot_id,
            include_inactive=include_inactive,
        )
        if worker is None:
            raise WorkerRegistryServiceError(
                "runtime_worker_not_registered",
                _normalize_key(worker_id),
            )
        return worker

    def _build_registration(
        self,
        *,
        spec: _BootstrapRuntimeWorkerSpec,
        compiled: RuntimeProfileSnapshotCompiledProfile,
        domains_by_id: dict[str, MemoryDomainContract],
        registry_service: MemoryContractRegistryService,
    ) -> RuntimeWorkerRegistration:
        source_worker = registry_service.get_worker(spec.source_worker_id)
        if source_worker is None:
            raise WorkerRegistryServiceError(
                "runtime_worker_registry_source_missing",
                spec.source_worker_id,
            )
        activation = compiled.worker_activation.get(spec.runtime_worker_id)
        if activation is None and spec.use_source_activation_fallback:
            activation = compiled.worker_activation.get(source_worker.worker_id)
        activation_payload = (
            activation.model_dump(mode="json")
            if activation is not None
            else RuntimeWorkerActivation(
                active=False,
                metadata={"missing_in_snapshot": True},
            ).model_dump(mode="json")
        )
        owned_domains = self._resolve_registered_domains(
            domains_by_id=domains_by_id,
            domain_ids=spec.owned_domains,
        )
        read_domains = self._resolve_registered_domains(
            domains_by_id=domains_by_id,
            domain_ids=spec.read_domains,
        )
        descriptor = WorkerDescriptor(
            worker_id=spec.runtime_worker_id,
            display_name=spec.display_name,
            owned_domains=owned_domains,
            read_domains=read_domains,
            allowed_layers=self._allowed_layers_for_domains(
                domains_by_id=domains_by_id,
                domain_ids=[*owned_domains, *read_domains],
            ),
            tool_allowlist=list(spec.tool_allowlist),
            default_execution_policy=spec.execution_policy.policy_id,
            supported_phases=list(spec.supported_phases),
            permission_profile_ref=_optional_text(activation_payload.get("profile_ref")),
            provider_defaults={},
            model_defaults=self._model_defaults_for_worker(
                compiled=compiled,
                runtime_worker_id=spec.runtime_worker_id,
                source_worker_id=source_worker.worker_id,
            ),
            context_slot_policy=dict(spec.context_slot_policy),
            output_schema_version="story-runtime.worker-result.v1",
            metadata={
                "bootstrap": True,
                "source_worker_id": source_worker.worker_id,
                "source_worker_label": source_worker.label,
                "source_worker_lifecycle": source_worker.lifecycle.value,
                "source_worker_aliases": list(source_worker.aliases),
                **dict(spec.metadata),
            },
        )
        return RuntimeWorkerRegistration(
            descriptor=descriptor,
            execution_policy=spec.execution_policy.model_copy(deep=True),
            active=bool(activation_payload.get("active", False)),
            source_worker_id=source_worker.worker_id,
            source_label=source_worker.label,
            activation_metadata=dict(activation_payload.get("metadata") or {}),
            metadata={
                "bootstrap": True,
                "compiled_from_snapshot": True,
            },
        )

    @staticmethod
    def _resolve_registered_domains(
        *,
        domains_by_id: dict[str, MemoryDomainContract],
        domain_ids: tuple[str, ...],
    ) -> list[str]:
        resolved: list[str] = []
        for domain_id in domain_ids:
            domain = domains_by_id.get(domain_id)
            if domain is None:
                continue
            resolved.append(domain.domain_id)
        return resolved

    @staticmethod
    def _allowed_layers_for_domains(
        *,
        domains_by_id: dict[str, MemoryDomainContract],
        domain_ids: list[str],
    ) -> list[str]:
        allowed_layers: list[str] = []
        seen: set[str] = set()
        for domain_id in domain_ids:
            domain = domains_by_id.get(domain_id)
            if domain is None:
                continue
            for layer in domain.allowed_layers:
                layer_key = _normalize_key(layer)
                if layer_key in seen:
                    continue
                seen.add(layer_key)
                allowed_layers.append(layer)
        return allowed_layers

    @staticmethod
    def _model_defaults_for_worker(
        *,
        compiled: RuntimeProfileSnapshotCompiledProfile,
        runtime_worker_id: str,
        source_worker_id: str,
    ) -> dict[str, Any]:
        if runtime_worker_id == WRITING_WORKER_ID:
            return dict(compiled.writer_model_profile or {})
        if runtime_worker_id in compiled.worker_model_profiles:
            return dict(compiled.worker_model_profiles.get(runtime_worker_id) or {})
        return dict(compiled.worker_model_profiles.get(source_worker_id) or {})

    def _effective_registry_service(self) -> MemoryContractRegistryService:
        if self._registry_service is not None:
            return self._registry_service
        return self._registry_management_service.registry_service()


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _longform_memory_policy() -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id="longform_memory_worker.default",
        execution_class=WorkerExecutionClass.ALWAYS_RUN,
        blocking_default=True,
        allow_async=False,
        allow_degrade=True,
        must_record_trace=True,
        requires_runtime_workspace=True,
        requires_post_write_job=True,
        metadata={"bootstrap": True, "legacy_source_worker_id": "specialist"},
    )


def _writing_worker_policy() -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id="writing_worker.default",
        execution_class=WorkerExecutionClass.ALWAYS_RUN,
        blocking_default=True,
        allow_async=False,
        allow_degrade=False,
        must_record_trace=True,
        requires_runtime_workspace=False,
        requires_post_write_job=False,
        metadata={"bootstrap": True, "legacy_source_worker_id": "writer"},
    )


def _scheduled_extension_policy(*, policy_id: str, source_worker_id: str) -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id=policy_id,
        execution_class=WorkerExecutionClass.SCHEDULED,
        blocking_default=True,
        allow_async=False,
        allow_degrade=True,
        must_record_trace=True,
        requires_runtime_workspace=True,
        requires_post_write_job=True,
        metadata={
            "bootstrap": True,
            "runtime_extension": True,
            "legacy_source_worker_id": source_worker_id,
        },
    )


def _always_run_extension_policy(
    *,
    policy_id: str,
    source_worker_id: str,
    blocking_default: bool,
) -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id=policy_id,
        execution_class=WorkerExecutionClass.ALWAYS_RUN,
        blocking_default=blocking_default,
        allow_async=False,
        allow_degrade=True,
        must_record_trace=True,
        requires_runtime_workspace=True,
        requires_post_write_job=True,
        metadata={
            "bootstrap": True,
            "runtime_extension": True,
            "legacy_source_worker_id": source_worker_id,
        },
    )


_BOOTSTRAP_RUNTIME_WORKERS: tuple[_BootstrapRuntimeWorkerSpec, ...] = (
    _BootstrapRuntimeWorkerSpec(
        runtime_worker_id=LONGFORM_MEMORY_WORKER_ID,
        source_worker_id="specialist",
        display_name="Longform Memory Worker",
        applicable_modes=("longform",),
        owned_domains=(
            "chapter",
            "character",
            "narrative_progress",
            "plot_thread",
            "foreshadow",
            "timeline",
            "goal",
        ),
        read_domains=("scene", "character", "knowledge_boundary", "relation"),
        tool_allowlist=(
            "memory.get_state",
            "memory.get_summary",
            "memory.search_recall",
            "memory.search_archival",
            "proposal.submit",
            "projection.refresh",
        ),
        supported_phases=(
            "pre_write_context",
            "post_write_maintenance",
            "manual_refresh",
        ),
        execution_policy=_longform_memory_policy(),
        context_slot_policy={
            "allow_recent_turn_refs": True,
            "allow_core_projection_refs": True,
            "allow_retrieval_refs": True,
            "allow_workspace_refs": True,
            "forbid_runtime_workspace_logs": False,
        },
        metadata={
            "adapter_candidates": ["LongformSpecialistService"],
            "runtime_truth": "worker_runtime_contract",
        },
    ),
    _BootstrapRuntimeWorkerSpec(
        runtime_worker_id=WRITING_WORKER_ID,
        source_worker_id="writer",
        display_name="Writing Worker",
        applicable_modes=("longform", "roleplay", "trpg"),
        owned_domains=(),
        read_domains=(),
        tool_allowlist=(),
        supported_phases=("writer_generation",),
        execution_policy=_writing_worker_policy(),
        context_slot_policy={
            "packet_required": True,
            "allow_workspace_refs": False,
            "allow_retrieval_refs": False,
            "allow_raw_memory_reads": False,
        },
        metadata={
            "adapter_candidates": ["WritingWorkerExecutionService"],
            "runtime_truth": "worker_runtime_contract",
        },
    ),
    _BootstrapRuntimeWorkerSpec(
        runtime_worker_id=CHARACTER_MEMORY_WORKER_ID,
        source_worker_id=ROLEPLAY_EXTENSION_SOURCE_WORKER_ID,
        display_name="Character Memory Worker",
        applicable_modes=("roleplay",),
        owned_domains=("character", "relation"),
        read_domains=("knowledge_boundary", "scene", "goal"),
        tool_allowlist=(
            "memory.get_state",
            "memory.get_summary",
            "memory.search_recall",
            "proposal.submit",
            "projection.refresh",
        ),
        supported_phases=(
            "pre_write_context",
            "post_write_maintenance",
            "manual_refresh",
        ),
        execution_policy=_always_run_extension_policy(
            policy_id="character_memory_worker.default",
            source_worker_id=ROLEPLAY_EXTENSION_SOURCE_WORKER_ID,
            blocking_default=True,
        ),
        context_slot_policy={
            "allow_recent_turn_refs": True,
            "allow_core_projection_refs": True,
            "allow_retrieval_refs": True,
            "allow_workspace_refs": True,
            "sidecar_slot_ids": ["character_local_memory", "knowledge_boundary_refs"],
            "forbid_runtime_workspace_logs": False,
        },
        metadata={
            "runtime_extension": True,
            "mode_scope": ["roleplay"],
            "adapter_candidates": [],
        },
        use_source_activation_fallback=False,
    ),
    _BootstrapRuntimeWorkerSpec(
        runtime_worker_id=SCENE_INTERACTION_WORKER_ID,
        source_worker_id=ROLEPLAY_EXTENSION_SOURCE_WORKER_ID,
        display_name="Scene Interaction Worker",
        applicable_modes=("roleplay",),
        owned_domains=("scene", "goal"),
        read_domains=("character", "knowledge_boundary", "relation"),
        tool_allowlist=(
            "memory.get_state",
            "memory.get_summary",
            "memory.search_recall",
            "proposal.submit",
            "projection.refresh",
        ),
        supported_phases=(
            "pre_write_context",
            "post_write_maintenance",
            "manual_refresh",
        ),
        execution_policy=_scheduled_extension_policy(
            policy_id="scene_interaction_worker.default",
            source_worker_id=ROLEPLAY_EXTENSION_SOURCE_WORKER_ID,
        ),
        context_slot_policy={
            "allow_recent_turn_refs": True,
            "allow_core_projection_refs": True,
            "allow_retrieval_refs": True,
            "allow_workspace_refs": True,
            "sidecar_slot_ids": ["scene_intent", "participant_intent"],
            "forbid_runtime_workspace_logs": False,
        },
        metadata={
            "runtime_extension": True,
            "mode_scope": ["roleplay"],
            "adapter_candidates": [],
        },
        use_source_activation_fallback=False,
    ),
    _BootstrapRuntimeWorkerSpec(
        runtime_worker_id=RULE_STATE_WORKER_ID,
        source_worker_id=TRPG_EXTENSION_SOURCE_WORKER_ID,
        display_name="Rule State Worker",
        applicable_modes=("trpg",),
        owned_domains=("rule_state", "inventory", "world_rule"),
        read_domains=("scene", "character", "goal", "knowledge_boundary"),
        tool_allowlist=(
            "memory.get_state",
            "memory.get_summary",
            "memory.search_recall",
            "memory.search_archival",
            "proposal.submit",
            "projection.refresh",
        ),
        supported_phases=(
            "pre_write_context",
            "post_write_maintenance",
            "manual_refresh",
        ),
        execution_policy=_always_run_extension_policy(
            policy_id="rule_state_worker.default",
            source_worker_id=TRPG_EXTENSION_SOURCE_WORKER_ID,
            blocking_default=True,
        ),
        context_slot_policy={
            "allow_recent_turn_refs": True,
            "allow_core_projection_refs": True,
            "allow_retrieval_refs": True,
            "allow_workspace_refs": True,
            "sidecar_slot_ids": ["rule_card", "rule_state_card"],
            "forbid_runtime_workspace_logs": False,
        },
        metadata={
            "runtime_extension": True,
            "mode_scope": ["trpg"],
            "adapter_candidates": [],
        },
        use_source_activation_fallback=False,
    ),
)
