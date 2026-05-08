"""Focused tests for the Phase B2 worker scheduler skeleton."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.worker_runtime_contracts import WorkerPlanSource
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_session_service import StorySessionService
from rp.services.context_orchestration_service import ContextOrchestrationService
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection_state_service import ProjectionStateService
from rp.services.story_runtime_workspace_facade import StoryRuntimeWorkspaceFacade
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.worker_execution_service import WorkerExecutionService
from rp.services.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WRITING_WORKER_ID,
    WorkerRegistryService,
)
from rp.services.worker_scheduler_service import (
    PRE_WRITE_CONTEXT_PHASE,
    WorkerSchedulerService,
)
from rp.services.writing_packet_builder import WritingPacketBuilder


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
async def test_worker_execution_service_adapts_longform_memory_worker_to_legacy_bundle(
    retrieval_session,
):
    session, chapter = _seed_story_runtime(
        retrieval_session,
        story_id="worker-execution-adapter",
    )
    snapshot = RuntimeProfileSnapshotService(retrieval_session).ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.worker_execution.adapter",
    )
    identity = MemoryRuntimeIdentity(
        story_id=session.story_id,
        session_id=session.session_id,
        branch_head_id="branch:test:main",
        turn_id="turn:test:1",
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    registry_service = WorkerRegistryService(retrieval_session)
    scheduler = WorkerSchedulerService(worker_registry_service=registry_service)
    plan = scheduler.build_plan(identity=identity, phase=PRE_WRITE_CONTEXT_PHASE)
    specialist = _RecordingSpecialistService()
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
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
    )
    runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    )
    execution_service = WorkerExecutionService(
        worker_registry_service=registry_service,
        longform_specialist_service=specialist,  # type: ignore[arg-type]
        context_orchestration_service=context_orchestration,
        runtime_workspace_facade=StoryRuntimeWorkspaceFacade(
            runtime_workspace_material_service=runtime_workspace_material_service
        ),
    )
    orchestrator_plan = OrchestratorPlan(
        output_kind=StoryArtifactKind.STORY_SEGMENT,
        writer_instruction="Write the next segment.",
        needs_retrieval=True,
        archival_queries=["storm"],
        recall_queries=["seal"],
    )

    outcome = await execution_service.execute_plan(
        session=SimpleNamespace(
            session_id=session.session_id,
            story_id=session.story_id,
            mode=session.mode,
        ),
        chapter=chapter,
        plan=plan,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        model_id="model",
        provider_id=None,
        user_prompt="Continue the chapter.",
        orchestrator_plan=orchestrator_plan,
        accepted_segments=[],
        pending_artifact=None,
    )

    assert len(specialist.calls) == 1
    assert specialist.calls[0]["runtime_identity"] == identity
    assert specialist.calls[0]["plan"] == orchestrator_plan
    context_packet = cast(Any, specialist.calls[0]["context_packet"])
    assert context_packet is not None
    assert context_packet.worker_id == LONGFORM_MEMORY_WORKER_ID
    assert context_packet.phase == PRE_WRITE_CONTEXT_PHASE
    assert context_packet.session_refs == [
        f"story_session:{session.session_id}",
        f"chapter_workspace:{chapter.chapter_workspace_id}",
    ]
    assert outcome.specialist_bundle.writer_hints == ["Hint A"]
    assert len(outcome.worker_results) == 1
    assert outcome.worker_results[0].worker_id == LONGFORM_MEMORY_WORKER_ID
    assert outcome.worker_results[0].metadata["legacy_bundle_kind"] == (
        "SpecialistResultBundle"
    )
    assert outcome.worker_results[0].metadata["context_packet_ref"].startswith(
        "worker-packet-"
    )
    assert outcome.worker_results[0].trace_summary["context_packet_ref"].startswith(
        "worker-packet-"
    )
    assert outcome.worker_results[0].trace_summary["adapter_role"] == (
        "legacy_executor_bridge"
    )
    assert outcome.worker_results[0].trace_summary["legacy_plan_role"] == (
        "adapter_input"
    )
    assert outcome.worker_results[0].metadata["runtime_truth"] == (
        "worker_runtime_contract"
    )
    assert outcome.worker_results[0].proposal_candidates == [
        {
            "candidate_kind": "legacy_state_patch",
            "payload": {"chapter_digest": {"current_chapter": 1}},
        }
    ]
    assert outcome.worker_results[0].recall_candidates == [
        {
            "candidate_kind": "legacy_recall_summary",
            "text": "Recall A",
        }
    ]
    evidence_materials = runtime_workspace_material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.WORKER_EVIDENCE_BUNDLE,
    )
    candidate_materials = runtime_workspace_material_service.list_materials(
        identity=identity,
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
