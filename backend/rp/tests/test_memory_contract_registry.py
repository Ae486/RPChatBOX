"""Tests for the RP Memory Contract Registry slice."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rp.models.dsl import Domain
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryContractRegistry,
    MemoryDirtyTarget,
    MemoryDomainContract,
    MemoryLifecycleState,
    MemoryModeDefault,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)
from rp.services.memory_contract_registry import (
    ARCHIVAL_LAYER,
    BOOTSTRAP_MEMORY_DOMAIN_IDS,
    CORE_STATE_AUTHORITATIVE_LAYER,
    CORE_STATE_PROJECTION_LAYER,
    MemoryContractRegistryError,
    RECALL_LAYER,
    MemoryContractRegistryService,
    RUNTIME_WORKSPACE_LAYER,
    build_bootstrap_memory_contract_registry,
)


def test_default_registry_bootstraps_all_domains_and_dsl_compatibility():
    service = MemoryContractRegistryService()

    assert service.registry_version() == "2026-05-04.memory-contract-registry.v1"
    assert [domain.domain_id for domain in service.list_domains()] == list(
        BOOTSTRAP_MEMORY_DOMAIN_IDS
    )
    assert service.require_domain("knowledge_boundary").lifecycle == (
        MemoryLifecycleState.ACTIVE
    )
    assert service.require_domain("rule_state").lifecycle == MemoryLifecycleState.ACTIVE
    assert Domain.KNOWLEDGE_BOUNDARY.value == "knowledge_boundary"
    assert Domain.RULE_STATE.value == "rule_state"


def test_default_registry_block_templates_cover_declared_layers():
    service = MemoryContractRegistryService()

    for domain in service.list_domains():
        template_layers = {
            template.layer
            for template in service.list_block_templates(domain_id=domain.domain_id)
        }

        assert set(domain.allowed_layers) == template_layers

    assert {
        template.layer
        for template in service.list_block_templates(domain_id="knowledge_boundary")
    } == {
        CORE_STATE_AUTHORITATIVE_LAYER,
        CORE_STATE_PROJECTION_LAYER,
        RECALL_LAYER,
        ARCHIVAL_LAYER,
        RUNTIME_WORKSPACE_LAYER,
    }
    recall_template = service.list_block_templates(
        domain_id="knowledge_boundary",
        layer=RECALL_LAYER,
    )[0]
    archival_template = service.list_block_templates(
        domain_id="knowledge_boundary",
        layer=ARCHIVAL_LAYER,
    )[0]

    assert recall_template.permission_defaults.propose is False
    assert recall_template.metadata == {
        "source_of_truth": False,
        "physical_store": "retrieval_core",
    }
    assert archival_template.permission_defaults.propose is False
    assert archival_template.metadata == {
        "source_of_truth": False,
        "physical_store": "retrieval_core",
    }


def test_registry_filters_lifecycle_for_lists_but_keeps_direct_resolution():
    registry = _registry_with_domains(
        MemoryDomainContract(
            domain_id="debug_only",
            label="Debug Only",
            lifecycle=MemoryLifecycleState.HIDDEN,
            allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER],
            mode_defaults={
                "longform": MemoryModeDefault(active=True, ui_visible=False)
            },
        ),
        MemoryDomainContract(
            domain_id="legacy_relation",
            label="Legacy Relation",
            lifecycle=MemoryLifecycleState.RETIRED,
            allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER],
        ),
        MemoryDomainContract(
            domain_id="old_threads",
            label="Old Threads",
            lifecycle=MemoryLifecycleState.MIGRATED,
            migrated_to="plot_thread",
            allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER],
        ),
    )
    service = MemoryContractRegistryService(registry=registry)

    listed = {domain.domain_id for domain in service.list_domains()}
    listed_with_hidden = {
        domain.domain_id for domain in service.list_domains(include_hidden=True)
    }

    assert "debug_only" not in listed
    assert "legacy_relation" not in listed
    assert "old_threads" not in listed
    assert "debug_only" in listed_with_hidden
    assert "legacy_relation" not in listed_with_hidden
    assert "old_threads" not in listed_with_hidden
    assert service.require_domain("legacy_relation").domain_id == "legacy_relation"


def test_alias_and_migration_resolution_are_registry_driven():
    registry = _registry_with_domains(
        MemoryDomainContract(
            domain_id="memory_magic",
            label="Memory Magic",
            aliases=["magic", "spell_memory"],
            allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER],
        ),
        MemoryDomainContract(
            domain_id="old_magic",
            label="Old Magic",
            lifecycle=MemoryLifecycleState.MIGRATED,
            migrated_to="memory_magic",
            allowed_layers=[CORE_STATE_AUTHORITATIVE_LAYER],
        ),
    )
    service = MemoryContractRegistryService(registry=registry)

    assert service.resolve_alias("knowledge") == "knowledge_boundary"
    assert service.resolve_alias("magic") == "memory_magic"
    assert service.require_domain("spell_memory").domain_id == "memory_magic"
    assert service.resolve_alias("old_magic") == "memory_magic"
    assert service.require_domain("old_magic").domain_id == "memory_magic"
    with pytest.raises(MemoryContractRegistryError) as exc:
        service.require_domain("unknown_domain")
    assert exc.value.code == "memory_domain_not_registered"


def test_mode_activation_defaults_are_resolved_from_registry_data():
    service = MemoryContractRegistryService()

    longform = {domain.domain_id for domain in service.list_domains(mode="longform")}
    roleplay = {domain.domain_id for domain in service.list_domains(mode="roleplay")}
    trpg = {domain.domain_id for domain in service.list_domains(mode="trpg")}

    assert {
        "chapter",
        "narrative_progress",
        "timeline",
        "plot_thread",
        "foreshadow",
        "character",
        "scene",
        "knowledge_boundary",
    }.issubset(longform)
    assert "rule_state" not in longform
    assert {"scene", "character", "knowledge_boundary", "relation", "goal"}.issubset(
        roleplay
    )
    assert "chapter" not in roleplay
    assert {
        "rule_state",
        "inventory",
        "world_rule",
        "scene",
        "character",
        "goal",
        "knowledge_boundary",
    }.issubset(trpg)
    assert "plot_thread" not in trpg


def test_registry_accepts_test_only_domain_extension_without_service_edits():
    service = MemoryContractRegistryService(
        registry=_registry_with_domains(
            MemoryDomainContract(
                domain_id="magic_system",
                label="Magic System",
                allowed_layers=[
                    CORE_STATE_AUTHORITATIVE_LAYER,
                    RUNTIME_WORKSPACE_LAYER,
                ],
                mode_defaults={
                    "longform": MemoryModeDefault(active=True, ui_visible=True),
                    "roleplay": MemoryModeDefault(active=True, ui_visible=True),
                },
                block_templates=[
                    {
                        "block_template_id": "magic_system.authoritative",
                        "domain_id": "magic_system",
                        "layer": CORE_STATE_AUTHORITATIVE_LAYER,
                        "label": "Magic System Authoritative State",
                        "domain_path_pattern": "magic_system.current",
                    },
                    {
                        "block_template_id": "magic_system.runtime_workspace",
                        "domain_id": "magic_system",
                        "layer": RUNTIME_WORKSPACE_LAYER,
                        "label": "Magic System Runtime Workspace",
                        "domain_path_pattern": "magic_system.runtime.*",
                    },
                ],
            )
        )
    )

    assert service.require_domain("magic_system").domain_id == "magic_system"
    assert "magic_system" in {
        domain.domain_id for domain in service.list_domains(mode="longform")
    }
    assert [
        template.block_template_id
        for template in service.list_block_templates(
            domain_id="magic_system",
            layer=RUNTIME_WORKSPACE_LAYER,
        )
    ] == ["magic_system.runtime_workspace"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "story_id",
        "session_id",
        "branch_head_id",
        "turn_id",
        "runtime_profile_snapshot_id",
    ],
)
def test_runtime_identity_rejects_missing_fields(missing_field: str):
    payload = _identity_payload()
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        MemoryRuntimeIdentity(**payload)


@pytest.mark.parametrize(
    "blank_field",
    [
        "story_id",
        "session_id",
        "branch_head_id",
        "turn_id",
        "runtime_profile_snapshot_id",
    ],
)
def test_runtime_identity_rejects_blank_fields(blank_field: str):
    payload = _identity_payload()
    payload[blank_field] = "  "

    with pytest.raises(ValidationError, match=blank_field):
        MemoryRuntimeIdentity(**payload)


def test_memory_change_event_carries_identity_source_dirty_and_metadata():
    identity = MemoryRuntimeIdentity(**_identity_payload())

    event = MemoryChangeEvent(
        event_id="event-1",
        identity=identity,
        actor="worker.character",
        event_kind="projection_refreshed",
        layer="core_state.projection",
        domain="knowledge_boundary",
        block_id="knowledge_boundary.projection",
        entry_id="secret-1",
        operation_kind="projection.refresh",
        source_refs=[
            MemorySourceRef(
                source_type="retrieval_card",
                source_id="R1",
                layer="runtime_workspace",
                domain="knowledge_boundary",
                block_id="knowledge_boundary.runtime",
                metadata={"score": 0.91},
            )
        ],
        dirty_targets=[
            MemoryDirtyTarget(
                target_kind="packet_window",
                target_id="writer.packet.current",
                domain="knowledge_boundary",
                reason="projection_changed",
                metadata={"consumer": "WritingPacketBuilder"},
            )
        ],
        visibility_effect="active",
        metadata={"trace_role": "invalidation_skeleton"},
    )

    dumped = event.model_dump(mode="json")

    assert dumped["identity"] == _identity_payload()
    assert dumped["domain"] == "knowledge_boundary"
    assert dumped["source_refs"] == [
        {
            "source_type": "retrieval_card",
            "source_id": "R1",
            "layer": "runtime_workspace",
            "domain": "knowledge_boundary",
            "block_id": "knowledge_boundary.runtime",
            "entry_id": None,
            "revision": None,
            "metadata": {"score": 0.91},
        }
    ]
    assert dumped["dirty_targets"] == [
        {
            "target_kind": "packet_window",
            "target_id": "writer.packet.current",
            "layer": None,
            "domain": "knowledge_boundary",
            "block_id": None,
            "reason": "projection_changed",
            "metadata": {"consumer": "WritingPacketBuilder"},
        }
    ]
    assert dumped["visibility_effect"] == "active"
    assert dumped["metadata"] == {"trace_role": "invalidation_skeleton"}


def _registry_with_domains(*domains: MemoryDomainContract) -> MemoryContractRegistry:
    bootstrap = build_bootstrap_memory_contract_registry()
    return bootstrap.model_copy(
        update={"domains": [*bootstrap.domains, *domains]},
    )


def _identity_payload() -> dict[str, str]:
    return {
        "story_id": "story-1",
        "session_id": "session-1",
        "branch_head_id": "branch-head-1",
        "turn_id": "turn-1",
        "runtime_profile_snapshot_id": "profile-snapshot-1",
    }
