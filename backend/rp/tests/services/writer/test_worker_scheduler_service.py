"""Focused tests for the Phase B2 worker scheduler skeleton."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.setup_agent.workspace import StoryMode
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.writer.worker_runtime_contracts import WorkerPlanSource
from rp.models.writer.worker_runtime_contracts import WorkerResultStatus
from rp.runtime import rp_runtime_factory as runtime_factory_module
from rp.services.runtime.structured_output_runner import (
    StoryStructuredOutputRunner,
)
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_agent.workspace_service import SetupWorkspaceService
from rp.services.story.session_service import StorySessionService
from rp.services.runtime.context_orchestration_service import ContextOrchestrationService
from rp.services.projection.builder_context_service import (
    BuilderProjectionContextService,
)
from rp.services.projection.chapter_workspace_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection.state_service import ProjectionStateService
from rp.services.story.runtime_workspace_facade import StoryRuntimeWorkspaceFacade
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.writer.memory_maintenance_worker_adapter import (
    MemoryMaintenanceWorkerAdapter,
    S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
    S3_MEMORY_MAINTENANCE_CANDIDATE_KIND,
    S3_MEMORY_WORKER_ADAPTER_ID,
    S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
    ScriptedMemoryMaintenanceStructuredOutputRunner,
)
from rp.services.writer.worker_execution_service import WorkerExecutionService
from rp.services.writer.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WRITING_WORKER_ID,
    WorkerRegistryService,
)
from rp.services.writer.worker_scheduler_service import (
    PRE_WRITE_CONTEXT_PHASE,
    WorkerSchedulerService,
)
from rp.services.writer.writing_packet_builder import WritingPacketBuilder


def _seed_story_runtime(retrieval_session, *, story_id: str):
    workspace = SetupWorkspaceService(retrieval_session).create_workspace(
        story_id=story_id,
        mode=StoryMode.LONGFORM,
    )
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id=story_id,
        source_workspace_id=workspace.workspace_id,
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={},
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        chapter_goal="Chapter 1",
    )
    service.commit()
    return session, chapter


class _RecordingSpecialistService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def analyze(self, **kwargs):
        self.calls.append(kwargs)
        return SpecialistResultBundle(
            foundation_digest=["Found A"],
            blueprint_digest=["Blueprint A"],
            current_outline_digest=["Outline A"],
            recent_segment_digest=["Segment A"],
            current_state_digest=["State A"],
            writer_hints=["Hint A"],
            state_patch_proposals={"chapter_digest": {"current_chapter": 1}},
            recall_summary_text="Recall A",
        )


class _FactoryGateway:
    def __init__(self, *, text: str) -> None:
        self._text = text
        self.calls: list[dict[str, Any]] = []

    async def complete_text_with_usage(self, **kwargs):
        self.calls.append(kwargs)
        return self._text, {"prompt_tokens": 5, "completion_tokens": 7}


def test_worker_scheduler_selects_active_prewrite_longform_worker_from_snapshot(
    retrieval_session,
):
    session, _ = _seed_story_runtime(
        retrieval_session,
        story_id="worker-scheduler-selection",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.worker_scheduler.selection",
    )
    identity = MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch:test:main",
        turn_id="turn:test:1",
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    scheduler = WorkerSchedulerService(
        worker_registry_service=WorkerRegistryService(retrieval_session)
    )

    plan = scheduler.build_plan(
        identity=identity,
        phase=PRE_WRITE_CONTEXT_PHASE,
    )

    assert plan.plan_source == WorkerPlanSource.DETERMINISTIC_FALLBACK
    assert plan.phase == PRE_WRITE_CONTEXT_PHASE
    assert [item.worker_id for item in plan.selected_workers] == [
        LONGFORM_MEMORY_WORKER_ID
    ]
    assert plan.selected_workers[0].reason_codes == [
        "selected_by_bootstrap_phase_policy",
        f"phase:{PRE_WRITE_CONTEXT_PHASE}",
    ]
    assert any(
        item.worker_id == WRITING_WORKER_ID
        and item.skip_reason == "phase_not_supported"
        for item in plan.skipped_workers
    )
    assert plan.trace_summary["snapshot_id"] == snapshot.runtime_profile_snapshot_id
    assert plan.trace_summary["selection_policy"] == "active_phase_always_run_only"


@pytest.mark.asyncio
async def test_worker_execution_service_uses_s3_memory_adapter_when_runner_exists(
    retrieval_session,
):
    fixture = _worker_execution_fixture(
        retrieval_session,
        story_id="worker-execution-s3-adapter",
    )
    runner = ScriptedMemoryMaintenanceStructuredOutputRunner(
        [_candidate_output(phase=PRE_WRITE_CONTEXT_PHASE)]
    )
    execution_service = WorkerExecutionService(
        worker_registry_service=fixture.registry_service,
        longform_specialist_service=fixture.specialist,
        context_orchestration_service=fixture.context_orchestration,
        runtime_workspace_facade=StoryRuntimeWorkspaceFacade(
            runtime_workspace_material_service=fixture.runtime_workspace_material_service
        ),
        longform_memory_worker_adapter=MemoryMaintenanceWorkerAdapter(
            structured_output_runner=runner
        ),
    )

    outcome = await execution_service.execute_plan(
        session=SimpleNamespace(
            session_id=fixture.session.session_id,
            story_id=fixture.session.story_id,
            mode=fixture.session.mode,
        ),
        chapter=fixture.chapter,
        plan=fixture.plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue the chapter.",
        orchestrator_plan=_orchestrator_plan(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert fixture.specialist.calls == []
    assert runner.call_count == 1
    assert outcome.specialist_bundle == SpecialistResultBundle()
    assert len(outcome.worker_results) == 1
    result = outcome.worker_results[0]
    assert result.worker_id == LONGFORM_MEMORY_WORKER_ID
    assert result.result_status == WorkerResultStatus.COMPLETED
    assert result.proposal_candidates[0]["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )
    assert result.proposal_candidates[0]["metadata"]["adapter"] == (
        S3_MEMORY_WORKER_ADAPTER_ID
    )
    assert result.metadata["adapter"] == S3_MEMORY_WORKER_ADAPTER_ID
    assert result.metadata["structured_output_metadata"] == {"fake_runner": True}
    assert result.trace_summary["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )


@pytest.mark.asyncio
async def test_worker_execution_service_uses_explicit_legacy_compatibility_fallback(
    retrieval_session,
):
    fixture = _worker_execution_fixture(
        retrieval_session,
        story_id="worker-execution-legacy-compat",
    )
    execution_service = WorkerExecutionService(
        worker_registry_service=fixture.registry_service,
        longform_specialist_service=fixture.specialist,
        context_orchestration_service=fixture.context_orchestration,
        runtime_workspace_facade=StoryRuntimeWorkspaceFacade(
            runtime_workspace_material_service=fixture.runtime_workspace_material_service
        ),
        longform_memory_worker_adapter=MemoryMaintenanceWorkerAdapter(),
        enable_legacy_longform_memory_worker_specialist_fallback=True,
    )

    outcome = await execution_service.execute_plan(
        session=SimpleNamespace(
            session_id=fixture.session.session_id,
            story_id=fixture.session.story_id,
            mode=fixture.session.mode,
        ),
        chapter=fixture.chapter,
        plan=fixture.plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue the chapter.",
        orchestrator_plan=_orchestrator_plan(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert len(fixture.specialist.calls) == 1
    assert fixture.specialist.calls[0]["runtime_identity"] == fixture.identity
    assert fixture.specialist.calls[0]["plan"] == _orchestrator_plan()
    context_packet = cast(Any, fixture.specialist.calls[0]["context_packet"])
    assert context_packet is not None
    assert context_packet.worker_id == LONGFORM_MEMORY_WORKER_ID
    assert context_packet.phase == PRE_WRITE_CONTEXT_PHASE
    assert context_packet.session_refs == [
        f"story_session:{fixture.session.session_id}",
        f"chapter_workspace:{fixture.chapter.chapter_workspace_id}",
    ]
    assert outcome.specialist_bundle.writer_hints == ["Hint A"]
    assert len(outcome.worker_results) == 1
    result = outcome.worker_results[0]
    assert result.worker_id == LONGFORM_MEMORY_WORKER_ID
    assert result.metadata["legacy_bundle_kind"] == "SpecialistResultBundle"
    assert result.metadata["context_packet_ref"].startswith("worker-packet-")
    assert result.trace_summary["context_packet_ref"].startswith("worker-packet-")
    assert result.trace_summary["adapter_role"] == "legacy_executor_bridge"
    assert result.trace_summary["legacy_plan_role"] == "adapter_input"
    assert result.metadata["runtime_truth"] == "worker_runtime_contract"
    assert result.metadata["executor_mode"] == "legacy_specialist_compatibility"
    assert result.trace_summary["executor_mode"] == (
        "legacy_specialist_compatibility"
    )
    assert result.metadata["compatibility_reason"] == (
        "memory_worker_structured_output_runner_missing"
    )
    assert result.trace_summary["compatibility_reason"] == (
        "memory_worker_structured_output_runner_missing"
    )
    assert result.metadata["s3_executor_migration_complete"] is False
    assert result.trace_summary["s3_executor_migration_complete"] is False
    assert result.proposal_candidates == [
        {
            "candidate_kind": "legacy_state_patch",
            "payload": {"chapter_digest": {"current_chapter": 1}},
        }
    ]
    assert result.recall_candidates == [
        {
            "candidate_kind": "legacy_recall_summary",
            "text": "Recall A",
        }
    ]
    evidence_materials = fixture.runtime_workspace_material_service.list_materials(
        identity=fixture.identity,
        material_kind=RuntimeWorkspaceMaterialKind.WORKER_EVIDENCE_BUNDLE,
    )
    candidate_materials = fixture.runtime_workspace_material_service.list_materials(
        identity=fixture.identity,
        material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
    )
    assert len(evidence_materials) == 1
    assert evidence_materials[0].payload["worker_id"] == LONGFORM_MEMORY_WORKER_ID
    assert evidence_materials[0].payload["context_packet_ref"].startswith(
        "worker-packet-"
    )
    assert len(candidate_materials) == 1
    assert candidate_materials[0].payload["proposal_candidates"] == [
        {
            "candidate_kind": "legacy_state_patch",
            "payload": {"chapter_digest": {"current_chapter": 1}},
        }
    ]
    assert candidate_materials[0].payload["recall_candidates"] == [
        {
            "candidate_kind": "legacy_recall_summary",
            "text": "Recall A",
        }
    ]


@pytest.mark.asyncio
async def test_worker_execution_service_fails_when_runner_and_compatibility_disabled(
    retrieval_session,
):
    fixture = _worker_execution_fixture(
        retrieval_session,
        story_id="worker-execution-disabled-runner-no-compat",
    )
    execution_service = WorkerExecutionService(
        worker_registry_service=fixture.registry_service,
        longform_specialist_service=fixture.specialist,
        context_orchestration_service=fixture.context_orchestration,
        runtime_workspace_facade=StoryRuntimeWorkspaceFacade(
            runtime_workspace_material_service=fixture.runtime_workspace_material_service
        ),
        longform_memory_worker_adapter=MemoryMaintenanceWorkerAdapter(),
        enable_legacy_longform_memory_worker_specialist_fallback=False,
    )

    outcome = await execution_service.execute_plan(
        session=SimpleNamespace(
            session_id=fixture.session.session_id,
            story_id=fixture.session.story_id,
            mode=fixture.session.mode,
        ),
        chapter=fixture.chapter,
        plan=fixture.plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue the chapter.",
        orchestrator_plan=_orchestrator_plan(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert fixture.specialist.calls == []
    assert outcome.specialist_bundle == SpecialistResultBundle()
    assert len(outcome.worker_results) == 1
    result = outcome.worker_results[0]
    assert result.worker_id == LONGFORM_MEMORY_WORKER_ID
    assert result.result_status == WorkerResultStatus.FAILED
    assert result.trace_summary["reason_code"] == (
        "memory_worker_structured_output_runner_missing"
    )
    assert result.trace_summary["failure_source"] == "fake_execution"
    assert result.proposal_candidates == []
    assert result.recall_candidates == []


def test_runtime_factory_wires_memory_worker_adapter_with_production_runner(
    monkeypatch,
    retrieval_session,
):
    captured_kwargs: dict[str, Any] = {}

    class _StopFactory(RuntimeError):
        pass

    class _CaptureWorkerExecutionService:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            raise _StopFactory

    monkeypatch.setattr(
        runtime_factory_module,
        "WorkerExecutionService",
        _CaptureWorkerExecutionService,
    )

    with pytest.raises(_StopFactory):
        runtime_factory_module.RpRuntimeFactory(
            retrieval_session
        ).build_story_turn_domain_service()

    adapter = captured_kwargs["longform_memory_worker_adapter"]
    assert isinstance(adapter, MemoryMaintenanceWorkerAdapter)
    assert adapter.has_structured_output_runner is True
    assert (
        captured_kwargs["enable_legacy_longform_memory_worker_specialist_fallback"]
        is True
    )


def test_runtime_factory_can_disable_production_runner_and_keep_compatibility_flag(
    monkeypatch,
    retrieval_session,
):
    captured_kwargs: dict[str, Any] = {}

    class _StopFactory(RuntimeError):
        pass

    class _CaptureWorkerExecutionService:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            raise _StopFactory

    monkeypatch.setattr(
        runtime_factory_module,
        "WorkerExecutionService",
        _CaptureWorkerExecutionService,
    )

    with pytest.raises(_StopFactory):
        runtime_factory_module.RpRuntimeFactory(
            retrieval_session,
            enable_longform_memory_worker_production_runner=False,
        ).build_story_turn_domain_service()

    adapter = captured_kwargs["longform_memory_worker_adapter"]
    assert isinstance(adapter, MemoryMaintenanceWorkerAdapter)
    assert adapter.has_structured_output_runner is False
    assert (
        captured_kwargs["enable_legacy_longform_memory_worker_specialist_fallback"]
        is True
    )


@pytest.mark.asyncio
async def test_factory_built_normal_path_uses_production_runner_without_legacy_specialist_call(
    monkeypatch,
    retrieval_session,
):
    fixture = _worker_execution_fixture(
        retrieval_session,
        story_id="worker-execution-factory-production",
    )
    fake_gateway = _FactoryGateway(
        text=json.dumps(_candidate_output(phase=PRE_WRITE_CONTEXT_PHASE))
    )
    specialist = _RecordingSpecialistService()

    monkeypatch.setattr(
        runtime_factory_module.RpRuntimeFactory,
        "_build_memory_worker_structured_output_runner_port",
        staticmethod(
            lambda: StoryStructuredOutputRunner(llm_gateway=fake_gateway)
        ),
    )
    monkeypatch.setattr(
        runtime_factory_module,
        "LongformSpecialistService",
        lambda *args, **kwargs: specialist,
    )

    turn_domain_service = runtime_factory_module.RpRuntimeFactory(
        retrieval_session
    ).build_story_turn_domain_service()
    execution_service = getattr(turn_domain_service, "_worker_execution_service")
    assert execution_service is not None

    outcome = await execution_service.execute_plan(
        session=SimpleNamespace(
            session_id=fixture.session.session_id,
            story_id=fixture.session.story_id,
            mode=fixture.session.mode,
        ),
        chapter=fixture.chapter,
        plan=fixture.plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model-a",
        provider_id="provider-a",
        user_prompt="Continue the chapter.",
        orchestrator_plan=_orchestrator_plan(),
        accepted_segments=[],
        pending_artifact=None,
    )

    assert specialist.calls == []
    assert len(fake_gateway.calls) == 1
    assert outcome.specialist_bundle == SpecialistResultBundle()
    result = outcome.worker_results[0]
    assert result.result_status == WorkerResultStatus.COMPLETED
    assert result.proposal_candidates[0]["candidate_kind"] == (
        S3_MEMORY_MAINTENANCE_CANDIDATE_KIND
    )
    assert result.trace_summary["runner_mode"] == "production"
    assert result.trace_summary["runner_schema_name"] == (
        "memory-maintenance-worker-output"
    )
    assert result.trace_summary["runner_schema_version"] == (
        S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION
    )


def _orchestrator_plan() -> OrchestratorPlan:
    return OrchestratorPlan(
        output_kind=StoryArtifactKind.STORY_SEGMENT,
        writer_instruction="Write the next segment.",
        needs_retrieval=True,
        archival_queries=["storm"],
        recall_queries=["seal"],
    )


def _worker_execution_fixture(retrieval_session, *, story_id: str):
    session, chapter = _seed_story_runtime(retrieval_session, story_id=story_id)
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from=f"test.{story_id}",
    )
    identity = MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch:test:main",
        turn_id="turn:test:1",
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    registry_service = WorkerRegistryService(retrieval_session)
    plan = WorkerSchedulerService(worker_registry_service=registry_service).build_plan(
        identity=identity,
        phase=PRE_WRITE_CONTEXT_PHASE,
    )
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    story_session_service = StorySessionService(retrieval_session)
    context_orchestration = ContextOrchestrationService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            ProjectionStateService(
                story_session_service=story_session_service,
                adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
            )
        ),
        writing_packet_builder=WritingPacketBuilder(),
        runtime_workspace_material_service=runtime_workspace_material_service,
    )
    return SimpleNamespace(
        session=session,
        chapter=chapter,
        identity=identity,
        registry_service=registry_service,
        plan=plan,
        specialist=_RecordingSpecialistService(),
        context_orchestration=context_orchestration,
        runtime_workspace_material_service=runtime_workspace_material_service,
    )


def _candidate_output(*, phase: str):
    return {
        "schema_version": S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION,
        "status": "candidate_batch",
        "worker_id": LONGFORM_MEMORY_WORKER_ID,
        "phase": phase,
        "candidate_batch": {
            "schema_version": S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION,
            "worker_id": LONGFORM_MEMORY_WORKER_ID,
            "phase": phase,
            "candidates": [
                {
                    "target_domain": "current_scene",
                    "target_block_id": "scene.frame",
                    "base_block_revision_id": "block-revision-1",
                    "operations": [
                        {
                            "kind": "append_item",
                            "field_id": "facts",
                            "content": "The storm has cut off the bridge.",
                        }
                    ],
                    "source_refs": [
                        {
                            "source_type": "accepted_prose",
                            "source_id": "segment-1",
                            "layer": "runtime_workspace",
                        }
                    ],
                    "change_summary": "Track the bridge cutoff as scene framing.",
                }
            ],
        },
        "metadata": {"fake_runner": True},
    }
