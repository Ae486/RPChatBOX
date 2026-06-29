"""Post-write regression for longform active-story MVP."""

from __future__ import annotations

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.story.runtime import (
    ChapterWorkspace,
    LongformTurnCommandKind,
    SpecialistResultBundle,
    StoryArtifact,
    StoryArtifactKind,
    StoryArtifactStatus,
    StorySession,
)
from rp.models.proposal.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from ..core_state.authoritative_compatibility_mirror_service import (
    AuthoritativeCompatibilityMirrorService,
)
from ..core_state.legacy_state_patch_proposal_builder import LegacyStatePatchProposalBuilder
from .longform_orchestrator_service import LongformOrchestratorService
from .longform_specialist_service import LongformSpecialistService
from ..projection.refresh_service import ProjectionRefreshService
from ..proposal.workflow_service import ProposalWorkflowService
from ..recall.character_long_history_ingestion_service import (
    RecallCharacterLongHistoryIngestionService,
)
from ..recall.continuity_note_ingestion_service import (
    RecallContinuityNoteIngestionService,
)
from ..recall.detail_ingestion_service import RecallDetailIngestionService
from ..recall.retired_foreshadow_ingestion_service import (
    RecallRetiredForeshadowIngestionService,
)
from ..recall.summary_ingestion_service import RecallSummaryIngestionService
from ..story.session_service import StorySessionService


class LongformRegressionService:
    """Digest accepted artifacts back into session/chapter runtime state."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        orchestrator_service: LongformOrchestratorService,
        specialist_service: LongformSpecialistService,
        proposal_workflow_service: ProposalWorkflowService,
        legacy_state_patch_proposal_builder: LegacyStatePatchProposalBuilder
        | None = None,
        projection_refresh_service: ProjectionRefreshService | None = None,
        recall_summary_ingestion_service: RecallSummaryIngestionService | None = None,
        recall_detail_ingestion_service: RecallDetailIngestionService | None = None,
        recall_continuity_note_ingestion_service: RecallContinuityNoteIngestionService
        | None = None,
        recall_character_long_history_ingestion_service: RecallCharacterLongHistoryIngestionService
        | None = None,
        recall_retired_foreshadow_ingestion_service: RecallRetiredForeshadowIngestionService
        | None = None,
        mirror_service: AuthoritativeCompatibilityMirrorService | None = None,
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
            projection_refresh_service
            or ProjectionRefreshService(story_session_service)
        )
        self._recall_summary_ingestion_service = recall_summary_ingestion_service
        self._recall_detail_ingestion_service = recall_detail_ingestion_service
        self._recall_continuity_note_ingestion_service = (
            recall_continuity_note_ingestion_service
        )
        self._recall_character_long_history_ingestion_service = (
            recall_character_long_history_ingestion_service
        )
        self._recall_retired_foreshadow_ingestion_service = (
            recall_retired_foreshadow_ingestion_service
        )
        self._mirror_service = mirror_service
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
        runtime_identity: MemoryRuntimeIdentity | None = None,
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
        updated_session = (
            self._story_session_service.get_session(session.session_id) or session
        )
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
        accepted_segments = self._list_accepted_story_segments(
            chapter_workspace_id=chapter.chapter_workspace_id
        )
        if all(
            item.artifact_id != accepted_artifact.artifact_id
            for item in accepted_segments
        ):
            accepted_segments.append(accepted_artifact)
        return accepted_segments

    def _list_accepted_story_segments(
        self,
        *,
        chapter_workspace_id: str,
    ) -> list[StoryArtifact]:
        return [
            item
            for item in self._story_session_service.list_artifacts(
                chapter_workspace_id=chapter_workspace_id
            )
            if (
                item.status == StoryArtifactStatus.ACCEPTED
                and item.artifact_kind == StoryArtifactKind.STORY_SEGMENT
            )
        ]

