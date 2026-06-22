"""Tests for the S3 longform runtime memory contract registry."""

from __future__ import annotations

import pytest

from rp.models.memory.runtime_memory_contract import (
    RUNTIME_MEMORY_FACT_FIELD_ID,
    RUNTIME_MEMORY_FACT_FIELD_SHAPE,
    RUNTIME_MEMORY_FACT_ITEM_SHAPE,
    RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS,
)
from rp.services.memory.runtime_memory_contract_registry import (
    RUNTIME_LONGFORM_MEMORY_CONTRACT_REGISTRY_VERSION,
    RuntimeLongformMemoryContractRegistryService,
    RuntimeMemoryContractRegistryError,
)


def test_runtime_longform_registry_exports_exact_five_domains_in_stable_order():
    service = RuntimeLongformMemoryContractRegistryService()

    assert service.registry_version() == RUNTIME_LONGFORM_MEMORY_CONTRACT_REGISTRY_VERSION
    assert [domain.domain_id for domain in service.list_domains()] == [
        "current_scene",
        "character_state",
        "knowledge_state",
        "plot_threads",
        "world_constraints",
    ]


def test_runtime_longform_registry_exports_exact_required_blocks():
    service = RuntimeLongformMemoryContractRegistryService()

    actual = {
        domain.domain_id: [block.block_id for block in domain.blocks]
        for domain in service.list_domains()
    }

    assert actual == {
        "current_scene": [
            "scene.frame",
            "scene.pressure",
            "scene.bridge",
        ],
        "character_state": [
            "character.current_state",
            "character.intent",
            "character.relationships",
        ],
        "knowledge_state": [
            "knowledge.by_subject",
            "knowledge.secrets_reveals",
        ],
        "plot_threads": [
            "plot.active_threads",
            "plot.foreshadow_payoff",
            "plot.causal_spine",
        ],
        "world_constraints": [
            "world.rules",
            "world.resources",
        ],
    }


def test_runtime_longform_blocks_use_primary_facts_field_semantics():
    service = RuntimeLongformMemoryContractRegistryService()

    for block in service.list_blocks():
        facts_field = block.facts_field()

        assert block.primary_field_id == RUNTIME_MEMORY_FACT_FIELD_ID
        assert facts_field.field_id == RUNTIME_MEMORY_FACT_FIELD_ID
        assert facts_field.value_shape == RUNTIME_MEMORY_FACT_FIELD_SHAPE
        assert facts_field.item_shape == RUNTIME_MEMORY_FACT_ITEM_SHAPE
        assert facts_field.allowed_operations == RUNTIME_MEMORY_SUPPORTED_OPERATION_KINDS
        assert facts_field.group_by is None or facts_field.group_by


def test_runtime_longform_unknown_domain_and_block_fail_closed():
    service = RuntimeLongformMemoryContractRegistryService()

    with pytest.raises(RuntimeMemoryContractRegistryError) as domain_exc:
        service.require_domain("scene")
    assert domain_exc.value.code == "runtime_memory_domain_not_registered"

    with pytest.raises(RuntimeMemoryContractRegistryError) as block_exc:
        service.require_block(
            domain_id="current_scene",
            block_id="scene.unknown",
        )
    assert block_exc.value.code == "runtime_memory_block_not_registered"


def test_runtime_longform_registry_rejects_unsupported_operation_lookup():
    service = RuntimeLongformMemoryContractRegistryService()

    with pytest.raises(RuntimeMemoryContractRegistryError) as exc:
        service.require_operation_supported(
            domain_id="current_scene",
            block_id="scene.frame",
            operation_kind="create_block",
        )

    assert exc.value.code == "runtime_memory_operation_not_supported"
