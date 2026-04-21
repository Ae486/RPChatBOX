"""Post-write regression for longform active-story MVP."""

from __future__ import annotations

from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    StoryArtifact,
    StorySession,
)
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_specialist_service import LongformSpecialistService
from .recall_summary_ingestion_service import RecallSummaryIngestionService
from .story_session_service import StorySessionService
from .story_state_apply_service import StoryStateApplyService


class LongformRegressionService:
    """Digest accepted artifacts back into session/chapter runtime state."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        orchestrator_service: LongformOrchestratorService,
        specialist_service: LongformSpecialistService,
        story_state_apply_service: StoryStateApplyService | None = None,
        recall_summary_ingestion_service: RecallSummaryIngestionService | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._orchestrator_service = orchestrator_service
        self._specialist_service = specialist_service
        self._story_state_apply_service = story_state_apply_service or StoryStateApplyService()
        self._recall_summary_ingestion_service = recall_summary_ingestion_service

    async def run_light_regression(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        accepted_artifact: StoryArtifact,
        model_id: str,
        provider_id: str | None,
    ) -> tuple[StorySession, ChapterWorkspace]:
        plan = await self._orchestrator_service.plan(
            session=session,
            chapter=chapter,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            target_artifact_id=accepted_artifact.artifact_id,
        )
        bundle = await self._specialist_service.analyze(
            session=session,
            chapter=chapter,
            plan=plan,
            command_kind=LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            accepted_segments=[
                *[
                    item
                    for item in self._story_session_service.list_artifacts(
                        chapter_workspace_id=chapter.chapter_workspace_id
                    )
                    if item.status.value == "accepted" and item.artifact_kind.value == "story_segment"
                ],
                accepted_artifact,
            ],
            pending_artifact=accepted_artifact,
        )
        return self._apply_bundle(session=session, chapter=chapter, bundle=bundle)

    async def run_heavy_regression(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        model_id: str,
        provider_id: str | None,
    ) -> tuple[StorySession, ChapterWorkspace]:
        accepted_segments = [
            item
            for item in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            if item.status.value == "accepted" and item.artifact_kind.value == "story_segment"
        ]
        plan = await self._orchestrator_service.plan(
            session=session,
            chapter=chapter,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            target_artifact_id=None,
        )
        bundle = await self._specialist_service.analyze(
            session=session,
            chapter=chapter,
            plan=plan,
            command_kind=LongformTurnCommandKind.COMPLETE_CHAPTER,
            model_id=model_id,
            provider_id=provider_id,
            user_prompt=None,
            accepted_segments=accepted_segments,
            pending_artifact=accepted_segments[-1] if accepted_segments else None,
        )
        updated_session, updated_chapter = self._apply_bundle(
            session=session,
            chapter=chapter,
            bundle=bundle,
        )
        if self._recall_summary_ingestion_service is not None and bundle.recall_summary_text:
            self._recall_summary_ingestion_service.ingest_chapter_summary(
                session_id=session.session_id,
                story_id=session.story_id,
                chapter_index=chapter.chapter_index,
                source_workspace_id=session.source_workspace_id,
                summary_text=bundle.recall_summary_text,
            )
        return updated_session, updated_chapter

    def _apply_bundle(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        bundle,
    ) -> tuple[StorySession, ChapterWorkspace]:
        updated_state = self._story_state_apply_service.apply(
            current_state_json=session.current_state_json,
            patch=bundle.state_patch_proposals,
        )
        updated_session = self._story_session_service.update_session(
            session_id=session.session_id,
            current_state_json=updated_state,
        )
        snapshot = dict(chapter.builder_snapshot_json)
        snapshot.update(
            {
                "chapter_index": chapter.chapter_index,
                "phase": chapter.phase.value,
                "foundation_digest": bundle.foundation_digest,
                "blueprint_digest": bundle.blueprint_digest,
                "current_outline_digest": bundle.current_outline_digest,
                "recent_segment_digest": bundle.recent_segment_digest,
                "current_state_digest": bundle.current_state_digest,
                "writer_hints": bundle.writer_hints,
            }
        )
        updated_chapter = self._story_session_service.update_chapter_workspace(
            chapter_workspace_id=chapter.chapter_workspace_id,
            builder_snapshot_json=snapshot,
        )
        return updated_session, updated_chapter
