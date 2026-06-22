"""S3 runtime longform memory contract registry service."""

from __future__ import annotations

from rp.errors import RPError
from rp.models.memory.runtime_memory_contract import (
    RUNTIME_MEMORY_FACT_FIELD_ID,
    RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS,
    RuntimeMemoryBlockContract,
    RuntimeMemoryContractRegistry,
    RuntimeMemoryDomainContract,
    RuntimeMemoryFieldContract,
)


RUNTIME_LONGFORM_MEMORY_CONTRACT_REGISTRY_VERSION = (
    "2026-06-23.s3a-longform-runtime-memory.v1"
)
RUNTIME_LONGFORM_MODE = "longform"
RUNTIME_LONGFORM_DOMAIN_IDS: tuple[str, ...] = (
    "current_scene",
    "character_state",
    "knowledge_state",
    "plot_threads",
    "world_constraints",
)
RUNTIME_LONGFORM_BLOCK_IDS_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "current_scene": (
        "scene.frame",
        "scene.pressure",
        "scene.bridge",
    ),
    "character_state": (
        "character.current_state",
        "character.intent",
        "character.relationships",
    ),
    "knowledge_state": (
        "knowledge.by_subject",
        "knowledge.secrets_reveals",
    ),
    "plot_threads": (
        "plot.active_threads",
        "plot.foreshadow_payoff",
        "plot.causal_spine",
    ),
    "world_constraints": (
        "world.rules",
        "world.resources",
    ),
}

_DOMAIN_LABELS: dict[str, str] = {
    "current_scene": "Current Scene",
    "character_state": "Character State",
    "knowledge_state": "Knowledge State",
    "plot_threads": "Plot Threads",
    "world_constraints": "World Constraints",
}
_DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "current_scene": "Current place, pressure, bridge, and scene continuation state.",
    "character_state": "Character condition, intent, and relationship facts.",
    "knowledge_state": "Subject knowledge, secrets, clues, and reveal state.",
    "plot_threads": "Active threads, foreshadowing, payoff, and causal spine facts.",
    "world_constraints": "Rules, resources, and continuity constraints that bound prose.",
}
_BLOCK_LABELS: dict[str, str] = {
    "scene.frame": "Scene Frame",
    "scene.pressure": "Scene Pressure",
    "scene.bridge": "Scene Bridge",
    "character.current_state": "Character Current State",
    "character.intent": "Character Intent",
    "character.relationships": "Character Relationships",
    "knowledge.by_subject": "Knowledge By Subject",
    "knowledge.secrets_reveals": "Secrets And Reveals",
    "plot.active_threads": "Active Plot Threads",
    "plot.foreshadow_payoff": "Foreshadow And Payoff",
    "plot.causal_spine": "Causal Spine",
    "world.rules": "World Rules",
    "world.resources": "World Resources",
}
_BLOCK_DESCRIPTIONS: dict[str, str] = {
    "scene.frame": "Current place, time, POV, and present subjects.",
    "scene.pressure": "Current scene goal, obstacle, conflict, and stakes.",
    "scene.bridge": "Accepted outcome and immediate continuation hook.",
    "character.current_state": "Physical, emotional, situational state, and limitations.",
    "character.intent": "Current goals, motivations, hidden intent, and active plans.",
    "character.relationships": "Trust, conflict, obligation, debt, and power shifts.",
    "knowledge.by_subject": "What subjects know, believe, misunderstand, or lack.",
    "knowledge.secrets_reveals": "Secrets, clues, reveal state, and withheld information.",
    "plot.active_threads": "Active problems, unresolved questions, and current pressure.",
    "plot.foreshadow_payoff": "Planted clues, callback obligations, and payoff state.",
    "plot.causal_spine": "Current-relevant causal event spine.",
    "world.rules": "Setting rules, institutions, genre, magic, technology, and social constraints.",
    "world.resources": "Current-relevant objects, locations, resources, and possession constraints.",
}
_BLOCK_GROUP_BY: dict[str, str | None] = {
    "scene.frame": None,
    "scene.pressure": None,
    "scene.bridge": None,
    "character.current_state": "character",
    "character.intent": "character",
    "character.relationships": "relationship",
    "knowledge.by_subject": "subject",
    "knowledge.secrets_reveals": "secret_or_reveal",
    "plot.active_threads": "thread",
    "plot.foreshadow_payoff": "thread",
    "plot.causal_spine": None,
    "world.rules": "rule_subject",
    "world.resources": "resource",
}


class RuntimeMemoryContractRegistryError(RPError, ValueError):
    """Stable runtime memory registry error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RuntimeLongformMemoryContractRegistryService:
    """Read-only S3 longform registry that coexists with the legacy bootstrap registry."""

    def __init__(self, registry: RuntimeMemoryContractRegistry | None = None) -> None:
        self._registry = registry or build_runtime_longform_memory_contract_registry()
        self._domains_by_id = {
            _normalize_key(domain.domain_id): domain for domain in self._registry.domains
        }
        self._blocks_by_domain_and_id: dict[tuple[str, str], RuntimeMemoryBlockContract] = {}
        for domain in self._registry.domains:
            for block in domain.blocks:
                self._blocks_by_domain_and_id[
                    (_normalize_key(domain.domain_id), _normalize_key(block.block_id))
                ] = block

    def registry_version(self) -> str:
        return self._registry.version

    def list_domains(self) -> list[RuntimeMemoryDomainContract]:
        return list(self._registry.domains)

    def get_domain(self, domain_id: str) -> RuntimeMemoryDomainContract | None:
        return self._domains_by_id.get(_normalize_key(domain_id))

    def require_domain(self, domain_id: str) -> RuntimeMemoryDomainContract:
        domain = self.get_domain(domain_id)
        if domain is None:
            raise RuntimeMemoryContractRegistryError(
                "runtime_memory_domain_not_registered",
                _normalize_key(domain_id),
            )
        return domain

    def list_blocks(
        self,
        *,
        domain_id: str | None = None,
    ) -> list[RuntimeMemoryBlockContract]:
        if domain_id is not None:
            return list(self.require_domain(domain_id).blocks)
        blocks: list[RuntimeMemoryBlockContract] = []
        for domain in self._registry.domains:
            blocks.extend(domain.blocks)
        return blocks

    def get_block(
        self,
        *,
        domain_id: str,
        block_id: str,
    ) -> RuntimeMemoryBlockContract | None:
        return self._blocks_by_domain_and_id.get(
            (_normalize_key(domain_id), _normalize_key(block_id))
        )

    def require_block(
        self,
        *,
        domain_id: str,
        block_id: str,
    ) -> RuntimeMemoryBlockContract:
        self.require_domain(domain_id)
        block = self.get_block(domain_id=domain_id, block_id=block_id)
        if block is None:
            raise RuntimeMemoryContractRegistryError(
                "runtime_memory_block_not_registered",
                f"{_normalize_key(domain_id)}:{_normalize_key(block_id)}",
            )
        return block

    def supports_operation(
        self,
        *,
        domain_id: str,
        block_id: str,
        operation_kind: str,
        field_id: str = RUNTIME_MEMORY_FACT_FIELD_ID,
    ) -> bool:
        block = self.require_block(domain_id=domain_id, block_id=block_id)
        for field in block.fields:
            if field.field_id == field_id:
                return operation_kind in field.allowed_operations
        raise RuntimeMemoryContractRegistryError(
            "runtime_memory_field_not_registered",
            f"{_normalize_key(domain_id)}:{_normalize_key(block_id)}:{field_id}",
        )

    def require_operation_supported(
        self,
        *,
        domain_id: str,
        block_id: str,
        operation_kind: str,
        field_id: str = RUNTIME_MEMORY_FACT_FIELD_ID,
    ) -> None:
        if not self.supports_operation(
            domain_id=domain_id,
            block_id=block_id,
            operation_kind=operation_kind,
            field_id=field_id,
        ):
            raise RuntimeMemoryContractRegistryError(
                "runtime_memory_operation_not_supported",
                (
                    f"{_normalize_key(domain_id)}:{_normalize_key(block_id)}:"
                    f"{field_id}:{operation_kind}"
                ),
            )


def build_runtime_longform_memory_contract_registry() -> RuntimeMemoryContractRegistry:
    """Build the fixed S3 longform runtime registry without altering legacy bootstrap."""

    return RuntimeMemoryContractRegistry(
        version=RUNTIME_LONGFORM_MEMORY_CONTRACT_REGISTRY_VERSION,
        mode=RUNTIME_LONGFORM_MODE,
        domains=tuple(_build_domain(domain_id) for domain_id in RUNTIME_LONGFORM_DOMAIN_IDS),
    )


def _build_domain(domain_id: str) -> RuntimeMemoryDomainContract:
    return RuntimeMemoryDomainContract(
        domain_id=domain_id,
        label=_DOMAIN_LABELS[domain_id],
        description=_DOMAIN_DESCRIPTIONS[domain_id],
        blocks=tuple(
            _build_block(domain_id=domain_id, block_id=block_id)
            for block_id in RUNTIME_LONGFORM_BLOCK_IDS_BY_DOMAIN[domain_id]
        ),
        metadata={"s3a_runtime_longform": "true"},
    )


def _build_block(*, domain_id: str, block_id: str) -> RuntimeMemoryBlockContract:
    return RuntimeMemoryBlockContract(
        domain_id=domain_id,
        block_id=block_id,
        label=_BLOCK_LABELS[block_id],
        description=_BLOCK_DESCRIPTIONS[block_id],
        fields=(
            RuntimeMemoryFieldContract(
                field_id=RUNTIME_MEMORY_FACT_FIELD_ID,
                group_by=_BLOCK_GROUP_BY[block_id],
                allowed_operations=RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS,
            ),
        ),
        metadata={"source_of_truth": "core_fact_candidates"},
    )


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower()
