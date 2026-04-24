"""Proposal service backed by persisted workflow routing."""
from __future__ import annotations

from sqlmodel import Session

from rp.models.memory_crud import ProposalReceipt, ProposalSubmitInput
from rp.services.memory_crud_validation_service import MemoryCrudValidationService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from services.database import get_engine


class ProposalService:
    """Submit proposals through persisted policy/apply workflow."""

    def __init__(
        self,
        *,
        validation_service: MemoryCrudValidationService | None = None,
        proposal_workflow_factory=None,
    ):
        self._validation_service = validation_service or MemoryCrudValidationService()
        self._proposal_workflow_factory = proposal_workflow_factory or self._build_default_workflow

    async def submit(self, input_model: ProposalSubmitInput) -> ProposalReceipt:
        self._validation_service.validate_proposal_submit(input_model)
        with Session(get_engine()) as session:
            workflow = self._proposal_workflow_factory(session)
            try:
                receipt = await workflow.submit_and_route(
                    input_model,
                    submit_source="tool",
                )
                session.commit()
                return receipt
            except Exception:
                session.commit()
                raise

    def _build_default_workflow(self, session: Session) -> ProposalWorkflowService:
        repository = ProposalRepository(session)
        story_session_service = StorySessionService(session)
        apply_service = ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
        )
        return ProposalWorkflowService(
            proposal_repository=repository,
            proposal_apply_service=apply_service,
            post_write_apply_handler=PostWriteApplyHandler(),
            validation_service=self._validation_service,
        )
