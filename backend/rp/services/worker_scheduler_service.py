"""Deterministic bootstrap scheduler for runtime worker execution."""

from __future__ import annotations

from uuid import uuid4

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.worker_runtime_contracts import (
    WorkerExecutionClass,
    WorkerExecutionItem,
    WorkerExecutionPlan,
    WorkerPlanSource,
    WorkerSkipItem,
)
from rp.services.worker_registry_service import WorkerRegistryService

PRE_WRITE_CONTEXT_PHASE = "pre_write_context"


class WorkerSchedulerService:
    """Build a narrow bootstrap worker plan from snapshot-pinned registry truth."""

    def __init__(self, *, worker_registry_service: WorkerRegistryService) -> None:
        self._worker_registry_service = worker_registry_service

    def build_plan(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        phase: str,
    ) -> WorkerExecutionPlan:
        registry = self._worker_registry_service.build_registry_for_snapshot(
            snapshot_id=identity.runtime_profile_snapshot_id
        )
        selected_workers: list[WorkerExecutionItem] = []
        skipped_workers: list[WorkerSkipItem] = []

        for registration in registry.workers:
            descriptor = registration.descriptor
            execution_policy = registration.execution_policy
            if not registration.active:
                skipped_workers.append(
                    WorkerSkipItem(
                        worker_id=descriptor.worker_id,
                        skip_reason="inactive_in_snapshot",
                        reason_codes=["snapshot_activation_inactive"],
                    )
                )
                continue
            if phase not in descriptor.supported_phases:
                skipped_workers.append(
                    WorkerSkipItem(
                        worker_id=descriptor.worker_id,
                        skip_reason="phase_not_supported",
                        reason_codes=[f"phase:{phase}"],
                    )
                )
                continue
            if execution_policy.execution_class != WorkerExecutionClass.ALWAYS_RUN:
                skipped_workers.append(
                    WorkerSkipItem(
                        worker_id=descriptor.worker_id,
                        skip_reason="execution_class_not_bootstrapped",
                        reason_codes=[
                            f"execution_class:{execution_policy.execution_class.value}"
                        ],
                    )
                )
                continue
            selected_workers.append(
                WorkerExecutionItem(
                    worker_id=descriptor.worker_id,
                    must_run=True,
                    allow_degrade=execution_policy.allow_degrade,
                    blocking=execution_policy.blocking_default,
                    async_allowed=execution_policy.allow_async,
                    context_requirements=dict(descriptor.context_slot_policy),
                    reason_codes=["selected_by_bootstrap_phase_policy", f"phase:{phase}"],
                    scheduler_constraints={
                        "selection_source": "registry_phase_bootstrap",
                        "requires_runtime_workspace": (
                            execution_policy.requires_runtime_workspace
                        ),
                        "requires_post_write_job": (
                            execution_policy.requires_post_write_job
                        ),
                    },
                )
            )

        return WorkerExecutionPlan(
            plan_id=f"worker-plan-{uuid4().hex}",
            identity=identity,
            plan_source=WorkerPlanSource.DETERMINISTIC_FALLBACK,
            phase=phase,
            selected_workers=selected_workers,
            skipped_workers=skipped_workers,
            trace_summary={
                "mode": registry.mode,
                "registry_version": registry.registry_version,
                "snapshot_id": identity.runtime_profile_snapshot_id,
                "selected_worker_ids": [
                    item.worker_id for item in selected_workers
                ],
                "skipped_worker_ids": [item.worker_id for item in skipped_workers],
                "selection_policy": "active_phase_always_run_only",
            },
            metadata={
                "bootstrap": True,
                "source": "worker_registry_service",
            },
        )
