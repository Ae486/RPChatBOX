"""In-memory proposal service for RP Phase A."""
from __future__ import annotations

from datetime import UTC, datetime
import uuid

from rp.models.memory_crud import ProposalReceipt, ProposalSubmitInput
from rp.services.memory_crud_validation_service import MemoryCrudValidationService


class ProposalService:
    """Minimal pending-only proposal service."""

    def __init__(self, *, validation_service: MemoryCrudValidationService | None = None):
        self._validation_service = validation_service or MemoryCrudValidationService()
        self._pending: dict[str, ProposalReceipt] = {}

    async def submit(self, input_model: ProposalSubmitInput) -> ProposalReceipt:
        self._validation_service.validate_proposal_submit(input_model)
        receipt = ProposalReceipt(
            proposal_id=f"proposal_{uuid.uuid4().hex[:12]}",
            status="pending",
            mode=input_model.mode,
            domain=input_model.domain,
            domain_path=input_model.domain_path,
            operation_kinds=[operation.kind for operation in input_model.operations],
            created_at=datetime.now(UTC),
        )
        self._pending[receipt.proposal_id] = receipt
        return receipt

