"""Node adapters for the phase-1 SetupGraph shell."""
from __future__ import annotations

from rp.models.setup_handoff import SetupContextBuilderInput
from rp.models.setup_agent import SetupAgentDialogueMessage, SetupAgentTurnRequest
from rp.models.setup_workspace import SetupStepId
from rp.services.setup_agent_execution_service import SetupAgentExecutionService
from rp.services.setup_context_builder import SetupContextBuilder
from rp.services.setup_workspace_service import SetupWorkspaceService

from .setup_graph_state import SetupGraphState


class SetupGraphNodes:
    """Wrap current setup services as coarse LangGraph nodes."""

    def __init__(
        self,
        *,
        workspace_service: SetupWorkspaceService,
        context_builder: SetupContextBuilder,
        execution_service: SetupAgentExecutionService,
    ) -> None:
        self._workspace_service = workspace_service
        self._context_builder = context_builder
        self._execution_service = execution_service

    def load_workspace(self, state: SetupGraphState) -> SetupGraphState:
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
        target_step = state.get("target_step") or workspace.current_step.value
        return {
            "mode": workspace.mode.value,
            "current_step": workspace.current_step.value,
            "target_step": target_step,
            "status": "workspace_loaded",
        }

    def build_context(self, state: SetupGraphState) -> SetupGraphState:
        if state.get("error"):
            return {}
        target_step = str(state.get("target_step") or state.get("current_step") or "")
        packet = self._context_builder.build(
            SetupContextBuilderInput(
                mode=str(state.get("mode") or ""),
                workspace_id=state["workspace_id"],
                current_step=target_step,
                user_prompt=str(state.get("user_prompt") or ""),
                user_edit_delta_ids=list(state.get("user_edit_delta_ids") or []),
                token_budget=None,
            )
        )
        return {
            "context_packet": packet.model_dump(mode="json"),
            "status": "context_built",
        }

    async def run_turn(self, state: SetupGraphState) -> SetupGraphState:
        if state.get("error"):
            return {}
        response = await self._execution_service.run_turn(self._request_from_state(state))
        runtime_result = self._execution_service.last_runtime_result
        update: SetupGraphState = {
            "assistant_text": response.assistant_text,
            "status": "completed",
        }
        if runtime_result is None:
            return update
        update["finish_reason"] = runtime_result.finish_reason
        if runtime_result.warnings:
            update["warnings"] = list(runtime_result.warnings)
        if runtime_result.structured_payload:
            update["response_payload"] = dict(runtime_result.structured_payload)
        if runtime_result.status == "failed":
            error = runtime_result.error or {
                "message": runtime_result.finish_reason,
                "type": "setup_runtime_failed",
            }
            update["status"] = "failed"
            update["error"] = {
                "message": str(error.get("message") or "Setup runtime failed"),
                "type": str(error.get("type") or runtime_result.finish_reason),
            }
        return update

    def finalize_stream(self, state: SetupGraphState) -> SetupGraphState:
        return {}

    @staticmethod
    def _request_from_state(state: SetupGraphState) -> SetupAgentTurnRequest:
        return SetupAgentTurnRequest(
            workspace_id=state["workspace_id"],
            model_id=state["model_id"],
            provider_id=state.get("provider_id"),
            target_step=(
                SetupStepId(state["target_step"]) if state.get("target_step") else None
            ),
            history=[
                SetupAgentDialogueMessage.model_validate(item)
                for item in state.get("history", [])
            ],
            user_edit_delta_ids=list(state.get("user_edit_delta_ids") or []),
            user_prompt=str(state.get("user_prompt") or ""),
        )
