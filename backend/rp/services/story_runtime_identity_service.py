"""Persistent runtime identity allocation for story boot-bar turns."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from models.rp_story_store import (
    BranchHeadRecord,
    StorySessionRecord,
    StoryTurnRecord,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_identity import (
    BranchHeadStatus,
    RuntimeProfileSnapshotStatus,
    StoryTurnStatus,
)
from rp.services.runtime_profile_snapshot_service import (
    RuntimeProfileSnapshotService,
    RuntimeProfileSnapshotServiceError,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StoryRuntimeIdentityServiceError(ValueError):
    """Stable runtime-identity error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class StoryRuntimeIdentityService:
    """Allocate persistent branch/turn identity for runtime-owned paths."""

    _DEFAULT_BRANCH_NAME = "main"
    _DEFAULT_VISIBILITY_SCOPE = "active_lineage"

    def __init__(
        self,
        session,
        *,
        runtime_profile_snapshot_service: RuntimeProfileSnapshotService | None = None,
    ) -> None:
        self._session = session
        self._runtime_profile_snapshot_service = (
            runtime_profile_snapshot_service or RuntimeProfileSnapshotService(session)
        )

    def ensure_default_branch(
        self,
        *,
        session_id: str,
        story_id: str,
    ) -> BranchHeadRecord:
        branch_head_id = self._default_branch_id(session_id)
        existing = self._session.get(BranchHeadRecord, branch_head_id)
        if existing is not None:
            if existing.session_id != session_id or existing.story_id != story_id:
                raise StoryRuntimeIdentityServiceError(
                    "runtime_branch_head_conflict",
                    branch_head_id,
                )
            return existing

        now = _utcnow()
        record = BranchHeadRecord(
            branch_head_id=branch_head_id,
            story_id=story_id,
            session_id=session_id,
            branch_name=self._DEFAULT_BRANCH_NAME,
            parent_branch_head_id=None,
            forked_from_turn_id=None,
            head_turn_id=None,
            status=BranchHeadStatus.ACTIVE.value,
            visibility_scope=self._DEFAULT_VISIBILITY_SCOPE,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def require_branch_head(self, branch_head_id: str) -> BranchHeadRecord:
        record = self._session.get(BranchHeadRecord, branch_head_id)
        if record is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_head_not_found",
                branch_head_id,
            )
        return record

    def create_turn(
        self,
        *,
        session_id: str,
        story_id: str,
        branch_head_id: str,
        runtime_profile_snapshot_id: str,
        turn_kind: str,
        command_kind: str,
        actor: str,
    ) -> StoryTurnRecord:
        snapshot_id = str(runtime_profile_snapshot_id or "").strip()
        if not snapshot_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_runtime_profile_snapshot_required",
                session_id,
            )

        branch = self.require_branch_head(branch_head_id)
        if branch.session_id != session_id or branch.story_id != story_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"branch_mismatch:{branch_head_id}",
            )

        try:
            snapshot = self._runtime_profile_snapshot_service.require_snapshot(
                snapshot_id
            )
        except RuntimeProfileSnapshotServiceError as exc:
            raise StoryRuntimeIdentityServiceError(exc.code, snapshot_id) from exc
        if snapshot.session_id != session_id or snapshot.story_id != story_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"snapshot_mismatch:{snapshot_id}",
            )
        if snapshot.status != RuntimeProfileSnapshotStatus.ACTIVE.value:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"snapshot_not_active:{snapshot_id}",
            )

        now = _utcnow()
        turn = StoryTurnRecord(
            turn_id=uuid4().hex,
            story_id=story_id,
            session_id=session_id,
            branch_head_id=branch_head_id,
            runtime_profile_snapshot_id=snapshot_id,
            turn_kind=str(turn_kind or "").strip() or "runtime_turn",
            command_kind=str(command_kind or "").strip() or "runtime_command",
            actor=str(actor or "").strip() or "story_runtime",
            status=StoryTurnStatus.STARTED.value,
            created_at=now,
            started_at=now,
            completed_at=None,
        )
        self._session.add(turn)

        branch.head_turn_id = turn.turn_id
        branch.updated_at = now
        self._session.add(branch)

        self._session.flush()
        return turn

    def resolve_memory_identity(
        self,
        *,
        session_id: str,
        story_id: str,
        branch_head_id: str,
        turn_id: str,
        runtime_profile_snapshot_id: str,
    ) -> MemoryRuntimeIdentity:
        branch = self.require_branch_head(branch_head_id)
        if branch.session_id != session_id or branch.story_id != story_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"branch_mismatch:{branch_head_id}",
            )

        turn = self._require_turn_record(turn_id)
        if (
            turn.session_id != session_id
            or turn.story_id != story_id
            or turn.branch_head_id != branch_head_id
            or turn.runtime_profile_snapshot_id != runtime_profile_snapshot_id
        ):
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"turn_mismatch:{turn_id}",
            )

        try:
            snapshot = self._runtime_profile_snapshot_service.require_snapshot(
                runtime_profile_snapshot_id
            )
        except RuntimeProfileSnapshotServiceError as exc:
            raise StoryRuntimeIdentityServiceError(
                exc.code,
                runtime_profile_snapshot_id,
            ) from exc
        if snapshot.session_id != session_id or snapshot.story_id != story_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"snapshot_mismatch:{runtime_profile_snapshot_id}",
            )

        try:
            return MemoryRuntimeIdentity(
                story_id=story_id,
                session_id=session_id,
                branch_head_id=branch_head_id,
                turn_id=turn_id,
                runtime_profile_snapshot_id=runtime_profile_snapshot_id,
            )
        except ValueError as exc:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                session_id,
            ) from exc

    def resolve_runtime_entry_identity(
        self,
        *,
        session_id: str,
        command_kind: str,
        actor: str,
        requested_branch_head_id: str | None = None,
        requested_runtime_profile_snapshot_id: str | None = None,
    ) -> MemoryRuntimeIdentity:
        session_record = self._require_session_record(session_id)
        branch = (
            self.require_branch_head(requested_branch_head_id)
            if requested_branch_head_id
            else self.ensure_default_branch(
                session_id=session_record.session_id,
                story_id=session_record.story_id,
            )
        )
        if branch.session_id != session_record.session_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"branch_session_mismatch:{branch.branch_head_id}",
            )

        snapshot_id = str(requested_runtime_profile_snapshot_id or "").strip()
        if snapshot_id:
            snapshot = self._runtime_profile_snapshot_service.require_snapshot(
                snapshot_id
            )
        else:
            snapshot = self._runtime_profile_snapshot_service.ensure_active_snapshot(
                session_id=session_record.session_id,
                created_from="story_runtime.turn_start",
            )
            snapshot_id = snapshot.runtime_profile_snapshot_id
        if snapshot.session_id != session_record.session_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"snapshot_session_mismatch:{snapshot_id}",
            )

        turn = self.create_turn(
            session_id=session_record.session_id,
            story_id=session_record.story_id,
            branch_head_id=branch.branch_head_id,
            runtime_profile_snapshot_id=snapshot_id,
            turn_kind=self._turn_kind(command_kind),
            command_kind=command_kind,
            actor=actor,
        )
        return self.resolve_memory_identity(
            session_id=session_record.session_id,
            story_id=session_record.story_id,
            branch_head_id=branch.branch_head_id,
            turn_id=turn.turn_id,
            runtime_profile_snapshot_id=snapshot_id,
        )

    def update_turn_status(
        self,
        *,
        turn_id: str,
        status: StoryTurnStatus,
    ) -> StoryTurnRecord:
        record = self._session.get(StoryTurnRecord, turn_id)
        if record is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_turn_not_found",
                turn_id,
            )
        record.status = status.value
        if status in {StoryTurnStatus.COMPLETED, StoryTurnStatus.FAILED}:
            record.completed_at = _utcnow()
        self._session.add(record)
        self._session.flush()
        return record

    @staticmethod
    def _default_branch_id(session_id: str) -> str:
        return f"branch:{session_id}:main"

    @staticmethod
    def _turn_kind(command_kind: str) -> str:
        normalized = str(command_kind or "").strip().lower()
        if normalized in {
            "accept_outline",
            "accept_pending_segment",
            "complete_chapter",
        }:
            return "control"
        return "generation"

    def _require_session_record(self, session_id: str) -> StorySessionRecord:
        record = self._session.get(StorySessionRecord, session_id)
        if record is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"story_session_not_found:{session_id}",
            )
        return record

    def _require_turn_record(self, turn_id: str) -> StoryTurnRecord:
        record = self._session.get(StoryTurnRecord, turn_id)
        if record is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_turn_not_found",
                turn_id,
            )
        return record
