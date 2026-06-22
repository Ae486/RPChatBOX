"""Maintenance-lock guarded story runtime controller wrapper."""

from __future__ import annotations

from typing import Any

from rp.models.proposal.core_mutation import DirectCoreEditRequest
from rp.models.runtime.identity import BranchControlReceipt
from rp.models.story.archival_evolution import ArchivalEvolutionRequest
from rp.models.story.runtime import ChapterWorkspaceSnapshot
from rp.services.runtime.maintenance_lock_service import RuntimeMaintenanceOperation

from .maintenance_guard_service import StoryRuntimeMaintenanceGuardService
from .runtime_controller import StoryRuntimeController


class MaintenanceGuardedStoryRuntimeController(StoryRuntimeController):
    """Add service-layer maintenance guards around mutating controller entrypoints."""

    def __init__(
        self,
        *,
        runtime_maintenance_guard_service: StoryRuntimeMaintenanceGuardService,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._runtime_maintenance_guard_service = runtime_maintenance_guard_service

    def create_branch_from_turn(
        self,
        *,
        session_id: str,
        origin_turn_id: str,
        branch_name: str | None = None,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        self._runtime_maintenance_guard_service.require_session_operation_allowed(
            session=self._require_session(session_id),
            operation=RuntimeMaintenanceOperation.BRANCH_CREATE,
        )
        return super().create_branch_from_turn(
            session_id=session_id,
            origin_turn_id=origin_turn_id,
            branch_name=branch_name,
            actor=actor,
            metadata=metadata,
        )

    def switch_branch(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        self._runtime_maintenance_guard_service.require_session_operation_allowed(
            session=self._require_session(session_id),
            operation=RuntimeMaintenanceOperation.BRANCH_SWITCH,
        )
        return super().switch_branch(
            session_id=session_id,
            branch_head_id=branch_head_id,
            actor=actor,
            metadata=metadata,
        )

    def rollback_to_turn(
        self,
        *,
        session_id: str,
        target_turn_id: str,
        actor: str = "story_runtime_ui",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ChapterWorkspaceSnapshot, BranchControlReceipt]:
        self._runtime_maintenance_guard_service.require_session_operation_allowed(
            session=self._require_session(session_id),
            operation=RuntimeMaintenanceOperation.ROLLBACK,
        )
        return super().rollback_to_turn(
            session_id=session_id,
            target_turn_id=target_turn_id,
            actor=actor,
            metadata=metadata,
        )

    async def direct_edit_memory_block(
        self,
        *,
        session_id: str,
        block_id: str,
        payload: DirectCoreEditRequest,
    ) -> dict | None:
        self._require_identity_matches_session(
            session_id=session_id,
            identity_session_id=payload.identity.session_id,
            identity_story_id=payload.identity.story_id,
            session_mismatch_code="memory_core_direct_edit_identity_session_mismatch",
            story_mismatch_code="memory_core_direct_edit_identity_story_mismatch",
        )
        self._runtime_maintenance_guard_service.require_identity_operation_allowed(
            identity=payload.identity,
            operation=RuntimeMaintenanceOperation.CORE_MEMORY_EDIT,
        )
        return await super().direct_edit_memory_block(
            session_id=session_id,
            block_id=block_id,
            payload=payload,
        )

    async def direct_edit_core_memory(
        self,
        *,
        session_id: str,
        payload: DirectCoreEditRequest,
    ) -> dict:
        self._require_identity_matches_session(
            session_id=session_id,
            identity_session_id=payload.identity.session_id,
            identity_story_id=payload.identity.story_id,
            session_mismatch_code="memory_core_direct_edit_identity_session_mismatch",
            story_mismatch_code="memory_core_direct_edit_identity_story_mismatch",
        )
        self._runtime_maintenance_guard_service.require_identity_operation_allowed(
            identity=payload.identity,
            operation=RuntimeMaintenanceOperation.CORE_MEMORY_EDIT,
        )
        return await super().direct_edit_core_memory(
            session_id=session_id,
            payload=payload,
        )

    def evolve_archival_memory(
        self,
        *,
        session_id: str,
        request: ArchivalEvolutionRequest,
    ) -> dict:
        self._require_identity_matches_session(
            session_id=session_id,
            identity_session_id=request.identity.session_id,
            identity_story_id=request.identity.story_id,
            session_mismatch_code="memory_archival_evolution_identity_session_mismatch",
            story_mismatch_code="memory_archival_evolution_identity_story_mismatch",
        )
        self._runtime_maintenance_guard_service.require_identity_operation_allowed(
            identity=request.identity,
            operation=RuntimeMaintenanceOperation.STORY_EVOLUTION_OR_ARCHIVAL_EDIT,
        )
        return super().evolve_archival_memory(
            session_id=session_id,
            request=request,
        )

    def _require_identity_matches_session(
        self,
        *,
        session_id: str,
        identity_session_id: str,
        identity_story_id: str,
        session_mismatch_code: str,
        story_mismatch_code: str,
    ) -> None:
        session = self._require_session(session_id)
        if identity_session_id != session.session_id:
            raise ValueError(session_mismatch_code)
        if identity_story_id != session.story_id:
            raise ValueError(story_mismatch_code)
