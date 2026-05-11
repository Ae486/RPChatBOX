"""Persistent runtime identity allocation for story boot-bar turns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import asc
from sqlmodel import select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from models.rp_story_store import (
    BranchControlReceiptRecord,
    BranchHeadRecord,
    StoryArtifactRecord,
    StorySessionRecord,
    StoryTurnRecord,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_identity import (
    BranchControlKind,
    BranchControlReceipt,
    BranchHeadStatus,
    BranchVisibilityState,
    RuntimeProfileSnapshotStatus,
    StoryTurnStatus,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialLifecycle
from rp.services.runtime_profile_snapshot_service import (
    RuntimeProfileSnapshotService,
    RuntimeProfileSnapshotServiceError,
)
from rp.services.runtime_workflow_job_service import RuntimeWorkflowJobService


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
    _DEFAULT_BRANCH_VISIBILITY_STATE = BranchVisibilityState.VISIBLE.value
    _GRAPH_CHECKPOINT_BINDING_KEY = "graph_checkpoint_binding"
    _GRAPH_CHECKPOINT_BINDINGS_BY_TURN_KEY = "graph_checkpoint_bindings_by_turn_id"
    _ADOPTED_OUTPUT_SETTLE_CANDIDATE_STATUSES = {
        StoryTurnStatus.WRITER_COMPLETED.value,
        StoryTurnStatus.POST_WRITE_PENDING.value,
        StoryTurnStatus.POST_WRITE_DEFERRED.value,
        StoryTurnStatus.COMPLETED.value,
    }
    _ADOPTED_OUTPUT_SETTLE_BLOCKED_VISIBILITY_STATES = {
        "hidden",
        "hidden_by_rollback",
        "invalidated",
        "discarded",
        "deleted",
    }

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
        session_record = self._require_session_record(session_id)
        if session_record.story_id != story_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"story_session_mismatch:{session_id}",
            )
        branch_head_id = self._default_branch_id(session_id)
        existing = self._session.get(BranchHeadRecord, branch_head_id)
        if existing is not None:
            if existing.session_id != session_id or existing.story_id != story_id:
                raise StoryRuntimeIdentityServiceError(
                    "runtime_branch_head_conflict",
                    branch_head_id,
                )
            self._pin_session_active_branch_if_unset(
                session_record=session_record,
                branch_head_id=existing.branch_head_id,
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
            fork_origin_turn_id=None,
            fork_base_turn_id=None,
            head_turn_id=None,
            last_settled_turn_id=None,
            status=BranchHeadStatus.ACTIVE.value,
            visibility_scope=self._DEFAULT_VISIBILITY_SCOPE,
            visibility_state=self._DEFAULT_BRANCH_VISIBILITY_STATE,
            created_at=now,
            updated_at=now,
        )
        self._session.add(record)
        self._session.flush()
        self._pin_session_active_branch_if_unset(
            session_record=session_record,
            branch_head_id=record.branch_head_id,
            updated_at=now,
        )
        return record

    def require_branch_head(self, branch_head_id: str) -> BranchHeadRecord:
        record = self._session.get(BranchHeadRecord, branch_head_id)
        if record is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_head_not_found",
                branch_head_id,
            )
        return record

    def create_branch_from_turn(
        self,
        *,
        session_id: str,
        origin_turn_id: str,
        actor: str,
        branch_name: str | None = None,
        metadata: dict | None = None,
    ) -> BranchControlReceipt:
        """Create a branch from a settled turn and immediately make it active."""

        session_record = self._require_session_record(session_id)
        origin_turn = self._require_turn_record(origin_turn_id)
        self._validate_turn_belongs_to_session(
            session_record=session_record,
            turn=origin_turn,
        )
        origin_branch = self.require_branch_head(origin_turn.branch_head_id)
        self._validate_branch_belongs_to_session(
            session_record=session_record,
            branch=origin_branch,
        )
        if self._turn_hidden_by_rollback(
            branch=origin_branch,
            turn=origin_turn,
        ):
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_invalid_turn",
                f"origin_hidden_by_rollback:{origin_turn_id}",
            )
        if origin_turn.status != StoryTurnStatus.SETTLED.value:
            origin_turn = self._settle_adopted_output_turn_if_visible(
                session_record=session_record,
                turn=origin_turn,
                reason="branch_create_adopted_visible_output",
            )
        if origin_turn.status != StoryTurnStatus.SETTLED.value:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_invalid_turn",
                f"origin_not_settled:{origin_turn_id}",
            )
        base_turn_id = origin_turn.turn_id
        now = _utcnow()
        normalized_branch_name = (
            str(branch_name or "").strip()
            or f"branch-{self._branch_count(session_id=session_id) + 1}"
        )
        branch = BranchHeadRecord(
            branch_head_id=f"branch:{session_id}:{uuid4().hex}",
            story_id=session_record.story_id,
            session_id=session_record.session_id,
            branch_name=normalized_branch_name,
            parent_branch_head_id=origin_branch.branch_head_id,
            # Product branch anchors are inclusive: the new branch preserves the
            # clicked settled turn and starts rewriting from the following turn.
            forked_from_turn_id=base_turn_id,
            fork_origin_turn_id=origin_turn.turn_id,
            fork_base_turn_id=base_turn_id,
            head_turn_id=base_turn_id,
            last_settled_turn_id=base_turn_id,
            status=BranchHeadStatus.ACTIVE.value,
            visibility_scope=self._DEFAULT_VISIBILITY_SCOPE,
            visibility_state=BranchVisibilityState.VISIBLE.value,
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        self._session.add(branch)
        self._session.flush()
        receipt = self._write_branch_control_receipt(
            session_record=session_record,
            branch_head_id=branch.branch_head_id,
            control_kind=BranchControlKind.BRANCH_CREATED,
            actor=actor,
            fork_origin_turn_id=origin_turn.turn_id,
            fork_base_turn_id=base_turn_id,
            from_branch_head_id=origin_branch.branch_head_id,
            to_branch_head_id=branch.branch_head_id,
            source_ref_ids=[f"turn:{origin_turn.turn_id}"],
            result_ref_ids=[f"branch_head:{branch.branch_head_id}"],
            metadata=metadata,
            created_at=now,
        )
        branch.created_by_control_receipt_id = receipt.receipt_id
        branch.updated_at = now
        session_record.active_branch_head_id = branch.branch_head_id
        session_record.updated_at = now
        self._session.add(branch)
        self._session.add(session_record)
        self._session.flush()
        return self._record_to_branch_control_receipt(receipt)

    def switch_branch(
        self,
        *,
        session_id: str,
        target_branch_head_id: str,
        actor: str,
        metadata: dict | None = None,
    ) -> BranchControlReceipt:
        """Switch the active branch pointer without creating a story turn."""

        session_record = self._require_session_record(session_id)
        target_branch = self.require_branch_head(target_branch_head_id)
        self._validate_branch_belongs_to_session(
            session_record=session_record,
            branch=target_branch,
        )
        self._require_branch_switchable(target_branch)
        now = _utcnow()
        from_branch_head_id = str(session_record.active_branch_head_id or "").strip()
        session_record.active_branch_head_id = target_branch.branch_head_id
        session_record.updated_at = now
        self._session.add(session_record)
        receipt = self._write_branch_control_receipt(
            session_record=session_record,
            branch_head_id=target_branch.branch_head_id,
            control_kind=BranchControlKind.BRANCH_SWITCHED,
            actor=actor,
            from_branch_head_id=from_branch_head_id or None,
            to_branch_head_id=target_branch.branch_head_id,
            result_ref_ids=[f"branch_head:{target_branch.branch_head_id}"],
            metadata=metadata,
            created_at=now,
        )
        self._session.flush()
        return self._record_to_branch_control_receipt(receipt)

    def delete_branch(
        self,
        *,
        session_id: str,
        branch_head_id: str,
        actor: str,
        metadata: dict | None = None,
    ) -> BranchControlReceipt:
        """Hide/delete a branch at the control layer without purging branch data."""

        session_record = self._require_session_record(session_id)
        branch = self.require_branch_head(branch_head_id)
        self._validate_branch_belongs_to_session(
            session_record=session_record,
            branch=branch,
        )
        if branch.branch_head_id == self._default_branch_id(session_id):
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_default_delete_not_supported",
                branch.branch_head_id,
            )
        if session_record.active_branch_head_id == branch.branch_head_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_current_delete_not_supported",
                branch.branch_head_id,
            )
        now = _utcnow()
        branch.status = BranchHeadStatus.SUPERSEDED.value
        branch.visibility_state = BranchVisibilityState.DELETED.value
        branch.updated_at = now
        self._session.add(branch)
        receipt = self._write_branch_control_receipt(
            session_record=session_record,
            branch_head_id=branch.branch_head_id,
            control_kind=BranchControlKind.BRANCH_DELETED,
            actor=actor,
            from_branch_head_id=branch.branch_head_id,
            result_ref_ids=[f"branch_head:{branch.branch_head_id}"],
            metadata=metadata,
            created_at=now,
        )
        self._session.flush()
        return self._record_to_branch_control_receipt(receipt)

    def rollback_to_turn(
        self,
        *,
        session_id: str,
        target_turn_id: str,
        actor: str,
        metadata: dict | None = None,
    ) -> BranchControlReceipt:
        """Rollback the active branch to a settled turn without creating a turn."""

        session_record = self._require_session_record(session_id)
        active_branch_id = str(session_record.active_branch_head_id or "").strip()
        if not active_branch_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_head_not_found",
                f"active_branch_missing:{session_id}",
            )
        branch = self.require_branch_head(active_branch_id)
        self._validate_branch_belongs_to_session(
            session_record=session_record,
            branch=branch,
        )
        self._require_branch_switchable(branch)
        target_turn = self._require_turn_record(target_turn_id)
        self._validate_turn_belongs_to_session(
            session_record=session_record,
            turn=target_turn,
        )
        target_branch = self.require_branch_head(target_turn.branch_head_id)
        self._validate_branch_belongs_to_session(
            session_record=session_record,
            branch=target_branch,
        )
        target_is_parent_lineage = self._turn_is_immediate_parent_lineage_target(
            active_branch=branch,
            target_turn=target_turn,
        )
        if (
            target_turn.branch_head_id != branch.branch_head_id
            and not target_is_parent_lineage
        ):
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_invalid_turn",
                f"target_branch_mismatch:{target_turn_id}",
            )
        if self._turn_hidden_by_rollback(
            branch=target_branch,
            turn=target_turn,
        ) or self._turn_hidden_by_rollback(branch=branch, turn=target_turn):
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_invalid_turn",
                f"target_hidden_by_rollback:{target_turn_id}",
            )
        if target_turn.status != StoryTurnStatus.SETTLED.value:
            target_turn = self._settle_adopted_output_turn_if_visible(
                session_record=session_record,
                turn=target_turn,
                reason="rollback_adopted_visible_output",
            )
        if target_turn.status != StoryTurnStatus.SETTLED.value:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_control_invalid_turn",
                f"target_not_settled:{target_turn_id}",
            )

        later_turns = self._later_turns_for_rollback(
            active_branch=branch,
            target_turn=target_turn,
            target_is_parent_lineage=target_is_parent_lineage,
        )
        now = _utcnow()
        target_checkpoint_binding = self._graph_checkpoint_binding_for_turn(
            branch=target_branch,
            target_turn=target_turn,
        )
        metadata_json = self._rollback_metadata(
            branch=branch,
            target_turn=target_turn,
            later_turns=later_turns,
            metadata=metadata,
            applied_at=now,
            target_checkpoint_binding=target_checkpoint_binding,
        )
        receipt = self._write_branch_control_receipt(
            session_record=session_record,
            branch_head_id=branch.branch_head_id,
            control_kind=BranchControlKind.ROLLBACK_APPLIED,
            actor=actor,
            target_turn_id=target_turn.turn_id,
            source_ref_ids=[f"turn:{target_turn.turn_id}"],
            result_ref_ids=[f"branch_head:{branch.branch_head_id}"],
            trace_refs=[f"turn:{turn.turn_id}" for turn in later_turns],
            metadata=metadata_json,
            created_at=now,
        )
        self._hide_later_turns_after_rollback(
            later_turns=later_turns,
            target_turn_id=target_turn.turn_id,
            receipt_id=receipt.receipt_id,
            updated_at=now,
        )
        invalidated_material_ids = self._invalidate_workspace_materials_for_turns(
            later_turns=later_turns,
            receipt_id=receipt.receipt_id,
            target_turn_id=target_turn.turn_id,
            updated_at=now,
        )
        metadata_json["visibility_transition"]["invalidated_workspace_material_ids"] = (
            invalidated_material_ids
        )
        receipt.metadata_json = metadata_json
        branch.head_turn_id = target_turn.turn_id
        branch.last_settled_turn_id = target_turn.turn_id
        if target_is_parent_lineage:
            branch.forked_from_turn_id = target_turn.turn_id
        branch.metadata_json = self._merge_branch_rollback_metadata(
            branch=branch,
            target_turn=target_turn,
            receipt=receipt,
            invalidated_material_ids=invalidated_material_ids,
            updated_at=now,
        )
        branch.updated_at = now
        self._session.add(receipt)
        self._session.add(branch)
        self._session.flush()
        return self._record_to_branch_control_receipt(receipt)

    def settle_adopted_output_turn_if_visible(
        self,
        *,
        session_id: str,
        turn_id: str,
        reason: str,
    ) -> StoryTurnRecord | None:
        """Settle a writer turn only when an accepted segment proves adoption.

        Branch and rollback product actions are anchored on settled turns, while
        the longform UI is anchored on accepted segment artifacts. This method is
        the narrow bridge between those contracts: it refuses ordinary unfinished
        turns and only promotes a writer turn whose own output artifact is an
        accepted story segment with matching runtime turn and branch metadata.
        """

        session_record = self._require_session_record(session_id)
        turn = self._require_turn_record(turn_id)
        self._validate_turn_belongs_to_session(
            session_record=session_record,
            turn=turn,
        )
        settled = self._settle_adopted_output_turn_if_visible(
            session_record=session_record,
            turn=turn,
            reason=reason,
        )
        return settled if settled.status == StoryTurnStatus.SETTLED.value else None

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
        self._require_branch_switchable(branch)

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
            visibility_state="active",
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
        branch = self._resolve_runtime_entry_branch(
            session_record=session_record,
            requested_branch_head_id=requested_branch_head_id,
        )
        if branch.session_id != session_record.session_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"branch_session_mismatch:{branch.branch_head_id}",
            )

        snapshot = self._resolve_runtime_entry_snapshot(
            session_record=session_record,
            requested_runtime_profile_snapshot_id=requested_runtime_profile_snapshot_id,
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
        visible_output_ref: str | None = None,
        selected_output_ref: str | None = None,
        settlement_reason: str | None = None,
        failure_reason: str | None = None,
    ) -> StoryTurnRecord:
        record = self._session.get(StoryTurnRecord, turn_id)
        if record is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_turn_not_found",
                turn_id,
            )
        now = _utcnow()
        record.status = status.value
        record.updated_at = now
        if visible_output_ref is not None:
            record.visible_output_ref = visible_output_ref
        if selected_output_ref is not None:
            record.selected_output_ref = selected_output_ref
        if settlement_reason is not None:
            record.settlement_reason = settlement_reason
        if failure_reason is not None:
            record.failure_reason = failure_reason
        if status == StoryTurnStatus.WRITER_COMPLETED:
            record.writer_completed_at = now
        elif status == StoryTurnStatus.POST_WRITE_PENDING:
            record.writer_completed_at = record.writer_completed_at or now
        elif status == StoryTurnStatus.POST_WRITE_RUNNING:
            record.post_write_started_at = now
        elif status == StoryTurnStatus.SETTLED:
            record.visibility_state = "active"
            record.settled_at = now
            record.completed_at = now
            branch = self._session.get(BranchHeadRecord, record.branch_head_id)
            if branch is not None:
                branch.last_settled_turn_id = record.turn_id
                branch.head_turn_id = record.turn_id
                branch.updated_at = now
                self._session.add(branch)
        elif status == StoryTurnStatus.FAILED:
            record.failed_at = now
            record.completed_at = now
        elif status == StoryTurnStatus.COMPLETED:
            record.completed_at = now
        self._session.add(record)
        self._session.flush()
        return record

    def bind_turn_output_refs_if_visible(
        self,
        *,
        session_id: str,
        turn_id: str,
        artifact_id: str,
        branch_head_id: str,
    ) -> StoryTurnRecord | None:
        record = self._session.get(StoryTurnRecord, turn_id)
        if record is None:
            return None
        branch = self._session.get(BranchHeadRecord, record.branch_head_id)
        if (
            branch is None
            or record.session_id != session_id
            or record.branch_head_id != branch_head_id
            or self._turn_hidden_by_rollback(branch=branch, turn=record)
        ):
            return None
        if (
            record.visible_output_ref == artifact_id
            and record.selected_output_ref == artifact_id
        ):
            return record
        now = _utcnow()
        record.visible_output_ref = artifact_id
        record.selected_output_ref = artifact_id
        record.updated_at = now
        self._session.add(record)
        self._session.flush()
        return record

    def get_turn(self, turn_id: str) -> StoryTurnRecord | None:
        return self._session.get(StoryTurnRecord, turn_id)

    def record_graph_checkpoint_binding(
        self,
        *,
        turn_id: str,
        checkpoint_id: str,
        parent_checkpoint_id: str | None = None,
        captured_after_node: str = "finalize_turn",
        captured_at: datetime | None = None,
        checkpoint_ns: str = "rp_story",
    ) -> dict:
        """Bind a settled turn to the LangGraph checkpoint captured after finalize."""

        normalized_turn_id = str(turn_id or "").strip()
        normalized_checkpoint_id = str(checkpoint_id or "").strip()
        if not normalized_turn_id:
            return {"recorded": False, "reason": "turn_id_missing"}
        if not normalized_checkpoint_id:
            return {"recorded": False, "reason": "checkpoint_id_missing"}
        turn = self._session.get(StoryTurnRecord, normalized_turn_id)
        if turn is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_turn_not_found",
                normalized_turn_id,
            )
        if turn.status != StoryTurnStatus.SETTLED.value:
            return {
                "recorded": False,
                "reason": "turn_not_settled",
                "turn_id": turn.turn_id,
                "turn_status": turn.status,
            }
        branch = self._session.get(BranchHeadRecord, turn.branch_head_id)
        if branch is None:
            raise StoryRuntimeIdentityServiceError(
                "runtime_branch_head_not_found",
                turn.branch_head_id,
            )
        if branch.session_id != turn.session_id or branch.story_id != turn.story_id:
            raise StoryRuntimeIdentityServiceError(
                "runtime_identity_resolution_failed",
                f"branch_turn_mismatch:{turn.turn_id}",
            )
        metadata_json = dict(branch.metadata_json or {})
        existing_by_turn = metadata_json.get(self._GRAPH_CHECKPOINT_BINDINGS_BY_TURN_KEY)
        bindings_by_turn = (
            dict(existing_by_turn) if isinstance(existing_by_turn, dict) else {}
        )
        existing_binding = bindings_by_turn.get(turn.turn_id)
        if self._valid_graph_checkpoint_binding(
            binding=existing_binding,
            target_turn=turn,
        ):
            # LangGraph replay/fork may produce later technical checkpoints for
            # the same application turn. The first settled-turn binding remains
            # the RP rollback anchor; subsequent captures are idempotent reads.
            return {
                "recorded": True,
                "binding": dict(cast(dict[str, Any], existing_binding)),
                "idempotent": True,
                "reason": "graph_checkpoint_binding_already_recorded",
            }
        now = captured_at or _utcnow()
        binding = {
            "graph_thread_id": self.build_graph_thread_id(
                session_id=turn.session_id,
                branch_head_id=turn.branch_head_id,
            ),
            "checkpoint_ns": str(checkpoint_ns or "rp_story").strip() or "rp_story",
            "checkpoint_id": normalized_checkpoint_id,
            "parent_checkpoint_id": (
                str(parent_checkpoint_id).strip()
                if parent_checkpoint_id is not None
                and str(parent_checkpoint_id).strip()
                else None
            ),
            "captured_after_node": (
                str(captured_after_node or "").strip() or "finalize_turn"
            ),
            "captured_at": now.isoformat(),
            "turn_id": turn.turn_id,
            "branch_head_id": turn.branch_head_id,
            "runtime_profile_snapshot_id": turn.runtime_profile_snapshot_id,
            "source": "langgraph_checkpoint",
        }
        bindings_by_turn[turn.turn_id] = binding
        metadata_json[self._GRAPH_CHECKPOINT_BINDINGS_BY_TURN_KEY] = bindings_by_turn
        if (
            branch.head_turn_id == turn.turn_id
            or branch.last_settled_turn_id == turn.turn_id
        ):
            metadata_json[self._GRAPH_CHECKPOINT_BINDING_KEY] = dict(binding)
        branch.metadata_json = metadata_json
        branch.updated_at = now
        self._session.add(branch)
        self._session.flush()
        return {"recorded": True, "binding": binding}

    @staticmethod
    def _default_branch_id(session_id: str) -> str:
        return f"branch:{session_id}:main"

    @staticmethod
    def build_graph_thread_id(*, session_id: str, branch_head_id: str) -> str:
        return f"story_session:{session_id}:branch_head:{branch_head_id}"

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

    @staticmethod
    def _validate_turn_belongs_to_session(
        *,
        session_record: StorySessionRecord,
        turn: StoryTurnRecord,
    ) -> None:
        if (
            turn.session_id == session_record.session_id
            and turn.story_id == session_record.story_id
        ):
            return
        raise StoryRuntimeIdentityServiceError(
            "runtime_identity_resolution_failed",
            f"turn_session_mismatch:{turn.turn_id}",
        )

    @staticmethod
    def _validate_branch_belongs_to_session(
        *,
        session_record: StorySessionRecord,
        branch: BranchHeadRecord,
    ) -> None:
        if (
            branch.session_id == session_record.session_id
            and branch.story_id == session_record.story_id
        ):
            return
        raise StoryRuntimeIdentityServiceError(
            "runtime_identity_resolution_failed",
            f"branch_session_mismatch:{branch.branch_head_id}",
        )

    def _previous_settled_turn(
        self,
        origin_turn: StoryTurnRecord,
    ) -> StoryTurnRecord | None:
        stmt = (
            select(StoryTurnRecord)
            .where(StoryTurnRecord.session_id == origin_turn.session_id)
            .where(StoryTurnRecord.branch_head_id == origin_turn.branch_head_id)
            .order_by(asc(StoryTurnRecord.created_at))
            .order_by(asc(StoryTurnRecord.turn_id))
        )
        ordered_turns = list(self._session.exec(stmt).all())
        previous: StoryTurnRecord | None = None
        for turn in ordered_turns:
            if turn.turn_id == origin_turn.turn_id:
                return previous
            if turn.status == StoryTurnStatus.SETTLED.value and not (
                self._turn_hidden_by_rollback(
                    branch=self.require_branch_head(turn.branch_head_id),
                    turn=turn,
                )
            ):
                previous = turn
        return previous

    def _settle_adopted_output_turn_if_visible(
        self,
        *,
        session_record: StorySessionRecord,
        turn: StoryTurnRecord,
        reason: str,
    ) -> StoryTurnRecord:
        if turn.status == StoryTurnStatus.SETTLED.value:
            return turn
        if turn.status not in self._ADOPTED_OUTPUT_SETTLE_CANDIDATE_STATUSES:
            return turn
        branch = self._session.get(BranchHeadRecord, turn.branch_head_id)
        if branch is None or self._turn_hidden_by_rollback(branch=branch, turn=turn):
            return turn
        artifact = self._accepted_output_artifact_for_turn(turn)
        if artifact is None:
            return turn

        identity = MemoryRuntimeIdentity(
            story_id=turn.story_id,
            session_id=turn.session_id,
            branch_head_id=turn.branch_head_id,
            turn_id=turn.turn_id,
            runtime_profile_snapshot_id=turn.runtime_profile_snapshot_id,
        )
        workflow_job_service = RuntimeWorkflowJobService(self._session)
        jobs_before = workflow_job_service.list_jobs_for_turn(turn_id=turn.turn_id)
        if jobs_before:
            workflow_job_service.mark_required_jobs_deferred(
                identity=identity,
                reason=reason,
                metadata={
                    "settlement_bridge": "accepted_story_segment_adoption",
                    "artifact_id": artifact.artifact_id,
                },
            )
            settlement = workflow_job_service.evaluate_turn_settlement(
                turn_id=turn.turn_id,
            )
            if settlement.required_job_ids and not settlement.eligible:
                return turn
            settlement_reason = settlement.settlement_reason or reason
        else:
            settlement_reason = reason
        return self._mark_turn_settled_preserving_branch_progress(
            turn=turn,
            settlement_reason=settlement_reason,
        )

    def _accepted_output_artifact_for_turn(
        self,
        turn: StoryTurnRecord,
    ) -> StoryArtifactRecord | None:
        artifact_ids = self._turn_output_artifact_ids(turn)
        if not artifact_ids:
            return None
        stmt = (
            select(StoryArtifactRecord)
            .where(StoryArtifactRecord.session_id == turn.session_id)
            .where(StoryArtifactRecord.artifact_id.in_(list(artifact_ids)))
        )
        for artifact in self._session.exec(stmt).all():
            if artifact.artifact_kind != "story_segment":
                continue
            if artifact.status != "accepted":
                continue
            metadata = dict(artifact.metadata_json or {})
            artifact_turn_id = self._metadata_text(
                metadata,
                "runtime_turn_id",
            )
            if artifact_turn_id != turn.turn_id:
                continue
            artifact_branch_id = self._metadata_text(
                metadata,
                "runtime_branch_head_id",
            )
            if artifact_branch_id != turn.branch_head_id:
                continue
            return artifact
        return None

    @staticmethod
    def _turn_output_artifact_ids(turn: StoryTurnRecord) -> set[str]:
        result: set[str] = set()
        for output_ref in (turn.visible_output_ref, turn.selected_output_ref):
            normalized = str(output_ref or "").strip()
            if not normalized:
                continue
            result.add(normalized)
            if normalized.startswith("artifact:"):
                stripped = normalized.removeprefix("artifact:").strip()
                if stripped:
                    result.add(stripped)
        return result

    def _mark_turn_settled_preserving_branch_progress(
        self,
        *,
        turn: StoryTurnRecord,
        settlement_reason: str,
    ) -> StoryTurnRecord:
        now = _utcnow()
        turn.status = StoryTurnStatus.SETTLED.value
        turn.visibility_state = "active"
        turn.settlement_reason = settlement_reason
        turn.settled_at = turn.settled_at or now
        turn.completed_at = turn.completed_at or now
        turn.updated_at = now
        branch = self._session.get(BranchHeadRecord, turn.branch_head_id)
        if branch is not None:
            if self._should_replace_last_settled_turn(
                existing_turn_id=branch.last_settled_turn_id,
                candidate_turn=turn,
            ):
                branch.last_settled_turn_id = turn.turn_id
            if self._should_advance_branch_head(
                existing_turn_id=branch.head_turn_id,
                candidate_turn=turn,
            ):
                branch.head_turn_id = turn.turn_id
            branch.updated_at = now
            self._session.add(branch)
        self._session.add(turn)
        self._session.flush()
        return turn

    def _should_replace_last_settled_turn(
        self,
        *,
        existing_turn_id: str | None,
        candidate_turn: StoryTurnRecord,
    ) -> bool:
        existing = self._session.get(
            StoryTurnRecord,
            str(existing_turn_id or "").strip(),
        )
        if existing is None:
            return True
        if existing.status != StoryTurnStatus.SETTLED.value:
            return True
        return self._turn_order_key(existing) <= self._turn_order_key(candidate_turn)

    def _should_advance_branch_head(
        self,
        *,
        existing_turn_id: str | None,
        candidate_turn: StoryTurnRecord,
    ) -> bool:
        existing = self._session.get(
            StoryTurnRecord,
            str(existing_turn_id or "").strip(),
        )
        if existing is None:
            return True
        if self._turn_hidden_by_rollback(
            branch=self.require_branch_head(existing.branch_head_id),
            turn=existing,
        ):
            return True
        return self._turn_order_key(existing) <= self._turn_order_key(candidate_turn)

    @staticmethod
    def _turn_order_key(turn: StoryTurnRecord) -> tuple[datetime, str]:
        return turn.created_at, turn.turn_id

    @staticmethod
    def _metadata_text(metadata: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = str(metadata.get(key) or "").strip()
            if value:
                return value
        return None

    def _turn_is_immediate_parent_lineage_target(
        self,
        *,
        active_branch: BranchHeadRecord,
        target_turn: StoryTurnRecord,
    ) -> bool:
        parent_branch_id = str(active_branch.parent_branch_head_id or "").strip()
        if not parent_branch_id or target_turn.branch_head_id != parent_branch_id:
            return False
        if target_turn.turn_id == str(active_branch.fork_origin_turn_id or "").strip():
            return True
        cutoff_turn = self._session.get(
            StoryTurnRecord,
            str(
                active_branch.forked_from_turn_id
                or active_branch.fork_base_turn_id
                or ""
            ).strip(),
        )
        if cutoff_turn is None or cutoff_turn.branch_head_id != parent_branch_id:
            return False
        return self._turn_order_key(target_turn) <= self._turn_order_key(cutoff_turn)

    def _later_turns_for_rollback(
        self,
        *,
        active_branch: BranchHeadRecord,
        target_turn: StoryTurnRecord,
        target_is_parent_lineage: bool,
    ) -> list[StoryTurnRecord]:
        if not target_is_parent_lineage:
            return self._later_turns_on_branch(target_turn)
        stmt = (
            select(StoryTurnRecord)
            .where(StoryTurnRecord.session_id == active_branch.session_id)
            .where(StoryTurnRecord.branch_head_id == active_branch.branch_head_id)
            .order_by(asc(StoryTurnRecord.created_at))
            .order_by(asc(StoryTurnRecord.turn_id))
        )
        return list(self._session.exec(stmt).all())

    def _later_turns_on_branch(
        self,
        target_turn: StoryTurnRecord,
    ) -> list[StoryTurnRecord]:
        stmt = (
            select(StoryTurnRecord)
            .where(StoryTurnRecord.session_id == target_turn.session_id)
            .where(StoryTurnRecord.branch_head_id == target_turn.branch_head_id)
            .order_by(asc(StoryTurnRecord.created_at))
            .order_by(asc(StoryTurnRecord.turn_id))
        )
        ordered_turns = list(self._session.exec(stmt).all())
        later_turns: list[StoryTurnRecord] = []
        target_seen = False
        for turn in ordered_turns:
            if target_seen:
                later_turns.append(turn)
                continue
            if turn.turn_id == target_turn.turn_id:
                target_seen = True
        if not target_seen:
            raise StoryRuntimeIdentityServiceError(
                "runtime_turn_not_found",
                target_turn.turn_id,
            )
        return later_turns

    @staticmethod
    def _turn_hidden_by_rollback(
        *,
        branch: BranchHeadRecord,
        turn: StoryTurnRecord,
    ) -> bool:
        visibility_state = str(turn.visibility_state or "").strip()
        if (
            visibility_state
            in StoryRuntimeIdentityService._ADOPTED_OUTPUT_SETTLE_BLOCKED_VISIBILITY_STATES
        ):
            return True
        hidden_turn_ids = branch.metadata_json.get("rollback_hidden_turn_ids", [])
        if not isinstance(hidden_turn_ids, list):
            return False
        return turn.turn_id in {str(item).strip() for item in hidden_turn_ids}

    def _graph_checkpoint_binding_for_turn(
        self,
        *,
        branch: BranchHeadRecord,
        target_turn: StoryTurnRecord,
    ) -> dict | None:
        metadata_json = dict(branch.metadata_json or {})
        bindings_by_turn = metadata_json.get(self._GRAPH_CHECKPOINT_BINDINGS_BY_TURN_KEY)
        if isinstance(bindings_by_turn, dict):
            binding = bindings_by_turn.get(target_turn.turn_id)
            if self._valid_graph_checkpoint_binding(
                binding=binding,
                target_turn=target_turn,
            ):
                return dict(cast(dict[str, Any], binding))
        latest_binding = metadata_json.get(self._GRAPH_CHECKPOINT_BINDING_KEY)
        if self._valid_graph_checkpoint_binding(
            binding=latest_binding,
            target_turn=target_turn,
        ):
            return dict(cast(dict[str, Any], latest_binding))
        return None

    @staticmethod
    def _valid_graph_checkpoint_binding(
        *,
        binding: object,
        target_turn: StoryTurnRecord,
    ) -> bool:
        if not isinstance(binding, dict):
            return False
        return (
            binding.get("turn_id") == target_turn.turn_id
            and binding.get("branch_head_id") == target_turn.branch_head_id
            and binding.get("runtime_profile_snapshot_id")
            == target_turn.runtime_profile_snapshot_id
            and bool(str(binding.get("checkpoint_id") or "").strip())
        )

    @staticmethod
    def _rollback_metadata(
        *,
        branch: BranchHeadRecord,
        target_turn: StoryTurnRecord,
        later_turns: list[StoryTurnRecord],
        metadata: dict | None,
        applied_at: datetime,
        target_checkpoint_binding: dict | None,
    ) -> dict:
        incoming = dict(metadata or {})
        incoming.pop("graph_thread_id", None)
        graph_thread_id = StoryRuntimeIdentityService.build_graph_thread_id(
            session_id=target_turn.session_id,
            branch_head_id=branch.branch_head_id,
        )
        ignored_checkpoint_inputs = {
            key: incoming.pop(key)
            for key in (
                "target_checkpoint_id",
                "graph_checkpoint_binding",
                "checkpoint_binding",
            )
            if key in incoming
        }
        previous_head_turn_id = branch.head_turn_id
        previous_last_settled_turn_id = branch.last_settled_turn_id
        previous = {
            key: incoming.pop(key)
            for key in (
                "previous_head_turn_id",
                "previous_last_settled_turn_id",
                "hidden_turn_ids",
                "visibility_transition",
            )
            if key in incoming
        }
        if ignored_checkpoint_inputs:
            previous["ignored_checkpoint_inputs"] = ignored_checkpoint_inputs
        checkpoint_binding: dict[str, object] = {
            "binding_kind": "branch_scoped_thread",
            "graph_thread_id": graph_thread_id,
            "branch_head_id": branch.branch_head_id,
            "target_turn_id": target_turn.turn_id,
            "target_checkpoint_id": None,
            "source": "application_visibility_contract",
        }
        if isinstance(target_checkpoint_binding, dict) and target_checkpoint_binding.get(
            "checkpoint_id"
        ):
            checkpoint_binding.update(
                {
                    "target_checkpoint_id": target_checkpoint_binding["checkpoint_id"],
                    "graph_checkpoint_binding": dict(target_checkpoint_binding),
                    "source": "captured_graph_checkpoint_binding",
                }
            )
        else:
            checkpoint_binding["checkpoint_binding_missing_reason"] = (
                "target_turn_has_no_graph_checkpoint_binding"
            )
        result = {
            **incoming,
            "previous": previous,
            "previous_head_turn_id": previous_head_turn_id,
            "previous_last_settled_turn_id": previous_last_settled_turn_id,
            "visibility_transition": {
                "hidden_after_turn_id": target_turn.turn_id,
                "hidden_turn_ids": [turn.turn_id for turn in later_turns],
                "invalidated_workspace_material_ids": [],
            },
            "checkpoint_binding": checkpoint_binding,
            "rollback_applied_at": applied_at.isoformat(),
        }
        if checkpoint_binding["target_checkpoint_id"]:
            result["target_checkpoint_id"] = checkpoint_binding["target_checkpoint_id"]
            result["graph_checkpoint_binding"] = dict(target_checkpoint_binding or {})
        else:
            result["checkpoint_binding_missing_reason"] = checkpoint_binding[
                "checkpoint_binding_missing_reason"
            ]
        return result

    def _hide_later_turns_after_rollback(
        self,
        *,
        later_turns: list[StoryTurnRecord],
        target_turn_id: str,
        receipt_id: str,
        updated_at: datetime,
    ) -> None:
        for turn in later_turns:
            turn.visibility_state = "hidden_by_rollback"
            turn.hidden_by_control_receipt_id = receipt_id
            turn.hidden_after_turn_id = target_turn_id
            turn.updated_at = updated_at
            self._session.add(turn)

    def _invalidate_workspace_materials_for_turns(
        self,
        *,
        later_turns: list[StoryTurnRecord],
        receipt_id: str,
        target_turn_id: str,
        updated_at: datetime,
    ) -> list[str]:
        if not later_turns:
            return []
        invalidated_ids: list[str] = []
        for turn in later_turns:
            stmt = (
                select(RuntimeWorkspaceMaterialRecord)
                .where(RuntimeWorkspaceMaterialRecord.story_id == turn.story_id)
                .where(RuntimeWorkspaceMaterialRecord.session_id == turn.session_id)
                .where(
                    RuntimeWorkspaceMaterialRecord.branch_head_id
                    == turn.branch_head_id
                )
                .where(RuntimeWorkspaceMaterialRecord.turn_id == turn.turn_id)
            )
            records = list(self._session.exec(stmt).all())
            for record in records:
                if record.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED.value:
                    continue
                metadata_json = dict(record.metadata_json or {})
                rollback_visibility = dict(
                    metadata_json.get("rollback_visibility") or {}
                )
                rollback_visibility.update(
                    {
                        "hidden_by_control_receipt_id": receipt_id,
                        "hidden_after_turn_id": target_turn_id,
                    }
                )
                metadata_json["rollback_visibility"] = rollback_visibility
                metadata_json["visibility_state"] = "hidden_by_rollback"
                metadata_json["hidden_after_turn_id"] = target_turn_id
                record.lifecycle = RuntimeWorkspaceMaterialLifecycle.INVALIDATED.value
                record.metadata_json = metadata_json
                record.updated_at = updated_at
                record.invalidated_at = updated_at
                self._session.add(record)
                invalidated_ids.append(record.material_id)
        return invalidated_ids

    @staticmethod
    def _merge_branch_rollback_metadata(
        *,
        branch: BranchHeadRecord,
        target_turn: StoryTurnRecord,
        receipt: BranchControlReceiptRecord,
        invalidated_material_ids: list[str],
        updated_at: datetime,
    ) -> dict:
        metadata_json = dict(branch.metadata_json or {})
        rollback_history = list(metadata_json.get("rollback_history") or [])
        rollback_history.append(
            {
                "receipt_id": receipt.receipt_id,
                "target_turn_id": target_turn.turn_id,
                "hidden_turn_ids": list(
                    receipt.metadata_json.get("visibility_transition", {}).get(
                        "hidden_turn_ids",
                        [],
                    )
                ),
                "invalidated_workspace_material_ids": list(invalidated_material_ids),
                "applied_at": updated_at.isoformat(),
            }
        )
        metadata_json["rollback_history"] = rollback_history
        metadata_json["rollback_cutoff_turn_id"] = target_turn.turn_id
        metadata_json["rollback_receipt_id"] = receipt.receipt_id
        metadata_json["rollback_applied_at"] = updated_at.isoformat()
        existing_hidden_turn_ids = [
            str(item).strip()
            for item in metadata_json.get("rollback_hidden_turn_ids", [])
            if str(item).strip()
        ]
        receipt_hidden_turn_ids = [
            str(item).strip()
            for item in receipt.metadata_json.get("visibility_transition", {}).get(
                "hidden_turn_ids",
                [],
            )
            if str(item).strip()
        ]
        metadata_json["rollback_hidden_turn_ids"] = list(
            dict.fromkeys([*existing_hidden_turn_ids, *receipt_hidden_turn_ids])
        )
        checkpoint_binding = receipt.metadata_json.get("checkpoint_binding")
        if isinstance(checkpoint_binding, dict):
            metadata_json["checkpoint_binding"] = dict(checkpoint_binding)
        graph_checkpoint_binding = receipt.metadata_json.get("graph_checkpoint_binding")
        if isinstance(graph_checkpoint_binding, dict):
            metadata_json[
                StoryRuntimeIdentityService._GRAPH_CHECKPOINT_BINDING_KEY
            ] = dict(graph_checkpoint_binding)
        return metadata_json

    def _branch_count(self, *, session_id: str) -> int:
        stmt = select(BranchHeadRecord).where(
            BranchHeadRecord.session_id == session_id
        )
        return len(list(self._session.exec(stmt).all()))

    def _require_branch_switchable(self, branch: BranchHeadRecord) -> None:
        visibility_state = str(branch.visibility_state or "").strip()
        if (
            branch.status == BranchHeadStatus.ACTIVE.value
            and visibility_state == BranchVisibilityState.VISIBLE.value
        ):
            return
        raise StoryRuntimeIdentityServiceError(
            "runtime_branch_head_not_active",
            branch.branch_head_id,
        )

    def _fallback_active_branch_after_delete(
        self,
        *,
        session_record: StorySessionRecord,
        deleted_branch: BranchHeadRecord,
    ) -> str:
        parent_branch_id = str(deleted_branch.parent_branch_head_id or "").strip()
        if parent_branch_id:
            parent_branch = self.require_branch_head(parent_branch_id)
            self._validate_branch_belongs_to_session(
                session_record=session_record,
                branch=parent_branch,
            )
            self._require_branch_switchable(parent_branch)
            return parent_branch.branch_head_id
        default_branch = self.ensure_default_branch(
            session_id=session_record.session_id,
            story_id=session_record.story_id,
        )
        self._require_branch_switchable(default_branch)
        return default_branch.branch_head_id

    def _write_branch_control_receipt(
        self,
        *,
        session_record: StorySessionRecord,
        branch_head_id: str,
        control_kind: BranchControlKind,
        actor: str,
        fork_origin_turn_id: str | None = None,
        fork_base_turn_id: str | None = None,
        from_branch_head_id: str | None = None,
        to_branch_head_id: str | None = None,
        target_turn_id: str | None = None,
        source_ref_ids: list[str] | None = None,
        result_ref_ids: list[str] | None = None,
        trace_refs: list[str] | None = None,
        metadata: dict | None = None,
        created_at: datetime | None = None,
    ) -> BranchControlReceiptRecord:
        record = BranchControlReceiptRecord(
            receipt_id=f"branch-control:{uuid4().hex}",
            story_id=session_record.story_id,
            session_id=session_record.session_id,
            branch_head_id=branch_head_id,
            control_kind=control_kind.value,
            actor=str(actor or "").strip() or "story_runtime",
            fork_origin_turn_id=fork_origin_turn_id,
            fork_base_turn_id=fork_base_turn_id,
            from_branch_head_id=from_branch_head_id,
            to_branch_head_id=to_branch_head_id,
            target_turn_id=target_turn_id,
            source_ref_ids_json=list(source_ref_ids or []),
            result_ref_ids_json=list(result_ref_ids or []),
            trace_refs_json=list(trace_refs or []),
            metadata_json=dict(metadata or {}),
            created_at=created_at or _utcnow(),
        )
        self._session.add(record)
        self._session.flush()
        return record

    @staticmethod
    def _record_to_branch_control_receipt(
        record: BranchControlReceiptRecord,
    ) -> BranchControlReceipt:
        return BranchControlReceipt(
            receipt_id=record.receipt_id,
            session_id=record.session_id,
            story_id=record.story_id,
            branch_head_id=record.branch_head_id,
            control_kind=BranchControlKind(record.control_kind),
            actor=record.actor,
            fork_origin_turn_id=record.fork_origin_turn_id,
            fork_base_turn_id=record.fork_base_turn_id,
            from_branch_head_id=record.from_branch_head_id,
            to_branch_head_id=record.to_branch_head_id,
            target_turn_id=record.target_turn_id,
            source_ref_ids=list(record.source_ref_ids_json or []),
            result_ref_ids=list(record.result_ref_ids_json or []),
            trace_refs=list(record.trace_refs_json or []),
            metadata=dict(record.metadata_json or {}),
            created_at=record.created_at,
        )

    def _resolve_runtime_entry_branch(
        self,
        *,
        session_record: StorySessionRecord,
        requested_branch_head_id: str | None,
    ) -> BranchHeadRecord:
        requested_branch_id = str(requested_branch_head_id or "").strip()
        if requested_branch_id:
            branch = self.require_branch_head(requested_branch_id)
            self._require_branch_switchable(branch)
            return branch

        pinned_branch_id = str(session_record.active_branch_head_id or "").strip()
        if not pinned_branch_id:
            return self.ensure_default_branch(
                session_id=session_record.session_id,
                story_id=session_record.story_id,
            )
        if pinned_branch_id == self._default_branch_id(session_record.session_id):
            return self.ensure_default_branch(
                session_id=session_record.session_id,
                story_id=session_record.story_id,
            )
        branch = self.require_branch_head(pinned_branch_id)
        self._require_branch_switchable(branch)
        return branch

    def _resolve_runtime_entry_snapshot(
        self,
        *,
        session_record: StorySessionRecord,
        requested_runtime_profile_snapshot_id: str | None,
    ):
        requested_snapshot_id = str(requested_runtime_profile_snapshot_id or "").strip()
        if requested_snapshot_id:
            try:
                return self._runtime_profile_snapshot_service.require_snapshot(
                    requested_snapshot_id
                )
            except RuntimeProfileSnapshotServiceError as exc:
                raise StoryRuntimeIdentityServiceError(
                    exc.code,
                    requested_snapshot_id,
                ) from exc
        try:
            return self._runtime_profile_snapshot_service.require_active_snapshot(
                session_id=session_record.session_id,
            )
        except RuntimeProfileSnapshotServiceError as exc:
            if exc.code != "runtime_profile_snapshot_no_active_snapshot":
                raise StoryRuntimeIdentityServiceError(
                    exc.code,
                    session_record.session_id,
                ) from exc
        return self._runtime_profile_snapshot_service.ensure_active_snapshot(
            session_id=session_record.session_id,
            created_from="story_runtime.turn_start",
        )

    def _pin_session_active_branch_if_unset(
        self,
        *,
        session_record: StorySessionRecord,
        branch_head_id: str,
        updated_at: datetime | None = None,
    ) -> None:
        current_branch_id = str(session_record.active_branch_head_id or "").strip()
        if current_branch_id:
            return
        session_record.active_branch_head_id = branch_head_id
        session_record.updated_at = updated_at or _utcnow()
        self._session.add(session_record)
        self._session.flush()
