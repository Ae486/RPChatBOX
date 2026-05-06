"""Workflow orchestration for persisted proposal submit/policy/apply."""

from __future__ import annotations

from rp.models.core_mutation import (
    CORE_MUTATION_ORIGIN_DETERMINISTIC_SYSTEM_REFRESH,
    CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY,
    CoreMutationEnvelope,
)
from rp.models.dsl import Layer
from rp.models.post_write_policy import (
    PolicyDecision,
    PostWriteMaintenancePolicy,
    build_balanced_policy,
)
from rp.models.memory_crud import ProposalReceipt, ProposalSubmitInput
from rp.models.worker_memory import WorkerProposalGovernanceMetadata
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
        self._post_write_apply_handler = (
            post_write_apply_handler or PostWriteApplyHandler()
        )
        self._validation_service = validation_service or MemoryCrudValidationService()

    async def submit_and_route(
        self,
        input_model: ProposalSubmitInput,
        *,
        session_id: str | None = None,
        chapter_workspace_id: str | None = None,
        submit_source: str = "tool",
        policy: PostWriteMaintenancePolicy | None = None,
        governance_metadata: WorkerProposalGovernanceMetadata | None = None,
        core_mutation_envelope: CoreMutationEnvelope | None = None,
    ) -> ProposalReceipt:
        effective_core_mutation = (
            core_mutation_envelope
            or self._synthesize_core_mutation_envelope(
                input_model=input_model,
                submit_source=submit_source,
                governance_metadata=governance_metadata,
            )
        )
        return await self._submit_canonical(
            input_model=input_model,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            submit_source=submit_source,
            policy=policy,
            governance_metadata=governance_metadata,
            core_mutation_envelope=effective_core_mutation,
        )

    async def submit_core_mutation(
        self,
        envelope: CoreMutationEnvelope,
        *,
        story_id: str,
        mode: str,
        session_id: str | None = None,
        chapter_workspace_id: str | None = None,
        submit_source: str = "tool",
        policy: PostWriteMaintenancePolicy | None = None,
    ) -> ProposalReceipt:
        input_model = ProposalSubmitInput(
            story_id=story_id,
            mode=mode,
            domain=envelope.domain,
            domain_path=envelope.domain_path,
            operations=envelope.operations,
            base_refs=envelope.base_refs,
            reason=envelope.reason,
            trace_id=None,
        )
        return await self._submit_canonical(
            input_model=input_model,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
            submit_source=submit_source,
            policy=policy,
            governance_metadata=None,
            core_mutation_envelope=envelope,
        )

    async def _submit_canonical(
        self,
        *,
        input_model: ProposalSubmitInput,
        session_id: str | None,
        chapter_workspace_id: str | None,
        submit_source: str,
        policy: PostWriteMaintenancePolicy | None,
        governance_metadata: WorkerProposalGovernanceMetadata | None,
        core_mutation_envelope: CoreMutationEnvelope | None,
    ) -> ProposalReceipt:
        self._validation_service.validate_proposal_submit(input_model)
        effective_policy = policy or self._default_policy(input_model.mode)
        decision = self._aggregate_decision(input_model, effective_policy)
        receipt = self._proposal_repository.create_proposal(
            input_model=input_model,
            status="review_required"
            if decision == PolicyDecision.REVIEW_REQUIRED
            else "pending",
            policy_decision=decision.value,
            submit_source=submit_source,
            governance_metadata=governance_metadata,
            core_mutation_envelope=core_mutation_envelope,
            session_id=session_id,
            chapter_workspace_id=chapter_workspace_id,
        )
        if decision == PolicyDecision.REVIEW_REQUIRED:
            return receipt
        applied_receipt = self._proposal_apply_service.apply_proposal(
            receipt.proposal_id
        )
        return applied_receipt

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

    @staticmethod
    def _synthesize_core_mutation_envelope(
        *,
        input_model: ProposalSubmitInput,
        submit_source: str,
        governance_metadata: WorkerProposalGovernanceMetadata | None,
    ) -> CoreMutationEnvelope | None:
        if not ProposalWorkflowService._operations_are_authoritative(input_model):
            return None
        if governance_metadata is not None:
            return CoreMutationEnvelope(
                identity=governance_metadata.identity,
                origin_kind=CORE_MUTATION_ORIGIN_WORKER_PROPOSAL_APPLY,
                actor=f"worker.{governance_metadata.worker_id}",
                worker_id=governance_metadata.worker_id,
                phase=governance_metadata.phase,
                domain=input_model.domain,
                domain_path=input_model.domain_path,
                operations=list(input_model.operations),
                base_refs=list(input_model.base_refs),
                source_refs=list(governance_metadata.source_refs),
                trace_refs=list(governance_metadata.trace_refs),
                permission_decision=governance_metadata.permission_decision,
                permission_reason_codes=list(
                    governance_metadata.permission_reason_codes
                ),
                reason=input_model.reason,
            )
        if submit_source == "post_write_regression":
            return CoreMutationEnvelope(
                identity=None,
                origin_kind=CORE_MUTATION_ORIGIN_DETERMINISTIC_SYSTEM_REFRESH,
                actor="system.post_write_regression",
                domain=input_model.domain,
                domain_path=input_model.domain_path,
                operations=list(input_model.operations),
                base_refs=list(input_model.base_refs),
                reason=input_model.reason,
            )
        return None

    @staticmethod
    def _operations_are_authoritative(input_model: ProposalSubmitInput) -> bool:
        return bool(input_model.operations) and all(
            operation.target_ref.layer == Layer.CORE_STATE_AUTHORITATIVE
            for operation in input_model.operations
        )
