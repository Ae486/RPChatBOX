"""Focused tests for the runtime-centric worker registry bootstrap."""

from __future__ import annotations

import json

from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.memory_registry_management_service import (
    MemoryRegistryManagementService,
)
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_session_service import StorySessionService
from rp.services.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WRITING_WORKER_ID,
    WorkerRegistryService,
)


def _seed_story_session(
    retrieval_session,
    *,
    story_id: str,
):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    return StorySessionService(retrieval_session).create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )


def test_worker_registry_bootstrap_exposes_runtime_centric_workers(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="worker-registry-bootstrap",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.worker_registry.bootstrap",
    )
    service = WorkerRegistryService(retrieval_session)

    registry = service.build_registry_for_snapshot(
        snapshot_id=snapshot.runtime_profile_snapshot_id
    )
    active_workers = service.list_workers(
        snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    longform_worker = service.require_worker(
        LONGFORM_MEMORY_WORKER_ID,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    writing_worker = service.require_worker(
        WRITING_WORKER_ID,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
    )

    assert registry.mode == "longform"
    assert registry.registry_version == snapshot.compiled_profile_json["mode_profile"][
        "registry_version"
    ]
    assert [worker.descriptor.worker_id for worker in registry.workers] == [
        LONGFORM_MEMORY_WORKER_ID,
        WRITING_WORKER_ID,
    ]
    assert [worker.descriptor.worker_id for worker in active_workers] == [
        LONGFORM_MEMORY_WORKER_ID,
        WRITING_WORKER_ID,
    ]
    assert longform_worker.source_worker_id == "specialist"
    assert writing_worker.source_worker_id == "writer"
    assert longform_worker.descriptor.owned_domains == [
        "chapter",
        "narrative_progress",
        "plot_thread",
        "foreshadow",
        "timeline",
        "goal",
    ]
    assert longform_worker.descriptor.default_execution_policy == (
        longform_worker.execution_policy.policy_id
    )
    assert longform_worker.execution_policy.execution_class.value == "always_run"
    assert writing_worker.descriptor.owned_domains == []
    assert writing_worker.descriptor.allowed_layers == []
    assert writing_worker.execution_policy.policy_id == "writing_worker.default"


def test_worker_registry_hides_longform_memory_worker_when_specialist_is_disabled(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="worker-registry-specialist-disabled",
    )
    management = MemoryRegistryManagementService(retrieval_session)
    management.create_mode_profile(
        profile_id="longform_specialist_disabled",
        mode="longform",
        actor="test",
        config_json={"worker_overrides": {"specialist": {"active": False}}},
    )
    management.activate_mode_profile(
        profile_id="longform_specialist_disabled",
        actor="test",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.worker_registry.specialist_disabled",
    )
    service = WorkerRegistryService(retrieval_session)

    registry = service.build_registry_for_snapshot(
        snapshot_id=snapshot.runtime_profile_snapshot_id
    )
    active_workers = service.list_workers(
        snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    inactive_longform_worker = service.require_worker(
        LONGFORM_MEMORY_WORKER_ID,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
        include_inactive=True,
    )

    assert [worker.descriptor.worker_id for worker in registry.workers] == [
        LONGFORM_MEMORY_WORKER_ID,
        WRITING_WORKER_ID,
    ]
    assert [worker.descriptor.worker_id for worker in active_workers] == [
        WRITING_WORKER_ID
    ]
    assert inactive_longform_worker.active is False
    assert inactive_longform_worker.source_worker_id == "specialist"


def test_worker_registry_payload_does_not_expose_legacy_plan_or_bundle_truth(
    retrieval_session,
):
    story_session = _seed_story_session(
        retrieval_session,
        story_id="worker-registry-runtime-centric-payload",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.worker_registry.runtime_truth",
    )
    service = WorkerRegistryService(retrieval_session)

    registry = service.build_registry_for_snapshot(
        snapshot_id=snapshot.runtime_profile_snapshot_id
    )
    payload = json.dumps(registry.model_dump(mode="json"), ensure_ascii=False)

    assert "specialist" not in {
        worker.descriptor.worker_id for worker in registry.workers
    }
    assert "writer" not in {worker.descriptor.worker_id for worker in registry.workers}
    assert "orchestrator" not in {
        worker.descriptor.worker_id for worker in registry.workers
    }
    assert "OrchestratorPlan" not in payload
    assert "SpecialistResultBundle" not in payload
    assert "writer_instruction" not in payload
    assert "specialist_focus" not in payload
