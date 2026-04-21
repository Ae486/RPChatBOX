"""Node adapters for the phase-1 ActivationGraph shell."""
from __future__ import annotations

from rp.models.story_runtime import LongformChapterPhase
from rp.services.setup_runtime_controller import SetupRuntimeController
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_activation_service import StoryActivationService
from rp.services.story_session_service import StorySessionService

from .activation_graph_state import ActivationGraphState


class ActivationGraphNodes:
    """Wrap current activation services as coarse LangGraph nodes."""

    def __init__(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        setup_controller: SetupRuntimeController,
        story_session_service: StorySessionService,
    ) -> None:
        self._workspace_service = workspace_service
        self._setup_controller = setup_controller
        self._story_session_service = story_session_service

    def load_workspace(self, state: ActivationGraphState) -> ActivationGraphState:
        if state.get("error"):
            return {}
        workspace = self._workspace_service.get_workspace(state["workspace_id"])
        if workspace is None:
            return {
                "error": {
                    "message": f"SetupWorkspace not found: {state['workspace_id']}",
                    "type": "setup_workspace_not_found",
                },
                "status": "failed",
            }
        if workspace.activated_story_session_id:
            existing = self._story_session_service.get_session(workspace.activated_story_session_id)
            if existing is not None:
                return {
                    "status": "completed",
                    "activation_result": {
                        "session_id": existing.session_id,
                        "story_id": existing.story_id,
                        "source_workspace_id": existing.source_workspace_id,
                        "current_chapter_index": existing.current_chapter_index,
                        "current_phase": existing.current_phase.value,
                        "initial_outline_required": True,
                    },
                }
        return {"status": "workspace_loaded"}

    def run_activation_check(self, state: ActivationGraphState) -> ActivationGraphState:
        if state.get("error") or state.get("activation_result"):
            return {}
        result = self._setup_controller.run_activation_check(workspace_id=state["workspace_id"])
        if result is None:
            return {
                "error": {
                    "message": f"SetupWorkspace not found: {state['workspace_id']}",
                    "type": "setup_workspace_not_found",
                },
                "status": "failed",
            }
        if not result.ready or result.handoff is None:
            return {
                "error": {
                    "message": "Workspace is not ready for activation"
                    + (f": {'; '.join(result.blocking_issues)}" if result.blocking_issues else ""),
                    "type": "story_activation_failed",
                },
                "status": "failed",
            }
        return {
            "handoff_payload": result.handoff.model_dump(mode="json"),
            "status": "activation_checked",
        }

    def seed_story_session(self, state: ActivationGraphState) -> ActivationGraphState:
        if state.get("error") or state.get("activation_result"):
            return {}
        workspace = self._workspace_service.get_workspace(state["workspace_id"])
        handoff = dict(state.get("handoff_payload") or {})
        if workspace is None or not handoff:
            return {
                "error": {
                    "message": "Activation handoff missing",
                    "type": "story_activation_failed",
                },
                "status": "failed",
            }
        initial_phase = LongformChapterPhase.OUTLINE_DRAFTING
        session = self._story_session_service.create_session(
            story_id=str(handoff["story_id"]),
            source_workspace_id=str(handoff["workspace_id"]),
            mode=str(handoff["mode"]),
            runtime_story_config=dict(handoff["runtime_story_config"]),
            writer_contract=dict(handoff["writer_contract"]),
            current_state_json=StoryActivationService._initial_current_state(workspace),
            initial_phase=initial_phase,
        )
        return {
            "session_id": session.session_id,
            "story_id": session.story_id,
            "source_workspace_id": session.source_workspace_id,
            "current_chapter_index": session.current_chapter_index,
            "current_phase": session.current_phase.value,
            "chapter_goal": StoryActivationService._chapter_goal(workspace, chapter_index=1),
            "builder_snapshot_json": StoryActivationService._initial_builder_snapshot(workspace),
            "status": "session_seeded",
        }

    def seed_first_chapter_workspace(self, state: ActivationGraphState) -> ActivationGraphState:
        if state.get("error") or state.get("activation_result"):
            return {}
        self._story_session_service.create_chapter_workspace(
            session_id=str(state["session_id"]),
            chapter_index=1,
            phase=LongformChapterPhase.OUTLINE_DRAFTING,
            chapter_goal=state.get("chapter_goal"),
            builder_snapshot_json=dict(state.get("builder_snapshot_json") or {}),
        )
        return {"status": "chapter_seeded"}

    def mark_workspace_activated(self, state: ActivationGraphState) -> ActivationGraphState:
        if state.get("error"):
            return {}
        if state.get("activation_result"):
            return {"status": "completed"}
        self._workspace_service.mark_activated_story_session(
            workspace_id=state["workspace_id"],
            session_id=str(state["session_id"]),
        )
        return {
            "status": "completed",
            "activation_result": {
                "session_id": state["session_id"],
                "story_id": state["story_id"],
                "source_workspace_id": state["source_workspace_id"],
                "current_chapter_index": state["current_chapter_index"],
                "current_phase": state["current_phase"],
                "initial_outline_required": True,
            },
        }

    def finalize_activation(self, state: ActivationGraphState) -> ActivationGraphState:
        return {}
