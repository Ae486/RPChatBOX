"""Shared domain service for story turn commands and generation flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import AsyncIterator, Protocol, cast
from uuid import uuid4

from models.rp_story_store import RuntimeWorkflowJobRecord, StoryTurnRecord
from rp.models.memory.contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.block.consumer import BlockConsumerKey
from rp.models.proposal.postwrite_runtime_contracts import (
    PostWriteExecutionEnvelope,
    PostWriteRunKind,
)
from rp.models.runtime.identity import INTERRUPTED_BY_RESTART, StoryTurnStatus
from rp.models.runtime.orchestrator_dispatch import OrchestratorPlanProposal
from rp.models.runtime.reason_codes import SchedulerReasonCode
from rp.models.runtime.workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.story.runtime import (
    ChapterWorkspace,
    ChapterWorkspaceSnapshot,
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    LongformTurnResponse,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StorySegmentStructuredMetadata,
    StorySession,
)
from rp.models.writer.worker_memory import WorkerSourceRefBundle
from rp.models.writer.worker_runtime_contracts import WorkerPlanSource, WorkerResultStatus
from rp.models.writer.writing_worker_contracts import (
    WritingWorkerExecutionRequest,
    WritingWorkerExecutionResult,
)
from rp.models.writer.writing_runtime import WritingPacket
from ..runtime.context_orchestration_service import ContextOrchestrationService
from ..writer.longform_chapter_runtime_service import LongformChapterRuntimeService
from ..writer.longform_chapter_runtime_service import LongformChapterRuntimeServiceError
from ..writer.longform_chapter_runtime_service import ResolvedChapterTransition
from ..writer.longform_orchestrator_service import LongformOrchestratorService
from ..writer.longform_regression_service import LongformRegressionService
from ..writer.longform_specialist_service import LongformSpecialistService
from ..proposal.post_write_governance_service import PostWriteGovernanceService
from ..proposal.post_write_scheduler_service import (
    POST_WRITE_MAINTENANCE_PHASE,
    PostWriteSchedulerService,
)
from ..projection.builder_context_service import BuilderProjectionContextService
from ..projection.state_service import ProjectionStateService
from ..recall.scene_transcript_ingestion_service import (
    RecallSceneTranscriptIngestionService,
)
from ..retrieval.runtime_card_service import RuntimeRetrievalCardService
from ..retrieval.writer_usage_guard_service import (
    WriterRetrievalUsageGuardService,
    WriterRetrievalUsageGuardServiceError,
)
from .block_consumer_state_service import StoryBlockConsumerStateService
from .runtime_identity_service import StoryRuntimeIdentityService
from .runtime_workspace_facade import StoryRuntimeWorkspaceFacade
from .session_service import StorySessionService
from ..runtime.read_manifest_service import RuntimeReadManifestService
from ..runtime.scheduler_decision_service import SchedulerDecisionError
from ..runtime.workflow_job_service import (
    RuntimeWorkflowJobServiceError,
    RuntimeWorkflowJobService,
    TurnSettlementEvaluation,
)
from ..runtime.maintenance_lock_service import RuntimeMaintenanceLockService
from ..runtime.workspace_material_service import RuntimeWorkspaceMaterialService
from .runtime_adapter_service import StoryRuntimeAdapterService
from ..writer.worker_execution_service import WorkerExecutionService
from ..writer.worker_scheduler_service import (
    PRE_WRITE_CONTEXT_PHASE,
    WorkerSchedulerService,
)
from ..writer.writing_packet_builder import WritingPacketBuilder
from ..writer.writing_worker_execution_service import WritingWorkerExecutionService


class OrchestratorDispatchProvider(Protocol):
    def propose(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        phase: str,
        turn,
        trigger_context,
    ) -> OrchestratorPlanProposal | None: ...


class WriterFinalizationRejected(Exception):
    """Raised when writer finalization is rejected before visible output is set."""

    reason_code: str

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class StoryTurnDomainService:
    """Own longform turn domain logic independent of graph/controller shell."""

    _DEFAULT_BRANCH_NAME = "main"

    # REV-025 re-open copies the origin-turn identity block + beat pointer so the
    # minted draft is snapshot-visible and the re-adopt gate can rebind it.
    _REOPEN_COPIED_METADATA_KEYS: frozenset[str] = frozenset(
        {
            "runtime_story_id",
            "runtime_session_id",
            "runtime_branch_head_id",
            "runtime_turn_id",
            "runtime_profile_snapshot_id",
            "target_beat_id",
        }
    )

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        orchestrator_service: LongformOrchestratorService,
        specialist_service: LongformSpecialistService,
        builder_projection_context_service: BuilderProjectionContextService,
        projection_state_service: ProjectionStateService,
        writing_packet_builder: WritingPacketBuilder,
        writing_worker_execution_service: WritingWorkerExecutionService,
        regression_service: LongformRegressionService,
        block_consumer_state_service: StoryBlockConsumerStateService | None = None,
        recall_scene_transcript_ingestion_service: (
            RecallSceneTranscriptIngestionService | None
        ) = None,
        runtime_identity_service: StoryRuntimeIdentityService | None = None,
        runtime_read_manifest_service: RuntimeReadManifestService | None = None,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService
        | None = None,
        worker_scheduler_service: WorkerSchedulerService | None = None,
        worker_execution_service: WorkerExecutionService | None = None,
        context_orchestration_service: ContextOrchestrationService | None = None,
        runtime_workspace_facade: StoryRuntimeWorkspaceFacade | None = None,
        runtime_workflow_job_service: RuntimeWorkflowJobService | None = None,
        post_write_scheduler_service: PostWriteSchedulerService | None = None,
        post_write_governance_service: PostWriteGovernanceService | None = None,
        orchestrator_dispatch_provider: OrchestratorDispatchProvider | None = None,
        story_runtime_adapter_service: StoryRuntimeAdapterService | None = None,
        longform_chapter_runtime_service: LongformChapterRuntimeService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._orchestrator_service = orchestrator_service
        self._specialist_service = specialist_service
        self._builder_projection_context_service = builder_projection_context_service
        self._projection_state_service = projection_state_service
        self._writing_packet_builder = writing_packet_builder
        self._writing_worker_execution_service = writing_worker_execution_service
        self._regression_service = regression_service
        self._block_consumer_state_service = block_consumer_state_service
        self._recall_scene_transcript_ingestion_service = (
            recall_scene_transcript_ingestion_service
        )
        self._runtime_identity_by_session: dict[str, MemoryRuntimeIdentity] = {}
        story_db_session = getattr(story_session_service, "_session", None)
        self._runtime_identity_service = runtime_identity_service or (
            StoryRuntimeIdentityService(story_db_session)
            if story_db_session is not None
            else None
        )
        self._worker_scheduler_service = worker_scheduler_service
        self._worker_execution_service = worker_execution_service
        resolver_session = (
            getattr(self._runtime_identity_service, "_session", None)
            if self._runtime_identity_service is not None
            else None
        )
        self._runtime_workspace_material_service = (
            runtime_workspace_material_service
            or (
                RuntimeWorkspaceMaterialService(session=resolver_session)
                if resolver_session is not None
                else None
            )
        )
        self._runtime_read_manifest_service: RuntimeReadManifestService | None
        if runtime_read_manifest_service is not None:
            self._runtime_read_manifest_service = runtime_read_manifest_service
        else:
            self._runtime_read_manifest_service = (
                RuntimeReadManifestService(
                    session=resolver_session,
                    runtime_workspace_material_service=(
                        self._runtime_workspace_material_service
                    ),
                )
                if resolver_session is not None
                else None
            )
        self._longform_chapter_runtime_service = (
            longform_chapter_runtime_service
            or (
                LongformChapterRuntimeService(
                    story_session_service=story_session_service,
                    workspace_material_service=(
                        self._runtime_workspace_material_service
                    ),
                    writing_worker_execution_service=(
                        writing_worker_execution_service
                    ),
                    session=resolver_session,
                )
                if resolver_session is not None
                else None
            )
        )
        self._context_orchestration_service = (
            context_orchestration_service
            or ContextOrchestrationService(
                story_session_service=story_session_service,
                builder_projection_context_service=builder_projection_context_service,
                writing_packet_builder=writing_packet_builder,
                runtime_workspace_material_service=(
                    self._runtime_workspace_material_service
                ),
                runtime_read_manifest_service=self._runtime_read_manifest_service,
                longform_chapter_runtime_service=(
                    self._longform_chapter_runtime_service
                ),
            )
        )
        self._runtime_workspace_facade = (
            runtime_workspace_facade
            or (
                StoryRuntimeWorkspaceFacade(
                    runtime_workspace_material_service=(
                        self._runtime_workspace_material_service
                    )
                )
                if self._runtime_workspace_material_service is not None
                else None
            )
        )
        self._runtime_workflow_job_service = (
            runtime_workflow_job_service
            or (
                RuntimeWorkflowJobService(resolver_session)
                if resolver_session is not None
                else None
            )
        )
        self._maintenance_lock_service = (
            RuntimeMaintenanceLockService(resolver_session)
            if resolver_session is not None
            else None
        )
        self._post_write_scheduler_service = post_write_scheduler_service
        self._post_write_governance_service = post_write_governance_service
        self._orchestrator_dispatch_provider = orchestrator_dispatch_provider
        self._story_runtime_adapter_service = (
            story_runtime_adapter_service or StoryRuntimeAdapterService()
        )

    def prepare_generation_inputs(
        self,
        *,
        session_id: str,
        user_prompt: str | None,
        target_artifact_id: str | None,
    ) -> dict[str, object]:
        session = self.require_session(session_id)
        chapter = self.require_active_branch_current_chapter(session_id)
        if user_prompt:
            self._story_session_service.create_discussion_entry(
                session_id=session.session_id,
                chapter_workspace_id=chapter.chapter_workspace_id,
                role="user",
                content_text=user_prompt,
            )
        pending_artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=target_artifact_id,
        )
        accepted_segment_ids = [
            item.artifact_id for item in self.accepted_segments(chapter)
        ]
        return {
            "pending_artifact_id": pending_artifact.artifact_id
            if pending_artifact
            else None,
            "accepted_segment_ids": accepted_segment_ids,
        }

    async def orchestrator_plan(
        self,
        *,
        session_id: str,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        target_artifact_id: str | None,
    ) -> OrchestratorPlan:
        session = self.require_session(session_id)
        chapter = self.require_active_branch_current_chapter(session_id)
        plan = await self._orchestrator_service.plan(
            session=session,
            chapter=chapter,
            command_kind=command_kind,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=user_prompt,
            target_artifact_id=target_artifact_id,
        )
        self._mark_block_consumer_synced(
            session_id=session_id,
            consumer_key="story.orchestrator",
        )
        return plan

    async def specialist_analyze(
        self,
        *,
        session_id: str,
        command_kind: LongformTurnCommandKind,
        model_id: str,
        provider_id: str | None,
        user_prompt: str | None,
        plan: OrchestratorPlan,
        pending_artifact_id: str | None,
        accepted_segment_ids: list[str],
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> SpecialistResultBundle:
        session = self.require_session(session_id)
        chapter = self.require_active_branch_current_chapter(session_id)
        pending_artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=pending_artifact_id,
        )
        visible_accepted_by_id = {
            artifact.artifact_id: artifact for artifact in self.accepted_segments(chapter)
        }
        accepted_segments = list(visible_accepted_by_id.values())
        chapter = chapter.model_copy(
            update={
                "accepted_segment_ids": [
                    artifact.artifact_id for artifact in accepted_segments
                ]
            }
        )
        if (
            runtime_identity is not None
            and self._worker_scheduler_service is not None
            and self._worker_execution_service is not None
        ):
            execution_plan = self._worker_scheduler_service.build_plan(
                identity=runtime_identity,
                phase=PRE_WRITE_CONTEXT_PHASE,
            )
            execution = await self._worker_execution_service.execute_plan(
                session=session,
                chapter=chapter,
                plan=execution_plan,
                command_kind=command_kind,
                model_id=model_id,
                provider_id=provider_id,
                user_prompt=user_prompt,
                orchestrator_plan=plan,
                accepted_segments=accepted_segments,
                pending_artifact=pending_artifact,
            )
            bundle = execution.specialist_bundle
        else:
            bundle = await self._specialist_service.analyze(
                session=session,
                chapter=chapter,
                plan=plan,
                command_kind=command_kind,
                model_id=model_id,
                provider_id=provider_id,
                user_prompt=user_prompt,
                accepted_segments=accepted_segments,
                pending_artifact=pending_artifact,
                runtime_identity=runtime_identity,
            )
        if runtime_identity is not None:
            self._runtime_identity_by_session[session.session_id] = runtime_identity
        self._mark_block_consumer_synced(
            session_id=session_id,
            consumer_key="story.specialist",
        )
        return bundle

    def resolve_graph_thread_binding(self, *, session_id: str) -> dict[str, str]:
        session = self.require_session(session_id)
        branch_head_id = str(session.active_branch_head_id or "").strip()
        default_branch_head_id = self._default_branch_head_id(session_id)
        branch = None
        if self._runtime_identity_service is not None:
            if not branch_head_id or branch_head_id == default_branch_head_id:
                branch = self._runtime_identity_service.ensure_default_branch(
                    session_id=session.session_id,
                    story_id=session.story_id,
                )
            else:
                branch = self._runtime_identity_service.require_branch_head(
                    branch_head_id
                )
                if (
                    branch.session_id != session.session_id
                    or branch.story_id != session.story_id
                ):
                    raise ValueError(
                        f"Runtime branch head mismatch for session {session.session_id}"
                    )
            branch_head_id = branch.branch_head_id
        elif not branch_head_id:
            branch_head_id = default_branch_head_id
        return {
            "branch_head_id": branch_head_id,
            "graph_thread_id": self.build_graph_thread_id(
                session_id=session.session_id,
                branch_head_id=branch_head_id,
            ),
            "visible_turn_head_id": (
                ""
                if branch is None or branch.head_turn_id is None
                else branch.head_turn_id
            ),
            "last_settled_turn_id": (
                ""
                if branch is None or branch.last_settled_turn_id is None
                else branch.last_settled_turn_id
            ),
        }

    def resolve_runtime_entry_identity(
        self,
        *,
        session_id: str,
        command_kind: LongformTurnCommandKind,
        actor: str = "story_runtime",
        requested_branch_head_id: str | None = None,
    ) -> MemoryRuntimeIdentity | None:
        if self._runtime_identity_service is None:
            return None
        return self._runtime_identity_service.resolve_runtime_entry_identity(
            session_id=session_id,
            command_kind=command_kind.value,
            actor=actor,
            requested_branch_head_id=requested_branch_head_id,
        )

    def finalize_runtime_turn(self, *, turn_id: str | None, failed: bool) -> None:
        if self._runtime_identity_service is None:
            return
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_turn_id:
            return
        if not failed:
            turn = self._runtime_identity_service.get_turn(normalized_turn_id)
            if (
                turn is not None
                and turn.status
                in {
                    StoryTurnStatus.POST_WRITE_PENDING.value,
                    StoryTurnStatus.POST_WRITE_RUNNING.value,
                    StoryTurnStatus.POST_WRITE_DEFERRED.value,
                    StoryTurnStatus.SETTLED.value,
                }
            ):
                self._runtime_identity_by_session = {
                    session_id: identity
                    for session_id, identity in self._runtime_identity_by_session.items()
                    if identity.turn_id != normalized_turn_id
                }
                return
        self._runtime_identity_service.update_turn_status(
            turn_id=normalized_turn_id,
            status=StoryTurnStatus.FAILED if failed else StoryTurnStatus.COMPLETED,
        )
        self._runtime_identity_by_session = {
            session_id: identity
            for session_id, identity in self._runtime_identity_by_session.items()
            if identity.turn_id != normalized_turn_id
        }

    def finalize_interrupted_turn(
        self,
        *,
        turn_id: str,
        reason: str = INTERRUPTED_BY_RESTART,
    ) -> None:
        identity_service = self._runtime_identity_service
        if identity_service is None:
            return
        turn = identity_service.get_turn_record(turn_id=turn_id)
        if turn is None:
            return
        if turn.visible_output_ref is not None:
            return
        turn = identity_service.update_turn_status(
            turn_id=turn_id,
            status=StoryTurnStatus.FAILED,
            failure_reason=reason,
        )
        if self._runtime_workflow_job_service is not None:
            identity = MemoryRuntimeIdentity(
                story_id=turn.story_id,
                session_id=turn.session_id,
                branch_head_id=turn.branch_head_id,
                turn_id=turn.turn_id,
                runtime_profile_snapshot_id=turn.runtime_profile_snapshot_id,
            )
            self._runtime_workflow_job_service.mark_required_jobs_failed(
                identity=identity,
                reason=reason,
            )
        identity_service.record_interrupt_receipt(turn_id=turn_id, reason=reason)
        self._story_session_service.commit()

    def list_interrupt_receipts(self, *, turn_id: str):
        if self._runtime_identity_service is None:
            return []
        return self._runtime_identity_service.list_interrupt_receipts(turn_id=turn_id)

    def record_graph_checkpoint_binding(
        self,
        *,
        turn_id: str | None,
        checkpoint_id: str | None,
        parent_checkpoint_id: str | None = None,
        captured_after_node: str = "finalize_turn",
        checkpoint_ns: str = "rp_story",
    ) -> dict:
        if self._runtime_identity_service is None:
            return {"recorded": False, "reason": "runtime_identity_service_missing"}
        normalized_turn_id = str(turn_id or "").strip()
        normalized_checkpoint_id = str(checkpoint_id or "").strip()
        if not normalized_turn_id:
            return {"recorded": False, "reason": "turn_id_missing"}
        if not normalized_checkpoint_id:
            return {"recorded": False, "reason": "checkpoint_id_missing"}
        return self._runtime_identity_service.record_graph_checkpoint_binding(
            turn_id=normalized_turn_id,
            checkpoint_id=normalized_checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            captured_after_node=captured_after_node,
            checkpoint_ns=checkpoint_ns,
        )

    def build_packet(
        self,
        *,
        session_id: str,
        plan: OrchestratorPlan,
        specialist_bundle: SpecialistResultBundle,
        command_kind: LongformTurnCommandKind | None = None,
        runtime_identity: MemoryRuntimeIdentity | None = None,
        target_artifact_id: str | None = None,
    ) -> WritingPacket:
        session = self.require_session(session_id)
        chapter = self.require_active_branch_current_chapter(session_id)
        resolved_runtime_identity = (
            runtime_identity or self._runtime_identity_by_session.get(session_id)
        )
        # S6-4 (REV-024): rewrite is a light local edit; the review-overlay heavy
        # chain is bypassed here, so no overlay sections are assembled and the
        # downstream packet degrades to a no-active-constraints rewrite packet.
        review_overlay_sections: list[dict[str, object]] | None = None
        packet = self._context_orchestration_service.build_writing_packet(
            session=session,
            chapter=chapter,
            plan=plan,
            specialist_bundle=specialist_bundle,
            operation_mode=self._resolve_writing_operation_mode(
                command_kind=command_kind,
                plan=plan,
            ),
            command_kind=command_kind,
            runtime_identity=resolved_runtime_identity,
            target_artifact_id=target_artifact_id,
            review_overlay_sections=review_overlay_sections,
        )
        if (
            resolved_runtime_identity is not None
            and self._runtime_workspace_facade is not None
        ):
            surface_refs = self._runtime_workspace_facade.record_writer_packet_surface(
                identity=resolved_runtime_identity,
                packet=packet,
            )
            packet = packet.model_copy(
                update={
                    "metadata": {
                        **dict(packet.metadata),
                        "runtime_workspace_writer_input_material_id": (
                            surface_refs.writer_input_material_id
                        ),
                        "runtime_workspace_packet_material_id": (
                            surface_refs.packet_material_id
                        ),
                    }
                }
            )
        self._mark_block_consumer_synced(
            session_id=session_id, consumer_key="story.writer_packet"
        )
        return packet

    async def writer_run(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> WritingWorkerExecutionResult:
        runtime_identity = self._packet_runtime_identity(packet)
        request = WritingWorkerExecutionRequest(
            request_id=f"writer-exec:{uuid4().hex}",
            identity=runtime_identity,
            operation_mode=packet.operation_mode,
            packet_ref=_optional_text(
                packet.metadata.get("runtime_workspace_packet_material_id")
            ),
            packet=packet,
            writer_model_id=model_id,
            writer_provider_id=provider_id,
            retrieval_allowed=self._packet_writer_retrieval_allowed(packet=packet),
            max_retrieval_attempts=self._packet_writer_max_retrieval_attempts(
                packet=packet
            ),
        )
        return await self._writing_worker_execution_service.execute(
            request=request,
        )

    def writer_stream_requires_buffered_execution(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> bool:
        return self._writing_worker_execution_service.should_buffer_stream(
            packet=packet,
            model_id=model_id,
            provider_id=provider_id,
        )

    async def writer_run_stream(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> AsyncIterator[str]:
        async for line in self._writing_worker_execution_service.run_stream(
            packet=packet,
            model_id=model_id,
            provider_id=provider_id,
        ):
            yield line

    def build_stream_writing_result(
        self,
        *,
        packet: WritingPacket,
        text: str,
        usage_metadata: dict[str, object] | None = None,
    ) -> WritingWorkerExecutionResult:
        return WritingWorkerExecutionResult(
            request_id=f"writer-stream:{packet.packet_id}",
            packet_id=packet.packet_id,
            turn_id=packet.turn_id,
            operation_mode=packet.operation_mode,
            output_text=text,
            output_kind=packet.output_kind,
            usage_metadata=dict(usage_metadata or {}),
            result_status="completed",
        )

    async def trigger_post_write(
        self,
        *,
        runtime_identity: MemoryRuntimeIdentity | None,
        model_id: str | None = None,
        provider_id: str | None = None,
        user_prompt: str | None = None,
        orchestrator_plan: OrchestratorPlan | None = None,
    ) -> dict[str, object]:
        if runtime_identity is None:
            return {"run_kind": "skipped", "reason": "runtime_identity_missing"}
        if self._runtime_workflow_job_service is None:
            return {"run_kind": "skipped", "reason": "workflow_job_service_missing"}
        if self._runtime_identity_service is None:
            return {"run_kind": "skipped", "reason": "runtime_identity_service_missing"}
        turn = self._runtime_identity_service.get_turn(runtime_identity.turn_id)
        if turn is None:
            return {"run_kind": "skipped", "reason": "turn_missing"}
        if turn.status not in _POST_WRITE_TRIGGER_READY_STATUSES:
            return {
                "run_kind": "skipped",
                "reason": "writer_output_not_finalized",
                "turn_status": turn.status,
            }
        jobs = self._runtime_workflow_job_service.ensure_creation_time_obligations(
            identity=runtime_identity,
            metadata={"triggered_by": "story_graph.post_write"},
        )
        if self._runtime_workflow_job_service.all_required_jobs_terminal(
            turn_id=runtime_identity.turn_id
        ):
            settlement = self._settle_turn_if_ready(identity=runtime_identity)
            existing_jobs = self._runtime_workflow_job_service.list_jobs_for_turn(
                turn_id=runtime_identity.turn_id
            )
            run_kind = (
                PostWriteRunKind.FULL_SCHEDULE
                if any(job.creation_mode == "derived" for job in existing_jobs)
                else PostWriteRunKind.MINIMAL_ONLY
            )
            return PostWriteExecutionEnvelope(
                turn_id=runtime_identity.turn_id,
                identity=runtime_identity,
                run_kind=run_kind,
                settled=settlement.eligible,
                settlement_reason=settlement.settlement_reason,
                metadata_json={
                    "job_ids": [job.job_id for job in jobs],
                    "idempotent_terminal_replay": True,
                },
            ).model_dump(mode="json")
        if (
            self._post_write_scheduler_service is None
            or self._worker_execution_service is None
            or self._post_write_governance_service is None
        ):
            return self._run_minimal_post_write(
                identity=runtime_identity,
                jobs=jobs,
                reason="post_write_full_schedule_services_missing",
                trigger_context_payload={},
            )

        session = self.require_session(runtime_identity.session_id)
        chapter = self.require_active_branch_current_chapter(
            runtime_identity.session_id
        )
        trigger_context = self._post_write_scheduler_service.build_trigger_context(
            identity=runtime_identity,
            turn=turn,
            mode=session.mode,
        )
        if not self._post_write_scheduler_service.should_run_full_schedule(
            trigger_context
        ):
            return self._run_minimal_post_write(
                identity=runtime_identity,
                jobs=jobs,
                reason="post_write_full_schedule_not_triggered",
                trigger_context_payload=trigger_context.model_dump(mode="json"),
            )
        if self._branch_maintenance_active_excluding_turn(identity=runtime_identity):
            # REV-006 rev2: another maintenance run holds the branch — this user turn
            # completes normally, maintenance defers (minimal) rather than double-running.
            return self._run_minimal_post_write(
                identity=runtime_identity,
                jobs=jobs,
                reason=SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value,
                trigger_context_payload=trigger_context.model_dump(mode="json"),
            )
        self._runtime_identity_service.update_turn_status(
            turn_id=runtime_identity.turn_id,
            status=StoryTurnStatus.POST_WRITE_RUNNING,
        )
        proposal = None
        if self._orchestrator_dispatch_provider is not None:
            proposal = self._orchestrator_dispatch_provider.propose(
                identity=runtime_identity,
                phase=POST_WRITE_MAINTENANCE_PHASE,
                turn=turn,
                trigger_context=trigger_context,
            )
        try:
            worker_plan = self._post_write_scheduler_service.build_worker_plan(
                identity=runtime_identity,
                proposal=proposal,
            )
        except SchedulerDecisionError as exc:
            return self._run_minimal_post_write(
                identity=runtime_identity,
                jobs=jobs,
                reason=exc.message,
                trigger_context_payload=trigger_context.model_dump(mode="json"),
            )
        gate_job = None
        if worker_plan.plan_source == WorkerPlanSource.ORCHESTRATOR:
            try:
                # Stable per-turn fingerprint (NUM-016 idempotent replay key). turn_id
                # is the correct window granularity ONLY for the single-maintenance-per-turn
                # W5-A case; a later K-window/multi-gate slice must add a window/source
                # discriminator here AND in _job_idempotency_key (deferred debt).
                gate_job = (
                    self._runtime_workflow_job_service.ensure_scheduler_maintenance_gate(
                        identity=runtime_identity,
                        scheduler_job_id=f"scheduler_maintenance:{runtime_identity.turn_id}",
                        anchor_turn_id=runtime_identity.turn_id,
                        metadata={
                            "phase": POST_WRITE_MAINTENANCE_PHASE,
                            "worker_plan_id": worker_plan.plan_id,
                        },
                    )
                )
            except RuntimeWorkflowJobServiceError as exc:
                if exc.code == SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value:
                    return self._run_minimal_post_write(
                        identity=runtime_identity,
                        jobs=jobs,
                        reason=exc.code,
                        trigger_context_payload=trigger_context.model_dump(mode="json"),
                    )
                raise
        command_kind = self._coerce_turn_command_kind(turn.command_kind)
        frozen_accepted_segments = self._resolve_accepted_segment_snapshot(
            snapshot=next(
                (
                    job.metadata_json.get("accepted_segment_snapshot")
                    for job in jobs
                    if isinstance(job.metadata_json, dict)
                    and job.metadata_json.get("accepted_segment_snapshot") is not None
                ),
                None,
            ),
        )
        execution = await self._worker_execution_service.execute_plan(
            session=session,
            chapter=chapter,
            plan=worker_plan,
            command_kind=command_kind,
            model_id=str(model_id or "post_write_maintenance"),
            provider_id=provider_id,
            user_prompt=user_prompt,
            orchestrator_plan=(
                orchestrator_plan
                or self._fallback_post_write_orchestrator_plan(command_kind)
            ),
            accepted_segments=(
                frozen_accepted_segments
                if frozen_accepted_segments is not None
                else self.accepted_segments(chapter)
            ),
            pending_artifact=self.resolve_pending_artifact(
                chapter=chapter,
                target_artifact_id=None,
            ),
        )
        dispatch_result = (
            await self._post_write_governance_service.dispatch_worker_results(
                identity=runtime_identity,
                session=session,
                chapter=chapter,
                worker_plan=worker_plan,
                worker_results=list(execution.worker_results),
                specialist_bundle=execution.specialist_bundle,
            )
        )
        if gate_job is not None:
            self._runtime_workflow_job_service.mark_job_completed(
                job_id=gate_job.job_id,
                reason="post_write_full_schedule_completed",
                metadata={"worker_plan_id": worker_plan.plan_id},
            )
        completed_obligations = (
            self._runtime_workflow_job_service.mark_required_jobs_completed(
                identity=runtime_identity,
                reason="post_write_full_schedule_completed",
                metadata={
                    "worker_plan_id": worker_plan.plan_id,
                    "worker_result_count": len(execution.worker_results),
                },
            )
        )
        settlement = self._settle_turn_if_ready(identity=runtime_identity)
        return PostWriteExecutionEnvelope(
            turn_id=runtime_identity.turn_id,
            identity=runtime_identity,
            run_kind=PostWriteRunKind.FULL_SCHEDULE,
            worker_plan_ref=f"worker_plan:{worker_plan.plan_id}",
            selected_worker_result_refs=dispatch_result.selected_worker_result_refs,
            projection_refresh_job_refs=dispatch_result.projection_refresh_job_refs,
            proposal_job_refs=dispatch_result.proposal_job_refs,
            materialization_job_refs=dispatch_result.materialization_job_refs,
            trace_refs=dispatch_result.trace_refs,
            settled=settlement.eligible,
            settlement_reason=settlement.settlement_reason,
            metadata_json={
                "job_ids": [job.job_id for job in jobs],
                "completed_obligation_job_ids": [
                    job.job_id for job in completed_obligations
                ],
                "trigger_context": trigger_context.model_dump(mode="json"),
                "worker_plan": worker_plan.model_dump(mode="json"),
                "dispatch": dispatch_result.model_dump(mode="json"),
            },
        ).model_dump(mode="json")

    def _run_minimal_post_write(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        jobs: list[RuntimeWorkflowJobRecord],
        reason: str,
        trigger_context_payload: dict[str, object],
    ) -> dict[str, object]:
        workflow_job_service = self._runtime_workflow_job_service
        runtime_identity_service = self._runtime_identity_service
        if workflow_job_service is None or runtime_identity_service is None:
            return {"run_kind": "skipped", "reason": "post_write_services_missing"}
        runtime_identity_service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.POST_WRITE_DEFERRED,
        )
        deferred_jobs = workflow_job_service.mark_required_jobs_deferred(
            identity=identity,
            reason=reason,
            metadata={
                "post_write_run_kind": PostWriteRunKind.MINIMAL_ONLY.value,
                "trigger_context": trigger_context_payload,
            },
        )
        settlement = self._settle_turn_if_ready(identity=identity)
        return PostWriteExecutionEnvelope(
            turn_id=identity.turn_id,
            identity=identity,
            run_kind=PostWriteRunKind.MINIMAL_ONLY,
            settled=settlement.eligible,
            settlement_reason=settlement.settlement_reason,
            metadata_json={
                "job_ids": [job.job_id for job in jobs],
                "deferred_job_ids": [job.job_id for job in deferred_jobs],
                "deferred_reason": reason,
                "trigger_context": trigger_context_payload,
            },
        ).model_dump(mode="json")

    def _settle_turn_if_ready(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> TurnSettlementEvaluation:
        workflow_job_service = self._runtime_workflow_job_service
        runtime_identity_service = self._runtime_identity_service
        if workflow_job_service is None:
            return TurnSettlementEvaluation(
                eligible=False,
                settlement_reason=None,
                required_job_ids=(),
                blocking_job_ids=(),
            )
        settlement = workflow_job_service.evaluate_turn_settlement(
            turn_id=identity.turn_id,
        )
        if settlement.eligible and runtime_identity_service is not None:
            runtime_identity_service.update_turn_status(
                turn_id=identity.turn_id,
                status=StoryTurnStatus.SETTLED,
                settlement_reason=settlement.settlement_reason,
            )
        return settlement

    def _coerce_turn_command_kind(self, command_kind: str) -> LongformTurnCommandKind:
        return self._story_runtime_adapter_service.coerce_legacy_command_kind(
            command_kind
        )

    def _fallback_post_write_orchestrator_plan(
        self,
        command_kind: LongformTurnCommandKind,
    ) -> OrchestratorPlan:
        return self._story_runtime_adapter_service.build_legacy_post_write_plan(
            command_kind=command_kind
        )

    def persist_generated_artifact(
        self,
        *,
        request: LongformTurnRequest,
        packet: WritingPacket,
        plan: OrchestratorPlan,
        text: str | None = None,
        writing_result: WritingWorkerExecutionResult | None = None,
        specialist_bundle: SpecialistResultBundle,
        pending_artifact_id: str | None,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_active_branch_current_chapter(request.session_id)
        pending_artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=pending_artifact_id,
        )
        try:
            artifact, next_chapter, finalized_result = (
                self._persist_generated_artifact_impl(
                    session=session,
                    chapter=chapter,
                    request=request,
                    packet=packet,
                    plan=plan,
                    writing_result=self._coerce_writing_result(
                        packet=packet,
                        writing_result=writing_result,
                        fallback_text=text,
                    ),
                    pending_artifact=pending_artifact,
                    specialist_bundle=specialist_bundle,
                )
            )
        except WriterFinalizationRejected as exc:
            self._terminalize_rejected_finalization(
                packet=packet,
                reason_code=exc.reason_code,
            )
            raise
        return LongformTurnResponse(
            session_id=session.session_id,
            chapter_workspace_id=next_chapter.chapter_workspace_id,
            command_kind=request.command_kind,
            current_chapter_index=next_chapter.chapter_index,
            current_phase=next_chapter.phase,
            assistant_text=finalized_result.output_text,
            artifact_id=artifact.artifact_id,
            artifact_kind=artifact.artifact_kind,
            writing_result=finalized_result,
            warnings=list(specialist_bundle.validation_findings),
        )

    def _terminalize_rejected_finalization(
        self,
        *,
        packet: WritingPacket,
        reason_code: str,
    ) -> None:
        """Roll back the staged writer-output writes for a gate-rejected turn and
        terminalize it as FAILED, committing only that flip (R1/F4 ordering)."""

        # F4: rollback FIRST so none of the staged writer-output writes (artifact,
        # obligations, surface, ledger, chapter, pre-visibility status) survive...
        self._story_session_service.rollback()
        identity = self._packet_runtime_identity(packet)
        if identity is None or self._runtime_identity_service is None:
            return
        # ...THEN flip the turn to FAILED, THEN commit ONLY that flip.
        self._runtime_identity_service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.FAILED,
            failure_reason=reason_code,
        )
        self._story_session_service.commit()

    def accept_outline(
        self,
        *,
        request: LongformTurnRequest,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_active_branch_current_chapter(request.session_id)
        artifact = self.resolve_outline_artifact(
            chapter=chapter,
            target_artifact_id=request.target_artifact_id,
        )
        if artifact is None:
            raise ValueError("No draft outline available to accept")
        warnings: list[str] = []
        accepted_artifact = artifact
        if self._longform_chapter_runtime_service is not None:
            (
                normalized_text,
                normalized_metadata,
                normalization_warnings,
            ) = self._longform_chapter_runtime_service.normalize_outline_artifact(
                chapter=chapter,
                artifact=artifact,
            )
            accepted_artifact = self._story_session_service.update_artifact(
                artifact_id=artifact.artifact_id,
                status=StoryArtifactStatus.ACCEPTED,
                content_text=normalized_text,
                metadata=normalized_metadata,
            )
            warnings.extend(normalization_warnings)
        else:
            accepted_artifact = self._story_session_service.update_artifact(
                artifact_id=artifact.artifact_id,
                status=StoryArtifactStatus.ACCEPTED,
            )
        next_phase = LongformChapterPhase.SEGMENT_DRAFTING
        accepted_outline_payload = (
            self._longform_chapter_runtime_service.build_outline_payload(
                artifact=accepted_artifact,
                metadata=accepted_artifact.metadata,
            )
            if self._longform_chapter_runtime_service is not None
            else {
                "artifact_id": accepted_artifact.artifact_id,
                "content_text": accepted_artifact.content_text,
                "metadata": accepted_artifact.metadata,
            }
        )
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=next_phase,
            outline_draft_json=chapter.outline_draft_json
            or {
                "artifact_id": accepted_artifact.artifact_id,
                "content_text": accepted_artifact.content_text,
                "metadata": accepted_artifact.metadata,
            },
            accepted_outline_json=accepted_outline_payload,
        )
        self._story_session_service.update_session(
            session_id=session.session_id,
            current_phase=next_phase,
        )
        self._projection_state_service.set_current_outline(
            chapter_workspace_id=chapter.chapter_workspace_id,
            outline_text=accepted_artifact.content_text,
        )
        if self._longform_chapter_runtime_service is not None:
            updated_chapter = self.require_active_branch_current_chapter(
                request.session_id
            )
            self._longform_chapter_runtime_service.initialize_outline_progress(
                identity=runtime_identity,
                chapter=updated_chapter,
                accepted_outline_json=accepted_outline_payload,
            )
        self._story_session_service.commit()
        return LongformTurnResponse(
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            command_kind=request.command_kind,
            current_chapter_index=chapter.chapter_index,
            current_phase=next_phase,
            assistant_text="Accepted outline. Ready to draft the next segment.",
            artifact_id=accepted_artifact.artifact_id,
            artifact_kind=accepted_artifact.artifact_kind,
            warnings=warnings,
        )

    async def accept_pending_segment(
        self,
        *,
        request: LongformTurnRequest,
        runtime_identity: MemoryRuntimeIdentity | None = None,
        readopt: bool = False,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        if readopt:
            chapter = self._require_readopt_chapter(
                session_id=request.session_id,
                target_artifact_id=request.target_artifact_id,
            )
        else:
            chapter = self.require_active_branch_current_chapter(request.session_id)
        is_completed_chapter = chapter.phase == LongformChapterPhase.CHAPTER_COMPLETED
        artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=request.target_artifact_id,
        )
        if artifact is None:
            raise ValueError("No pending segment available to accept")
        accepted_metadata = self._accepted_story_segment_metadata(
            artifact=artifact,
            patch=request.story_segment_metadata_patch,
        )
        if readopt:
            # REV-025 re-adopt: supersede the same-scene old ACCEPTED revision BEFORE
            # the beat precheck so the covered-beat recompute frees the target beat
            # (ordering is load-bearing); record re-adopt provenance on the artifact.
            self._supersede_reopen_source_segment(
                chapter=chapter,
                new_artifact=artifact,
            )
            accepted_metadata["readopt_source"] = (
                str(dict(artifact.metadata or {}).get("reopen_source_artifact_id") or "")
                or "manual_reopen"
            )
        if self._longform_chapter_runtime_service is not None:
            progress_before = self._longform_chapter_runtime_service.effective_outline_progress(
                chapter=chapter,
                identity=runtime_identity,
            )
            target_beat_id = str(accepted_metadata.get("target_beat_id") or "").strip()
            if (
                progress_before is not None
                and not target_beat_id
                and progress_before.current_beat_id is not None
            ):
                target_beat_id = progress_before.current_beat_id
                accepted_metadata["target_beat_id"] = target_beat_id
            current_beat_id = (
                None if progress_before is None else progress_before.current_beat_id
            )
            if current_beat_id and target_beat_id and current_beat_id != target_beat_id:
                raise LongformChapterRuntimeServiceError(
                    "longform_outline_progress_target_beat_mismatch",
                    f"{current_beat_id}:{target_beat_id}",
                )
        accepted = self._story_session_service.update_artifact(
            artifact_id=artifact.artifact_id,
            status=StoryArtifactStatus.ACCEPTED,
            metadata=accepted_metadata,
        )
        if (
            self._longform_chapter_runtime_service is not None
            and runtime_identity is not None
        ):
            # REV-023: marking ACCEPTED and authoring the adoption receipt are one
            # action on the single 甲套 write gate (atomic before the commit below).
            self._longform_chapter_runtime_service.record_accept_pending_segment_adoption_receipt(
                identity=runtime_identity,
                accepted_artifact_id=accepted.artifact_id,
            )
        visible_artifact_ids = {
            item.artifact_id
            for item in self._story_session_service.build_chapter_snapshot(
                session_id=session.session_id,
                chapter_index=chapter.chapter_index,
            ).artifacts
        }
        for candidate in self._story_session_service.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        ):
            if candidate.artifact_id == accepted.artifact_id:
                continue
            if candidate.artifact_id not in visible_artifact_ids:
                continue
            if candidate.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
                continue
            if candidate.status != StoryArtifactStatus.DRAFT:
                continue
            self._story_session_service.update_artifact(
                artifact_id=candidate.artifact_id,
                status=StoryArtifactStatus.SUPERSEDED,
            )
        self._bind_accepted_artifact_to_origin_turn_if_visible(
            session=session,
            accepted_artifact=accepted,
        )
        self._settle_accepted_artifact_origin_turn(
            session=session,
            accepted_artifact=accepted,
        )
        accepted_segment_ids = [
            item.artifact_id
            for item in self._story_session_service.active_branch_accepted_story_segments(
                session_id=session.session_id,
                chapter_index=chapter.chapter_index,
            )
        ]
        updated_chapter = self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=(
                chapter.phase
                if is_completed_chapter
                else LongformChapterPhase.SEGMENT_DRAFTING
            ),
            pending_segment_artifact_id=None,
        ).model_copy(
            update={"accepted_segment_ids": accepted_segment_ids}
        )
        if self._longform_chapter_runtime_service is not None:
            self._longform_chapter_runtime_service.advance_outline_progress_for_adoption(
                identity=runtime_identity,
                chapter_before_accept=chapter,
                chapter_after_accept=updated_chapter,
                accepted_artifact=accepted,
            )
        updated_session = session
        if not is_completed_chapter:
            # REV-025: a completed-chapter re-adopt keeps CHAPTER_COMPLETED, leaves
            # session.current_phase untouched, and skips the light-regression /
            # transcript maintenance tail (manual memory catch-up per裁定 D).
            updated_session = self._story_session_service.update_session(
                session_id=session.session_id,
                current_phase=LongformChapterPhase.SEGMENT_DRAFTING,
            )
            (
                updated_session,
                updated_chapter,
            ) = await self._regression_service.run_light_regression(
                session=updated_session,
                chapter=updated_chapter,
                accepted_artifact=accepted,
                model_id=request.model_id,
                provider_id=request.provider_id,
                runtime_identity=runtime_identity,
            )
            self._materialize_closed_scene_transcript_if_needed(
                session=updated_session,
                chapter=updated_chapter,
                scene_ref=accepted.scene_ref,
                runtime_identity=runtime_identity,
                source_refs=self._runtime_turn_source_refs(
                    identity=runtime_identity,
                    session_id=session.session_id,
                    chapter_index=chapter.chapter_index,
                ),
            )
        self._story_session_service.commit()
        return LongformTurnResponse(
            session_id=session.session_id,
            chapter_workspace_id=updated_chapter.chapter_workspace_id,
            command_kind=request.command_kind,
            current_chapter_index=updated_chapter.chapter_index,
            current_phase=updated_chapter.phase,
            assistant_text="Accepted segment and refreshed chapter runtime state.",
            artifact_id=accepted.artifact_id,
            artifact_kind=accepted.artifact_kind,
        )

    async def reopen_accepted_segment(
        self,
        *,
        session_id: str,
        artifact_id: str,
    ) -> ChapterWorkspaceSnapshot:
        """REV-025 re-open: mint an editable revision+1 DRAFT from an ACCEPTED segment.

        A completed chapter keeps CHAPTER_COMPLETED (no maintenance re-fire); an active
        chapter moves to SEGMENT_REVIEW to block WRITE_NEXT until re-adoption. Single
        pending slot: a re-open is rejected while a pending draft already exists.
        """
        session = self.require_session(session_id)
        source = self._story_session_service.get_artifact(artifact_id)
        if source is None:
            raise ValueError(f"StoryArtifact not found: {artifact_id}")
        if source.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
            raise ValueError(f"segment_reopen_kind_invalid:{artifact_id}")
        if source.status != StoryArtifactStatus.ACCEPTED:
            raise ValueError(f"segment_reopen_status_invalid:{artifact_id}")
        chapter = self._story_session_service.get_chapter_workspace(
            source.chapter_workspace_id
        )
        if chapter is None:
            raise ValueError(f"Current ChapterWorkspace not found: {session_id}")
        if chapter.pending_segment_artifact_id:
            raise ValueError(
                f"segment_reopen_pending_exists:{chapter.pending_segment_artifact_id}"
            )
        reopen_metadata: dict[str, object] = {
            key: value
            for key, value in dict(source.metadata or {}).items()
            if key in self._REOPEN_COPIED_METADATA_KEYS
        }
        reopen_metadata["manual_reopen"] = True
        reopen_metadata["reopen_source_artifact_id"] = source.artifact_id
        draft = self._story_session_service.create_artifact(
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            artifact_kind=StoryArtifactKind.STORY_SEGMENT,
            status=StoryArtifactStatus.DRAFT,
            content_text=source.content_text,
            metadata=reopen_metadata,
            revision=source.revision + 1,
            scene_ref=source.scene_ref,
        )
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=(
                chapter.phase
                if chapter.phase == LongformChapterPhase.CHAPTER_COMPLETED
                else LongformChapterPhase.SEGMENT_REVIEW
            ),
            pending_segment_artifact_id=draft.artifact_id,
        )
        self._story_session_service.commit()
        return self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=chapter.chapter_index,
        )

    async def re_adopt_pending_segment(
        self,
        *,
        session_id: str,
        target_artifact_id: str | None = None,
        model_id: str | None = None,
        provider_id: str | None = None,
    ) -> ChapterWorkspaceSnapshot:
        """REV-023/REV-025 re-adopt: run the reopened draft through the single accept
        gate. The origin-turn identity is derived from metadata copied at re-open."""
        self.require_session(session_id)
        pending = self._resolve_readopt_pending_artifact(
            session_id=session_id,
            target_artifact_id=target_artifact_id,
        )
        runtime_identity = self._readopt_identity_from_artifact(pending)
        await self.accept_pending_segment(
            request=LongformTurnRequest(
                session_id=session_id,
                command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
                model_id=str(model_id or "segment_readopt"),
                provider_id=provider_id,
                target_artifact_id=pending.artifact_id,
            ),
            runtime_identity=runtime_identity,
            readopt=True,
        )
        chapter = self._story_session_service.get_chapter_workspace(
            pending.chapter_workspace_id
        )
        chapter_index = (
            chapter.chapter_index
            if chapter is not None
            else self.require_session(session_id).current_chapter_index
        )
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=chapter_index,
        )

    def cancel_reopen(
        self,
        *,
        session_id: str,
        target_artifact_id: str | None = None,
    ) -> ChapterWorkspaceSnapshot:
        """A2: discard a reopened pending draft without re-adopting it.

        Supersedes the discarded draft, clears the pending slot, and restores an
        active chapter to SEGMENT_DRAFTING; a completed chapter only clears the slot.
        Only reopened drafts (``manual_reopen``) are cancellable here.
        """
        session = self.require_session(session_id)
        pending = self._resolve_readopt_pending_artifact(
            session_id=session_id,
            target_artifact_id=target_artifact_id,
        )
        if not dict(pending.metadata or {}).get("manual_reopen"):
            raise ValueError(f"segment_reopen_cancel_not_reopened:{pending.artifact_id}")
        chapter = self._story_session_service.get_chapter_workspace(
            pending.chapter_workspace_id
        )
        if chapter is None:
            raise ValueError(f"Current ChapterWorkspace not found: {session_id}")
        if chapter.pending_segment_artifact_id != pending.artifact_id:
            raise ValueError(
                f"segment_reopen_cancel_not_pending:{pending.artifact_id}"
            )
        self._story_session_service.update_artifact(
            artifact_id=pending.artifact_id,
            status=StoryArtifactStatus.SUPERSEDED,
        )
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=(
                chapter.phase
                if chapter.phase == LongformChapterPhase.CHAPTER_COMPLETED
                else LongformChapterPhase.SEGMENT_DRAFTING
            ),
            pending_segment_artifact_id=None,
        )
        self._story_session_service.commit()
        return self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=chapter.chapter_index,
        )

    def _require_readopt_chapter(
        self,
        *,
        session_id: str,
        target_artifact_id: str | None,
    ) -> ChapterWorkspace:
        artifact_id = str(target_artifact_id or "").strip()
        if not artifact_id:
            raise ValueError("No pending segment available to accept")
        artifact = self._story_session_service.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"StoryArtifact not found: {artifact_id}")
        chapter = self._story_session_service.get_chapter_workspace(
            artifact.chapter_workspace_id
        )
        if chapter is None:
            raise ValueError(f"Current ChapterWorkspace not found: {session_id}")
        return chapter

    def _resolve_readopt_pending_artifact(
        self,
        *,
        session_id: str,
        target_artifact_id: str | None,
    ) -> StoryArtifact:
        artifact_id = str(target_artifact_id or "").strip()
        if not artifact_id:
            chapter = self.require_active_branch_current_chapter(session_id)
            artifact_id = str(chapter.pending_segment_artifact_id or "").strip()
        if not artifact_id:
            raise ValueError("No pending segment available to accept")
        artifact = self._story_session_service.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"StoryArtifact not found: {artifact_id}")
        return artifact

    def _supersede_reopen_source_segment(
        self,
        *,
        chapter: ChapterWorkspace,
        new_artifact: StoryArtifact,
    ) -> None:
        source_id = str(
            dict(new_artifact.metadata or {}).get("reopen_source_artifact_id") or ""
        ).strip()
        if not source_id:
            return
        source = self._story_session_service.get_artifact(source_id)
        if source is None or source.status != StoryArtifactStatus.ACCEPTED:
            return
        self._story_session_service.update_artifact(
            artifact_id=source_id,
            status=StoryArtifactStatus.SUPERSEDED,
        )

    @staticmethod
    def _readopt_identity_from_artifact(
        artifact: StoryArtifact,
    ) -> MemoryRuntimeIdentity:
        metadata = dict(artifact.metadata or {})
        story_id = str(metadata.get("runtime_story_id") or "").strip()
        session_id = str(metadata.get("runtime_session_id") or "").strip()
        branch_head_id = str(metadata.get("runtime_branch_head_id") or "").strip()
        turn_id = str(metadata.get("runtime_turn_id") or "").strip()
        snapshot_id = str(metadata.get("runtime_profile_snapshot_id") or "").strip()
        if not (story_id and session_id and branch_head_id and turn_id and snapshot_id):
            raise ValueError(
                f"segment_readopt_origin_identity_missing:{artifact.artifact_id}"
            )
        return MemoryRuntimeIdentity(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            runtime_profile_snapshot_id=snapshot_id,
        )

    async def complete_chapter(
        self,
        *,
        request: LongformTurnRequest,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_active_branch_current_chapter(request.session_id)
        resolved_transition: ResolvedChapterTransition | None = None
        if self._longform_chapter_runtime_service is not None:
            # Fail-closed input gate (A-QB-02): an un-adopted pending draft raises
            # ``longform_chapter_adoption_required`` here, BEFORE any job is created.
            # Only the deterministic chapter mutation runs pre-graph; the writer-role
            # summary + bridge are driven INSIDE JOB A (``_run_chapter_close_summary``).
            resolved_transition = (
                self._longform_chapter_runtime_service.resolve_chapter_transition_state(
                    identity=runtime_identity,
                    chapter=chapter,
                )
            )
            if resolved_transition is not None:
                chapter = resolved_transition.chapter
        await self._run_chapter_close_job_graph(
            identity=runtime_identity,
            session=session,
            chapter=chapter,
            resolved=resolved_transition,
            request=request,
        )
        closed_scene_refs = list(chapter.closed_scene_refs)
        last_closed_scene_ref = chapter.last_closed_scene_ref
        if chapter.current_scene_ref:
            last_closed_scene_ref = chapter.current_scene_ref
            if last_closed_scene_ref not in closed_scene_refs:
                closed_scene_refs.append(last_closed_scene_ref)
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=LongformChapterPhase.CHAPTER_COMPLETED,
            current_scene_ref=None,
            last_closed_scene_ref=last_closed_scene_ref,
            closed_scene_refs=closed_scene_refs,
        )
        next_chapter_index = chapter.chapter_index + 1
        next_chapter = self._story_session_service.create_chapter_workspace(
            session_id=session.session_id,
            chapter_index=next_chapter_index,
            phase=LongformChapterPhase.OUTLINE_DRAFTING,
            chapter_goal=f"Chapter {next_chapter_index}",
        )
        self._projection_state_service.seed_next_chapter(
            previous_chapter_workspace_id=chapter.chapter_workspace_id,
            next_chapter_workspace_id=next_chapter.chapter_workspace_id,
            next_chapter_index=next_chapter_index,
        )
        self._story_session_service.update_session(
            session_id=session.session_id,
            current_chapter_index=next_chapter_index,
            current_phase=LongformChapterPhase.OUTLINE_DRAFTING,
        )
        self._story_session_service.commit()
        return LongformTurnResponse(
            session_id=session.session_id,
            chapter_workspace_id=next_chapter.chapter_workspace_id,
            command_kind=request.command_kind,
            current_chapter_index=next_chapter_index,
            current_phase=LongformChapterPhase.OUTLINE_DRAFTING,
            assistant_text=(
                f"Chapter {chapter.chapter_index} completed. "
                f"Chapter {next_chapter_index} is ready for outline drafting."
            ),
        )

    async def _run_chapter_close_job_graph(
        self,
        *,
        identity: MemoryRuntimeIdentity | None,
        session: StorySession,
        chapter: ChapterWorkspace,
        resolved: ResolvedChapterTransition | None,
        request: LongformTurnRequest,
    ) -> None:
        """Register and drive the AUTH-013 chapter-close job graph on the close turn.

        JOB A (chapter summary) ∥ JOB B (tail-flush Core maintenance) + JOB G
        (scheduler maintenance gate); each terminalized INDIVIDUALLY by its own
        outcome (never the batch helper), then settlement is re-evaluated so the
        turn settles only when A, B, G are all terminal (TURN-004). The
        deterministic chapter-state transition runs afterwards in ``complete_chapter``.
        """

        workflow_job_service = self._runtime_workflow_job_service
        identity_service = self._runtime_identity_service
        if identity is None or workflow_job_service is None or identity_service is None:
            return
        turn = identity_service.get_turn(identity.turn_id)
        if turn is None:
            return
        anchor_turn_id = self._chapter_close_anchor_turn_id(chapter=chapter)
        accepted_segment_snapshot = self._freeze_accepted_segment_snapshot(
            chapter=chapter,
            captured_turn_id=identity.turn_id,
        )
        job_a = workflow_job_service.ensure_job(
            identity=identity,
            job_kind=RuntimeWorkflowJobKind.REQUIRED_POST_WRITE_ANALYSIS,
            job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
            creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
            required_for_turn_completion=True,
            anchor_turn_id=anchor_turn_id,
            metadata={
                "chapter_close_slot": "chapter_summary",
                "command_kind": LongformTurnCommandKind.COMPLETE_CHAPTER.value,
                "accepted_segment_snapshot": accepted_segment_snapshot,
            },
        )
        job_b = workflow_job_service.ensure_job(
            identity=identity,
            job_kind=RuntimeWorkflowJobKind.RUNTIME_WORKSPACE_FINALIZE,
            job_category=RuntimeWorkflowJobCategory.TURN_FINALIZATION,
            creation_mode=RuntimeWorkflowJobCreationMode.CREATION_TIME_OBLIGATION,
            required_for_turn_completion=True,
            anchor_turn_id=anchor_turn_id,
            metadata={
                "chapter_close_slot": "tail_flush",
                "command_kind": LongformTurnCommandKind.COMPLETE_CHAPTER.value,
                "accepted_segment_snapshot": accepted_segment_snapshot,
            },
        )
        gate_job = workflow_job_service.ensure_scheduler_maintenance_gate(
            identity=identity,
            scheduler_job_id=f"chapter_close:{identity.turn_id}",
            anchor_turn_id=identity.turn_id,
            metadata={"phase": "chapter_close"},
        )
        identity_service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.POST_WRITE_RUNNING,
        )
        # JOB A: the chapter summary is EXECUTED BY THE WRITER ROLE inside this job's
        # lifecycle (``_run_chapter_close_summary``), then the branch-scoped bridge is
        # materialized after it (bridge-after-summary). JOB A terminalizes on that real
        # writer outcome — per-job (never the batch helper): completed (+ bridge id) on
        # success, failed on a writer-role failure (settlement then stays blocked).
        summary_outcome = await self._run_chapter_close_summary(
            identity=identity,
            resolved=resolved,
            request=request,
        )
        if summary_outcome.status == RuntimeWorkflowJobStatus.COMPLETED.value:
            workflow_job_service.mark_job_completed(
                job_id=job_a.job_id,
                reason=summary_outcome.reason,
                result_ref_ids=(
                    [summary_outcome.bridge_material_id]
                    if summary_outcome.bridge_material_id
                    else ()
                ),
                metadata={"chapter_close_slot": "chapter_summary"},
            )
        else:
            workflow_job_service.mark_job_failed(
                job_id=job_a.job_id,
                reason=summary_outcome.reason,
                metadata={"chapter_close_slot": "chapter_summary"},
                last_error=summary_outcome.last_error,
            )
        # JOB B: final Core memory-maintenance run over the chapter tail (S3 path).
        tail_flush = await self._run_chapter_close_tail_flush(
            identity=identity,
            session=session,
            chapter=chapter,
            turn=turn,
            request=request,
            frozen_accepted_segments=self._resolve_accepted_segment_snapshot(
                snapshot=(job_b.metadata_json or {}).get("accepted_segment_snapshot"),
            ),
        )
        if tail_flush.status == RuntimeWorkflowJobStatus.COMPLETED.value:
            workflow_job_service.mark_job_completed(
                job_id=job_b.job_id,
                reason=tail_flush.reason,
                result_ref_ids=tail_flush.result_ref_ids,
                trace_refs=tail_flush.trace_refs,
                metadata={"chapter_close_slot": "tail_flush"},
            )
        elif tail_flush.status == RuntimeWorkflowJobStatus.DEFERRED.value:
            workflow_job_service.mark_job_deferred(
                job_id=job_b.job_id,
                reason=tail_flush.reason,
                metadata={"chapter_close_slot": "tail_flush"},
            )
        else:
            workflow_job_service.mark_job_failed(
                job_id=job_b.job_id,
                reason=tail_flush.reason,
                metadata={"chapter_close_slot": "tail_flush"},
                last_error=tail_flush.last_error,
            )
        # JOB G: turn<->SchedulerJob settlement bridge (WRK-008) completes independently.
        workflow_job_service.mark_job_completed(
            job_id=gate_job.job_id,
            reason="chapter_close_gate_completed",
            metadata={"phase": "chapter_close"},
        )
        self._settle_turn_if_ready(identity=identity)

    async def _run_chapter_close_summary(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        resolved: ResolvedChapterTransition | None,
        request: LongformTurnRequest,
    ) -> _ChapterCloseSummaryOutcome:
        """Drive JOB A's summary THROUGH THE WRITER ROLE and materialize the bridge.

        Returns the terminal outcome for JOB A: ``completed`` (+ branch-scoped bridge
        id) when the writer role produces the summary, or ``failed`` when the writer
        role raises (no bridge materialized → settlement stays blocked; the JOB A
        analog of the JOB B tail-flush failure). When no chapter runtime service /
        resolved transition is wired, JOB A completes deterministically with no bridge.
        """

        chapter_runtime_service = self._longform_chapter_runtime_service
        if chapter_runtime_service is None or resolved is None:
            return _ChapterCloseSummaryOutcome(
                status=RuntimeWorkflowJobStatus.COMPLETED.value,
                reason="chapter_close_summary_no_op",
            )
        try:
            prepared = await chapter_runtime_service.summarize_and_materialize_bridge(
                identity=identity,
                resolved=resolved,
                model_id=request.model_id,
                provider_id=request.provider_id,
            )
        except Exception as exc:  # noqa: BLE001
            # A writer-role summary failure terminalizes JOB A as failed (settlement
            # stays blocked) without failing the whole close command — mirrors JOB B.
            reason = _chapter_close_failure_code(exc)
            return _ChapterCloseSummaryOutcome(
                status=RuntimeWorkflowJobStatus.FAILED.value,
                reason=reason,
                last_error={
                    "code": reason,
                    "message": str(exc),
                    "stage": "chapter_close_summary_writer_execution",
                },
            )
        bridge_material_id = (
            prepared.receipt.bridge_material_ref
            if prepared.receipt is not None
            else None
        )
        return _ChapterCloseSummaryOutcome(
            status=RuntimeWorkflowJobStatus.COMPLETED.value,
            reason="chapter_close_summary_completed",
            bridge_material_id=bridge_material_id,
        )

    async def _run_chapter_close_tail_flush(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        session: StorySession,
        chapter: ChapterWorkspace,
        turn: StoryTurnRecord,
        request: LongformTurnRequest,
        frozen_accepted_segments: list[StoryArtifact] | None = None,
    ) -> _ChapterCloseTailFlushOutcome:
        """Run the final Core memory-maintenance pass over the chapter tail through
        the existing post-write spine (worker-side retrieval stays OFF, RET-007).

        Returns the terminal outcome for JOB B: ``completed`` on a clean maintenance
        run, ``failed`` on a worker/ingestion failure (WRK-011 — keeps settlement
        blocked), or ``deferred`` when the full-schedule spine is not wired.
        """

        scheduler = self._post_write_scheduler_service
        executor = self._worker_execution_service
        governance = self._post_write_governance_service
        if scheduler is None or executor is None or governance is None:
            return _ChapterCloseTailFlushOutcome(
                status=RuntimeWorkflowJobStatus.DEFERRED.value,
                reason="chapter_close_tail_flush_services_missing",
            )
        if self._branch_maintenance_active_excluding_turn(identity=identity):
            # REV-006 rev2: defer the chapter-tail maintenance while another run holds
            # the branch; the close turn still settles on the deferred JOB B.
            return _ChapterCloseTailFlushOutcome(
                status=RuntimeWorkflowJobStatus.DEFERRED.value,
                reason=SchedulerReasonCode.MAINTENANCE_IN_PROGRESS.value,
            )
        try:
            worker_plan = scheduler.build_worker_plan(identity=identity, proposal=None)
        except SchedulerDecisionError as exc:
            return _ChapterCloseTailFlushOutcome(
                status=RuntimeWorkflowJobStatus.DEFERRED.value,
                reason=exc.message,
            )
        command_kind = self._coerce_turn_command_kind(turn.command_kind)
        try:
            execution = await executor.execute_plan(
                session=session,
                chapter=chapter,
                plan=worker_plan,
                command_kind=command_kind,
                model_id=str(request.model_id or "chapter_close_tail_flush"),
                provider_id=request.provider_id,
                user_prompt=None,
                orchestrator_plan=self._fallback_post_write_orchestrator_plan(
                    command_kind
                ),
                accepted_segments=(
                    frozen_accepted_segments
                    if frozen_accepted_segments is not None
                    else self.accepted_segments(chapter)
                ),
                pending_artifact=self.resolve_pending_artifact(
                    chapter=chapter,
                    target_artifact_id=None,
                ),
            )
            dispatch_result = await governance.dispatch_worker_results(
                identity=identity,
                session=session,
                chapter=chapter,
                worker_plan=worker_plan,
                worker_results=list(execution.worker_results),
                specialist_bundle=execution.specialist_bundle,
            )
        except Exception as exc:  # noqa: BLE001
            # WRK-011: any tail-flush ingestion failure terminalizes JOB B as failed
            # (settlement stays blocked) without failing the whole close command.
            reason = _chapter_close_failure_code(exc)
            return _ChapterCloseTailFlushOutcome(
                status=RuntimeWorkflowJobStatus.FAILED.value,
                reason=reason,
                last_error={
                    "code": reason,
                    "message": str(exc),
                    "stage": "chapter_close_tail_flush_dispatch",
                },
            )
        failed_results = [
            result
            for result in execution.worker_results
            if result.result_status == WorkerResultStatus.FAILED
        ]
        if failed_results:
            return _ChapterCloseTailFlushOutcome(
                status=RuntimeWorkflowJobStatus.FAILED.value,
                reason="chapter_close_tail_flush_worker_failed",
                last_error={
                    "code": "chapter_close_tail_flush_worker_failed",
                    "worker_ids": [result.worker_id for result in failed_results],
                    "stage": "chapter_close_tail_flush_execute",
                },
            )
        return _ChapterCloseTailFlushOutcome(
            status=RuntimeWorkflowJobStatus.COMPLETED.value,
            reason="chapter_close_tail_flush_completed",
            result_ref_ids=tuple(dispatch_result.selected_worker_result_refs),
            trace_refs=tuple(dispatch_result.trace_refs),
        )

    def _chapter_close_anchor_turn_id(
        self,
        *,
        chapter: ChapterWorkspace,
    ) -> str | None:
        """WRK-007 anchor = adoption turn of the window's last accepted segment
        (06 SEAM 2). Falls back to the close turn (ensure_job default) when absent."""

        accepted = self.accepted_segments(chapter)
        if not accepted:
            return None
        return _optional_text(dict(accepted[-1].metadata or {}).get("runtime_turn_id"))

    def require_session(self, session_id: str) -> StorySession:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return session

    def require_current_chapter(self, session_id: str) -> ChapterWorkspace:
        chapter = self._story_session_service.get_current_chapter(session_id)
        if chapter is None:
            raise ValueError(f"Current ChapterWorkspace not found: {session_id}")
        return chapter

    def require_active_branch_current_chapter(
        self,
        session_id: str,
    ) -> ChapterWorkspace:
        chapter = self._story_session_service.get_active_branch_current_chapter(
            session_id
        )
        if chapter is None:
            raise ValueError(f"Current ChapterWorkspace not found: {session_id}")
        return chapter

    def accepted_segments(self, chapter: ChapterWorkspace) -> list[StoryArtifact]:
        return self._story_session_service.active_branch_accepted_segment_artifacts(
            session_id=chapter.session_id,
            chapter_index=chapter.chapter_index,
            chapter=chapter,
        )

    def _freeze_accepted_segment_snapshot(
        self,
        *,
        chapter: ChapterWorkspace,
        captured_turn_id: str | None,
    ) -> dict[str, object]:
        """REV-006 trigger-time snapshot: freeze accepted-segment {id, revision} refs.

        Accepted rows are append-only per revision (no in-place edit of ACCEPTED
        content_text), so id+revision resolves to the trigger-moment text even if a
        later re-adopt supersedes the row inside the maintenance window.
        """
        return {
            "refs": [
                {"artifact_id": segment.artifact_id, "revision": segment.revision}
                for segment in self.accepted_segments(chapter)
            ],
            "anchor": {
                "chapter_workspace_id": chapter.chapter_workspace_id,
                "captured_turn_id": captured_turn_id,
            },
        }

    def _resolve_accepted_segment_snapshot(
        self,
        *,
        snapshot: object,
    ) -> list[StoryArtifact] | None:
        """Resolve a frozen snapshot to rows by id+revision (never status-filtered).

        Returns ``None`` when no snapshot was captured (callers fall back to the live
        read); a present-but-empty snapshot resolves to ``[]`` (zero frozen refs).
        """
        if not isinstance(snapshot, dict):
            return None
        raw_refs = snapshot.get("refs")
        if not isinstance(raw_refs, list):
            return None
        resolved: list[StoryArtifact] = []
        for ref in raw_refs:
            if not isinstance(ref, dict):
                continue
            artifact_id = str(ref.get("artifact_id") or "").strip()
            if not artifact_id:
                continue
            artifact = self._story_session_service.get_artifact(artifact_id)
            if artifact is None:
                continue
            expected_revision = ref.get("revision")
            if expected_revision is not None and artifact.revision != expected_revision:
                continue
            resolved.append(artifact)
        return resolved

    def _branch_maintenance_active_excluding_turn(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> bool:
        """REV-006 rev2 maintenance mutual-exclusion: True when another maintenance
        run is in flight on this branch (a non-terminal job/proposal from a different
        turn). This turn's own obligations are excluded so it never defers itself."""
        if self._maintenance_lock_service is None:
            return False
        state = self._maintenance_lock_service.evaluate(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
        )
        return any(cause.turn_id != identity.turn_id for cause in state.causes)

    def resolve_pending_artifact(
        self,
        *,
        chapter: ChapterWorkspace,
        target_artifact_id: str | None,
    ) -> StoryArtifact | None:
        artifact_id = target_artifact_id or chapter.pending_segment_artifact_id
        if artifact_id is None:
            return None
        artifact = self._story_session_service.get_artifact(artifact_id)
        if artifact is None:
            return None
        visible_ids = {
            item.artifact_id
            for item in self._story_session_service.build_chapter_snapshot(
                session_id=chapter.session_id,
                chapter_index=chapter.chapter_index,
            ).artifacts
        }
        return artifact if artifact.artifact_id in visible_ids else None

    def resolve_outline_artifact(
        self,
        *,
        chapter: ChapterWorkspace,
        target_artifact_id: str | None,
    ) -> StoryArtifact | None:
        if target_artifact_id:
            return self._story_session_service.get_artifact(target_artifact_id)
        artifacts = self._story_session_service.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        outlines = [
            item
            for item in artifacts
            if item.artifact_kind == StoryArtifactKind.CHAPTER_OUTLINE
            and item.status == StoryArtifactStatus.DRAFT
        ]
        return outlines[-1] if outlines else None

    @staticmethod
    def typed(payload: dict) -> str:
        return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    @staticmethod
    def parse_typed(line: str) -> dict | None:
        stripped = line.strip()
        if not stripped.startswith("data: "):
            return None
        payload = stripped[6:]
        if payload == "[DONE]":
            return {"type": "done"}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def extract_text_delta(line: str) -> str:
        return WritingWorkerExecutionService.extract_text_delta(line)

    def _mark_block_consumer_synced(
        self,
        *,
        session_id: str,
        consumer_key: str,
    ) -> None:
        if self._block_consumer_state_service is None:
            return
        self._block_consumer_state_service.mark_consumer_synced(
            session_id=session_id,
            consumer_key=cast(BlockConsumerKey, consumer_key),
        )

    @staticmethod
    def _accepted_story_segment_metadata(
        *,
        artifact: StoryArtifact,
        patch: StorySegmentStructuredMetadata | None,
    ) -> dict[str, object]:
        metadata = dict(artifact.metadata)
        if patch is None:
            return metadata
        metadata.pop("foreshadow_status_updates", None)
        metadata.update(patch.to_artifact_metadata())
        return metadata

    def _settle_accepted_artifact_origin_turn(
        self,
        *,
        session: StorySession,
        accepted_artifact: StoryArtifact,
    ) -> None:
        if self._runtime_identity_service is None:
            return
        turn_id = _optional_text(
            dict(accepted_artifact.metadata).get("runtime_turn_id")
        )
        if turn_id is None:
            return
        self._runtime_identity_service.settle_adopted_output_turn_if_visible(
            session_id=session.session_id,
            turn_id=turn_id,
            reason="accept_pending_segment_adopted_visible_output",
        )

    def _bind_accepted_artifact_to_origin_turn_if_visible(
        self,
        *,
        session: StorySession,
        accepted_artifact: StoryArtifact,
    ) -> None:
        if self._runtime_identity_service is None:
            return
        metadata = dict(accepted_artifact.metadata)
        turn_id = _optional_text(metadata.get("runtime_turn_id"))
        branch_head_id = _optional_text(metadata.get("runtime_branch_head_id"))
        if turn_id is None or branch_head_id is None:
            return
        turn = self._runtime_identity_service.get_turn(turn_id)
        if turn is None:
            return
        if (
            turn.session_id != session.session_id
            or turn.story_id != session.story_id
            or turn.branch_head_id != branch_head_id
        ):
            return
        self._runtime_identity_service.bind_turn_output_refs_if_visible(
            session_id=session.session_id,
            turn_id=turn_id,
            artifact_id=accepted_artifact.artifact_id,
            branch_head_id=branch_head_id,
        )

    def _materialize_closed_scene_transcript_if_needed(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        scene_ref: str | None,
        allow_current_scene: bool = False,
        runtime_identity: MemoryRuntimeIdentity | None = None,
        source_refs: list[MemorySourceRef] | None = None,
    ) -> None:
        if self._recall_scene_transcript_ingestion_service is None:
            return
        normalized_scene_ref = (scene_ref or "").strip()
        if not normalized_scene_ref:
            return
        if normalized_scene_ref in chapter.closed_scene_refs:
            pass
        elif allow_current_scene and normalized_scene_ref == chapter.current_scene_ref:
            pass
        else:
            return
        snapshot = self._story_session_service.build_chapter_snapshot(
            session_id=session.session_id,
            chapter_index=chapter.chapter_index,
        )
        input_model = (
            self._recall_scene_transcript_ingestion_service.build_promotion_input(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                scene_ref=normalized_scene_ref,
                source_workspace_id=session.source_workspace_id,
                discussion_entries=snapshot.discussion_entries,
                artifacts=snapshot.artifacts,
                runtime_identity=runtime_identity,
                source_refs=source_refs or [],
            )
        )
        self._recall_scene_transcript_ingestion_service.ingest_scene_transcript(
            input_model
        )

    @staticmethod
    def _runtime_turn_source_refs(
        *,
        identity: MemoryRuntimeIdentity | None,
        session_id: str,
        chapter_index: int,
    ) -> list[MemorySourceRef]:
        if identity is None:
            return []
        return [
            MemorySourceRef(
                source_type="story_turn",
                source_id=identity.turn_id,
                layer="runtime_identity",
                domain="chapter",
                metadata={
                    "session_id": session_id,
                    "chapter_index": chapter_index,
                    "branch_head_id": identity.branch_head_id,
                    "runtime_profile_snapshot_id": (
                        identity.runtime_profile_snapshot_id
                    ),
                },
            )
        ]

    def _persist_generated_artifact_impl(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        request: LongformTurnRequest,
        packet: WritingPacket,
        plan: OrchestratorPlan,
        writing_result: WritingWorkerExecutionResult,
        pending_artifact: StoryArtifact | None,
        specialist_bundle: SpecialistResultBundle,
    ) -> tuple[StoryArtifact, ChapterWorkspace, WritingWorkerExecutionResult]:
        text = writing_result.output_text
        revision = 1
        if (
            request.command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT
            and pending_artifact is not None
        ):
            revision = pending_artifact.revision + 1
        create_artifact_kwargs: dict[str, str | None] = {}
        if (
            request.command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT
            and pending_artifact is not None
        ):
            create_artifact_kwargs["scene_ref"] = pending_artifact.scene_ref
        runtime_identity = self._packet_runtime_identity(packet)
        artifact_metadata: dict[str, object] = {
            "command_kind": request.command_kind.value,
            "packet_id": packet.packet_id,
            "writer_hints": specialist_bundle.writer_hints,
        }
        if runtime_identity is not None:
            artifact_metadata.update(
                {
                    "runtime_story_id": runtime_identity.story_id,
                    "runtime_session_id": runtime_identity.session_id,
                    "runtime_branch_head_id": runtime_identity.branch_head_id,
                    "runtime_turn_id": runtime_identity.turn_id,
                    "runtime_profile_snapshot_id": (
                        runtime_identity.runtime_profile_snapshot_id
                    ),
                }
            )
        self._record_runtime_retrieval_usage_for_artifact(
            packet=packet,
            writing_result=writing_result,
            artifact_metadata=artifact_metadata,
        )
        runtime_read_manifest_id = packet.metadata.get("runtime_read_manifest_id")
        if (
            isinstance(runtime_read_manifest_id, str)
            and runtime_read_manifest_id.strip()
        ):
            artifact_metadata["runtime_read_manifest_id"] = runtime_read_manifest_id
        if plan.output_kind == StoryArtifactKind.STORY_SEGMENT:
            target_beat_id = ""
            if pending_artifact is not None:
                target_beat_id = str(
                    dict(pending_artifact.metadata or {}).get("target_beat_id") or ""
                ).strip()
            if (
                not target_beat_id
                and self._longform_chapter_runtime_service is not None
            ):
                progress = self._longform_chapter_runtime_service.effective_outline_progress(
                    chapter=chapter,
                    identity=runtime_identity,
                )
                target_beat_id = (
                    ""
                    if progress is None or progress.current_beat_id is None
                    else progress.current_beat_id
                )
            if target_beat_id:
                artifact_metadata["target_beat_id"] = target_beat_id
            artifact_metadata.update(
                specialist_bundle.story_segment_metadata.to_artifact_metadata()
            )
        artifact = self._story_session_service.create_artifact(
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            artifact_kind=plan.output_kind,
            status=StoryArtifactStatus.DRAFT,
            content_text=text,
            metadata=artifact_metadata,
            revision=revision,
            **create_artifact_kwargs,
        )
        next_phase = chapter.phase
        outline_draft = chapter.outline_draft_json
        accepted_outline = chapter.accepted_outline_json
        pending_segment_artifact_id = chapter.pending_segment_artifact_id
        linked_discussion_entry_id: str | None = None
        finalized_result = writing_result

        if artifact.artifact_kind == StoryArtifactKind.CHAPTER_OUTLINE:
            if self._longform_chapter_runtime_service is not None:
                (
                    normalized_text,
                    normalized_metadata,
                    normalization_warnings,
                ) = self._longform_chapter_runtime_service.normalize_outline_artifact(
                    chapter=chapter,
                    artifact=artifact,
                )
                artifact = self._story_session_service.update_artifact(
                    artifact_id=artifact.artifact_id,
                    content_text=normalized_text,
                    metadata=normalized_metadata,
                )
                finalized_result = writing_result.model_copy(
                    update={
                        "output_text": normalized_text,
                        "metadata_json": {
                            **dict(writing_result.metadata_json),
                            "outline_normalization_warnings": list(
                                normalization_warnings
                            ),
                            "outline_normalization_source": normalized_metadata.get(
                                "outline_normalization_source"
                            ),
                        },
                    }
                )
                outline_draft = (
                    self._longform_chapter_runtime_service.build_outline_payload(
                        artifact=artifact,
                        metadata=artifact.metadata,
                    )
                )
            else:
                outline_draft = {
                    "artifact_id": artifact.artifact_id,
                    "content_text": artifact.content_text,
                    "metadata": artifact.metadata,
                }
            next_phase = LongformChapterPhase.OUTLINE_REVIEW
            self._story_session_service.update_session(
                session_id=session.session_id,
                current_phase=next_phase,
            )
        elif artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT:
            pending_segment_artifact_id = artifact.artifact_id
            next_phase = LongformChapterPhase.SEGMENT_REVIEW
            self._story_session_service.update_session(
                session_id=session.session_id,
                current_phase=next_phase,
            )
        else:
            discussion_entry = self._story_session_service.create_discussion_entry(
                session_id=session.session_id,
                chapter_workspace_id=chapter.chapter_workspace_id,
                role="assistant",
                content_text=artifact.content_text,
                linked_artifact_id=artifact.artifact_id,
            )
            linked_discussion_entry_id = discussion_entry.entry_id

        if runtime_identity is not None and self._runtime_workspace_facade is not None:
            surface_refs = self._runtime_workspace_facade.record_writer_output_surface(
                identity=runtime_identity,
                packet=packet,
                artifact=artifact,
                result=writing_result,
                linked_discussion_entry_id=linked_discussion_entry_id,
            )
            finalized_result = self._finalize_writing_result_refs(
                request=request,
                artifact=artifact,
                result=finalized_result,
                surface_refs=surface_refs,
            )
        else:
            finalized_result = self._finalize_writing_result_refs(
                request=request,
                artifact=artifact,
                result=finalized_result,
                surface_refs=None,
            )

        if (
            runtime_identity is not None
            and self._runtime_workflow_job_service is not None
        ):
            self._ensure_writer_completion_obligations(
                identity=runtime_identity,
                artifact=artifact,
                finalized_result=finalized_result,
                accepted_segment_snapshot=self._freeze_accepted_segment_snapshot(
                    chapter=chapter,
                    captured_turn_id=runtime_identity.turn_id,
                ),
            )

        next_chapter = self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=next_phase,
            outline_draft_json=outline_draft or {},
            accepted_outline_json=accepted_outline or {},
            pending_segment_artifact_id=pending_segment_artifact_id,
        )
        if artifact.artifact_kind == StoryArtifactKind.CHAPTER_OUTLINE:
            self._projection_state_service.set_current_outline(
                chapter_workspace_id=chapter.chapter_workspace_id,
                outline_text=artifact.content_text,
            )
        elif artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT:
            self._projection_state_service.append_recent_segment(
                chapter_workspace_id=chapter.chapter_workspace_id,
                excerpt=artifact.content_text,
            )
        self._story_session_service.commit()
        refreshed_chapter = self._story_session_service.get_chapter_workspace(
            next_chapter.chapter_workspace_id
        )
        return artifact, refreshed_chapter or next_chapter, finalized_result

    def _ensure_writer_completion_obligations(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        artifact: StoryArtifact,
        finalized_result: WritingWorkerExecutionResult,
        accepted_segment_snapshot: dict[str, object] | None = None,
    ) -> None:
        workflow_job_service = self._runtime_workflow_job_service
        if workflow_job_service is None:
            return
        source_ref_ids = [
            ref
            for ref in (
                finalized_result.writer_output_material_id,
                finalized_result.token_usage_material_id,
                artifact.artifact_id,
            )
            if ref
        ]
        trace_refs = [
            ref
            for ref in finalized_result.trace_refs
            if str(ref or "").strip()
        ]
        obligation_metadata: dict[str, object] = {
            "artifact_id": artifact.artifact_id,
            "artifact_kind": artifact.artifact_kind.value,
            "visible_output_ref": finalized_result.visible_output_ref,
            "selected_output_ref": finalized_result.selected_output_ref,
            "candidate_output_ref": finalized_result.candidate_output_ref,
        }
        if accepted_segment_snapshot is not None:
            obligation_metadata["accepted_segment_snapshot"] = accepted_segment_snapshot
        workflow_job_service.ensure_creation_time_obligations(
            identity=identity,
            source_ref_ids=source_ref_ids,
            trace_refs=trace_refs,
            metadata=obligation_metadata,
        )
        if self._runtime_identity_service is None:
            return
        self._apply_writer_finalization_gate(
            identity=identity,
            writer_result=finalized_result,
        )
        self._runtime_identity_service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.POST_WRITE_PENDING,
            visible_output_ref=finalized_result.visible_output_ref,
            selected_output_ref=finalized_result.selected_output_ref,
        )

    def _apply_writer_finalization_gate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        writer_result: WritingWorkerExecutionResult,
    ) -> None:
        """Durable turn-level RET-005 backstop (RET-003 deterministic layer).

        Defense-in-depth: rather than trusting the in-memory ``writer_result``,
        re-apply the frozen in-flight rule
        (``WriterRetrievalUsageGuardService.ensure_final_output_allowed``) over the
        PERSISTED retrieval-usage ledger for this turn identity, so the property
        holds regardless of which writer path produced the result. Raised before
        the TURN-008 visibility commit; a raise here rolls back the staged
        writer-output writes (R1).
        """

        del writer_result  # gate reads durable ledger state, not the in-memory result
        material_service = self._runtime_workspace_material_service
        if material_service is None:
            return None
        ledgers = material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_LEDGER,
        )
        if not ledgers:
            return None
        payload = ledgers[-1].payload or {}
        retrieval_generation = int(payload.get("retrieval_generation") or 0)
        if retrieval_generation <= 0:
            return None
        guard = WriterRetrievalUsageGuardService(
            runtime_retrieval_card_service=RuntimeRetrievalCardService(
                runtime_workspace_material_service=material_service,
            ),
        )
        try:
            guard.ensure_final_output_allowed(
                identity=identity,
                retrieval_generation=retrieval_generation,
                usage_generation=int(payload.get("usage_generation") or 0),
                usage_material_id=payload.get("usage_material_id"),
            )
        except WriterRetrievalUsageGuardServiceError as exc:
            raise WriterFinalizationRejected(exc.code) from exc
        return None

    def _record_runtime_retrieval_usage_for_artifact(
        self,
        *,
        packet: WritingPacket,
        writing_result: WritingWorkerExecutionResult,
        artifact_metadata: dict[str, object],
    ) -> None:
        self._record_retrieval_usage_ledger_material(
            packet=packet,
            writing_result=writing_result,
        )
        source_ref_bundle = writing_result.retrieval_source_ref_bundle
        if source_ref_bundle.is_empty():
            bundle_payload = packet.metadata.get("worker_source_ref_bundle")
            if not isinstance(bundle_payload, dict):
                return
            source_ref_bundle = WorkerSourceRefBundle.model_validate(bundle_payload)
        if source_ref_bundle.is_empty():
            return
        artifact_metadata["worker_source_ref_bundle"] = WorkerSourceRefBundle(
            retrieval_card_material_ids=(source_ref_bundle.retrieval_card_material_ids),
            retrieval_expanded_chunk_material_ids=(
                source_ref_bundle.retrieval_expanded_chunk_material_ids
            ),
            retrieval_usage_material_ids=(
                source_ref_bundle.retrieval_usage_material_ids
            ),
        ).model_dump(mode="json")

    def _record_retrieval_usage_ledger_material(
        self,
        *,
        packet: WritingPacket,
        writing_result: WritingWorkerExecutionResult,
    ) -> None:
        """Persist the writer retrieval-tool gate ledger so the durable RET-005
        gate carries forward the in-flight verdict (RET-004-safe; staged in the
        shared session before the gate and the single finalize commit)."""

        ledger = writing_result.retrieval_usage_ledger
        if ledger is None:
            return
        material_service = self._runtime_workspace_material_service
        if material_service is None:
            return
        identity = self._packet_runtime_identity(packet)
        if identity is None:
            return
        material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=f"retrieval_usage_ledger_{uuid4().hex}",
                material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_LEDGER,
                identity=identity,
                domain="chapter",
                domain_path="chapter.runtime.retrieval.usage_ledger",
                payload=ledger.model_dump(mode="json"),
                lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
                visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
                created_by="story.turn.finalization",
            )
        )

    @staticmethod
    def _packet_runtime_identity(
        packet: WritingPacket,
    ) -> MemoryRuntimeIdentity | None:
        if packet.identity is not None:
            return packet.identity
        payload = packet.metadata.get("runtime_identity")
        if not isinstance(payload, dict):
            return None
        return MemoryRuntimeIdentity.model_validate(payload)

    @classmethod
    def _packet_writer_retrieval_allowed(cls, *, packet: WritingPacket) -> bool:
        configured = packet.metadata.get("writer_retrieval_allowed")
        if isinstance(configured, bool):
            return configured
        return False

    @classmethod
    def _packet_writer_max_retrieval_attempts(cls, *, packet: WritingPacket) -> int:
        configured = packet.metadata.get("writer_max_retrieval_attempts")
        if isinstance(configured, int):
            return max(0, min(configured, 3))
        return 2 if cls._packet_writer_retrieval_allowed(packet=packet) else 0

    def _resolve_writing_operation_mode(
        self,
        *,
        command_kind: LongformTurnCommandKind | None,
        plan: OrchestratorPlan,
    ) -> str:
        return self._story_runtime_adapter_service.translate_legacy_command(
            command_kind=command_kind,
            plan=plan,
        ).operation_mode

    @staticmethod
    def _coerce_writing_result(
        *,
        packet: WritingPacket,
        writing_result: WritingWorkerExecutionResult | None,
        fallback_text: str | None,
    ) -> WritingWorkerExecutionResult:
        if writing_result is not None:
            return writing_result
        return WritingWorkerExecutionResult(
            request_id=f"writer-stream:{packet.packet_id}",
            packet_id=packet.packet_id,
            turn_id=packet.turn_id,
            operation_mode=packet.operation_mode,
            output_text=str(fallback_text or ""),
            output_kind=packet.output_kind,
            usage_metadata={},
            result_status="completed",
        )

    @staticmethod
    def _finalize_writing_result_refs(
        *,
        request: LongformTurnRequest,
        artifact: StoryArtifact,
        result: WritingWorkerExecutionResult,
        surface_refs,
    ) -> WritingWorkerExecutionResult:
        is_rewrite = (
            request.command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT
        )
        writer_output_material_id = (
            None if surface_refs is None else surface_refs.writer_output_material_id
        )
        token_usage_material_id = (
            None if surface_refs is None else surface_refs.token_usage_material_id
        )
        trace_refs = list(result.trace_refs)
        for material_id in (writer_output_material_id, token_usage_material_id):
            if material_id:
                trace_refs.append(f"runtime_workspace:{material_id}")
        return result.model_copy(
            update={
                "visible_output_ref": None if is_rewrite else artifact.artifact_id,
                "candidate_output_ref": artifact.artifact_id if is_rewrite else None,
                "selected_output_ref": None if is_rewrite else artifact.artifact_id,
                "writer_output_material_id": writer_output_material_id,
                "token_usage_material_id": token_usage_material_id,
                "trace_refs": trace_refs,
                "writer_tool_trace_refs": list(result.writer_tool_trace_refs),
                "metadata_json": {
                    **dict(result.metadata_json),
                    "artifact_id": artifact.artifact_id,
                    "artifact_kind": artifact.artifact_kind.value,
                    "artifact_status": artifact.status.value,
                    "artifact_revision": artifact.revision,
                },
            }
        )

    @staticmethod
    def build_graph_thread_id(*, session_id: str, branch_head_id: str) -> str:
        return StoryRuntimeIdentityService.build_graph_thread_id(
            session_id=session_id,
            branch_head_id=branch_head_id,
        )

    @classmethod
    def _default_branch_head_id(cls, session_id: str) -> str:
        return f"branch:{session_id}:{cls._DEFAULT_BRANCH_NAME}"


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@dataclass(frozen=True)
class _ChapterCloseTailFlushOutcome:
    """Terminal outcome for the chapter-close tail-flush job (JOB B)."""

    status: str
    reason: str
    result_ref_ids: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()
    last_error: dict[str, object] | None = None


@dataclass(frozen=True)
class _ChapterCloseSummaryOutcome:
    """Terminal outcome for the chapter-close summary job (JOB A).

    ``bridge_material_id`` carries the branch-scoped bridge id on success (recorded
    into JOB A's ``result_ref_ids`` so bridge-after-summary stays observable, D-S5-01).
    """

    status: str
    reason: str
    bridge_material_id: str | None = None
    last_error: dict[str, object] | None = None


def _chapter_close_failure_code(exc: Exception) -> str:
    explicit_code = getattr(exc, "code", None)
    if isinstance(explicit_code, str) and explicit_code.strip():
        return explicit_code.strip()
    return exc.__class__.__name__


_POST_WRITE_TRIGGER_READY_STATUSES: set[str] = {
    StoryTurnStatus.POST_WRITE_PENDING.value,
    StoryTurnStatus.POST_WRITE_RUNNING.value,
    StoryTurnStatus.POST_WRITE_DEFERRED.value,
    StoryTurnStatus.SETTLED.value,
}
