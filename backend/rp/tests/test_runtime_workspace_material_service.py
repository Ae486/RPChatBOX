"""Tests for the Runtime Workspace typed turn-material store slice."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rp.models.memory_contract_registry import (
    MemoryBlockTemplate,
    MemoryContractRegistry,
    MemoryDomainContract,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)
from rp.models.runtime_workspace_material import (
    RUNTIME_WORKSPACE_MATERIAL_LAYER,
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.services.memory_contract_registry import (
    CORE_STATE_AUTHORITATIVE_LAYER,
    MemoryContractRegistryService,
    RUNTIME_WORKSPACE_LAYER,
    build_bootstrap_memory_contract_registry,
)
from rp.services.runtime_workspace_material_service import (
    RUNTIME_WORKSPACE_TRACE_ROLE,
    RuntimeWorkspaceMaterialService,
    RuntimeWorkspaceMaterialServiceError,
)


def test_material_kind_and_lifecycle_enums_match_spec():
    assert {kind.value for kind in RuntimeWorkspaceMaterialKind} == {
        "writer_input_ref",
        "writer_output_ref",
        "retrieval_card",
        "retrieval_expanded_chunk",
        "retrieval_miss",
        "retrieval_usage_record",
        "rule_card",
        "rule_state_card",
        "review_overlay",
        "worker_candidate",
        "worker_evidence_bundle",
        "post_write_trace",
        "packet_ref",
        "token_usage_metadata",
    }
    assert {state.value for state in RuntimeWorkspaceMaterialLifecycle} == {
        "active",
        "used",
        "unused",
        "expanded",
        "promoted",
        "discarded",
        "expired",
        "invalidated",
    }
    assert RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value == "writer_visible"


@pytest.mark.parametrize(
    "blank_field",
    ["material_id", "domain", "visibility", "created_by"],
)
def test_material_rejects_blank_required_text(blank_field: str):
    payload = _material_payload()
    payload[blank_field] = "  "

    with pytest.raises(ValidationError, match=blank_field):
        RuntimeWorkspaceMaterial(**payload)


def test_material_rejects_blank_short_id_but_defaults_payload_and_source_refs():
    with pytest.raises(ValidationError, match="short_id"):
        RuntimeWorkspaceMaterial(**_material_payload(short_id=" "))

    material = RuntimeWorkspaceMaterial(
        material_id="mat-defaults",
        material_kind=RuntimeWorkspaceMaterialKind.TOKEN_USAGE_METADATA,
        identity=_identity(),
        domain="narrative_progress",
        visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
        created_by="runtime.token_meter",
    )

    assert material.payload == {}
    assert material.source_refs == []
    assert material.lifecycle == RuntimeWorkspaceMaterialLifecycle.ACTIVE
    assert material.metadata["memory_layer"] == RUNTIME_WORKSPACE_MATERIAL_LAYER
    assert material.metadata["temporary"] is True
    assert material.metadata["source_of_truth"] is False
    assert material.metadata["core_state_truth"] is False
    assert material.metadata["recall_truth"] is False
    assert material.metadata["archival_truth"] is False


def test_record_list_get_and_require_material_by_full_identity():
    service = RuntimeWorkspaceMaterialService()
    identity = _identity()
    source_ref = MemorySourceRef(
        source_type="recall_hit",
        source_id="chunk-1",
        layer="recall",
        domain="knowledge_boundary",
        metadata={"rank": 1},
    )
    material = _material(
        material_id="mat-retrieval-r1",
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        identity=identity,
        domain="knowledge",
        short_id="R1",
        source_refs=[source_ref],
        payload={"excerpt": "A remembered constraint."},
    )

    receipt = service.record_material(material)

    assert receipt.material.domain == "knowledge_boundary"
    assert receipt.material.lifecycle == RuntimeWorkspaceMaterialLifecycle.ACTIVE
    assert service.get_material(identity=identity, material_id="mat-retrieval-r1") == (
        receipt.material
    )
    assert (
        service.require_material(
            identity=identity,
            material_id="mat-retrieval-r1",
        )
        == receipt.material
    )
    assert service.list_materials(identity=identity) == [receipt.material]
    assert service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
    ) == [receipt.material]
    assert service.list_materials(identity=identity, domain="knowledge") == [
        receipt.material
    ]
    assert (
        service.list_materials(
            identity=identity,
            lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
        )
        == []
    )

    event = receipt.event
    assert event.identity == identity
    assert event.layer == RUNTIME_WORKSPACE_MATERIAL_LAYER
    assert event.domain == "knowledge_boundary"
    assert event.block_id == "knowledge_boundary.runtime_workspace"
    assert event.entry_id == "mat-retrieval-r1"
    assert event.operation_kind == "runtime_material.record"
    assert event.visibility_effect == RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE
    assert event.source_refs[0] == source_ref
    assert event.source_refs[-1].source_type == "retrieval_card"
    assert event.source_refs[-1].source_id == "R1"
    assert event.source_refs[-1].entry_id == "mat-retrieval-r1"
    assert event.dirty_targets[0].target_kind == "runtime_workspace_material"
    assert event.dirty_targets[0].target_id == "mat-retrieval-r1"
    assert event.metadata["trace_role"] == RUNTIME_WORKSPACE_TRACE_ROLE
    assert event.metadata["temporary"] is True
    assert event.metadata["source_of_truth"] is False


def test_materials_are_isolated_by_full_runtime_identity_not_session_only():
    service = RuntimeWorkspaceMaterialService()
    base_identity = _identity()
    branch_identity = _identity(branch_head_id="branch-head-2")
    turn_identity = _identity(turn_id="turn-2")
    profile_identity = _identity(runtime_profile_snapshot_id="profile-snapshot-2")

    receipt = service.record_material(
        _material(
            material_id="mat-scene-1",
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            identity=base_identity,
            domain="scene",
            short_id="OV1",
        )
    )

    assert service.list_materials(identity=base_identity) == [receipt.material]
    assert (
        service.get_material(identity=branch_identity, material_id="mat-scene-1")
        is None
    )
    assert (
        service.get_material(identity=turn_identity, material_id="mat-scene-1") is None
    )
    assert (
        service.get_material(identity=profile_identity, material_id="mat-scene-1")
        is None
    )

    for wrong_identity in [branch_identity, turn_identity, profile_identity]:
        with pytest.raises(RuntimeWorkspaceMaterialServiceError) as exc:
            service.require_material(
                identity=wrong_identity,
                material_id="mat-scene-1",
            )
        assert exc.value.code == "runtime_workspace_material_not_found"


def test_domain_registry_validation_and_test_only_extension():
    service = RuntimeWorkspaceMaterialService()

    with pytest.raises(RuntimeWorkspaceMaterialServiceError) as exc:
        service.record_material(_material(domain="unknown_domain"))
    assert exc.value.code == "runtime_workspace_domain_not_registered"

    extended_service = RuntimeWorkspaceMaterialService(
        registry_service=MemoryContractRegistryService(
            registry=_registry_with_domains(
                MemoryDomainContract(
                    domain_id="magic_system",
                    label="Magic System",
                    allowed_layers=[
                        CORE_STATE_AUTHORITATIVE_LAYER,
                        RUNTIME_WORKSPACE_LAYER,
                    ],
                    block_templates=[
                        MemoryBlockTemplate(
                            block_template_id="magic_system.runtime_workspace",
                            domain_id="magic_system",
                            layer=RUNTIME_WORKSPACE_LAYER,
                            label="Magic System Runtime Workspace",
                        )
                    ],
                )
            )
        )
    )

    receipt = extended_service.record_material(
        _material(
            material_id="mat-magic-rule",
            material_kind=RuntimeWorkspaceMaterialKind.RULE_CARD,
            domain="magic_system",
            short_id="RULE1",
        )
    )

    assert receipt.material.domain == "magic_system"


def test_short_id_uniqueness_is_identity_scoped():
    service = RuntimeWorkspaceMaterialService()
    identity = _identity()
    branch_identity = _identity(branch_head_id="branch-head-2")
    next_turn_identity = _identity(turn_id="turn-2")
    profile_identity = _identity(runtime_profile_snapshot_id="profile-snapshot-2")

    service.record_material(
        _material(
            material_id="mat-r1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            short_id="R1",
        )
    )

    with pytest.raises(RuntimeWorkspaceMaterialServiceError) as exc:
        service.record_material(
            _material(
                material_id="mat-r1-duplicate",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK,
                identity=identity,
                short_id="r1",
            )
        )
    assert exc.value.code == "runtime_workspace_short_id_conflict"

    branch_identity_receipt = service.record_material(
        _material(
            material_id="mat-r1-next-branch",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=branch_identity,
            short_id="R1",
        )
    )
    turn_identity_receipt = service.record_material(
        _material(
            material_id="mat-r1-next-turn",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=next_turn_identity,
            short_id="R1",
        )
    )
    profile_identity_receipt = service.record_material(
        _material(
            material_id="mat-r1-next-profile",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=profile_identity,
            short_id="R1",
        )
    )

    assert branch_identity_receipt.material.short_id == "R1"
    assert turn_identity_receipt.material.short_id == "R1"
    assert profile_identity_receipt.material.short_id == "R1"
    assert len(service.list_materials(identity=identity)) == 1
    assert len(service.list_materials(identity=branch_identity)) == 1
    assert len(service.list_materials(identity=next_turn_identity)) == 1
    assert len(service.list_materials(identity=profile_identity)) == 1


def test_lifecycle_update_returns_receipt_and_trace_event():
    service = RuntimeWorkspaceMaterialService()
    identity = _identity()
    service.record_material(
        _material(
            material_id="mat-used-r1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            identity=identity,
            short_id="USE1",
        )
    )

    receipt = service.update_lifecycle(
        identity=identity,
        material_id="mat-used-r1",
        lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
        reason="writer_output_referenced_material",
    )

    assert receipt.material.lifecycle == RuntimeWorkspaceMaterialLifecycle.USED
    assert (
        service.require_material(
            identity=identity,
            material_id="mat-used-r1",
        ).lifecycle
        == RuntimeWorkspaceMaterialLifecycle.USED
    )
    assert receipt.event.identity == identity
    assert receipt.event.layer == RUNTIME_WORKSPACE_MATERIAL_LAYER
    assert receipt.event.domain == "knowledge_boundary"
    assert receipt.event.operation_kind == "runtime_material.lifecycle.update"
    assert receipt.event.source_refs[-1].entry_id == "mat-used-r1"
    assert receipt.event.dirty_targets[0].reason == "writer_output_referenced_material"
    assert receipt.event.metadata["previous_lifecycle"] == "active"
    assert receipt.event.metadata["lifecycle"] == "used"
    assert receipt.event.metadata["temporary"] is True
    assert receipt.event.metadata["source_of_truth"] is False

    with pytest.raises(RuntimeWorkspaceMaterialServiceError) as exc:
        service.update_lifecycle(
            identity=identity,
            material_id="mat-missing",
            lifecycle=RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
            reason="test",
        )
    assert exc.value.code == "runtime_workspace_material_not_found"


def test_retrieval_card_and_worker_candidate_remain_runtime_material_only():
    service = RuntimeWorkspaceMaterialService()
    identity = _identity()

    retrieval_receipt = service.record_material(
        _material(
            material_id="mat-retrieval-card",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            short_id="R2",
            payload={"excerpt": "Candidate evidence."},
        )
    )
    worker_receipt = service.record_material(
        _material(
            material_id="mat-worker-candidate",
            material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
            identity=identity,
            domain="character",
            short_id="CAND1",
            payload={"candidate_patch": {"mood": "uneasy"}},
        )
    )

    for receipt in [retrieval_receipt, worker_receipt]:
        assert receipt.material.materialization_ref is None
        assert (
            receipt.material.metadata["memory_layer"]
            == RUNTIME_WORKSPACE_MATERIAL_LAYER
        )
        assert receipt.material.metadata["temporary"] is True
        assert receipt.material.metadata["source_of_truth"] is False
        assert receipt.material.metadata["authoritative_mutation"] is False
        assert receipt.material.metadata["core_state_truth"] is False
        assert receipt.material.metadata["recall_truth"] is False
        assert receipt.material.metadata["archival_truth"] is False
        assert receipt.material.metadata["materialized_to_recall"] is False
        assert receipt.material.metadata["materialized_to_archival"] is False
        assert receipt.event.layer == RUNTIME_WORKSPACE_MATERIAL_LAYER
        assert receipt.event.metadata["core_state_truth"] is False
        assert receipt.event.metadata["recall_truth"] is False
        assert receipt.event.metadata["archival_truth"] is False


def _registry_with_domains(*domains: MemoryDomainContract) -> MemoryContractRegistry:
    bootstrap = build_bootstrap_memory_contract_registry()
    return bootstrap.model_copy(update={"domains": [*bootstrap.domains, *domains]})


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    payload = {
        "story_id": "story-1",
        "session_id": "session-1",
        "branch_head_id": "branch-head-1",
        "turn_id": "turn-1",
        "runtime_profile_snapshot_id": "profile-snapshot-1",
        **overrides,
    }
    return MemoryRuntimeIdentity(**payload)


def _material_payload(**overrides):
    payload = {
        "material_id": "mat-1",
        "material_kind": RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        "identity": _identity(),
        "domain": "knowledge_boundary",
        "domain_path": "knowledge_boundary.runtime.turn",
        "source_refs": [],
        "short_id": "R1",
        "payload": {"excerpt": "Evidence."},
        "lifecycle": RuntimeWorkspaceMaterialLifecycle.ACTIVE,
        "visibility": RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
        "created_by": "writer.retrieval",
        "expiration_ref": None,
        "materialization_ref": None,
        "metadata": {},
        **overrides,
    }
    return payload


def _material(
    *,
    material_id: str = "mat-1",
    material_kind: RuntimeWorkspaceMaterialKind = (
        RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD
    ),
    identity: MemoryRuntimeIdentity | None = None,
    domain: str = "knowledge_boundary",
    domain_path: str | None = "knowledge_boundary.runtime.turn",
    source_refs: list[MemorySourceRef] | None = None,
    short_id: str | None = "R1",
    payload: dict | None = None,
    lifecycle: RuntimeWorkspaceMaterialLifecycle = (
        RuntimeWorkspaceMaterialLifecycle.ACTIVE
    ),
    visibility: str = RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
    created_by: str = "writer.retrieval",
    expiration_ref: str | None = None,
    materialization_ref: str | None = None,
    metadata: dict | None = None,
) -> RuntimeWorkspaceMaterial:
    return RuntimeWorkspaceMaterial(
        material_id=material_id,
        material_kind=material_kind,
        identity=identity or _identity(),
        domain=domain,
        domain_path=domain_path,
        source_refs=source_refs or [],
        short_id=short_id,
        payload=payload or {"excerpt": "Evidence."},
        lifecycle=lifecycle,
        visibility=visibility,
        created_by=created_by,
        expiration_ref=expiration_ref,
        materialization_ref=materialization_ref,
        metadata=metadata or {},
    )
