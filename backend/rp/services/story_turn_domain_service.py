"""Shared domain service for story turn commands and generation flow."""
from __future__ import annotations

import json
from typing import AsyncIterator

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
    StorySession,
)
from rp.models.writing_runtime import WritingPacket
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_regression_service import LongformRegressionService
from .longform_specialist_service import LongformSpecialistService
from .builder_projection_context_service import BuilderProjectionContextService
from .projection_state_service import ProjectionStateService
from .story_session_service import StorySessionService
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
    ) -> None:
        self._story_session_service = story_session_service
        self._orchestrator_service = orchestrator_service
        self._specialist_service = specialist_service
        self._builder_projection_context_service = builder_projection_context_service
        self._projection_state_service = projection_state_service
        self._writing_packet_builder = writing_packet_builder
        self._writing_worker_execution_service = writing_worker_execution_service
        self._regression_service = regression_service

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
        accepted_segment_ids = [item.artifact_id for item in self.accepted_segments(chapter)]
        return {
            "pending_artifact_id": pending_artifact.artifact_id if pending_artifact else None,
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
        return await self._orchestrator_service.plan(
            session=session,
            chapter=chapter,
            command_kind=command_kind,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=user_prompt,
            target_artifact_id=target_artifact_id,
        )

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
        return await self._specialist_service.analyze(
            session=session,
            chapter=chapter,
            plan=plan,
            command_kind=command_kind,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=user_prompt,
            accepted_segments=accepted_segments,
            pending_artifact=pending_artifact,
        )

    def build_packet(
        self,
        *,
        session_id: str,
        plan: OrchestratorPlan,
        specialist_bundle: SpecialistResultBundle,
    ) -> WritingPacket:
        session = self.require_session(session_id)
        chapter = self.require_current_chapter(session_id)
        return self._writing_packet_builder.build(
            session=session,
            chapter=chapter,
            plan=plan,
            projection_context_sections=self._builder_projection_context_service.build_context_sections(
                session_id=session_id,
            ),
            runtime_writer_hints=list(specialist_bundle.writer_hints),
            user_instruction=plan.writer_instruction,
        )

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
    ) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_current_chapter(request.session_id)
        artifact = self.resolve_pending_artifact(
            chapter=chapter,
            target_artifact_id=request.target_artifact_id,
        )
        if artifact is None:
            raise ValueError("No pending segment available to accept")
        accepted = self._story_session_service.update_artifact(
            artifact_id=artifact.artifact_id,
            status=StoryArtifactStatus.ACCEPTED,
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
        updated_session, updated_chapter = await self._regression_service.run_light_regression(
            session=updated_session,
            chapter=updated_chapter,
            accepted_artifact=accepted,
            model_id=request.model_id,
            provider_id=request.provider_id,
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

    async def complete_chapter(self, *, request: LongformTurnRequest) -> LongformTurnResponse:
        session = self.require_session(request.session_id)
        chapter = self.require_current_chapter(request.session_id)
        updated_session, updated_chapter = await self._regression_service.run_heavy_regression(
            session=session,
            chapter=chapter,
            model_id=request.model_id,
            provider_id=request.provider_id,
        )
        self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=updated_chapter.chapter_workspace_id,
            phase=LongformChapterPhase.CHAPTER_COMPLETED,
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
        if request.command_kind == LongformTurnCommandKind.REWRITE_PENDING_SEGMENT and pending_artifact is not None:
            self._story_session_service.update_artifact(
                artifact_id=pending_artifact.artifact_id,
                status=StoryArtifactStatus.SUPERSEDED,
            )
            revision = pending_artifact.revision + 1
        artifact = self._story_session_service.create_artifact(
            session_id=session.session_id,
            chapter_workspace_id=chapter.chapter_workspace_id,
            artifact_kind=plan.output_kind,
            status=StoryArtifactStatus.DRAFT,
            content_text=text,
            metadata={
                "command_kind": request.command_kind.value,
                "packet_id": packet.packet_id,
                "writer_hints": specialist_bundle.writer_hints,
            },
            revision=revision,
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
