"""Tests for the shared lightweight memory change event spine."""

from __future__ import annotations

import pytest

from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.services.memory_change_event_service import (
    MemoryChangeEventService,
    MemoryChangeEventServiceError,
)
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)


def test_record_event_normalizes_alias_and_lists_by_full_identity_only():
    service = MemoryChangeEventService()
    identity = _identity()
    other_branch = _identity(branch_head_id="branch-head-2")
    other_turn = _identity(turn_id="turn-2")
    other_profile = _identity(runtime_profile_snapshot_id="profile-snapshot-2")

    event = service.record_event(
        _event(
            event_id="event-1",
            identity=identity,
            domain="knowledge",
            source_refs=[
                _source_ref(source_type="retrieval_card", source_id="R1"),
            ],
            dirty_targets=[
                _dirty_target(
                    target_kind="packet_window",
                    target_id="writer.packet.current",
                ),
            ],
        )
    )

    assert event.domain == "knowledge_boundary"
    assert service.list_events(identity=identity) == [event]
    assert service.list_events(identity=identity, domain="knowledge") == [event]
    assert service.list_events(
        identity=identity,
        domain="knowledge_boundary",
    ) == [event]
    assert service.list_events(identity=other_branch) == []
    assert service.list_events(identity=other_turn) == []
    assert service.list_events(identity=other_profile) == []


def test_record_event_rejects_unknown_domain_and_duplicate_event_id():
    service = MemoryChangeEventService()
    identity = _identity()

    with pytest.raises(MemoryChangeEventServiceError) as exc:
        service.record_event(
            _event(event_id="event-1", identity=identity, domain="bogus")
        )
    assert exc.value.code == "memory_change_event_domain_not_registered"

    service.record_event(_event(event_id="event-1", identity=identity))

    with pytest.raises(MemoryChangeEventServiceError) as exc:
        service.record_event(
            _event(
                event_id="event-1",
                identity=_identity(branch_head_id="branch-head-2"),
            )
        )
    assert exc.value.code == "memory_change_event_id_conflict"


def test_list_events_filters_by_layer_kind_operation_source_dirty_target_and_visibility():
    service = MemoryChangeEventService()
    identity = _identity()

    first = service.record_event(
        _event(
            event_id="event-1",
            identity=identity,
            layer="runtime_workspace",
            event_kind="runtime_workspace_material_recorded",
            operation_kind="runtime_material.record",
            visibility_effect=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            source_refs=[
                _source_ref(source_type="retrieval_card", source_id="R1"),
                _source_ref(source_type="packet_ref", source_id="packet-1"),
            ],
            dirty_targets=[
                _dirty_target(
                    target_kind="packet_window",
                    target_id="writer.packet.current",
                ),
            ],
        )
    )
    second = service.record_event(
        _event(
            event_id="event-2",
            identity=identity,
            domain="character",
            layer="core_state.projection",
            event_kind="projection_refreshed",
            operation_kind="projection.refresh",
            visibility_effect=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
            source_refs=[
                _source_ref(source_type="writer_input_ref", source_id="draft-1"),
            ],
            dirty_targets=[
                _dirty_target(
                    target_kind="worker_refresh",
                    target_id="worker.character",
                ),
            ],
        )
    )

    assert service.list_events(identity=identity, layer="runtime_workspace") == [first]
    assert service.list_events(
        identity=identity,
        event_kind="projection_refreshed",
    ) == [second]
    assert service.list_events(
        identity=identity,
        operation_kind="projection.refresh",
    ) == [second]
    assert service.list_events(
        identity=identity,
        source_type="writer_input_ref",
    ) == [second]
    assert service.list_events(
        identity=identity,
        dirty_target_kind="packet_window",
    ) == [first]
    assert service.list_events(
        identity=identity,
        visibility_effect=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
    ) == [second]
    assert service.list_events(
        identity=identity,
        source_type="writer_input_ref",
        dirty_target_kind="worker_refresh",
        visibility_effect=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
    ) == [second]


def test_list_dirty_targets_flattens_matching_events_without_fabrication():
    service = MemoryChangeEventService()
    identity = _identity()
    first_packet = _dirty_target(
        target_kind="packet_window",
        target_id="writer.packet.current",
        reason="material_recorded",
    )
    first_worker = _dirty_target(
        target_kind="worker_refresh",
        target_id="worker.character",
    )
    second_packet = _dirty_target(
        target_kind="packet_window",
        target_id="writer.packet.next",
    )
    service.record_event(
        _event(
            event_id="event-1",
            identity=identity,
            dirty_targets=[first_packet, first_worker],
        )
    )
    service.record_event(
        _event(
            event_id="event-2",
            identity=identity,
            domain="character",
            layer="core_state.projection",
            dirty_targets=[second_packet],
        )
    )
    service.record_event(
        _event(
            event_id="event-3",
            identity=_identity(branch_head_id="branch-head-2"),
            dirty_targets=[
                _dirty_target(
                    target_kind="packet_window",
                    target_id="writer.packet.other",
                )
            ],
        )
    )

    assert service.list_dirty_targets(identity=identity) == [
        first_packet,
        first_worker,
        second_packet,
    ]
    assert service.list_dirty_targets(
        identity=identity,
        target_kind="packet_window",
    ) == [first_packet, second_packet]
    assert service.list_dirty_targets(
        identity=identity,
        domain="knowledge",
    ) == [first_packet, first_worker]
    assert service.list_dirty_targets(
        identity=identity,
        domain="character",
        layer="core_state.projection",
    ) == [second_packet]
    assert (
        service.list_dirty_targets(
            identity=_identity(turn_id="turn-2"),
        )
        == []
    )


def test_runtime_workspace_material_service_publishes_receipts_to_shared_spine():
    event_service = MemoryChangeEventService()
    material_service = RuntimeWorkspaceMaterialService(
        memory_change_event_service=event_service
    )
    identity = _identity()

    receipt = material_service.record_material(
        _material(
            material_id="mat-retrieval-r1",
            identity=identity,
            domain="knowledge",
            short_id="R1",
            payload={"excerpt": "A remembered constraint."},
        )
    )

    assert receipt.material.domain == "knowledge_boundary"
    assert material_service.store.events == [receipt.event]
    assert event_service.list_events(identity=identity) == [receipt.event]

    lifecycle_receipt = material_service.update_lifecycle(
        identity=identity,
        material_id="mat-retrieval-r1",
        lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
        reason="writer_output_referenced_material",
    )

    assert material_service.store.events == [receipt.event, lifecycle_receipt.event]
    assert event_service.list_events(identity=identity) == [
        receipt.event,
        lifecycle_receipt.event,
    ]
    assert (
        material_service.require_material(
            identity=identity,
            material_id="mat-retrieval-r1",
        ).lifecycle
        == lifecycle_receipt.material.lifecycle
    )


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


def _event(
    *,
    event_id: str,
    identity: MemoryRuntimeIdentity,
    domain: str = "knowledge_boundary",
    layer: str = "runtime_workspace",
    event_kind: str = "runtime_workspace_material_recorded",
    operation_kind: str = "runtime_material.record",
    visibility_effect: str = RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
    source_refs: list[MemorySourceRef] | None = None,
    dirty_targets: list[MemoryDirtyTarget] | None = None,
) -> MemoryChangeEvent:
    return MemoryChangeEvent(
        event_id=event_id,
        identity=identity,
        actor="writer.retrieval",
        event_kind=event_kind,
        layer=layer,
        domain=domain,
        block_id="knowledge_boundary.runtime_workspace",
        entry_id=event_id,
        operation_kind=operation_kind,
        source_refs=source_refs or [],
        dirty_targets=dirty_targets or [],
        visibility_effect=visibility_effect,
        metadata={},
    )


def _source_ref(*, source_type: str, source_id: str) -> MemorySourceRef:
    return MemorySourceRef(
        source_type=source_type,
        source_id=source_id,
        layer="runtime_workspace",
        domain="knowledge_boundary",
        block_id="knowledge_boundary.runtime_workspace",
        metadata={},
    )


def _dirty_target(
    *,
    target_kind: str,
    target_id: str,
    reason: str | None = None,
) -> MemoryDirtyTarget:
    return MemoryDirtyTarget(
        target_kind=target_kind,
        target_id=target_id,
        layer="runtime_workspace",
        domain="knowledge_boundary",
        block_id="knowledge_boundary.runtime_workspace",
        reason=reason,
        metadata={},
    )


def _material(
    *,
    material_id: str,
    identity: MemoryRuntimeIdentity,
    domain: str,
    short_id: str,
    payload: dict[str, object] | None = None,
) -> RuntimeWorkspaceMaterial:
    return RuntimeWorkspaceMaterial(
        material_id=material_id,
        material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        identity=identity,
        domain=domain,
        domain_path="knowledge_boundary.runtime.turn",
        source_refs=[],
        short_id=short_id,
        payload=payload or {"excerpt": "Evidence."},
        visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
        created_by="writer.retrieval",
        metadata={},
    )
