"""Governed Block-addressed mutation adapter over the existing proposal workflow."""

from __future__ import annotations

from rp.models.block_view import RpBlockView
from rp.models.dsl import Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryBlockProposalSubmitRequest,
    ProposalReceipt,
    ProposalSubmitInput,
    StatePatchOperation,
)

from .memory_inspection_read_service import MemoryInspectionReadService
from .proposal_apply_service import ProposalApplyService
from .proposal_workflow_service import ProposalWorkflowService
from .rp_block_read_service import RpBlockReadService
from .story_session_service import StorySessionService


class MemoryBlockMutationUnsupportedError(RuntimeError):
    """Raised when a resolved Block does not support governed mutation."""


class MemoryBlockTargetMismatchError(RuntimeError):
    """Raised when a submitted operation targets the wrong Block identity."""


class MemoryBlockProposalNotFoundError(RuntimeError):
    """Raised when a proposal is not visible from the addressed session/block path."""


class StoryBlockMutationService:
    """Resolve one Block path and submit the mutation through the canonical workflow."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        rp_block_read_service: RpBlockReadService,
        memory_inspection_read_service: MemoryInspectionReadService,
        proposal_apply_service: ProposalApplyService,
        proposal_workflow_service: ProposalWorkflowService,
    ) -> None:
        self._story_session_service = story_session_service
        self._rp_block_read_service = rp_block_read_service
        self._memory_inspection_read_service = memory_inspection_read_service
        self._proposal_apply_service = proposal_apply_service
        self._proposal_workflow_service = proposal_workflow_service

    async def submit_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: MemoryBlockProposalSubmitRequest,
    ) -> ProposalReceipt | None:
        session = self._require_session(session_id)
        chapter = self._story_session_service.get_current_chapter(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        self._ensure_block_mutable(block)

        canonical_target_ref = self._block_ref(block)
        operations = self._normalize_operations(
            payload.operations,
            target_ref=canonical_target_ref,
        )
        input_model = ProposalSubmitInput(
            story_id=session.story_id,
            mode=session.mode,
            domain=block.domain,
            domain_path=block.domain_path,
            operations=operations,
            base_refs=payload.base_refs,
            reason=payload.reason,
            trace_id=payload.trace_id,
        )
        try:
            receipt = await self._proposal_workflow_service.submit_and_route(
                input_model,
                session_id=session_id,
                chapter_workspace_id=(
                    chapter.chapter_workspace_id if chapter is not None else None
                ),
                submit_source="api.memory.block",
            )
            self._story_session_service.commit()
            return receipt
        except Exception:
            # Mirror ProposalService semantics so any persisted proposal status
            # transition survives even when workflow/apply raises.
            self._story_session_service.commit()
            raise

    def apply_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> ProposalReceipt | None:
        session = self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        self._ensure_block_mutable(block)
        proposal = self._memory_inspection_read_service.get_proposal_for_authoritative_ref(
            story_id=session.story_id,
            session_id=session_id,
            target_ref=self._block_ref(block),
            proposal_id=proposal_id,
        )
        if proposal is None:
            raise MemoryBlockProposalNotFoundError(
                f"Memory block proposal not found: {proposal_id}"
            )
        try:
            receipt = self._proposal_apply_service.apply_proposal(proposal_id)
            self._story_session_service.commit()
            return receipt
        except Exception:
            self._story_session_service.commit()
            raise

    def _require_session(self, session_id: str):
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return session

    @staticmethod
    def _ensure_block_mutable(block: RpBlockView) -> None:
        if block.metadata.get("read_only") is True:
            raise MemoryBlockMutationUnsupportedError(
                "Memory block mutation only supports authoritative blocks; "
                "resolved block is read-only"
            )
        if block.layer != Layer.CORE_STATE_AUTHORITATIVE:
            raise MemoryBlockMutationUnsupportedError(
                "Memory block mutation only supports authoritative blocks"
            )

    def _normalize_operations(
        self,
        operations: list[StatePatchOperation],
        *,
        target_ref: ObjectRef,
    ) -> list[StatePatchOperation]:
        target_identity = self._target_identity(target_ref)
        normalized: list[StatePatchOperation] = []
        for operation in operations:
            if self._target_identity(operation.target_ref) != target_identity:
                raise MemoryBlockTargetMismatchError(
                    "Operation target_ref must match the resolved authoritative block"
                )
            normalized.append(operation.model_copy(update={"target_ref": target_ref}))
        return normalized

    @staticmethod
    def _target_identity(ref: ObjectRef) -> tuple[str, str, str, str, str]:
        return (
            ref.object_id,
            ref.layer.value,
            ref.domain.value,
            ref.domain_path or ref.object_id,
            ref.scope or "story",
        )

    @staticmethod
    def _block_ref(block: RpBlockView) -> ObjectRef:
        return ObjectRef(
            object_id=block.label,
            layer=block.layer,
            domain=block.domain,
            domain_path=block.domain_path,
            scope=block.scope,
            revision=block.revision,
        )
