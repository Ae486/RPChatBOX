"""Deterministic post-write trigger and scheduling helpers."""

from __future__ import annotations

from models.rp_story_store import StoryTurnRecord
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.proposal.postwrite_runtime_contracts import PostWriteTriggerContext
from rp.models.runtime.orchestrator_dispatch import OrchestratorPlanProposal
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.writer.worker_runtime_contracts import WorkerExecutionPlan
from rp.services.runtime.scheduler_decision_service import (
    SchedulerDecisionError,
    SchedulerDecisionService,
)
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.models.runtime.reason_codes import SchedulerFailureCategory
from rp.services.writer.worker_registry_service import WorkerRegistryService
from rp.services.writer.worker_scheduler_service import WorkerSchedulerService


POST_WRITE_MAINTENANCE_PHASE = "post_write_maintenance"


class PostWriteSchedulerService:
    """Own trigger facts and worker-plan selection for post-write F2."""

    def __init__(
        self,
        *,
        worker_scheduler_service: WorkerSchedulerService,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService | None,
        scheduler_decision_service: SchedulerDecisionService | None = None,
        worker_registry_service: WorkerRegistryService | None = None,
    ) -> None:
        self._worker_scheduler_service = worker_scheduler_service
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._scheduler_decision_service = scheduler_decision_service
        self._worker_registry_service = worker_registry_service

    def build_trigger_context(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn: StoryTurnRecord,
        mode: str,
    ) -> PostWriteTriggerContext:
        material_counts = self._turn_material_counts(identity=identity)
        retrieval_occurred = material_counts.get(
            RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD.value,
            0,
        ) > 0
        rule_card_present = any(
            material_counts.get(kind.value, 0) > 0
            for kind in (
                RuntimeWorkspaceMaterialKind.RULE_CARD,
                RuntimeWorkspaceMaterialKind.RULE_STATE_CARD,
            )
        )
        return PostWriteTriggerContext(
            identity=identity,
            turn_id=identity.turn_id,
            mode=str(mode or "").strip() or "unknown",
            turn_kind=turn.turn_kind,
            command_kind=turn.command_kind,
            retrieval_occurred=retrieval_occurred,
            rule_card_present=rule_card_present,
            metadata_json={
                "trigger_source": "post_write_scheduler_service",
                "runtime_workspace_material_counts": material_counts,
            },
        )

    def should_run_full_schedule(self, context: PostWriteTriggerContext) -> bool:
        return any(
            (
                context.retrieval_occurred,
                context.manual_core_edit_occurred,
                context.rule_card_present,
                context.scene_switch_detected,
                context.chapter_transition_detected,
                bool(context.dirty_domains),
                context.pending_threshold_reached,
                context.full_schedule_due_by_frequency,
            )
        )

    def build_worker_plan(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        proposal: OrchestratorPlanProposal | None = None,
    ) -> WorkerExecutionPlan:
        if proposal is None:
            return self._worker_scheduler_service.build_plan(
                identity=identity,
                phase=POST_WRITE_MAINTENANCE_PHASE,
            )
        if (
            self._scheduler_decision_service is None
            or self._worker_registry_service is None
        ):
            raise SchedulerDecisionError(
                category=SchedulerFailureCategory.VALIDATION_ERROR,
                message="scheduler_decision_unavailable",
            )
        if proposal.source_unit_count is None:
            raise SchedulerDecisionError(
                category=SchedulerFailureCategory.VALIDATION_ERROR,
                message="source_unit_count_missing",
            )
        registry = self._worker_registry_service.build_registry_for_snapshot(
            snapshot_id=identity.runtime_profile_snapshot_id,
        )
        return self._scheduler_decision_service.decide(
            identity=identity,
            phase=POST_WRITE_MAINTENANCE_PHASE,
            dispatch_input=proposal.dispatch_input,
            registry=registry,
            source_unit_count=proposal.source_unit_count,
        )

    def _turn_material_counts(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> dict[str, int]:
        if self._runtime_workspace_material_service is None:
            return {}
        counts: dict[str, int] = {}
        for material in self._runtime_workspace_material_service.list_materials(
            identity=identity
        ):
            kind = material.material_kind.value
            counts[kind] = counts.get(kind, 0) + 1
        return counts
