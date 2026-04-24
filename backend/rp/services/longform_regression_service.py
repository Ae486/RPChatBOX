"""Post-write regression for longform active-story MVP."""

from __future__ import annotations

from rp.models.story_runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    SpecialistResultBundle,
    StoryArtifact,
    StorySession,
)
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from .legacy_state_patch_proposal_builder import LegacyStatePatchProposalBuilder
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_specialist_service import LongformSpecialistService
from .projection_refresh_service import ProjectionRefreshService
from .proposal_workflow_service import ProposalWorkflowService
from .recall_summary_ingestion_service import RecallSummaryIngestionService
from .story_session_service import StorySessionService


class LongformRegressionService:
    """Digest accepted artifacts back into session/chapter runtime state."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        orchestrator_service: LongformOrchestratorService,
        specialist_service: LongformSpecialistService,
        proposal_workflow_service: ProposalWorkflowService,
        legacy_state_patch_proposal_builder: LegacyStatePatchProposalBuilder | None = None,
        projection_refresh_service: ProjectionRefreshService | None = None,
        recall_summary_ingestion_service: RecallSummaryIngestionService | None = None,
        regression_policy: PostWriteMaintenancePolicy | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._orchestrator_service = orchestrator_service
        self._specialist_service = specialist_service
        self._proposal_workflow_service = proposal_workflow_service
        self._legacy_state_patch_proposal_builder = (
            legacy_state_patch_proposal_builder or LegacyStatePatchProposalBuilder()
        )
        self._projection_refresh_service = (
            projection_refresh_service or ProjectionRefreshService(story_session_service)
        )
        self._recall_summary_ingestion_service = recall_summary_ingestion_service
        self._regression_policy = regression_policy or PostWriteMaintenancePolicy(
            preset_id="phase_e_internal_regression",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        )

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
            accepted_segments=self._collect_light_regression_segments(
                chapter=chapter,
                accepted_artifact=accepted_artifact,
            ),
            pending_artifact=accepted_artifact,
        )
        return await self._apply_bundle(session=session, chapter=chapter, bundle=bundle)

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
        updated_session, updated_chapter = await self._apply_bundle(
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

    async def _apply_bundle(
        self,
        *,
        session: StorySession,
        chapter: ChapterWorkspace,
        bundle: SpecialistResultBundle,
    ) -> tuple[StorySession, ChapterWorkspace]:
        if bundle.state_patch_proposals:
            proposal_inputs = self._legacy_state_patch_proposal_builder.build_inputs(
                story_id=session.story_id,
                mode=session.mode,
                patch=bundle.state_patch_proposals,
            )
            for proposal_input in proposal_inputs:
                await self._proposal_workflow_service.submit_and_route(
                    proposal_input,
                    session_id=session.session_id,
                    chapter_workspace_id=chapter.chapter_workspace_id,
                    submit_source="post_write_regression",
                    policy=self._regression_policy,
                )
        updated_session = self._story_session_service.get_session(session.session_id) or session
        updated_chapter = self._projection_refresh_service.refresh_from_bundle(
            chapter=chapter,
            bundle=bundle,
        )
        return updated_session, updated_chapter

    def _collect_light_regression_segments(
        self,
        *,
        chapter: ChapterWorkspace,
        accepted_artifact: StoryArtifact,
    ) -> list[StoryArtifact]:
        accepted_segments = [
            item
            for item in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter.chapter_workspace_id
            )
            if item.status.value == "accepted" and item.artifact_kind.value == "story_segment"
        ]
        if all(item.artifact_id != accepted_artifact.artifact_id for item in accepted_segments):
            accepted_segments.append(accepted_artifact)
        return accepted_segments
