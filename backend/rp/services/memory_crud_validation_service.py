"""Validation helpers for RP memory CRUD contracts."""
from __future__ import annotations

from rp.models.memory_crud import (
    AppendEventOp,
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    PatchFieldsOp,
    ProposalSubmitInput,
    UpsertRecordOp,
)


class MemoryCrudValidationService:
    """Centralized lightweight validation before storage is implemented."""

    _PHASE_E_SUPPORTED_PROPOSAL_OPS = (
        PatchFieldsOp,
        UpsertRecordOp,
        AppendEventOp,
    )

    @staticmethod
    def validate_get_state(input_model: MemoryGetStateInput) -> None:
        if not input_model.refs and input_model.domain is None:
            raise ValueError("get_state requires refs or domain")

    @staticmethod
    def validate_get_summary(input_model: MemoryGetSummaryInput) -> None:
        if not input_model.summary_ids and not input_model.domains:
            raise ValueError("get_summary requires summary_ids or domains")

    @staticmethod
    def validate_search_recall(input_model: MemorySearchRecallInput) -> None:
        if input_model.top_k <= 0:
            raise ValueError("top_k must be greater than 0")

    @staticmethod
    def validate_search_archival(input_model: MemorySearchArchivalInput) -> None:
        if input_model.top_k <= 0:
            raise ValueError("top_k must be greater than 0")

    @staticmethod
    def validate_list_versions(input_model: MemoryListVersionsInput) -> None:
        if not input_model.target_ref.object_id:
            raise ValueError("target_ref.object_id is required")

    @staticmethod
    def validate_read_provenance(input_model: MemoryReadProvenanceInput) -> None:
        if not input_model.target_ref.object_id:
            raise ValueError("target_ref.object_id is required")

    @staticmethod
    def validate_proposal_submit(input_model: ProposalSubmitInput) -> None:
        if not input_model.operations:
            raise ValueError("proposal.submit requires at least one operation")
        for operation in input_model.operations:
            if operation.target_ref.domain != input_model.domain:
                raise ValueError("operation target_ref.domain must match proposal domain")
            if not isinstance(operation, MemoryCrudValidationService._PHASE_E_SUPPORTED_PROPOSAL_OPS):
                raise ValueError(f"phase_e_operation_not_supported:{operation.kind}")
