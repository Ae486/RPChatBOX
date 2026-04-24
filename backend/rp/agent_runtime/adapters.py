"""Project-layer adapters for the RP agent runtime."""
from __future__ import annotations

from models.chat import ProviderConfig
from rp.agent_runtime.contracts import (
    RpAgentTurnInput,
    RpAgentTurnResult,
    RuntimeProfile,
    SetupCognitiveStateSnapshot,
    SetupCognitiveStateSummary,
)
from rp.agent_runtime.profiles import SETUP_AGENT_VISIBLE_TOOLS, build_setup_agent_profile
from rp.models.setup_agent import SetupAgentTurnRequest, SetupAgentTurnResponse
from rp.models.setup_handoff import SetupContextPacket
from rp.models.setup_workspace import CommitProposalStatus, QuestionSeverity, QuestionStatus
from rp.services.setup_agent_prompt_service import SetupAgentPromptService


class SetupRuntimeAdapter:
    """Map setup-layer objects into runtime-internal contracts."""

    def __init__(
        self,
        *,
        prompt_service: SetupAgentPromptService | None = None,
    ) -> None:
        self._prompt_service = prompt_service or SetupAgentPromptService()

    def build_turn_input(
        self,
        *,
        request: SetupAgentTurnRequest,
        workspace,
        context_packet: SetupContextPacket,
        model_name: str,
        provider: ProviderConfig,
        cognitive_state: SetupCognitiveStateSnapshot | None = None,
        cognitive_state_summary: SetupCognitiveStateSummary | None = None,
    ) -> RpAgentTurnInput:
        current_step = request.target_step or workspace.current_step
        system_prompt = self._prompt_service.build_system_prompt(
            mode=workspace.mode,
            current_step=current_step,
            context_packet=context_packet,
        )
        open_questions = [
            question
            for question in workspace.open_questions
            if question.step_id == current_step and question.status == QuestionStatus.OPEN
        ]
        blocking_open_questions = [
            question
            for question in open_questions
            if question.severity == QuestionSeverity.BLOCKING
        ]
        latest_proposal = self._latest_step_proposal(workspace=workspace, current_step=current_step)
        step_state = next(
            (item for item in workspace.step_states if item.step_id == current_step),
            None,
        )
        return RpAgentTurnInput(
            profile_id="setup_agent",
            run_kind="interactive_agent_turn",
            story_id=workspace.story_id,
            workspace_id=workspace.workspace_id,
            model_id=request.model_id,
            provider_id=request.provider_id,
            stream=False,
            user_visible_request=request.user_prompt,
            conversation_messages=[item.model_dump(mode="json") for item in request.history],
            context_bundle={
                "system_prompt": system_prompt,
                "context_packet": context_packet.model_dump(mode="json", exclude_none=True),
                "mode": workspace.mode.value,
                "current_step": current_step.value,
                "step_state": (
                    step_state.model_dump(mode="json", exclude_none=True)
                    if step_state is not None
                    else None
                ),
                "step_readiness": workspace.readiness_status.step_readiness.get(current_step.value),
                "open_question_count": len(open_questions),
                "blocking_open_question_count": len(blocking_open_questions),
                "open_question_texts": [question.text for question in open_questions[:5]],
                "has_user_edit_deltas": bool(context_packet.user_edit_deltas),
                "last_proposal_status": (
                    latest_proposal.status.value if latest_proposal is not None else None
                ),
                "has_rejected_commit_proposal": bool(
                    latest_proposal is not None
                    and latest_proposal.status == CommitProposalStatus.REJECTED
                ),
                "cognitive_state": (
                    cognitive_state.model_dump(mode="json", exclude_none=True)
                    if cognitive_state is not None
                    else None
                ),
                "cognitive_state_summary": (
                    cognitive_state_summary.model_dump(mode="json", exclude_none=True)
                    if cognitive_state_summary is not None
                    else None
                ),
                "cognitive_state_invalidated": bool(
                    cognitive_state_summary is not None and cognitive_state_summary.invalidated
                ),
            },
            tool_scope=list(SETUP_AGENT_VISIBLE_TOOLS),
            metadata={
                "model_name": model_name,
                "provider": provider.model_dump(mode="json", exclude_none=True),
            },
        )

    @staticmethod
    def to_turn_response(result: RpAgentTurnResult) -> SetupAgentTurnResponse:
        return SetupAgentTurnResponse(assistant_text=result.assistant_text)

    @staticmethod
    def build_runtime_profile() -> RuntimeProfile:
        return build_setup_agent_profile()

    @staticmethod
    def _latest_step_proposal(*, workspace, current_step):
        proposals = [
            proposal
            for proposal in workspace.commit_proposals
            if proposal.step_id == current_step
        ]
        if not proposals:
            return None
        return max(proposals, key=lambda item: item.created_at)
