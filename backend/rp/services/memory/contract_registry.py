"""Declarative bootstrap registry for RP Memory OS contracts."""

from __future__ import annotations

from typing import Any

from rp.models.memory_contract_registry import (
    MemoryBlockTemplate,
    MemoryContractRegistry,
    MemoryDomainContract,
    MemoryLifecycleState,
    MemoryModeDefault,
    MemoryPermissionDefaults,
    MemoryWorkerDescriptor,
    MemoryWorkerModeDefault,
)


BOOTSTRAP_MEMORY_CONTRACT_REGISTRY_VERSION = "2026-05-04.memory-contract-registry.v1"

CORE_STATE_AUTHORITATIVE_LAYER = "core_state.authoritative"
CORE_STATE_PROJECTION_LAYER = "core_state.projection"
RECALL_LAYER = "recall"
ARCHIVAL_LAYER = "archival"
RUNTIME_WORKSPACE_LAYER = "runtime_workspace"

BOOTSTRAP_MEMORY_DOMAIN_IDS: tuple[str, ...] = (
    "scene",
    "character",
    "knowledge_boundary",
    "relation",
    "goal",
    "timeline",
    "plot_thread",
    "foreshadow",
    "world_rule",
    "inventory",
    "rule_state",
    "chapter",
    "narrative_progress",
)

LONGFORM_ACTIVE_DOMAIN_IDS: frozenset[str] = frozenset(
    {
        "chapter",
        "narrative_progress",
        "timeline",
        "plot_thread",
        "foreshadow",
        "character",
        "scene",
        "knowledge_boundary",
    }
)
ROLEPLAY_ACTIVE_DOMAIN_IDS: frozenset[str] = frozenset(
    {"scene", "character", "knowledge_boundary", "relation", "goal"}
)
TRPG_ACTIVE_DOMAIN_IDS: frozenset[str] = frozenset(
    {
        "rule_state",
        "inventory",
        "world_rule",
        "scene",
        "character",
        "goal",
        "knowledge_boundary",
    }
)

DEFAULT_ALLOWED_LAYERS: tuple[str, ...] = (
    CORE_STATE_AUTHORITATIVE_LAYER,
    CORE_STATE_PROJECTION_LAYER,
    RECALL_LAYER,
    ARCHIVAL_LAYER,
    RUNTIME_WORKSPACE_LAYER,
)

_DOMAIN_LABELS: dict[str, str] = {
    "scene": "Scene",
    "character": "Character",
    "knowledge_boundary": "Knowledge Boundary",
    "relation": "Relation",
    "goal": "Goal",
    "timeline": "Timeline",
    "plot_thread": "Plot Thread",
    "foreshadow": "Foreshadow",
    "world_rule": "World Rule",
    "inventory": "Inventory",
    "rule_state": "Rule State",
    "chapter": "Chapter",
    "narrative_progress": "Narrative Progress",
}

_DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "scene": "Current place, participants, pressure, and local interaction frame.",
    "character": "Character profile, current state, traits, and role-specific facts.",
    "knowledge_boundary": "Who knows what, secrets, misinformation, and reveal state.",
    "relation": "Relationship state between characters, factions, or user-facing actors.",
    "goal": "Active objectives, intents, tasks, and short-term direction.",
    "timeline": "Ordered events, continuity anchors, and temporal state.",
    "plot_thread": "Open narrative threads and their active or pending status.",
    "foreshadow": "Promises, planted details, payoff state, and unresolved hints.",
    "world_rule": "World laws, constraints, rule text, and stable setting mechanics.",
    "inventory": "Items, resources, equipment, and ownership state.",
    "rule_state": "TRPG mechanics state, rule cards, and current mechanical constraints.",
    "chapter": "Chapter-level planning, accepted material, and close-out state.",
    "narrative_progress": "Manuscript progress, outline progress, and writer-facing milestones.",
}

_DOMAIN_ALIASES: dict[str, tuple[str, ...]] = {
    "knowledge_boundary": ("knowledge", "character_knowledge"),
    "rule_state": ("mechanics", "mechanics_state"),
    "plot_thread": ("thread", "story_thread"),
}

BOOTSTRAP_MEMORY_WORKER_IDS: tuple[str, ...] = (
    "orchestrator",
    "specialist",
    "writer",
    "graph_extraction",
)

_WORKER_LABELS: dict[str, str] = {
    "orchestrator": "Story Orchestrator",
    "specialist": "Memory Specialist",
    "writer": "Writer",
    "graph_extraction": "Graph Extraction",
}

_WORKER_DESCRIPTIONS: dict[str, str] = {
    "orchestrator": "Plans the next story-runtime action and dispatches workers.",
    "specialist": "Reads memory and prepares digest/proposal context.",
    "writer": "Produces final user-facing story text from packet input.",
    "graph_extraction": "Maintains archival/retrieval graph projections.",
}

_WORKER_PERMISSION_DEFAULTS: dict[str, dict[str, object]] = {
    "orchestrator": {
        "read": True,
        "propose": False,
        "refresh_projection": False,
    },
    "specialist": {
        "read": True,
        "propose": True,
        "refresh_projection": True,
    },
    "writer": {
        "read": False,
        "propose": False,
        "refresh_projection": False,
    },
    "graph_extraction": {
        "read": True,
        "propose": False,
        "refresh_projection": False,
    },
}

_WORKER_MODE_ROLES: dict[str, dict[str, str]] = {
    "orchestrator": {
        "longform": "planner",
        "roleplay": "scene_dispatch",
        "trpg": "gm_dispatch",
    },
    "specialist": {
        "longform": "context_digest",
        "roleplay": "memory_digest",
        "trpg": "rule_context_digest",
    },
    "writer": {
        "longform": "final_output",
        "roleplay": "response_generation",
        "trpg": "response_generation",
    },
    "graph_extraction": {
        "longform": "retrieval_maintenance",
        "roleplay": "retrieval_maintenance",
        "trpg": "retrieval_maintenance",
    },
}


class MemoryContractRegistryError(ValueError):
    """Stable registry error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class MemoryContractRegistryService:
    """Read-only resolver over the versioned Memory OS registry."""

    def __init__(self, registry: MemoryContractRegistry | None = None) -> None:
        self._registry = registry or build_bootstrap_memory_contract_registry()
        self._domains_by_id = {
            _normalize_key(domain.domain_id): domain
            for domain in self._registry.domains
        }
        self._aliases_by_id: dict[str, str] = {}
        for domain in self._registry.domains:
            for alias in domain.aliases:
                self._aliases_by_id[_normalize_key(alias)] = domain.domain_id
        self._workers_by_id = {
            _normalize_key(worker.worker_id): worker
            for worker in self._registry.workers
        }
        self._worker_aliases_by_id: dict[str, str] = {}
        for worker in self._registry.workers:
            for alias in worker.aliases:
                self._worker_aliases_by_id[_normalize_key(alias)] = worker.worker_id
        self._block_templates_by_id: dict[str, MemoryBlockTemplate] = {}
        self._block_template_aliases_by_id: dict[str, str] = {}
        for domain in self._registry.domains:
            for template in domain.block_templates:
                template_key = _normalize_key(template.block_template_id)
                self._block_templates_by_id[template_key] = template
                for alias in template.aliases:
                    self._block_template_aliases_by_id[_normalize_key(alias)] = (
                        template.block_template_id
                    )

    def registry_version(self) -> str:
        return self._registry.version

    def list_domains(
        self,
        *,
        mode: str | None = None,
        include_hidden: bool = False,
    ) -> list[MemoryDomainContract]:
        normalized_mode = _normalize_key(mode) if mode is not None else None
        domains: list[MemoryDomainContract] = []
        for domain in self._registry.domains:
            if not self._is_listable(domain, include_hidden=include_hidden):
                continue
            if normalized_mode is not None and not self._is_active_for_mode(
                domain,
                normalized_mode,
            ):
                continue
            domains.append(domain)
        return domains

    def get_domain(self, domain_id: str) -> MemoryDomainContract | None:
        resolved_id = self.resolve_alias(domain_id)
        return self._domains_by_id.get(_normalize_key(resolved_id))

    def require_domain(self, domain_id: str) -> MemoryDomainContract:
        domain = self.get_domain(domain_id)
        if domain is None:
            raise MemoryContractRegistryError(
                "memory_domain_not_registered",
                _normalize_key(domain_id),
            )
        return domain

    def resolve_alias(self, domain_id: str) -> str:
        current_id = self._aliases_by_id.get(
            _normalize_key(domain_id),
            _normalize_key(domain_id),
        )
        seen: set[str] = set()
        while True:
            current_key = _normalize_key(current_id)
            if current_key in seen:
                raise MemoryContractRegistryError(
                    "memory_domain_migration_cycle",
                    current_key,
                )
            seen.add(current_key)

            domain = self._domains_by_id.get(current_key)
            if domain is None:
                return current_key
            if domain.lifecycle != MemoryLifecycleState.MIGRATED:
                return domain.domain_id
            if domain.migrated_to is None:
                raise MemoryContractRegistryError(
                    "memory_domain_migration_target_missing",
                    domain.domain_id,
                )
            migrated_to_key = _normalize_key(domain.migrated_to)
            if (
                migrated_to_key not in self._domains_by_id
                and migrated_to_key not in self._aliases_by_id
            ):
                raise MemoryContractRegistryError(
                    "memory_domain_migration_target_missing",
                    domain.domain_id,
                )
            current_id = self._aliases_by_id.get(
                migrated_to_key,
                migrated_to_key,
            )

    def list_block_templates(
        self,
        *,
        domain_id: str | None = None,
        layer: str | None = None,
        include_hidden: bool = False,
    ) -> list[MemoryBlockTemplate]:
        normalized_layer = _normalize_key(layer) if layer is not None else None
        domains = (
            [self.require_domain(domain_id)]
            if domain_id is not None
            else self.list_domains(include_hidden=True)
        )

        templates: list[MemoryBlockTemplate] = []
        for domain in domains:
            for template in domain.block_templates:
                if not self._is_listable(template, include_hidden=include_hidden):
                    continue
                if (
                    normalized_layer is not None
                    and _normalize_key(template.layer) != normalized_layer
                ):
                    continue
                templates.append(template)
        return templates

    def get_block_template(self, block_template_id: str) -> MemoryBlockTemplate | None:
        resolved_id = self.resolve_block_template_alias(block_template_id)
        return self._block_templates_by_id.get(_normalize_key(resolved_id))

    def require_block_template(self, block_template_id: str) -> MemoryBlockTemplate:
        template = self.get_block_template(block_template_id)
        if template is None:
            raise MemoryContractRegistryError(
                "memory_block_template_not_registered",
                _normalize_key(block_template_id),
            )
        return template

    def resolve_block_template_alias(self, block_template_id: str) -> str:
        return self._resolve_registry_alias(
            value=block_template_id,
            items_by_id=self._block_templates_by_id,
            aliases_by_id=self._block_template_aliases_by_id,
            id_getter=lambda item: item.block_template_id,
            migrated_to_getter=lambda item: item.migrated_to,
            cycle_code="memory_block_template_migration_cycle",
            target_missing_code="memory_block_template_migration_target_missing",
        )

    def list_workers(
        self,
        *,
        mode: str | None = None,
        include_hidden: bool = False,
    ) -> list[MemoryWorkerDescriptor]:
        normalized_mode = _normalize_key(mode) if mode is not None else None
        workers: list[MemoryWorkerDescriptor] = []
        for worker in self._registry.workers:
            if not self._is_listable(worker, include_hidden=include_hidden):
                continue
            if normalized_mode is not None and not self._is_worker_active_for_mode(
                worker,
                normalized_mode,
            ):
                continue
            workers.append(worker)
        return workers

    def get_worker(self, worker_id: str) -> MemoryWorkerDescriptor | None:
        resolved_id = self.resolve_worker_alias(worker_id)
        return self._workers_by_id.get(_normalize_key(resolved_id))

    def require_worker(self, worker_id: str) -> MemoryWorkerDescriptor:
        worker = self.get_worker(worker_id)
        if worker is None:
            raise MemoryContractRegistryError(
                "memory_worker_not_registered",
                _normalize_key(worker_id),
            )
        return worker

    def resolve_worker_alias(self, worker_id: str) -> str:
        return self._resolve_registry_alias(
            value=worker_id,
            items_by_id=self._workers_by_id,
            aliases_by_id=self._worker_aliases_by_id,
            id_getter=lambda item: item.worker_id,
            migrated_to_getter=lambda item: item.migrated_to,
            cycle_code="memory_worker_migration_cycle",
            target_missing_code="memory_worker_migration_target_missing",
        )

    @staticmethod
    def _is_listable(
        item: Any,
        *,
        include_hidden: bool,
    ) -> bool:
        if item.lifecycle == MemoryLifecycleState.ACTIVE:
            return True
        return include_hidden and item.lifecycle == MemoryLifecycleState.HIDDEN

    @staticmethod
    def _is_active_for_mode(domain: MemoryDomainContract, mode: str) -> bool:
        defaults = domain.mode_defaults.get(mode)
        return bool(defaults and defaults.active)

    @staticmethod
    def _is_worker_active_for_mode(
        worker: MemoryWorkerDescriptor,
        mode: str,
    ) -> bool:
        defaults = worker.mode_defaults.get(mode)
        return bool(defaults and defaults.active)

    @staticmethod
    def _resolve_registry_alias(
        *,
        value: str,
        items_by_id: dict[str, Any],
        aliases_by_id: dict[str, str],
        id_getter,
        migrated_to_getter,
        cycle_code: str,
        target_missing_code: str,
    ) -> str:
        current_id = aliases_by_id.get(
            _normalize_key(value),
            _normalize_key(value),
        )
        seen: set[str] = set()
        while True:
            current_key = _normalize_key(current_id)
            if current_key in seen:
                raise MemoryContractRegistryError(cycle_code, current_key)
            seen.add(current_key)

            item = items_by_id.get(current_key)
            if item is None:
                return current_key
            if getattr(item, "lifecycle") != MemoryLifecycleState.MIGRATED:
                return str(id_getter(item))
            migrated_to = migrated_to_getter(item)
            if migrated_to is None:
                raise MemoryContractRegistryError(
                    target_missing_code,
                    str(id_getter(item)),
                )
            migrated_to_key = _normalize_key(str(migrated_to))
            if (
                migrated_to_key not in items_by_id
                and migrated_to_key not in aliases_by_id
            ):
                raise MemoryContractRegistryError(
                    target_missing_code,
                    str(id_getter(item)),
                )
            current_id = aliases_by_id.get(migrated_to_key, migrated_to_key)


def build_bootstrap_memory_contract_registry() -> MemoryContractRegistry:
    """Build the first declarative registry without making enum values authoritative."""

    return MemoryContractRegistry(
        version=BOOTSTRAP_MEMORY_CONTRACT_REGISTRY_VERSION,
        domains=[
            _build_bootstrap_domain(domain_id)
            for domain_id in BOOTSTRAP_MEMORY_DOMAIN_IDS
        ],
        workers=[
            _build_bootstrap_worker(worker_id)
            for worker_id in BOOTSTRAP_MEMORY_WORKER_IDS
        ],
    )


def _build_bootstrap_domain(domain_id: str) -> MemoryDomainContract:
    permission_defaults = MemoryPermissionDefaults(
        read=True,
        propose=True,
        refresh_projection=True,
        governed_write=False,
        auto_apply=False,
        metadata={"governance": "proposal_or_governed_user_edit"},
    )
    return MemoryDomainContract(
        domain_id=domain_id,
        label=_DOMAIN_LABELS[domain_id],
        description=_DOMAIN_DESCRIPTIONS[domain_id],
        aliases=list(_DOMAIN_ALIASES.get(domain_id, ())),
        allowed_layers=list(DEFAULT_ALLOWED_LAYERS),
        mode_defaults=_build_mode_defaults(domain_id),
        permission_defaults=permission_defaults,
        block_templates=_build_default_block_templates(
            domain_id=domain_id,
            label=_DOMAIN_LABELS[domain_id],
            permission_defaults=permission_defaults,
        ),
        metadata={"bootstrap": True},
    )


def _build_mode_defaults(domain_id: str) -> dict[str, MemoryModeDefault]:
    return {
        "longform": MemoryModeDefault(
            active=domain_id in LONGFORM_ACTIVE_DOMAIN_IDS,
            ui_visible=domain_id in LONGFORM_ACTIVE_DOMAIN_IDS,
        ),
        "roleplay": MemoryModeDefault(
            active=domain_id in ROLEPLAY_ACTIVE_DOMAIN_IDS,
            ui_visible=domain_id in ROLEPLAY_ACTIVE_DOMAIN_IDS,
        ),
        "trpg": MemoryModeDefault(
            active=domain_id in TRPG_ACTIVE_DOMAIN_IDS,
            ui_visible=domain_id in TRPG_ACTIVE_DOMAIN_IDS,
        ),
    }


def _build_bootstrap_worker(worker_id: str) -> MemoryWorkerDescriptor:
    metadata: dict[str, object] = {"bootstrap": True}
    if worker_id == "graph_extraction":
        metadata["activation_policy"] = {
            "retrieval_policy_field": "graph_extraction_enabled"
        }
    return MemoryWorkerDescriptor(
        worker_id=worker_id,
        label=_WORKER_LABELS[worker_id],
        description=_WORKER_DESCRIPTIONS[worker_id],
        mode_defaults={
            mode: MemoryWorkerModeDefault(
                active=True,
                permission_defaults=dict(_WORKER_PERMISSION_DEFAULTS[worker_id]),
                metadata={"role": role},
            )
            for mode, role in _WORKER_MODE_ROLES[worker_id].items()
        },
        permission_defaults=dict(_WORKER_PERMISSION_DEFAULTS[worker_id]),
        metadata=metadata,
    )


def _build_default_block_templates(
    *,
    domain_id: str,
    label: str,
    permission_defaults: MemoryPermissionDefaults,
) -> list[MemoryBlockTemplate]:
    projection_permissions = permission_defaults.model_copy(
        update={"governed_write": False, "auto_apply": False}
    )
    retrieval_permissions = permission_defaults.model_copy(
        update={
            "propose": False,
            "refresh_projection": False,
            "governed_write": False,
            "auto_apply": False,
            "metadata": {"governance": "retrieval_core_read_only"},
        }
    )
    runtime_permissions = permission_defaults.model_copy(
        update={"governed_write": False, "auto_apply": False}
    )
    return [
        MemoryBlockTemplate(
            block_template_id=f"{domain_id}.authoritative",
            domain_id=domain_id,
            layer=CORE_STATE_AUTHORITATIVE_LAYER,
            label=f"{label} Authoritative State",
            description="Current story truth governed by proposal/apply or user edit.",
            domain_path_pattern=f"{domain_id}.current",
            permission_defaults=permission_defaults,
            allowed_operations=[
                "read",
                "proposal.submit",
                "proposal.apply",
                "user_edit.apply",
            ],
            metadata={"source_of_truth": True},
        ),
        MemoryBlockTemplate(
            block_template_id=f"{domain_id}.projection",
            domain_id=domain_id,
            layer=CORE_STATE_PROJECTION_LAYER,
            label=f"{label} Projection",
            description="Derived current view refreshed from truth and evidence.",
            domain_path_pattern=f"{domain_id}.projection.current",
            permission_defaults=projection_permissions,
            allowed_operations=["read", "projection.refresh"],
            metadata={"source_of_truth": False, "derived": True},
        ),
        MemoryBlockTemplate(
            block_template_id=f"{domain_id}.recall",
            domain_id=domain_id,
            layer=RECALL_LAYER,
            label=f"{label} Recall",
            description="Historical story memory backed by retrieval-core material.",
            domain_path_pattern=f"{domain_id}.recall.*",
            permission_defaults=retrieval_permissions,
            allowed_operations=["read", "retrieval.search_recall"],
            metadata={"source_of_truth": False, "physical_store": "retrieval_core"},
        ),
        MemoryBlockTemplate(
            block_template_id=f"{domain_id}.archival",
            domain_id=domain_id,
            layer=ARCHIVAL_LAYER,
            label=f"{label} Archival Knowledge",
            description="Imported or authored source knowledge backed by retrieval-core material.",
            domain_path_pattern=f"{domain_id}.archival.*",
            permission_defaults=retrieval_permissions,
            allowed_operations=["read", "retrieval.search_archival"],
            metadata={"source_of_truth": False, "physical_store": "retrieval_core"},
        ),
        MemoryBlockTemplate(
            block_template_id=f"{domain_id}.runtime_workspace",
            domain_id=domain_id,
            layer=RUNTIME_WORKSPACE_LAYER,
            label=f"{label} Runtime Workspace",
            description="Current-turn scratch, candidate, evidence, and usage material.",
            domain_path_pattern=f"{domain_id}.runtime.*",
            permission_defaults=runtime_permissions,
            allowed_operations=[
                "read",
                "runtime_material.record",
                "runtime_material.invalidate",
            ],
            metadata={"temporary": True, "source_of_truth": False},
        ),
    ]


def _normalize_key(value: str) -> str:
    return value.strip().lower()
