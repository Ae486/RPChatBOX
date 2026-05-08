from __future__ import annotations

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.story_runtime import (
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerDescriptor,
    WorkerExecutionClass,
    WorkerExecutionPolicy,
    WorkerExecutionRequest,
)
from rp.services.story_runtime_adapter_service import (
    LONGFORM_ADAPTER_POLICY_ID,
    StoryRuntimeAdapterService,
)
from rp.services.worker_registry_service import LONGFORM_MEMORY_WORKER_ID


def test_legacy_command_translation_is_adapter_metadata_not_worker_plan():
    service = StoryRuntimeAdapterService()

    translation = service.translate_legacy_command(
        command_kind=LongformTurnCommandKind.REWRITE_PENDING_SEGMENT,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.DISCUSSION_MESSAGE,
            writer_instruction="Discuss the draft.",
        ),
    )

    assert translation.operation_mode == "rewrite"
    assert translation.command_surface == "legacy_longform_command"
    assert translation.adapter_policy_id == LONGFORM_ADAPTER_POLICY_ID
    assert "adapter_boundary:legacy_command_translation" in translation.notes
    assert not hasattr(translation, "selected_workers")
    metadata_notes = translation.metadata()["notes"]
    assert isinstance(metadata_notes, list)
    assert "runtime_contract_owner:writing_worker_contract" in metadata_notes


def test_legacy_post_write_plan_is_marked_as_adapter_input_only():
    service = StoryRuntimeAdapterService()

    plan = service.build_legacy_post_write_plan(
        command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
    )

    assert plan.output_kind == StoryArtifactKind.STORY_SEGMENT
    assert plan.writer_instruction == "Post-write maintenance adapter input."
    assert "adapter_input:legacy_orchestrator_plan" in plan.notes
    assert "not_canonical_worker_plan" in plan.notes
    assert f"adapter_policy:{LONGFORM_ADAPTER_POLICY_ID}" in plan.notes
    assert "deterministic_action:accept_pending_segment" in plan.notes


def test_specialist_bundle_adapter_maps_into_worker_result_without_plan_truth():
    service = StoryRuntimeAdapterService()
    request = WorkerExecutionRequest(
        request_id="worker-request-1",
        identity=MemoryRuntimeIdentity(
            story_id="story-1",
            session_id="session-1",
            branch_head_id="branch-1",
            turn_id="turn-1",
            runtime_profile_snapshot_id="snapshot-1",
        ),
        worker_id=LONGFORM_MEMORY_WORKER_ID,
        phase="pre_write_context",
        mode="longform",
        turn_id="turn-1",
        context_packet_ref="worker-packet-1",
        execution_policy=_execution_policy(),
    )
    registration = RuntimeWorkerRegistration(
        descriptor=WorkerDescriptor(
            worker_id=LONGFORM_MEMORY_WORKER_ID,
            display_name="Longform Memory Worker",
            default_execution_policy="longform_memory_worker.default",
            supported_phases=["pre_write_context"],
        ),
        execution_policy=_execution_policy(),
        source_worker_id="specialist",
    )
    bundle = SpecialistResultBundle(
        writer_hints=["Keep the storm callback active."],
        validation_findings=["No conflict found."],
        state_patch_proposals={"chapter_digest": {"beat": "storm"}},
        recall_summary_text="The storm callback was seeded.",
        summary_updates=["Storm callback retained."],
    )

    result = service.adapt_specialist_bundle_to_worker_result(
        request=request,
        registration=registration,
        bundle=bundle,
    )

    assert result.worker_id == LONGFORM_MEMORY_WORKER_ID
    assert result.trace_summary["adapter_role"] == "legacy_executor_bridge"
    assert result.trace_summary["legacy_plan_role"] == "adapter_input"
    assert result.trace_summary["canonical_contract_owner"] == "WorkerExecutionPlan"
    assert result.metadata["adapter_boundary"] == "legacy_bundle_to_worker_result"
    assert result.metadata["runtime_truth"] == "worker_runtime_contract"
    assert "worker_plan" not in result.metadata
    assert result.proposal_candidates == [
        {
            "candidate_kind": "legacy_state_patch",
            "payload": {"chapter_digest": {"beat": "storm"}},
        }
    ]
    assert result.recall_candidates == [
        {
            "candidate_kind": "legacy_recall_summary",
            "text": "The storm callback was seeded.",
        }
    ]


def _execution_policy() -> WorkerExecutionPolicy:
    return WorkerExecutionPolicy(
        policy_id="longform_memory_worker.default",
        execution_class=WorkerExecutionClass.ALWAYS_RUN,
        blocking_default=True,
        allow_async=False,
        allow_degrade=True,
        must_record_trace=True,
        requires_runtime_workspace=True,
        requires_post_write_job=True,
    )
