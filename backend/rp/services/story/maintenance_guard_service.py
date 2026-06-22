"""Service-layer guards for story runtime maintenance locks."""

from __future__ import annotations

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.story.runtime import LongformTurnCommandKind, StorySession
from rp.services.runtime.maintenance_lock_service import (
    RuntimeMaintenanceLockService,
    RuntimeMaintenanceOperation,
)

from .command_policy import maintenance_operation_for_story_command


class StoryRuntimeMaintenanceGuardService:
    """Apply the current-branch maintenance lock to mutating story operations."""

    def __init__(self, lock_service: RuntimeMaintenanceLockService) -> None:
        self._lock_service = lock_service

    def require_story_command_allowed(
        self,
        *,
        command_kind: LongformTurnCommandKind,
        runtime_identity: MemoryRuntimeIdentity | None,
    ) -> None:
        if runtime_identity is None:
            return
        self.require_identity_operation_allowed(
            identity=runtime_identity,
            operation=maintenance_operation_for_story_command(command_kind),
        )

    def require_session_operation_allowed(
        self,
        *,
        session: StorySession,
        operation: RuntimeMaintenanceOperation,
    ) -> None:
        self._lock_service.require_allowed(
            story_id=session.story_id,
            session_id=session.session_id,
            branch_head_id=_active_branch_head_id(session),
            operation=operation,
        )

    def require_identity_operation_allowed(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        operation: RuntimeMaintenanceOperation,
    ) -> None:
        self._lock_service.require_allowed(
            story_id=identity.story_id,
            session_id=identity.session_id,
            branch_head_id=identity.branch_head_id,
            operation=operation,
        )


def _active_branch_head_id(session: StorySession) -> str:
    branch_head_id = str(session.active_branch_head_id or "").strip()
    return branch_head_id or f"branch:{session.session_id}:main"
