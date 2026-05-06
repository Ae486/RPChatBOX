"""Shared domain service for story turn commands and generation flow."""

from __future__ import annotations

import json
from typing import AsyncIterator

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
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
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.worker_memory import WorkerSourceRefBundle
from rp.models.writing_runtime import WritingPacket
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_regression_service import LongformRegressionService
from .longform_specialist_service import LongformSpecialistService
from .builder_projection_context_service import BuilderProjectionContextService
from .projection_state_service import ProjectionStateService
from .recall_scene_transcript_ingestion_service import (
    RecallSceneTranscriptIngestionService,
)
from .story_block_consumer_state_service import StoryBlockConsumerStateService
from .story_runtime_identity_service import StoryRuntimeIdentityService
from .story_session_service import StorySessionService
from .runtime_retrieval_card_service import RuntimeRetrievalCardService
from .runtime_read_manifest_service import RuntimeReadManifestService
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from .writing_packet_builder import WritingPacketBuilder
from .writing_worker_execution_service import WritingWorkerExecutionService


class StoryTurnDomainService:
    """Own longform turn domain logic independent of graph/controller shell."""

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
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._runtime_read_manifest_service: RuntimeReadManifestService | None
        if runtime_read_manifest_service is not None:
            self._runtime_read_manifest_service = runtime_read_manifest_service
        else:
            resolver_session = (
                getattr(runtime_identity_service, "_session", None)
                if runtime_identity_service is not None
                else None
            )
            self._runtime_read_manifest_service = (
                RuntimeReadManifestService(
                    session=resolver_session,
                    runtime_workspace_material_service=runtime_workspace_material_service,
                )
                if resolver_session is not None
                else None
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

    def resolve_runtime_entry_identity(
        self,
        *,
        session_id: str,
        command_kind: LongformTurnCommandKind,
        actor: str = "story_runtime",
    ) -> MemoryRuntimeIdentity | None:
        if self._runtime_identity_service is None:
            return None
        return self._runtime_identity_service.resolve_runtime_entry_identity(
            session_id=session_id,
            command_kind=command_kind.value,
            actor=actor,
        )

    def finalize_runtime_turn(self, *, turn_id: str | None, failed: bool) -> None:
        if self._runtime_identity_service is None:
            return
        normalized_turn_id = str(turn_id or "").strip()
        if not normalized_turn_id:
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

    def build_packet(
        self,
        *,
        session_id: str,
        plan: OrchestratorPlan,
        specialist_bundle: SpecialistResultBundle,
        runtime_identity: MemoryRuntimeIdentity | None = None,
    ) -> WritingPacket:
        session = self.require_session(session_id)
        chapter = self.require_current_chapter(session_id)
        resolved_runtime_identity = (
            runtime_identity or self._runtime_identity_by_session.get(session_id)
        )
        projection_context_sections = (
            self._builder_projection_context_service.build_context_sections(
                session_id=session_id,
            )
        )
        runtime_retrieval_sections: list[dict[str, object]] = []
        packet_metadata: dict[str, object] = {}
        if resolved_runtime_identity is not None:
            packet_metadata["runtime_identity"] = resolved_runtime_identity.model_dump(
                mode="json"
            )
            (
                runtime_retrieval_sections,
                source_ref_bundle,
            ) = self._build_runtime_retrieval_packet_context(
                identity=resolved_runtime_identity
            )
            if not source_ref_bundle.is_empty():
                packet_metadata["worker_source_ref_bundle"] = (
                    source_ref_bundle.model_dump(mode="json")
                )
        packet = self._writing_packet_builder.build(
            session=session,
            chapter=chapter,
            plan=plan,
            projection_context_sections=projection_context_sections,
            runtime_retrieval_sections=runtime_retrieval_sections,
            runtime_writer_hints=list(specialist_bundle.writer_hints),
            user_instruction=plan.writer_instruction,
            packet_metadata=packet_metadata,
        )
        if (
            resolved_runtime_identity is not None
            and self._runtime_read_manifest_service is not None
        ):
            manifest = self._runtime_read_manifest_service.build_writer_manifest(
                identity=resolved_runtime_identity,
                packet_kind="writer",
                packet_sections=projection_context_sections,
                selected_section_labels=[
                    str(section.get("label") or "").strip()
                    for section in packet.context_sections
                    if str(section.get("label") or "").strip()
                ],
                policy_versions={"packet_kind": "writer"},
            )
            packet = packet.model_copy(
                update={
                    "metadata": {
                        **dict(packet.metadata),
                        "runtime_read_manifest_id": manifest.manifest_id,
                        "runtime_read_manifest": manifest.model_dump(mode="json"),
                    }
                }
            )
        self._mark_block_consumer_synced(
            session_id=session_id,
            consumer_key="story.writer_packet",
        )
        return packet

    async def writer_run(
        self,
        *,
        packet: WritingPacket,
        model_id: str,
        provider_id: str | None,
    ) -> str:
        return await self._writing_worker_execution_service.run(
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

    def persist_generated_artifact(
        self,
        *,
        request: LongformTurnRequest,
        packet: WritingPacket,
        plan: OrchestratorPlan,
        text: str,
        specialist_bundle: SpecialistResultBundle,
        pending_artifact_id: str | None,
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_current_chapter(request.session_id)
        pending_artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=pending_artifact_id,
        )
        artifact, next_chapter = self._persist_generated_artifact_impl(
            session=session,
            chapter=chapter,
            request=request,
            packet=packet,
            plan=plan,
            text=text,
            pending_artifact=pending_artifact,
            specialist_bundle=specialist_bundle,
        )
        return LongformTurnResponse(
            session_id=session.session_id,
            chapter_workspace_id=next_chapter.chapter_workspace_id,
            command_kind=request.command_kind,
            current_chapter_index=next_chapter.chapter_index,
            current_phase=next_chapter.phase,
            assistant_text=text,
            artifact_id=artifact.artifact_id,
            artifact_kind=artifact.artifact_kind,
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
        text: str,
        pending_artifact: StoryArtifact | None,
        specialist_bundle: SpecialistResultBundle,
    ) -> tuple[StoryArtifact, ChapterWorkspace]:
        revision = 1
        if (
            request.command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT
            and pending_artifact is not None
        ):
            self._story_session_service.update_artifact(
                artifact_id=pending_artifact.artifact_id,
                status=StoryArtifactStatus.SUPERSEDED,
            )
            revision = pending_artifact.revision + 1
        create_artifact_kwargs: dict[str, str | None] = {}
        if (
            request.command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT
            and pending_artifact is not None
        ):
            create_artifact_kwargs["scene_ref"] = pending_artifact.scene_ref
        artifact_metadata = {
            "command_kind": request.command_kind.value,
            "packet_id": packet.packet_id,
            "writer_hints": specialist_bundle.writer_hints,
        }
        self._record_runtime_retrieval_usage_for_artifact(
            packet=packet,
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
            self._story_session_service.create_discussion_entry(
                session_id=session.session_id,
                chapter_workspace_id=chapter.chapter_workspace_id,
                role="assistant",
                content_text=artifact.content_text,
                linked_artifact_id=artifact.artifact_id,
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
        return artifact, refreshed_chapter or next_chapter

    def _build_runtime_retrieval_packet_context(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> tuple[list[dict[str, object]], WorkerSourceRefBundle]:
        retrieval_service = self._runtime_retrieval_cards()
        writer_visible_materials = retrieval_service.list_writer_visible_materials(
            identity=identity
        )
        card_ids = [
            material.material_id
            for material in writer_visible_materials
            if material.material_kind == RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD
        ]
        expanded_ids = [
            material.material_id
            for material in writer_visible_materials
            if material.material_kind
            == RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK
        ]
        if not card_ids and not expanded_ids:
            return [], WorkerSourceRefBundle()
        items = []
        for item in retrieval_service.list_writer_visible_context(identity=identity):
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            short_id = str(item.get("short_id") or "").strip()
            kind = str(item.get("kind") or "").strip()
            title = str(item.get("title") or "").strip()
            prefix = f"{short_id} " if short_id else ""
            title_prefix = f"{title}: " if title else ""
            items.append(f"{prefix}[{kind}] {title_prefix}{summary}".strip())
        return (
            [{"label": "retrieval_context", "items": items}] if items else [],
            WorkerSourceRefBundle(
                retrieval_card_material_ids=card_ids,
                retrieval_expanded_chunk_material_ids=expanded_ids,
            ),
        )

    def _runtime_retrieval_cards(self) -> RuntimeRetrievalCardService:
        return RuntimeRetrievalCardService(
            runtime_workspace_material_service=self._runtime_workspace_material_service
        )

    def _record_runtime_retrieval_usage_for_artifact(
        self,
        *,
        packet: WritingPacket,
        artifact_metadata: dict[str, object],
    ) -> None:
        bundle_payload = packet.metadata.get("worker_source_ref_bundle")
        if not isinstance(bundle_payload, dict):
            return
        source_ref_bundle = WorkerSourceRefBundle.model_validate(bundle_payload)
        identity_payload = packet.metadata.get("runtime_identity")
        if not isinstance(identity_payload, dict):
            artifact_metadata["worker_source_ref_bundle"] = (
                source_ref_bundle.model_dump(mode="json")
            )
            return
        identity = MemoryRuntimeIdentity.model_validate(identity_payload)
        usage_ids = list(source_ref_bundle.retrieval_usage_material_ids)
        if (
            source_ref_bundle.retrieval_card_material_ids
            or source_ref_bundle.retrieval_expanded_chunk_material_ids
        ) and not usage_ids:
            usage = self._runtime_retrieval_cards().record_writer_usage(
                identity=identity,
                used_card_ids=source_ref_bundle.retrieval_card_material_ids,
                used_expanded_chunk_ids=(
                    source_ref_bundle.retrieval_expanded_chunk_material_ids
                ),
                actor="worker.writer_output",
            )
            usage_ids.append(usage.material_id)
        artifact_metadata["worker_source_ref_bundle"] = WorkerSourceRefBundle(
            retrieval_card_material_ids=(source_ref_bundle.retrieval_card_material_ids),
            retrieval_expanded_chunk_material_ids=(
                source_ref_bundle.retrieval_expanded_chunk_material_ids
            ),
            retrieval_usage_material_ids=usage_ids,
        ).model_dump(mode="json")
