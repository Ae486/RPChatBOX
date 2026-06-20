"""Deterministic scheduler decision service for orchestrator dispatch input."""

from __future__ import annotations

from uuid import uuid4

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.runtime.orchestrator_dispatch import OrchestratorDispatchToolInput
from rp.models.runtime.reason_codes import (
    SchedulerFailureCategory,
    SchedulerReasonCode,
)
from rp.models.writer.worker_runtime_contracts import (
    RuntimeWorkerRegistry,
    WorkerExecutionItem,
    WorkerExecutionPlan,
    WorkerPlanSource,
    WorkerSkipItem,
)


class SchedulerDecisionError(Exception):
    """Fail-closed scheduler precondition violation."""

    def __init__(self, *, category: SchedulerFailureCategory, message: str) -> None:
        self.category = category
        self.message = message
        super().__init__(f"{category.value}:{message}")


class SchedulerDecisionService:
    """Validate orchestrator dispatch against registry truth before execution."""

    def decide(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        phase: str,
        dispatch_input: OrchestratorDispatchToolInput,
        registry: RuntimeWorkerRegistry,
        source_unit_count: int,
    ) -> WorkerExecutionPlan:
        if registry.snapshot_id is None:
            raise SchedulerDecisionError(
                category=SchedulerFailureCategory.VALIDATION_ERROR,
                message="registry_snapshot_missing",
            )
        if registry.snapshot_id != identity.runtime_profile_snapshot_id:
            raise SchedulerDecisionError(
                category=SchedulerFailureCategory.VALIDATION_ERROR,
                message="registry_snapshot_mismatch",
            )

        by_id = {registration.descriptor.worker_id: registration for registration in registry.workers}
        selected_workers: list[WorkerExecutionItem] = []
        skipped_workers: list[WorkerSkipItem] = []
        seen_worker_ids: set[str] = set()

        for selection in dispatch_input.selections:
            reason_codes: list[str] = []
            registration = by_id.get(selection.worker_id)
            if registration is None:
                reason_codes.append(SchedulerReasonCode.ORCHESTRATOR_SCHEMA_INVALID.value)
            elif not registration.active:
                reason_codes.append(SchedulerReasonCode.WORKER_DISABLED.value)
            elif phase not in registration.descriptor.supported_phases:
                reason_codes.append(SchedulerReasonCode.WORKER_NOT_ACTIVE.value)
            elif not selection.source_unit_numbers:
                reason_codes.append(SchedulerReasonCode.SOURCE_WINDOW_EMPTY.value)
            elif any(
                number < 1 or number > source_unit_count
                for number in selection.source_unit_numbers
            ):
                reason_codes.append(SchedulerReasonCode.PARAGRAPH_NUMBER_OUT_OF_RANGE.value)
            elif selection.worker_id in seen_worker_ids:
                reason_codes.append(SchedulerReasonCode.ORCHESTRATOR_SCHEMA_INVALID.value)

            if reason_codes:
                skipped_workers.append(
                    WorkerSkipItem(
                        worker_id=selection.worker_id,
                        skip_reason=reason_codes[0],
                        reason_codes=reason_codes,
                    )
                )
                continue

            policy = registration.execution_policy
            selected_workers.append(
                WorkerExecutionItem(
                    worker_id=selection.worker_id,
                    must_run=policy.blocking_default,
                    allow_degrade=policy.allow_degrade,
                    blocking=policy.blocking_default,
                    async_allowed=policy.allow_async,
                    reason_codes=[],
                    scheduler_constraints={
                        "selection_source": "orchestrator_dispatch",
                        "orchestrator_reason_codes": list(selection.reason_codes),
                    },
                )
            )
            seen_worker_ids.add(selection.worker_id)

        return WorkerExecutionPlan(
            plan_id=f"worker_plan:{uuid4().hex}",
            identity=identity,
            plan_source=WorkerPlanSource.ORCHESTRATOR,
            phase=phase,
            selected_workers=selected_workers,
            skipped_workers=skipped_workers,
            trace_summary={
                "decision": "orchestrator_dispatch",
                "selected": len(selected_workers),
                "skipped": len(skipped_workers),
            },
        )
