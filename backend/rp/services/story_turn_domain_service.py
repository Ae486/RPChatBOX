"""Shared domain service for story turn commands and generation flow."""

from __future__ import annotations

import json
from typing import AsyncIterator
from uuid import uuid4

from models.rp_story_store import RuntimeWorkflowJobRecord
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.postwrite_runtime_contracts import (
    PostWriteExecutionEnvelope,
    PostWriteRunKind,
)
from rp.models.runtime_identity import StoryTurnStatus
from rp.models.story_runtime import (
    ChapterWorkspace,
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
from rp.models.worker_memory import WorkerSourceRefBundle
from rp.models.writing_worker_contracts import (
    WritingWorkerExecutionRequest,
    WritingWorkerExecutionResult,
)
from rp.models.writing_runtime import WritingPacket
from .context_orchestration_service import ContextOrchestrationService
from .longform_chapter_runtime_service import LongformChapterRuntimeService
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_regression_service import LongformRegressionService
from .longform_specialist_service import LongformSpecialistService
from .post_write_governance_service import PostWriteGovernanceService
from .post_write_scheduler_service import PostWriteSchedulerService
from .builder_projection_context_service import BuilderProjectionContextService
from .projection_state_service import ProjectionStateService
from .recall_scene_transcript_ingestion_service import (
    RecallSceneTranscriptIngestionService,
)
from .story_block_consumer_state_service import StoryBlockConsumerStateService
from .story_runtime_identity_service import StoryRuntimeIdentityService
from .story_runtime_workspace_facade import StoryRuntimeWorkspaceFacade
from .story_session_service import StorySessionService
from .runtime_read_manifest_service import RuntimeReadManifestService
from .runtime_workflow_job_service import (
    RuntimeWorkflowJobService,
    TurnSettlementEvaluation,
)
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from .story_runtime_adapter_service import StoryRuntimeAdapterService
from .worker_execution_service import WorkerExecutionService
from .worker_scheduler_service import (
    PRE_WRITE_CONTEXT_PHASE,
    WorkerSchedulerService,
)
from .writing_packet_builder import WritingPacketBuilder
from .writing_worker_execution_service import WritingWorkerExecutionService


class StoryTurnDomainService:
    """Own longform turn domain logic independent of graph/controller shell."""

    _DEFAULT_BRANCH_NAME = "main"

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
        self._runtime_identity_service = runtime_identity_service
        self._worker_scheduler_service = worker_scheduler_service
        self._worker_execution_service = worker_execution_service
        resolver_session = (
            getattr(runtime_identity_service, "_session", None)
            if runtime_identity_service is not None
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
        self._post_write_scheduler_service = post_write_scheduler_service
        self._post_write_governance_service = post_write_governance_service
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
        chapter = self.require_current_chapter(session_id)
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
        chapter = self.require_current_chapter(session_id)
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
        chapter = self.require_current_chapter(session_id)
        pending_artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=pending_artifact_id,
        )
        accepted_segments = [
            artifact
            for artifact in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            if artifact.artifact_id in set(accepted_segment_ids)
        ]
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
    ) -> WritingPacket:
        session = self.require_session(session_id)
        chapter = self.require_current_chapter(session_id)
        resolved_runtime_identity = (
            runtime_identity or self._runtime_identity_by_session.get(session_id)
        )
        packet = self._context_orchestration_service.build_writing_packet(
            session=session,
            chapter=chapter,
            plan=plan,
            specialist_bundle=specialist_bundle,
            operation_mode=self._resolve_writing_operation_mode(
                command_kind=command_kind,
                plan=plan,
            ),
            runtime_identity=resolved_runtime_identity,
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
        chapter = self.require_current_chapter(runtime_identity.session_id)
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
        self._runtime_identity_service.update_turn_status(
            turn_id=runtime_identity.turn_id,
            status=StoryTurnStatus.POST_WRITE_RUNNING,
        )
        worker_plan = self._post_write_scheduler_service.build_worker_plan(
            identity=runtime_identity,
        )
        command_kind = self._coerce_turn_command_kind(turn.command_kind)
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
            accepted_segments=self.accepted_segments(chapter),
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
        chapter = self.require_current_chapter(request.session_id)
        pending_artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=pending_artifact_id,
        )
        artifact, next_chapter, finalized_result = self._persist_generated_artifact_impl(
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

    def accept_outline(self, *, request: LongformTurnRequest) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_current_chapter(request.session_id)
        artifact = self.resolve_outline_artifact(
            chapter=chapter,
            target_artifact_id=request.target_artifact_id,
        )
        if artifact is None:
            raise ValueError("No draft outline available to accept")
        self._story_session_service.update_artifact(
            artifact_id=artifact.artifact_id,
            status=StoryArtifactStatus.ACCEPTED,
        )
        next_phase = LongformChapterPhase.SEGMENT_DRAFTING
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=next_phase,
            outline_draft_json=chapter.outline_draft_json
            or {
                "artifact_id": artifact.artifact_id,
                "content_text": artifact.content_text,
                "metadata": artifact.metadata,
            },
            accepted_outline_json={
                "artifact_id": artifact.artifact_id,
                "content_text": artifact.content_text,
                "metadata": artifact.metadata,
            },
        )
        self._story_session_service.update_session(
            session_id=session.session_id,
            current_phase=next_phase,
        )
        self._projection_state_service.set_current_outline(
            chapter_workspace_id=chapter.chapter_workspace_id,
            outline_text=artifact.content_text,
        )
        self._story_session_service.commit()
        return LongformTurnResponse(
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            command_kind=request.command_kind,
            current_chapter_index=chapter.chapter_index,
            current_phase=next_phase,
            assistant_text="Accepted outline. Ready to draft the next segment.",
            artifact_id=artifact.artifact_id,
            artifact_kind=artifact.artifact_kind,
        )

    async def accept_pending_segment(
        self,
        *,
        request: LongformTurnRequest,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_current_chapter(request.session_id)
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
        accepted = self._story_session_service.update_artifact(
            artifact_id=artifact.artifact_id,
            status=StoryArtifactStatus.ACCEPTED,
            metadata=accepted_metadata,
        )
        for candidate in self._story_session_service.list_artifacts(
            chapter_workspace_id=chapter.chapter_workspace_id
        ):
            if candidate.artifact_id == accepted.artifact_id:
                continue
            if candidate.artifact_kind != StoryArtifactKind.STORY_SEGMENT:
                continue
            if candidate.status != StoryArtifactStatus.DRAFT:
                continue
            self._story_session_service.update_artifact(
                artifact_id=candidate.artifact_id,
                status=StoryArtifactStatus.SUPERSEDED,
            )
        updated_chapter = self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            phase=LongformChapterPhase.SEGMENT_DRAFTING,
            accepted_segment_ids=[*chapter.accepted_segment_ids, accepted.artifact_id],
            pending_segment_artifact_id=None,
        )
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

    async def complete_chapter(
        self,
        *,
        request: LongformTurnRequest,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_current_chapter(request.session_id)
        if self._longform_chapter_runtime_service is not None:
            prepared_transition = (
                self._longform_chapter_runtime_service.prepare_chapter_transition(
                    identity=runtime_identity,
                    session=session,
                    chapter=chapter,
                )
            )
            chapter = prepared_transition.chapter
        (
            updated_session,
            updated_chapter,
        ) = await self._regression_service.run_heavy_regression(
            session=session,
            chapter=chapter,
            model_id=request.model_id,
            provider_id=request.provider_id,
            runtime_identity=runtime_identity,
        )
        self._materialize_closed_scene_transcript_if_needed(
            session=updated_session,
            chapter=updated_chapter,
            scene_ref=updated_chapter.current_scene_ref,
            allow_current_scene=True,
            runtime_identity=runtime_identity,
            source_refs=self._runtime_turn_source_refs(
                identity=runtime_identity,
                session_id=session.session_id,
                chapter_index=chapter.chapter_index,
            ),
        )
        closed_scene_refs = list(updated_chapter.closed_scene_refs)
        last_closed_scene_ref = updated_chapter.last_closed_scene_ref
        if updated_chapter.current_scene_ref:
            last_closed_scene_ref = updated_chapter.current_scene_ref
            if last_closed_scene_ref not in closed_scene_refs:
                closed_scene_refs.append(last_closed_scene_ref)
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=updated_chapter.chapter_workspace_id,
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
            previous_chapter_workspace_id=updated_chapter.chapter_workspace_id,
            next_chapter_workspace_id=next_chapter.chapter_workspace_id,
            next_chapter_index=next_chapter_index,
        )
        self._story_session_service.update_session(
            session_id=updated_session.session_id,
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

    def accepted_segments(self, chapter: ChapterWorkspace) -> list[StoryArtifact]:
        return [
            item
            for item in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            if item.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            and item.status == StoryArtifactStatus.ACCEPTED
        ]

    def resolve_pending_artifact(
        self,
        *,
        chapter: ChapterWorkspace,
        target_artifact_id: str | None,
    ) -> StoryArtifact | None:
        artifact_id = target_artifact_id or chapter.pending_segment_artifact_id
        if artifact_id is None:
            return None
        return self._story_session_service.get_artifact(artifact_id)

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
            consumer_key=consumer_key,
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
                result=writing_result,
                surface_refs=surface_refs,
            )
        else:
            finalized_result = self._finalize_writing_result_refs(
                request=request,
                artifact=artifact,
                result=writing_result,
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
        workflow_job_service.ensure_creation_time_obligations(
            identity=identity,
            source_ref_ids=source_ref_ids,
            trace_refs=trace_refs,
            metadata={
                "artifact_id": artifact.artifact_id,
                "artifact_kind": artifact.artifact_kind.value,
                "visible_output_ref": finalized_result.visible_output_ref,
                "selected_output_ref": finalized_result.selected_output_ref,
                "candidate_output_ref": finalized_result.candidate_output_ref,
            },
        )
        if self._runtime_identity_service is None:
            return
        self._runtime_identity_service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.POST_WRITE_PENDING,
            visible_output_ref=finalized_result.visible_output_ref,
            selected_output_ref=finalized_result.selected_output_ref,
        )

    def _record_runtime_retrieval_usage_for_artifact(
        self,
        *,
        packet: WritingPacket,
        writing_result: WritingWorkerExecutionResult,
        artifact_metadata: dict[str, object],
    ) -> None:
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


_POST_WRITE_TRIGGER_READY_STATUSES: set[str] = {
    StoryTurnStatus.POST_WRITE_PENDING.value,
    StoryTurnStatus.POST_WRITE_RUNNING.value,
    StoryTurnStatus.POST_WRITE_DEFERRED.value,
    StoryTurnStatus.SETTLED.value,
}
