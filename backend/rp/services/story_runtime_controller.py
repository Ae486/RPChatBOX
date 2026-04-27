"""Active-story longform read/list/activate facade."""

from __future__ import annotations

from typing import Any

from rp.models.block_view import BlockSource, RpBlockView
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryBlockProposalSubmitRequest,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProvenanceResult,
    VersionListResult,
)
from rp.models.story_runtime import (
    ChapterWorkspaceSnapshot,
    StoryActivationResult,
    StorySession,
)
from .memory_inspection_read_service import MemoryInspectionReadService
from .projection_read_service import ProjectionReadService
from .provenance_read_service import ProvenanceReadService
from .rp_block_read_service import RpBlockReadService
from .story_block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    MemoryBlockProposalNotFoundError,
    StoryBlockMutationService,
)
from .story_block_consumer_state_service import StoryBlockConsumerStateService
from .story_activation_service import StoryActivationService
from .story_session_service import StorySessionService
from .version_history_read_service import VersionHistoryReadService


class MemoryBlockHistoryUnsupportedError(RuntimeError):
    """Raised when a Block envelope has no read-only history/provenance backend."""


class StoryRuntimeController:
    """Thin facade for activation, read-model access, and governed Block mutation."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        story_activation_service: StoryActivationService,
        version_history_read_service: VersionHistoryReadService,
        provenance_read_service: ProvenanceReadService,
        projection_read_service: ProjectionReadService,
        memory_inspection_read_service: MemoryInspectionReadService,
        rp_block_read_service: RpBlockReadService,
        story_block_mutation_service: StoryBlockMutationService | None = None,
        story_block_consumer_state_service: StoryBlockConsumerStateService
        | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._story_activation_service = story_activation_service
        self._version_history_read_service = version_history_read_service
        self._provenance_read_service = provenance_read_service
        self._projection_read_service = projection_read_service
        self._memory_inspection_read_service = memory_inspection_read_service
        self._rp_block_read_service = rp_block_read_service
        self._story_block_mutation_service = story_block_mutation_service
        self._story_block_consumer_state_service = story_block_consumer_state_service

    def activate_workspace(self, *, workspace_id: str) -> StoryActivationResult:
        return self._story_activation_service.activate_workspace(
            workspace_id=workspace_id
        )

    def list_sessions(self) -> list[StorySession]:
        return self._story_session_service.list_sessions()

    def read_session(self, *, session_id: str) -> ChapterWorkspaceSnapshot:
        session = self._require_session(session_id)
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=session.current_chapter_index,
        )

    def read_chapter(
        self, *, session_id: str, chapter_index: int
    ) -> ChapterWorkspaceSnapshot:
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=chapter_index,
        )

    def update_runtime_story_config(
        self,
        *,
        session_id: str,
        patch: dict[str, Any],
    ) -> ChapterWorkspaceSnapshot:
        updated_session = self._story_session_service.update_session(
            session_id=session_id,
            runtime_story_config_patch=patch,
        )
        self._story_session_service.commit()
        return self._story_session_service.build_chapter_snapshot(
            session_id=session_id,
            chapter_index=updated_session.current_chapter_index,
        )

    def list_memory_authoritative(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        return self._memory_inspection_read_service.list_authoritative_objects(
            session_id=session_id
        )

    def list_memory_projection(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        return self._memory_inspection_read_service.list_projection_slots(
            session_id=session_id
        )

    def list_memory_blocks(
        self,
        *,
        session_id: str,
        layer: Layer | None = None,
        source: BlockSource | None = None,
    ) -> list[dict]:
        self._require_session(session_id)
        return [
            block.model_dump(mode="json")
            for block in self._rp_block_read_service.list_blocks(
                session_id=session_id,
                layer=layer,
                source=source,
            )
        ]

    def get_memory_block(self, *, session_id: str, block_id: str) -> dict | None:
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        return block.model_dump(mode="json")

    async def read_memory_block_versions(
        self,
        *,
        session_id: str,
        block_id: str,
    ) -> VersionListResult | None:
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        block_ref = self._block_ref(block)
        if block.layer == Layer.CORE_STATE_AUTHORITATIVE:
            return self._version_history_read_service.list_versions(
                block_ref,
                session_id=session_id,
            )
        if block.layer == Layer.CORE_STATE_PROJECTION:
            return await self._projection_read_service.list_versions(
                MemoryListVersionsInput(target_ref=block_ref),
                session_id=session_id,
            )
        raise MemoryBlockHistoryUnsupportedError(
            f"Memory block history is unsupported for layer: {block.layer.value}"
        )

    async def read_memory_block_provenance(
        self,
        *,
        session_id: str,
        block_id: str,
    ) -> ProvenanceResult | None:
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        block_ref = self._block_ref(block)
        if block.layer == Layer.CORE_STATE_AUTHORITATIVE:
            return self._provenance_read_service.read_provenance(
                block_ref,
                session_id=session_id,
            )
        if block.layer == Layer.CORE_STATE_PROJECTION:
            return await self._projection_read_service.read_provenance(
                MemoryReadProvenanceInput(target_ref=block_ref),
                session_id=session_id,
            )
        raise MemoryBlockHistoryUnsupportedError(
            f"Memory block provenance is unsupported for layer: {block.layer.value}"
        )

    def list_memory_proposals(
        self,
        *,
        session_id: str,
        status: str | None = None,
    ) -> list[dict]:
        session = self._require_session(session_id)
        return self._memory_inspection_read_service.list_proposals(
            story_id=session.story_id,
            session_id=session_id,
            status=status,
        )

    def list_memory_block_proposals(
        self,
        *,
        session_id: str,
        block_id: str,
        status: str | None = None,
    ) -> list[dict] | None:
        session = self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        if block.layer != Layer.CORE_STATE_AUTHORITATIVE:
            return []
        return (
            self._memory_inspection_read_service.list_proposals_for_authoritative_ref(
                story_id=session.story_id,
                session_id=session_id,
                target_ref=self._block_ref(block),
                status=status,
            )
        )

    def get_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> dict | None:
        session = self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        if block.layer != Layer.CORE_STATE_AUTHORITATIVE:
            raise MemoryBlockMutationUnsupportedError(
                "Memory block proposal detail only supports authoritative blocks"
            )
        detail = (
            self._memory_inspection_read_service.get_proposal_for_authoritative_ref(
                story_id=session.story_id,
                session_id=session_id,
                target_ref=self._block_ref(block),
                proposal_id=proposal_id,
            )
        )
        if detail is None:
            raise MemoryBlockProposalNotFoundError(
                f"Memory block proposal not found: {proposal_id}"
            )
        return detail

    async def submit_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: MemoryBlockProposalSubmitRequest,
    ) -> dict | None:
        if self._story_block_mutation_service is None:
            raise RuntimeError("story_block_mutation_service_not_configured")
        receipt = await self._story_block_mutation_service.submit_block_proposal(
            session_id=session_id,
            block_id=block_id,
            payload=payload,
        )
        if receipt is None:
            return None
        return receipt.model_dump(mode="json")

    def apply_memory_block_proposal(
        self,
        *,
        session_id: str,
        block_id: str,
        proposal_id: str,
    ) -> dict | None:
        if self._story_block_mutation_service is None:
            raise RuntimeError("story_block_mutation_service_not_configured")
        self._require_session(session_id)
        block = self._rp_block_read_service.get_block(
            session_id=session_id,
            block_id=block_id,
        )
        if block is None:
            return None
        self._story_block_mutation_service.apply_block_proposal(
            session_id=session_id,
            block_id=block_id,
            proposal_id=proposal_id,
        )
        return self.get_memory_block_proposal(
            session_id=session_id,
            block_id=block_id,
            proposal_id=proposal_id,
        )

    def list_memory_block_consumers(self, *, session_id: str) -> list[dict]:
        self._require_session(session_id)
        if self._story_block_consumer_state_service is None:
            return []
        return [
            item.model_dump(mode="json")
            for item in self._story_block_consumer_state_service.list_consumers(
                session_id=session_id
            )
        ]

    def get_memory_block_consumer(
        self,
        *,
        session_id: str,
        consumer_key: str,
    ) -> dict | None:
        self._require_session(session_id)
        if self._story_block_consumer_state_service is None:
            return None
        item = self._story_block_consumer_state_service.get_consumer(
            session_id=session_id,
            consumer_key=consumer_key,
        )
        if item is None:
            return None
        return item.model_dump(mode="json")

    def read_memory_versions(
        self,
        *,
        session_id: str,
        object_id: str,
        domain: Domain,
        domain_path: str | None = None,
    ) -> VersionListResult:
        self._require_session(session_id)
        return self._version_history_read_service.list_versions(
            self._build_authoritative_ref(
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
            ),
            session_id=session_id,
        )

    def read_memory_provenance(
        self,
        *,
        session_id: str,
        object_id: str,
        domain: Domain,
        domain_path: str | None = None,
    ) -> ProvenanceResult:
        self._require_session(session_id)
        return self._provenance_read_service.read_provenance(
            self._build_authoritative_ref(
                object_id=object_id,
                domain=domain,
                domain_path=domain_path,
            ),
            session_id=session_id,
        )

    def _require_session(self, session_id: str) -> StorySession:
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise ValueError(f"StorySession not found: {session_id}")
        return session

    @staticmethod
    def _build_authoritative_ref(
        *,
        object_id: str,
        domain: Domain,
        domain_path: str | None,
    ) -> ObjectRef:
        return ObjectRef(
            object_id=object_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=domain,
            domain_path=domain_path or object_id,
            scope="story",
            revision=1,
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
