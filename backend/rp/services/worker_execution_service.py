"""Execute story-runtime worker plans through narrow executor adapters."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifact,
    StorySession,
    StorySegmentStructuredMetadata,
)
from rp.models.worker_runtime_contracts import (
    RuntimeWorkerRegistration,
    WorkerContextPacket,
    WorkerExecutionPlan,
    WorkerExecutionRequest,
    WorkerResult,
    WorkerResultStatus,
)
from rp.services.context_orchestration_service import ContextOrchestrationService
from rp.services.longform_specialist_service import LongformSpecialistService
from rp.services.story_runtime_adapter_service import StoryRuntimeAdapterService
from rp.services.story_runtime_workspace_facade import (
    StoryRuntimeWorkspaceFacade,
)
from rp.services.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WorkerRegistryService,
)


@dataclass(frozen=True)
class WorkerExecutionOutcome:
    """Compatibility execution aggregate for the bootstrap scheduler slice."""

    plan: WorkerExecutionPlan
    worker_results: list[WorkerResult]
    specialist_bundle: SpecialistResultBundle


@dataclass(frozen=True)
class _WorkerAdapterOutcome:
    worker_result: WorkerResult
    specialist_bundle: SpecialistResultBundle | None = None


class WorkerExecutionServiceError(ValueError):
    """Stable worker execution error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class WorkerExecutionService:
    """Execute scheduler-selected runtime workers without redefining the plan."""

    def __init__(
        self,
        *,
        worker_registry_service: WorkerRegistryService,
        longform_specialist_service: LongformSpecialistService,
        context_orchestration_service: ContextOrchestrationService | None = None,
        runtime_workspace_facade: StoryRuntimeWorkspaceFacade | None = None,
        story_runtime_adapter_service: StoryRuntimeAdapterService | None = None,
    ) -> None:
        self._worker_registry_service = worker_registry_service
        self._longform_specialist_service = longform_specialist_service
        self._context_orchestration_service = context_orchestration_service
        self._runtime_workspace_facade = runtime_workspace_facade
        self._story_runtime_adapter_service = (
            story_runtime_adapter_service or StoryRuntimeAdapterService()
        )

    async def execute_plan(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        plan: WorkerExecutionPlan,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        orchestrator_plan: OrchestratorPlan,
        accepted_segments: list[StoryArtifact],
        pending_artifact: StoryArtifact | None,
    ) -> WorkerExecutionOutcome:
        worker_results: list[WorkerResult] = []
        specialist_bundle = SpecialistResultBundle()

        for item in plan.selected_workers:
            registration = self._worker_registry_service.require_worker(
                item.worker_id,
                snapshot_id=plan.identity.runtime_profile_snapshot_id,
            )
            context_packet = None
            if self._context_orchestration_service is not None:
                context_packet = (
                    self._context_orchestration_service.build_worker_context_packet(
                        session=session,
                        chapter=chapter,
                        identity=plan.identity,
                        worker_id=item.worker_id,
                        phase=plan.phase,
                        mode=session.mode,
                        context_requirements=item.context_requirements,
                        reason_codes=item.reason_codes,
                        budget_class=item.budget_class,
                    )
                )
            request = WorkerExecutionRequest(
                request_id=f"worker-request-{uuid4().hex}",
                identity=plan.identity,
                worker_id=item.worker_id,
                phase=plan.phase,
                mode=session.mode,
                turn_id=plan.identity.turn_id,
                context_packet_ref=(
                    context_packet.packet_id if context_packet is not None else None
                ),
                context_packet=(
                    context_packet.model_dump(mode="json")
                    if context_packet is not None
                    else None
                ),
                execution_policy=registration.execution_policy,
                budget_class=item.budget_class,
                reason_codes=list(item.reason_codes),
                scheduler_constraints=dict(item.scheduler_constraints),
                metadata={
                    "bootstrap": True,
                    "source_worker_id": registration.source_worker_id,
                },
            )
            outcome = await self._execute_one(
                request=request,
                registration=registration,
                session=session,
                chapter=chapter,
                command_kind=command_kind,
                model_id=model_id,
                provider_id=provider_id,
                user_prompt=user_prompt,
                orchestrator_plan=orchestrator_plan,
                accepted_segments=accepted_segments,
                pending_artifact=pending_artifact,
            )
            worker_results.append(outcome.worker_result)
            if self._runtime_workspace_facade is not None:
                self._runtime_workspace_facade.record_prewrite_worker_surface(
                    request=request,
                    result=outcome.worker_result,
                )
            if outcome.specialist_bundle is not None:
                specialist_bundle = self._merge_specialist_bundle(
                    specialist_bundle,
                    outcome.specialist_bundle,
                )

        return WorkerExecutionOutcome(
            plan=plan,
            worker_results=worker_results,
            specialist_bundle=specialist_bundle,
        )

    async def _execute_one(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        session: StorySession,
        chapter: ChapterWorkspace,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        orchestrator_plan: OrchestratorPlan,
        accepted_segments: list[StoryArtifact],
        pending_artifact: StoryArtifact | None,
    ) -> _WorkerAdapterOutcome:
        if request.worker_id == LONGFORM_MEMORY_WORKER_ID:
            return await self._run_longform_memory_worker(
                request=request,
                registration=registration,
                session=session,
                chapter=chapter,
                command_kind=command_kind,
                model_id=model_id,
                provider_id=provider_id,
                user_prompt=user_prompt,
                orchestrator_plan=orchestrator_plan,
                accepted_segments=accepted_segments,
                pending_artifact=pending_artifact,
            )
        if registration.execution_policy.allow_degrade:
            return _WorkerAdapterOutcome(
                worker_result=self._build_missing_executor_result(
                    request=request,
                    registration=registration,
                ),
                specialist_bundle=None,
            )
        raise WorkerExecutionServiceError(
            "runtime_worker_executor_not_supported",
            request.worker_id,
        )

    async def _run_longform_memory_worker(
        self,
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
        session: StorySession,
        chapter: ChapterWorkspace,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        orchestrator_plan: OrchestratorPlan,
        accepted_segments: list[StoryArtifact],
        pending_artifact: StoryArtifact | None,
    ) -> _WorkerAdapterOutcome:
        context_packet = (
            WorkerContextPacket.model_validate(request.context_packet)
            if isinstance(request.context_packet, dict)
            else None
        )
        bundle = await self._longform_specialist_service.analyze(
            session=session,
            chapter=chapter,
            plan=orchestrator_plan,
            command_kind=command_kind,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=user_prompt,
            accepted_segments=accepted_segments,
            pending_artifact=pending_artifact,
            runtime_identity=request.identity,
            context_packet=context_packet,
        )
        result = self._story_runtime_adapter_service.adapt_specialist_bundle_to_worker_result(
            request=request,
            registration=registration,
            bundle=bundle,
        )
        return _WorkerAdapterOutcome(
            worker_result=result,
            specialist_bundle=bundle,
        )

    @staticmethod
    def _build_missing_executor_result(
        *,
        request: WorkerExecutionRequest,
        registration: RuntimeWorkerRegistration,
    ) -> WorkerResult:
        return WorkerResult(
            worker_id=request.worker_id,
            phase=request.phase,
            result_status=WorkerResultStatus.DEGRADED,
            writer_hints=[],
            validation_findings=[
                {
                    "reason_code": "runtime_worker_executor_missing",
                    "worker_id": request.worker_id,
                    "source_worker_id": registration.source_worker_id,
                }
            ],
            evidence_refs=[],
            trace_summary={
                "degrade_reason": "runtime_worker_executor_missing",
                "worker_id": request.worker_id,
                "phase": request.phase,
                "context_packet_ref": request.context_packet_ref,
                "runtime_extension": bool(
                    registration.execution_policy.metadata.get("runtime_extension")
                ),
            },
            metadata={
                "runtime_truth": "worker_runtime_contract",
                "degraded": True,
                "degrade_reason": "runtime_worker_executor_missing",
                "context_packet_ref": request.context_packet_ref,
                "source_worker_id": registration.source_worker_id,
            },
        )

    @staticmethod
    def _merge_specialist_bundle(
        base: SpecialistResultBundle,
        incoming: SpecialistResultBundle,
    ) -> SpecialistResultBundle:
        if base == SpecialistResultBundle():
            return incoming
        return SpecialistResultBundle(
            foundation_digest=_extend_unique(
                base.foundation_digest,
                incoming.foundation_digest,
            ),
            blueprint_digest=_extend_unique(
                base.blueprint_digest,
                incoming.blueprint_digest,
            ),
            current_outline_digest=_extend_unique(
                base.current_outline_digest,
                incoming.current_outline_digest,
            ),
            recent_segment_digest=_extend_unique(
                base.recent_segment_digest,
                incoming.recent_segment_digest,
            ),
            current_state_digest=_extend_unique(
                base.current_state_digest,
                incoming.current_state_digest,
            ),
            writer_hints=_extend_unique(base.writer_hints, incoming.writer_hints),
            validation_findings=_extend_unique(
                base.validation_findings,
                incoming.validation_findings,
            ),
            state_patch_proposals={
                **dict(base.state_patch_proposals),
                **dict(incoming.state_patch_proposals),
            },
            summary_updates=_extend_unique(
                base.summary_updates,
                incoming.summary_updates,
            ),
            recall_summary_text=(
                incoming.recall_summary_text or base.recall_summary_text
            ),
            story_segment_metadata=(
                incoming.story_segment_metadata
                if incoming.story_segment_metadata != StorySegmentStructuredMetadata()
                else base.story_segment_metadata
            ),
        )


def _extend_unique(left: list[str], right: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*left, *right]:
        normalized = str(value).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    return merged
