"""Activation bootstrap from SetupWorkspace to active StorySession."""

from __future__ import annotations

from rp.models.story_runtime import LongformChapterPhase, StoryActivationResult
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.setup_runtime_controller import SetupRuntimeController
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_session_service import StorySessionService


class StoryActivationService:
    """Materialize setup truth into one active-story session."""

    def __init__(
        self,
        *,
        setup_controller: SetupRuntimeController,
        workspace_service: SetupWorkspaceService,
        story_session_service: StorySessionService,
        core_state_dual_write_service: CoreStateDualWriteService | None = None,
    ) -> None:
        self._setup_controller = setup_controller
        self._workspace_service = workspace_service
        self._story_session_service = story_session_service
        self._core_state_dual_write_service = core_state_dual_write_service

    def activate_workspace(self, *, workspace_id: str) -> StoryActivationResult:
        workspace = self._workspace_service.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")

        if workspace.activated_story_session_id:
            existing = self._story_session_service.get_session(
                workspace.activated_story_session_id
            )
            if existing is not None:
                return StoryActivationResult(
                    session_id=existing.session_id,
                    story_id=existing.story_id,
                    source_workspace_id=existing.source_workspace_id,
                    current_chapter_index=existing.current_chapter_index,
                    current_phase=existing.current_phase,
                    initial_outline_required=True,
                )

        check = self._setup_controller.run_activation_check(workspace_id=workspace_id)
        if check is None:
            raise ValueError(f"SetupWorkspace not found: {workspace_id}")
        if not check.ready or check.handoff is None:
            raise ValueError(
                "Workspace is not ready for activation"
                + (f": {'; '.join(check.blocking_issues)}" if check.blocking_issues else "")
            )

        initial_phase = LongformChapterPhase.OUTLINE_DRAFTING
        session = self._story_session_service.create_session(
            story_id=check.handoff.story_id,
            source_workspace_id=check.handoff.workspace_id,
            mode=check.handoff.mode.value,
            runtime_story_config=check.handoff.runtime_story_config.model_dump(mode="json"),
            writer_contract=check.handoff.writer_contract.model_dump(mode="json"),
            current_state_json=self._initial_current_state(workspace),
            initial_phase=initial_phase,
        )
        chapter = self._story_session_service.create_chapter_workspace(
            session_id=session.session_id,
            chapter_index=1,
            phase=initial_phase,
            chapter_goal=self._chapter_goal(workspace, chapter_index=1),
            builder_snapshot_json=self._initial_builder_snapshot(workspace),
        )
        if self._core_state_dual_write_service is not None:
            self._core_state_dual_write_service.seed_activation_state(
                session=self._story_session_service.get_session(session.session_id) or session,
                chapter=chapter,
            )
        self._workspace_service.mark_activated_story_session(
            workspace_id=workspace_id,
            session_id=session.session_id,
        )
        return StoryActivationResult(
            session_id=session.session_id,
            story_id=session.story_id,
            source_workspace_id=session.source_workspace_id,
            current_chapter_index=session.current_chapter_index,
            current_phase=session.current_phase,
            initial_outline_required=True,
        )

    @staticmethod
    def _initial_current_state(workspace) -> dict:
        return {
            "chapter_digest": {
                "current_chapter": 1,
                "title": StoryActivationService._chapter_title(workspace, chapter_index=1),
            },
            "narrative_progress": {
                "current_phase": LongformChapterPhase.OUTLINE_DRAFTING.value,
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        }

    @staticmethod
    def _initial_builder_snapshot(workspace) -> dict:
        foundation_digest = [
            commit.summary_tier_1 or commit.summary_tier_0 or f"commit:{commit.commit_id}"
            for commit in workspace.accepted_commits
            if commit.step_id.value == "foundation"
        ]
        blueprint_digest = []
        if workspace.longform_blueprint_draft is not None:
            blueprint = workspace.longform_blueprint_draft
            for value in (
                blueprint.premise,
                blueprint.central_conflict,
                blueprint.protagonist_arc,
                blueprint.chapter_strategy,
                blueprint.ending_direction,
            ):
                if value:
                    blueprint_digest.append(value)
            if blueprint.chapter_blueprints:
                first = blueprint.chapter_blueprints[0]
                if first.title:
                    blueprint_digest.append(first.title)
                if first.purpose:
                    blueprint_digest.append(first.purpose)
                blueprint_digest.extend(first.major_beats)
        return {
            "chapter_index": 1,
            "phase": LongformChapterPhase.OUTLINE_DRAFTING.value,
            "foundation_digest": foundation_digest,
            "blueprint_digest": blueprint_digest,
            "current_outline_digest": [],
            "recent_segment_digest": [],
        }

    @staticmethod
    def _chapter_goal(workspace, *, chapter_index: int) -> str | None:
        if workspace.longform_blueprint_draft is None:
            return workspace.story_config_draft.notes if workspace.story_config_draft else None
        chapter_blueprints = workspace.longform_blueprint_draft.chapter_blueprints
        if len(chapter_blueprints) >= chapter_index:
            entry = chapter_blueprints[chapter_index - 1]
            return entry.purpose or entry.title
        return workspace.longform_blueprint_draft.premise

    @staticmethod
    def _chapter_title(workspace, *, chapter_index: int) -> str | None:
        if workspace.longform_blueprint_draft is None:
            return None
        chapter_blueprints = workspace.longform_blueprint_draft.chapter_blueprints
        if len(chapter_blueprints) >= chapter_index:
            return chapter_blueprints[chapter_index - 1].title
        return None
