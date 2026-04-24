"""Workflow orchestration for persisted proposal submit/policy/apply."""

from __future__ import annotations

from rp.models.post_write_policy import (
    PolicyDecision,
    PostWriteMaintenancePolicy,
    build_balanced_policy,
)
from rp.models.memory_crud import ProposalReceipt, ProposalSubmitInput
from rp.services.memory_crud_validation_service import MemoryCrudValidationService

from .post_write_apply_handler import PostWriteApplyHandler
from .proposal_apply_service import ProposalApplyService
from .proposal_repository import ProposalRepository


class ProposalWorkflowService:
    """Route canonical proposal inputs through persistence, policy, and apply."""

    def __init__(
        self,
        *,
        proposal_repository: ProposalRepository,
        proposal_apply_service: ProposalApplyService,
        post_write_apply_handler: PostWriteApplyHandler | None = None,
        validation_service: MemoryCrudValidationService | None = None,
    ) -> None:
        self._proposal_repository = proposal_repository
        self._proposal_apply_service = proposal_apply_service
        self._post_write_apply_handler = post_write_apply_handler or PostWriteApplyHandler()
        self._validation_service = validation_service or MemoryCrudValidationService()

    async def submit_and_route(
        self,
        input_model: ProposalSubmitInput,
        *,
        session_id: str | None = None,
        chapter_workspace_id: str | None = None,
        submit_source: str = "tool",
        policy: PostWriteMaintenancePolicy | None = None,
    ) -> ProposalReceipt:
        self._validation_service.validate_proposal_submit(input_model)
        effective_policy = policy or self._default_policy(input_model.mode)
        decision = self._aggregate_decision(input_model, effective_policy)
        receipt = self._proposal_repository.create_proposal(
            input_model=input_model,
            status="review_required" if decision == PolicyDecision.REVIEW_REQUIRED else "pending",
            policy_decision=decision.value,
            submit_source=submit_source,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
        )
        if decision == PolicyDecision.REVIEW_REQUIRED:
            return receipt
        return self._proposal_apply_service.apply_proposal(receipt.proposal_id)

    def _aggregate_decision(
        self,
        input_model: ProposalSubmitInput,
        policy: PostWriteMaintenancePolicy,
    ) -> PolicyDecision:
        decisions: list[PolicyDecision] = []
        for operation in input_model.operations:
            decision = self._post_write_apply_handler.decide(
                mode=input_model.mode,
                domain=input_model.domain.value,
                domain_path=operation.target_ref.domain_path or input_model.domain_path,
                operation_kind=operation.kind,
                policy=policy,
            )
            decisions.append(decision)
        if PolicyDecision.REVIEW_REQUIRED in decisions:
            return PolicyDecision.REVIEW_REQUIRED
        if PolicyDecision.NOTIFY_APPLY in decisions:
            return PolicyDecision.NOTIFY_APPLY
        return PolicyDecision.SILENT

    @staticmethod
    def _default_policy(mode: str) -> PostWriteMaintenancePolicy:
        if mode == "longform":
            return build_balanced_policy()
        return build_balanced_policy()
