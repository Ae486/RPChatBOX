from __future__ import annotations

import pytest
from pydantic import ValidationError

from rp.models.runtime.identity import RuntimeProfileSnapshotCompiledProfile
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import LongformChapterPhase
from rp.models.writer.worker_family import WorkerFamily
from rp.models.writer.worker_runtime_contracts import (
    WorkerDescriptor,
    WorkerToolPolicy,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
from rp.services.story.session_service import StorySessionService
from rp.services.writer.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WorkerRegistryService,
)


def test_worker_family_members_are_string_values() -> None:
    assert WorkerFamily.MEMORY_MAINTENANCE.value == "memory_maintenance"
    assert WorkerFamily.WRITER.value == "writer"
    assert WorkerFamily.RETRIEVAL.value == "retrieval"
    assert WorkerFamily.RUNTIME_CONTEXT.value == "runtime_context"
    assert WorkerFamily.SIMPLE.value == "simple"


def test_worker_descriptor_requires_kind_and_family() -> None:
    with pytest.raises(ValidationError):
        WorkerDescriptor(
            worker_id="worker-a",
            display_name="Worker A",
            family=WorkerFamily.MEMORY_MAINTENANCE,
            default_execution_policy="worker-a.default",
        )

    with pytest.raises(ValidationError):
        WorkerDescriptor(
            worker_id="worker-b",
            display_name="Worker B",
            kind="memory_maintenance_worker",
            default_execution_policy="worker-b.default",
        )


def test_worker_descriptor_derives_tool_allowlist_from_tool_policy() -> None:
    descriptor = WorkerDescriptor(
        worker_id="worker-c",
        display_name="Worker C",
        kind="memory_maintenance_worker",
        family=WorkerFamily.MEMORY_MAINTENANCE,
        default_execution_policy="worker-c.default",
        tool_policy=WorkerToolPolicy(allowed_tools=["a", "b"]),
    )

    assert descriptor.tool_allowlist == ["a", "b"]
    assert descriptor.model_dump()["tool_allowlist"] == ["a", "b"]


def test_worker_registry_longform_memory_worker_uses_family_and_compiled_tool_policy(
    retrieval_session,
) -> None:
    snapshot = _seed_and_publish_longform_snapshot(retrieval_session)
    service = WorkerRegistryService(retrieval_session)

    registry = service.build_registry_for_snapshot(
        snapshot_id=snapshot.runtime_profile_snapshot_id
    )
    longform_worker = service.require_worker(
        LONGFORM_MEMORY_WORKER_ID,
        snapshot_id=snapshot.runtime_profile_snapshot_id,
    )

    assert longform_worker.descriptor.family == WorkerFamily.MEMORY_MAINTENANCE
    assert longform_worker.descriptor.kind == "memory_maintenance_worker"
    assert longform_worker.descriptor.tool_policy.max_tool_rounds == 8
    assert not any(
        tool.startswith("retrieval.") for tool in longform_worker.descriptor.tool_allowlist
    )
    assert registry.workers[0].descriptor.tool_allowlist == list(
        registry.workers[0].descriptor.tool_policy.allowed_tools
    )


def test_worker_registry_tool_policy_override_comes_from_compiled_profile(
    retrieval_session,
) -> None:
    snapshot = _seed_and_publish_longform_snapshot(retrieval_session)
    service = WorkerRegistryService(retrieval_session)
    compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(
        {
            **snapshot.compiled_profile_json,
            "worker_tool_policies": {
                LONGFORM_MEMORY_WORKER_ID: {"max_tool_rounds": 5}
            },
        }
    )

    registry = service.build_registry(compiled_profile=compiled)
    longform_worker = next(
        worker
        for worker in registry.workers
        if worker.descriptor.worker_id == LONGFORM_MEMORY_WORKER_ID
    )

    assert longform_worker.descriptor.tool_policy.max_tool_rounds == 5


def _seed_and_publish_longform_snapshot(retrieval_session):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id="worker-family-and-tool-policy",
        mode=StoryMode.LONGFORM,
    )
    story_session = StorySessionService(retrieval_session).create_session(
        story_id="worker-family-and-tool-policy",
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    return RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.worker_family_and_tool_policy",
    )
