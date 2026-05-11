"""Read-only runtime inspection bundle for story-runtime debug surfaces."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlmodel import Session, select

from models.rp_memory_store import MemoryChangeEventRecord, RuntimeWorkspaceMaterialRecord
from models.rp_retrieval_store import IndexJobRecord, SourceAssetRecord
from models.rp_story_store import (
    BranchControlReceiptRecord,
    BranchHeadRecord,
    RuntimeConfigControlReceiptRecord,
    RuntimeProfileSnapshotRecord,
    StoryTurnRecord,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
)

from .memory_trace_read_service import MemoryTraceReadService
from .runtime_profile_snapshot_service import (
    RuntimeProfileSnapshotService,
    RuntimeProfileSnapshotServiceError,
)
from .runtime_read_manifest_service import BranchVisibilityResolver
from .runtime_workflow_job_service import RuntimeWorkflowJobService
from .story_runtime_identity_service import StoryRuntimeIdentityService
from .story_session_service import StorySessionService

_DEFAULT_LIMIT = 25
_MAX_LIMIT = 100

_RUNTIME_INSPECT_BOUNDARIES = [
    "read_only_debug_surface",
    "does_not_mutate_runtime_truth",
    "graph_checkpoint_debug_remains_separate_route",
    "runtime_workspace_materials_are_evidence_not_truth",
    "branch_control_receipts_stay_outside_story_turn_timeline",
    "runtime_config_control_history_stays_outside_story_turn_timeline",
    "story_evolution_history_is_receipt_readback_not_truth",
    "extension_sidecars_expose_formal_source_refs_only",
]


class StoryRuntimeDebugQueryServiceError(ValueError):
    """Stable runtime debug/inspect read error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class StoryRuntimeDebugQueryService:
    """Assemble a minimal runtime-native inspection bundle without writes."""

    def __init__(
        self,
        *,
        session: Session,
        story_session_service: StorySessionService,
        runtime_profile_snapshot_service: RuntimeProfileSnapshotService | None = None,
        memory_trace_read_service: MemoryTraceReadService | None = None,
        runtime_workflow_job_service: RuntimeWorkflowJobService | None = None,
        branch_visibility_resolver: BranchVisibilityResolver | None = None,
    ) -> None:
        self._session = session
        self._story_session_service = story_session_service
        self._runtime_profile_snapshot_service = (
            runtime_profile_snapshot_service
            or RuntimeProfileSnapshotService(session)
        )
        self._memory_trace_read_service = (
            memory_trace_read_service or MemoryTraceReadService(session=session)
        )
        self._runtime_workflow_job_service = (
            runtime_workflow_job_service or RuntimeWorkflowJobService(session)
        )
        self._branch_visibility_resolver = (
            branch_visibility_resolver or BranchVisibilityResolver(session)
        )

    def read_runtime_inspection(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
        turn_id: str | None = None,
        target_chapter_index: int | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        normalized_limit = _normalize_limit(limit)
        session = self._require_session(session_id)
        branches = self._list_branch_records(session_id=session.session_id)
        selected_branch = self._select_branch(
            session_id=session.session_id,
            active_branch_head_id=session.active_branch_head_id,
            branches=branches,
            requested_branch_head_id=branch_head_id,
        )
        available_turns = self._list_turn_records(
            session_id=session.session_id,
            branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            limit=normalized_limit,
        )
        selected_turn = self._select_turn(
            session_id=session.session_id,
            selected_branch=selected_branch,
            available_turns=available_turns,
            requested_turn_id=turn_id,
        )
        latest_branch_receipts = self._latest_branch_control_receipts_by_branch(
            session_id=session.session_id
        )
        snapshot = self._resolve_snapshot(
            session_id=session.session_id,
            selected_turn=selected_turn,
            active_snapshot_id=session.active_runtime_profile_snapshot_id,
        )
        identity = self._identity_from_turn(selected_turn=selected_turn)
        branch_read_scope_model = (
            None
            if identity is None
            else self._branch_visibility_resolver.build_runtime_scope(
                identity=identity
            )
        )
        turn_trace = (
            None
            if identity is None
            else self._memory_trace_read_service.get_turn_trace(identity=identity)
        )
        jobs = (
            []
            if selected_turn is None
            else [
                self._job_item(item)
                for item in self._runtime_workflow_job_service.list_jobs_for_turn(
                    turn_id=selected_turn.turn_id
                )
            ]
        )
        writer_packet = self._writer_packet_summary(turn_trace=turn_trace)
        worker_execution = self._worker_execution_summary(
            turn_trace=turn_trace,
            jobs=jobs,
        )
        retrieval = self._retrieval_summary(turn_trace=turn_trace)
        branch_receipts = [
            self._branch_control_receipt_item(item)
            for item in self._list_branch_control_receipts(
                session_id=session.session_id,
                branch_head_id=(
                    None if selected_branch is None else selected_branch.branch_head_id
                ),
                limit=normalized_limit,
            )
        ]
        runtime_config = self._runtime_config_summary(
            session=session,
            limit=normalized_limit,
        )
        story_evolution = self._story_evolution_summary(
            story_id=session.story_id,
            session_id=session.session_id,
            selected_branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            selected_turn_id=(None if selected_turn is None else selected_turn.turn_id),
            branch_read_scope=branch_read_scope_model,
            limit=normalized_limit,
        )
        chapter_bridge = self._chapter_bridge_summary(
            story_id=session.story_id,
            session_id=session.session_id,
            selected_branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            branch_read_scope=branch_read_scope_model,
            target_chapter_index=target_chapter_index,
            limit=normalized_limit,
        )
        chapter_progress = self._chapter_progress_summary(
            story_id=session.story_id,
            session_id=session.session_id,
            selected_branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            branch_read_scope=branch_read_scope_model,
            target_chapter_index=target_chapter_index,
            limit=normalized_limit,
        )
        mode_sidecars = self._mode_sidecar_summary(
            story_id=session.story_id,
            session_id=session.session_id,
            selected_branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            branch_read_scope=branch_read_scope_model,
            turn_trace=turn_trace,
            limit=normalized_limit,
        )
        active_snapshot_id = _optional_text(session.active_runtime_profile_snapshot_id)
        warnings: list[str] = []
        if selected_branch is None:
            warnings.append("runtime_branch_unavailable_for_session")
        if selected_turn is None:
            warnings.append("no_exact_turn_selected_for_branch")
        if snapshot is None:
            if selected_turn is None and active_snapshot_id is not None:
                warnings.append("runtime_profile_snapshot_stale_session_anchor")
            warnings.append("runtime_profile_snapshot_unavailable")
        return {
            "surface_role": "story_runtime_debug_inspect_read_surface",
            "read_only": True,
            "selection": {
                "requested_branch_head_id": _optional_text(branch_head_id),
                "requested_turn_id": _optional_text(turn_id),
                "selected_branch_head_id": (
                    None if selected_branch is None else selected_branch.branch_head_id
                ),
                "selected_turn_id": (
                    None if selected_turn is None else selected_turn.turn_id
                ),
                "selected_runtime_profile_snapshot_id": (
                    None
                    if snapshot is None
                    else snapshot.runtime_profile_snapshot_id
                ),
            },
            "session": session.model_dump(mode="json"),
            "selected_branch": (
                None
                if selected_branch is None
                else self._branch_record_item(
                    selected_branch,
                    latest_receipt=latest_branch_receipts.get(
                        selected_branch.branch_head_id
                    ),
                )
            ),
            "available_branches": [
                self._branch_record_item(
                    item,
                    latest_receipt=latest_branch_receipts.get(item.branch_head_id),
                )
                for item in branches
            ],
            "selected_turn": (
                None if selected_turn is None else _record_json(selected_turn)
            ),
            "available_turns": [_record_json(item) for item in available_turns],
            "branch_anchor_turn_id": (
                None
                if selected_branch is None
                else _optional_text(
                    selected_branch.head_turn_id or selected_branch.last_settled_turn_id
                )
            ),
            "graph_thread_binding": (
                None
                if selected_branch is None
                else {
                    "branch_head_id": selected_branch.branch_head_id,
                    "graph_thread_id": StoryRuntimeIdentityService.build_graph_thread_id(
                        session_id=session.session_id,
                        branch_head_id=selected_branch.branch_head_id,
                    ),
                }
            ),
            "runtime_profile_snapshot": (
                None if snapshot is None else _record_json(snapshot)
            ),
            "branch_read_scope": (
                None
                if branch_read_scope_model is None
                else branch_read_scope_model.model_dump(mode="json")
            ),
            "runtime_config": runtime_config,
            "story_evolution": story_evolution,
            "writer_packet": writer_packet,
            "worker_execution": worker_execution,
            "retrieval": retrieval,
            "chapter_bridge": chapter_bridge,
            "chapter_progress": chapter_progress,
            "mode_sidecars": mode_sidecars,
            "runtime_workspace": {
                "materials": []
                if turn_trace is None
                else list(turn_trace.get("runtime_workspace_materials") or []),
                "material_count": 0
                if turn_trace is None
                else len(turn_trace.get("runtime_workspace_materials") or []),
            },
            "proposal_governance": {
                "proposal_receipts": []
                if turn_trace is None
                else list(turn_trace.get("proposal_receipts") or []),
            },
            "memory_events": {
                "events": [] if turn_trace is None else list(turn_trace.get("events") or []),
                "dirty_targets": []
                if turn_trace is None
                else list(turn_trace.get("dirty_targets") or []),
            },
            "job_ledger": {
                "items": jobs,
                "status_counts": self._count_values(
                    item["status"] for item in jobs if item.get("status") is not None
                ),
            },
            "branch_control_receipts": branch_receipts,
            "turn_trace": turn_trace,
            "warnings": warnings,
            "boundaries": list(_RUNTIME_INSPECT_BOUNDARIES),
        }

    def read_story_evolution_history(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
        turn_id: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        normalized_limit = _normalize_limit(limit)
        session = self._require_session(session_id)
        branches = self._list_branch_records(session_id=session.session_id)
        selected_branch = self._select_branch(
            session_id=session.session_id,
            active_branch_head_id=session.active_branch_head_id,
            branches=branches,
            requested_branch_head_id=branch_head_id,
        )
        available_turns = self._list_turn_records(
            session_id=session.session_id,
            branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            limit=normalized_limit,
        )
        selected_turn = self._select_turn(
            session_id=session.session_id,
            selected_branch=selected_branch,
            available_turns=available_turns,
            requested_turn_id=turn_id,
        )
        identity = self._identity_from_turn(selected_turn=selected_turn)
        branch_read_scope = (
            None
            if identity is None
            else self._branch_visibility_resolver.build_runtime_scope(identity=identity)
        )
        payload = self._story_evolution_summary(
            story_id=session.story_id,
            session_id=session.session_id,
            selected_branch_head_id=(
                None if selected_branch is None else selected_branch.branch_head_id
            ),
            selected_turn_id=(None if selected_turn is None else selected_turn.turn_id),
            branch_read_scope=branch_read_scope,
            limit=normalized_limit,
        )
        payload["read_only"] = True
        payload["surface_role"] = "story_evolution_history_read_surface"
        payload["boundaries"] = [
            "read_only_story_evolution_history_surface",
            "does_not_mutate_archival_truth",
            "branch_visibility_filter_applies_to_receipt_readback",
        ]
        return payload

    def _require_session(self, session_id: str):
        session = self._story_session_service.get_session(session_id)
        if session is None:
            raise StoryRuntimeDebugQueryServiceError(
                "story_runtime_debug_session_not_found",
                session_id,
            )
        return session

    def _select_branch(
        self,
        *,
        session_id: str,
        active_branch_head_id: str | None,
        branches: list[BranchHeadRecord],
        requested_branch_head_id: str | None,
    ) -> BranchHeadRecord | None:
        requested_branch_id = _optional_text(requested_branch_head_id)
        if requested_branch_id is not None:
            for branch in branches:
                if branch.branch_head_id == requested_branch_id:
                    return branch
            raise StoryRuntimeDebugQueryServiceError(
                "story_runtime_debug_branch_not_found",
                requested_branch_id,
            )
        active_branch_id = _optional_text(active_branch_head_id)
        if active_branch_id is not None:
            for branch in branches:
                if branch.branch_head_id == active_branch_id:
                    return branch
        for branch in branches:
            if branch.session_id == session_id:
                return branch
        return None

    def _select_turn(
        self,
        *,
        session_id: str,
        selected_branch: BranchHeadRecord | None,
        available_turns: list[StoryTurnRecord],
        requested_turn_id: str | None,
    ) -> StoryTurnRecord | None:
        requested_turn = _optional_text(requested_turn_id)
        if requested_turn is not None:
            record = self._session.get(StoryTurnRecord, requested_turn)
            if record is None or record.session_id != session_id:
                raise StoryRuntimeDebugQueryServiceError(
                    "story_runtime_debug_turn_not_found",
                    requested_turn,
                )
            if (
                selected_branch is not None
                and record.branch_head_id != selected_branch.branch_head_id
            ):
                raise StoryRuntimeDebugQueryServiceError(
                    "story_runtime_debug_turn_branch_mismatch",
                    requested_turn,
                )
            return record
        if selected_branch is None:
            return None
        selected_anchor_turn_id = _optional_text(selected_branch.head_turn_id)
        if selected_anchor_turn_id is None:
            selected_anchor_turn_id = _optional_text(selected_branch.last_settled_turn_id)
        if selected_anchor_turn_id is not None:
            record = self._session.get(StoryTurnRecord, selected_anchor_turn_id)
            if (
                record is not None
                and record.session_id == session_id
                and record.branch_head_id == selected_branch.branch_head_id
            ):
                return record
        return available_turns[0] if available_turns else None

    def _resolve_snapshot(
        self,
        *,
        session_id: str,
        selected_turn: StoryTurnRecord | None,
        active_snapshot_id: str | None,
    ) -> RuntimeProfileSnapshotRecord | None:
        snapshot_id = (
            selected_turn.runtime_profile_snapshot_id
            if selected_turn is not None
            else _optional_text(active_snapshot_id)
        )
        if snapshot_id is None:
            return None
        try:
            snapshot = self._runtime_profile_snapshot_service.require_snapshot(snapshot_id)
        except RuntimeProfileSnapshotServiceError:
            if selected_turn is None:
                return None
            raise
        if snapshot.session_id != session_id:
            if selected_turn is None:
                return None
            raise StoryRuntimeDebugQueryServiceError(
                "story_runtime_debug_snapshot_session_mismatch",
                snapshot_id,
            )
        return snapshot

    def _list_branch_records(self, *, session_id: str) -> list[BranchHeadRecord]:
        stmt = (
            select(BranchHeadRecord)
            .where(BranchHeadRecord.session_id == session_id)
            .order_by(BranchHeadRecord.created_at.asc())
            .order_by(BranchHeadRecord.branch_head_id.asc())
        )
        return list(self._session.exec(stmt).all())

    @staticmethod
    def _identity_from_turn(
        *,
        selected_turn: StoryTurnRecord | None,
    ) -> MemoryRuntimeIdentity | None:
        if selected_turn is None:
            return None
        return MemoryRuntimeIdentity(
            story_id=selected_turn.story_id,
            session_id=selected_turn.session_id,
            branch_head_id=selected_turn.branch_head_id,
            turn_id=selected_turn.turn_id,
            runtime_profile_snapshot_id=selected_turn.runtime_profile_snapshot_id,
        )

    def _list_turn_records(
        self,
        *,
        session_id: str,
        branch_head_id: str | None,
        limit: int,
    ) -> list[StoryTurnRecord]:
        stmt = select(StoryTurnRecord).where(StoryTurnRecord.session_id == session_id)
        if branch_head_id is not None:
            stmt = stmt.where(StoryTurnRecord.branch_head_id == branch_head_id)
        stmt = (
            stmt.order_by(StoryTurnRecord.created_at.desc())
            .order_by(StoryTurnRecord.turn_id.desc())
            .limit(limit)
        )
        return list(self._session.exec(stmt).all())

    def _list_branch_control_receipts(
        self,
        *,
        session_id: str,
        branch_head_id: str | None,
        limit: int,
    ) -> list[BranchControlReceiptRecord]:
        stmt = select(BranchControlReceiptRecord).where(
            BranchControlReceiptRecord.session_id == session_id
        )
        if branch_head_id is not None:
            stmt = stmt.where(BranchControlReceiptRecord.branch_head_id == branch_head_id)
        stmt = (
            stmt.order_by(BranchControlReceiptRecord.created_at.desc())
            .order_by(BranchControlReceiptRecord.receipt_id.desc())
            .limit(limit)
        )
        return list(self._session.exec(stmt).all())

    def _latest_branch_control_receipts_by_branch(
        self,
        *,
        session_id: str,
    ) -> dict[str, dict[str, Any]]:
        stmt = (
            select(BranchControlReceiptRecord)
            .where(BranchControlReceiptRecord.session_id == session_id)
            .order_by(BranchControlReceiptRecord.created_at.desc())
            .order_by(BranchControlReceiptRecord.receipt_id.desc())
        )
        latest: dict[str, dict[str, Any]] = {}
        for record in self._session.exec(stmt).all():
            if record.branch_head_id in latest:
                continue
            latest[record.branch_head_id] = self._branch_control_receipt_item(record)
        return latest

    def _list_runtime_config_receipts(
        self,
        *,
        session_id: str,
        limit: int,
    ) -> list[RuntimeConfigControlReceiptRecord]:
        stmt = (
            select(RuntimeConfigControlReceiptRecord)
            .where(RuntimeConfigControlReceiptRecord.session_id == session_id)
            .order_by(RuntimeConfigControlReceiptRecord.created_at.desc())
            .order_by(RuntimeConfigControlReceiptRecord.receipt_id.desc())
            .limit(limit)
        )
        return list(self._session.exec(stmt).all())

    def _list_story_evolution_assets(
        self,
        *,
        story_id: str,
    ) -> list[SourceAssetRecord]:
        stmt = (
            select(SourceAssetRecord)
            .where(SourceAssetRecord.story_id == story_id)
            .order_by(SourceAssetRecord.created_at.desc())
            .order_by(SourceAssetRecord.asset_id.desc())
        )
        return list(self._session.exec(stmt).all())

    def _list_story_evolution_events(
        self,
        *,
        story_id: str,
    ) -> list[MemoryChangeEventRecord]:
        stmt = (
            select(MemoryChangeEventRecord)
            .where(MemoryChangeEventRecord.story_id == story_id)
            .where(MemoryChangeEventRecord.event_kind == "archival_source_evolved")
            .order_by(MemoryChangeEventRecord.created_at.desc())
            .order_by(MemoryChangeEventRecord.event_id.desc())
        )
        return list(self._session.exec(stmt).all())

    def _list_index_jobs(
        self,
        *,
        story_id: str,
    ) -> list[IndexJobRecord]:
        stmt = (
            select(IndexJobRecord)
            .where(IndexJobRecord.story_id == story_id)
            .order_by(IndexJobRecord.created_at.desc())
            .order_by(IndexJobRecord.job_id.desc())
        )
        return list(self._session.exec(stmt).all())

    def _list_branch_workspace_materials(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        material_kind: str | None = None,
    ) -> list[RuntimeWorkspaceMaterialRecord]:
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(RuntimeWorkspaceMaterialRecord.story_id == story_id)
            .where(RuntimeWorkspaceMaterialRecord.session_id == session_id)
            .where(RuntimeWorkspaceMaterialRecord.branch_head_id == branch_head_id)
            .order_by(RuntimeWorkspaceMaterialRecord.created_at.desc())
            .order_by(RuntimeWorkspaceMaterialRecord.material_id.desc())
        )
        if material_kind is not None:
            stmt = stmt.where(RuntimeWorkspaceMaterialRecord.material_kind == material_kind)
        return list(self._session.exec(stmt).all())

    @staticmethod
    def _job_item(record) -> dict[str, Any]:
        return {
            "job_id": record.job_id,
            "turn_id": record.turn_id,
            "story_id": record.story_id,
            "session_id": record.session_id,
            "branch_head_id": record.branch_head_id,
            "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
            "job_kind": record.job_kind,
            "job_category": record.job_category,
            "status": record.status,
            "creation_mode": record.creation_mode,
            "required_for_turn_completion": record.required_for_turn_completion,
            "worker_id": record.worker_id,
            "parent_job_id": record.parent_job_id,
            "idempotency_key": record.idempotency_key,
            "source_ref_ids": list(record.source_ref_ids_json or []),
            "result_ref_ids": list(record.result_ref_ids_json or []),
            "trace_refs": list(record.trace_refs_json or []),
            "attempt_count": record.attempt_count,
            "completion_reason": record.completion_reason,
            "failure_reason": record.failure_reason,
            "last_error": deepcopy(record.last_error_json),
            "metadata": deepcopy(record.metadata_json or {}),
            "created_at": record.created_at.isoformat(),
            "started_at": _datetime_or_none(record.started_at),
            "completed_at": _datetime_or_none(record.completed_at),
        }

    @staticmethod
    def _branch_control_receipt_item(record: BranchControlReceiptRecord) -> dict[str, Any]:
        return {
            "receipt_id": record.receipt_id,
            "story_id": record.story_id,
            "session_id": record.session_id,
            "branch_head_id": record.branch_head_id,
            "control_kind": record.control_kind,
            "actor": record.actor,
            "fork_origin_turn_id": record.fork_origin_turn_id,
            "fork_base_turn_id": record.fork_base_turn_id,
            "from_branch_head_id": record.from_branch_head_id,
            "to_branch_head_id": record.to_branch_head_id,
            "target_turn_id": record.target_turn_id,
            "source_ref_ids": list(record.source_ref_ids_json or []),
            "result_ref_ids": list(record.result_ref_ids_json or []),
            "trace_refs": list(record.trace_refs_json or []),
            "metadata": deepcopy(record.metadata_json or {}),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _runtime_config_receipt_item(
        record: RuntimeConfigControlReceiptRecord,
    ) -> dict[str, Any]:
        return {
            "receipt_id": record.receipt_id,
            "story_id": record.story_id,
            "session_id": record.session_id,
            "previous_snapshot_id": record.previous_snapshot_id,
            "published_snapshot_id": record.published_snapshot_id,
            "changed_fields": list(record.changed_fields_json or []),
            "actor_id": record.actor_id,
            "source": record.source,
            "reason": record.reason,
            "metadata": deepcopy(record.metadata_json or {}),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _branch_record_item(
        record: BranchHeadRecord,
        *,
        latest_receipt: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = _record_json(record)
        payload["latest_control_receipt"] = deepcopy(latest_receipt)
        return payload

    @classmethod
    def _writer_packet_summary(cls, *, turn_trace: dict[str, Any] | None) -> dict[str, Any] | None:
        if turn_trace is None:
            return None
        materials = list(turn_trace.get("runtime_workspace_materials") or [])
        material_groups = cls._group_materials_by_kind(materials)
        manifests = list(turn_trace.get("read_manifests") or [])
        packet_refs = material_groups.get(RuntimeWorkspaceMaterialKind.PACKET_REF.value, [])
        writer_inputs = material_groups.get(
            RuntimeWorkspaceMaterialKind.WRITER_INPUT_REF.value,
            [],
        )
        writer_outputs = material_groups.get(
            RuntimeWorkspaceMaterialKind.WRITER_OUTPUT_REF.value,
            [],
        )
        if not manifests and not packet_refs and not writer_inputs and not writer_outputs:
            return None
        return {
            "writer_input_refs": writer_inputs,
            "packet_refs": packet_refs,
            "writer_output_refs": writer_outputs,
            "read_manifests": manifests,
            "runtime_read_manifest_ids": _unique_non_blank(
                item.get("payload", {}).get("runtime_read_manifest_id")
                for item in [*packet_refs, *writer_outputs]
            ),
        }

    @classmethod
    def _worker_execution_summary(
        cls,
        *,
        turn_trace: dict[str, Any] | None,
        jobs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        materials = [] if turn_trace is None else list(
            turn_trace.get("runtime_workspace_materials") or []
        )
        material_groups = cls._group_materials_by_kind(materials)
        job_metadata_worker_plan_ids = _unique_non_blank(
            item.get("metadata", {}).get("worker_plan_id")
            for item in jobs
        )
        worker_plan_refs = [
            f"worker_plan:{item}" for item in job_metadata_worker_plan_ids if item
        ]
        worker_result_refs = _unique_non_blank(
            ref
            for item in jobs
            for ref in (
                *list(item.get("source_ref_ids") or []),
                *list(item.get("result_ref_ids") or []),
                *list(item.get("trace_refs") or []),
            )
            if str(ref).strip().startswith("worker_result:")
        )
        return {
            "prewrite_worker_results": material_groups.get(
                RuntimeWorkspaceMaterialKind.WORKER_EVIDENCE_BUNDLE.value,
                [],
            ),
            "worker_candidate_materials": material_groups.get(
                RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE.value,
                [],
            ),
            "post_write_traces": material_groups.get(
                RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE.value,
                [],
            ),
            "worker_plan_refs": worker_plan_refs,
            "worker_result_refs": worker_result_refs,
        }

    @classmethod
    def _retrieval_summary(cls, *, turn_trace: dict[str, Any] | None) -> dict[str, Any]:
        materials = [] if turn_trace is None else list(
            turn_trace.get("runtime_workspace_materials") or []
        )
        material_groups = cls._group_materials_by_kind(materials)
        return {
            "cards": material_groups.get(
                RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD.value,
                [],
            ),
            "expanded_chunks": material_groups.get(
                RuntimeWorkspaceMaterialKind.RETRIEVAL_EXPANDED_CHUNK.value,
                [],
            ),
            "misses": material_groups.get(
                RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS.value,
                [],
            ),
            "usage_records": material_groups.get(
                RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD.value,
                [],
            ),
            "usage_refs": []
            if turn_trace is None
            else list(turn_trace.get("retrieval_usage_refs") or []),
        }

    def _runtime_config_summary(
        self,
        *,
        session,
        limit: int,
    ) -> dict[str, Any]:
        receipts = self._list_runtime_config_receipts(
            session_id=session.session_id,
            limit=limit,
        )
        return {
            "active_runtime_profile_snapshot_id": _optional_text(
                session.active_runtime_profile_snapshot_id
            ),
            "effective_runtime_story_config": deepcopy(
                session.runtime_story_config or {}
            ),
            "control_history": [
                self._runtime_config_receipt_item(item) for item in receipts
            ],
        }

    def _story_evolution_summary(
        self,
        *,
        story_id: str,
        session_id: str,
        selected_branch_head_id: str | None,
        selected_turn_id: str | None,
        branch_read_scope,
        limit: int,
    ) -> dict[str, Any]:
        items = self._story_evolution_items(
            story_id=story_id,
            branch_read_scope=branch_read_scope,
            limit=limit,
        )
        return {
            "session_id": session_id,
            "selected_branch_head_id": selected_branch_head_id,
            "selected_turn_id": selected_turn_id,
            "items": items,
        }

    def _story_evolution_items(
        self,
        *,
        story_id: str,
        branch_read_scope,
        limit: int,
    ) -> list[dict[str, Any]]:
        assets = self._list_story_evolution_assets(story_id=story_id)
        events = self._list_story_evolution_events(story_id=story_id)
        jobs_by_id = {
            item.job_id: item for item in self._list_index_jobs(story_id=story_id)
        }
        events_by_evolution_id: dict[str, MemoryChangeEventRecord] = {}
        for event in events:
            metadata = dict(event.metadata_json or {})
            evolution_id = _optional_text(metadata.get("evolution_id") or event.entry_id)
            if evolution_id is None or evolution_id in events_by_evolution_id:
                continue
            events_by_evolution_id[evolution_id] = event
        items: list[dict[str, Any]] = []
        for asset in assets:
            metadata = dict(asset.metadata_json or {})
            evolution_id = _optional_text(metadata.get("archival_evolution_id"))
            if evolution_id is None:
                continue
            if (
                branch_read_scope is not None
                and not self._source_asset_visible(
                    metadata=metadata,
                    branch_read_scope=branch_read_scope,
                )
            ):
                continue
            event = events_by_evolution_id.get(evolution_id)
            event_metadata = {} if event is None else dict(event.metadata_json or {})
            reindex_job_id = _optional_text(event_metadata.get("reindex_job_id"))
            reindex_job = (
                None if reindex_job_id is None else jobs_by_id.get(reindex_job_id)
            )
            warnings = list(event_metadata.get("warnings") or [])
            items.append(
                {
                    "evolution_id": evolution_id,
                    "source_asset_id": asset.asset_id,
                    "root_source_asset_id": _optional_text(
                        metadata.get("root_source_asset_id")
                    ),
                    "new_source_version": metadata.get("source_version")
                    or metadata.get("source_asset_version"),
                    "superseded_source_asset_id": _optional_text(
                        metadata.get("supersedes_source_asset_id")
                    ),
                    "superseded_source_version": metadata.get(
                        "supersedes_source_version"
                    ),
                    "visibility_scope": _optional_text(
                        metadata.get("visibility_scope")
                    )
                    or "current_branch",
                    "selected_branch_head_ids": _string_list(
                        metadata.get("selected_branch_head_ids")
                    ),
                    "reason": _optional_text(metadata.get("reason")),
                    "source_refs": deepcopy(
                        event.source_refs_json if event is not None else metadata.get("source_refs") or []
                    ),
                    "event_ids": [] if event is None else [event.event_id],
                    "dirty_targets": []
                    if event is None
                    else deepcopy(event.dirty_targets_json or []),
                    "replacement_chunk_ids": list(
                        event_metadata.get("replacement_chunk_ids") or []
                    ),
                    "reindex_jobs": []
                    if reindex_job is None
                    else [
                        {
                            "job_id": reindex_job.job_id,
                            "job_kind": reindex_job.job_kind,
                            "job_state": reindex_job.job_state,
                            "warnings": list(reindex_job.warnings_json or []),
                            "error_message": reindex_job.error_message,
                            "created_at": reindex_job.created_at.isoformat(),
                            "completed_at": _datetime_or_none(
                                reindex_job.completed_at
                            ),
                        }
                    ],
                    "status": "pending_reindex"
                    if warnings
                    or (
                        reindex_job is not None
                        and reindex_job.job_state != "completed"
                    )
                    else "accepted",
                    "metadata": deepcopy(metadata),
                    "created_at": asset.created_at.isoformat(),
                    "updated_at": asset.updated_at.isoformat(),
                }
            )
            if len(items) >= limit:
                break
        return items

    def _chapter_bridge_summary(
        self,
        *,
        story_id: str,
        session_id: str,
        selected_branch_head_id: str | None,
        branch_read_scope,
        target_chapter_index: int | None,
        limit: int,
    ) -> dict[str, Any]:
        if selected_branch_head_id is None:
            return {
                "selected_branch_head_id": None,
                "target_chapter_index": target_chapter_index,
                "items": [],
                "latest_for_target_chapter": None,
            }
        records = self._list_branch_workspace_materials(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=selected_branch_head_id,
            material_kind=RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE.value,
        )
        items: list[dict[str, Any]] = []
        for record in records:
            if (
                branch_read_scope is not None
                and not self._workspace_material_visible(
                    record=record,
                    branch_read_scope=branch_read_scope,
                )
            ):
                continue
            payload = dict(record.payload_json or {})
            if _optional_text(payload.get("payload_kind")) != "chapter_bridge_material":
                continue
            bridge = payload.get("record")
            if not isinstance(bridge, dict):
                continue
            if (
                target_chapter_index is not None
                and int(bridge.get("target_chapter_index") or -1)
                != target_chapter_index
            ):
                continue
            items.append(
                {
                    "material_id": record.material_id,
                    "turn_id": record.turn_id,
                    "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
                    "source_chapter_index": bridge.get("source_chapter_index"),
                    "target_chapter_index": bridge.get("target_chapter_index"),
                    "adopted_output_ref": bridge.get("adopted_output_ref"),
                    "accepted_outline_ref": bridge.get("accepted_outline_ref"),
                    "chapter_goal_ref": bridge.get("chapter_goal_ref"),
                    "continuity_refs": list(bridge.get("continuity_refs") or []),
                    "summary_text": bridge.get("summary_text"),
                    "source_refs": deepcopy(record.source_refs_json or []),
                    "metadata": deepcopy(record.metadata_json or {}),
                    "created_at": record.created_at.isoformat(),
                }
            )
            if len(items) >= limit:
                break
        return {
            "selected_branch_head_id": selected_branch_head_id,
            "target_chapter_index": target_chapter_index,
            "items": items,
            "latest_for_target_chapter": items[0] if items else None,
        }

    def _chapter_progress_summary(
        self,
        *,
        story_id: str,
        session_id: str,
        selected_branch_head_id: str | None,
        branch_read_scope,
        target_chapter_index: int | None,
        limit: int,
    ) -> dict[str, Any]:
        if selected_branch_head_id is None:
            return {
                "selected_branch_head_id": None,
                "chapter_index": target_chapter_index,
                "items": [],
                "latest_for_chapter": None,
            }
        records = self._list_branch_workspace_materials(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=selected_branch_head_id,
            material_kind=RuntimeWorkspaceMaterialKind.POST_WRITE_TRACE.value,
        )
        items: list[dict[str, Any]] = []
        for record in records:
            if (
                branch_read_scope is not None
                and not self._workspace_material_visible(
                    record=record,
                    branch_read_scope=branch_read_scope,
                )
            ):
                continue
            payload = dict(record.payload_json or {})
            if _optional_text(payload.get("payload_kind")) != "longform_outline_progress":
                continue
            progress = payload.get("record")
            if not isinstance(progress, dict):
                continue
            if (
                target_chapter_index is not None
                and int(progress.get("chapter_index") or -1) != target_chapter_index
            ):
                continue
            covered_beat_ids = [
                str(item).strip()
                for item in list(progress.get("covered_beat_ids") or [])
                if str(item).strip()
            ]
            items.append(
                {
                    "material_id": record.material_id,
                    "turn_id": record.turn_id,
                    "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
                    "chapter_index": progress.get("chapter_index"),
                    "outline_artifact_id": progress.get("outline_artifact_id"),
                    "current_beat_id": progress.get("current_beat_id"),
                    "covered_beat_ids": covered_beat_ids,
                    "covered_beat_count": len(covered_beat_ids),
                    "segment_by_beat_id": deepcopy(progress.get("segment_by_beat_id") or {}),
                    "status_by_beat_id": deepcopy(progress.get("status_by_beat_id") or {}),
                    "metadata": deepcopy(record.metadata_json or {}),
                    "created_at": record.created_at.isoformat(),
                }
            )
            if len(items) >= limit:
                break
        return {
            "selected_branch_head_id": selected_branch_head_id,
            "chapter_index": target_chapter_index,
            "items": items,
            "latest_for_chapter": items[0] if items else None,
        }

    def _mode_sidecar_summary(
        self,
        *,
        story_id: str,
        session_id: str,
        selected_branch_head_id: str | None,
        branch_read_scope,
        turn_trace: dict[str, Any] | None,
        limit: int,
    ) -> dict[str, Any]:
        packet_sections: list[dict[str, Any]] = []
        for manifest in list((turn_trace or {}).get("read_manifests") or []):
            manifest_id = _optional_text(manifest.get("manifest_id"))
            for section in list(manifest.get("packet_sections") or []):
                if not isinstance(section, dict):
                    continue
                if self._packet_section_family(section) != "mode_sidecar":
                    continue
                packet_sections.append(
                    {
                        "manifest_id": manifest_id,
                        "section_id": section.get("section_id"),
                        "label": section.get("label"),
                        "source_ref_ids": list(section.get("source_ref_ids") or []),
                        "metadata": deepcopy(
                            section.get("metadata_json") or section.get("metadata") or {}
                        ),
                    }
                )
        if selected_branch_head_id is None:
            return {
                "selected_branch_head_id": None,
                "materials": [],
                "packet_sections": packet_sections,
            }
        records = self._list_branch_workspace_materials(
            story_id=story_id,
            session_id=session_id,
            branch_head_id=selected_branch_head_id,
        )
        sidecar_kinds = {
            RuntimeWorkspaceMaterialKind.RULE_CARD.value,
            RuntimeWorkspaceMaterialKind.RULE_STATE_CARD.value,
        }
        materials: list[dict[str, Any]] = []
        for record in records:
            if record.material_kind not in sidecar_kinds:
                continue
            if (
                branch_read_scope is not None
                and not self._workspace_material_visible(
                    record=record,
                    branch_read_scope=branch_read_scope,
                )
            ):
                continue
            materials.append(
                {
                    "material_id": record.material_id,
                    "turn_id": record.turn_id,
                    "runtime_profile_snapshot_id": record.runtime_profile_snapshot_id,
                    "material_kind": record.material_kind,
                    "domain": record.domain,
                    "domain_path": record.domain_path,
                    "short_id": record.short_id,
                    "lifecycle": record.lifecycle,
                    "visibility": record.visibility,
                    "source_refs": deepcopy(record.source_refs_json or []),
                    "created_at": record.created_at.isoformat(),
                }
            )
            if len(materials) >= limit:
                break
        return {
            "selected_branch_head_id": selected_branch_head_id,
            "materials": materials,
            "packet_sections": packet_sections,
        }

    @staticmethod
    def _packet_section_family(section: dict[str, Any]) -> str:
        metadata = dict(section.get("metadata_json") or section.get("metadata") or {})
        family = _optional_text(metadata.get("section_family"))
        if family is not None:
            return family
        source_kind = _optional_text(section.get("source_kind"))
        if source_kind in {"mode_sidecar", "runtime_mode_sidecar"}:
            return "mode_sidecar"
        section_id = _optional_text(section.get("section_id")) or ""
        if section_id.startswith("mode_sidecar."):
            return "mode_sidecar"
        return "packet_section"

    def _workspace_material_visible(
        self,
        *,
        record: RuntimeWorkspaceMaterialRecord,
        branch_read_scope,
    ) -> bool:
        lifecycle = str(record.lifecycle or "").strip().lower()
        visibility_state = (
            "hidden"
            if lifecycle
            in {
                RuntimeWorkspaceMaterialLifecycle.INVALIDATED.value,
                RuntimeWorkspaceMaterialLifecycle.EXPIRED.value,
                RuntimeWorkspaceMaterialLifecycle.DISCARDED.value,
            }
            else "active"
        )
        return self._branch_visibility_resolver.is_visible(
            scope=branch_read_scope,
            visibility_scope="branch_scoped",
            visibility_state=visibility_state,
            owning_branch_head_id=record.branch_head_id,
            origin_turn_id=record.turn_id,
        )

    def _source_asset_visible(
        self,
        *,
        metadata: dict[str, Any],
        branch_read_scope,
    ) -> bool:
        return self._branch_visibility_resolver.is_visible(
            scope=branch_read_scope,
            visibility_scope=(
                _optional_text(metadata.get("visibility_scope"))
                or self._default_asset_visibility_scope(metadata)
            ),
            visibility_state=(
                _optional_text(
                    metadata.get("visibility_state")
                    or metadata.get("lifecycle_state")
                )
                or "active"
            ),
            owning_branch_head_id=_first_text(
                metadata,
                "owning_branch_head_id",
                "branch_head_id",
                "branch_id",
            ),
            origin_turn_id=_first_text(metadata, "origin_turn_id", "turn_id"),
            selected_branch_head_ids=_string_list(
                metadata.get("selected_branch_head_ids")
                or metadata.get("branch_ids")
                or metadata.get("selected_branch_ids")
            ),
            hidden_by_branch_head_id=_first_text(metadata, "hidden_by_branch_head_id"),
            hidden_after_turn_id=_first_text(metadata, "hidden_after_turn_id"),
        )

    @staticmethod
    def _default_asset_visibility_scope(metadata: dict[str, Any]) -> str:
        if metadata.get("selected_branch_head_ids") or metadata.get("branch_ids"):
            return "selected_branches"
        if _first_text(
            metadata, "owning_branch_head_id", "branch_head_id", "branch_id"
        ):
            return "branch_scoped"
        return "story_global"

    @staticmethod
    def _group_materials_by_kind(
        materials: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in materials:
            material_kind = str(item.get("material_kind") or "").strip()
            if not material_kind:
                continue
            groups.setdefault(material_kind, []).append(item)
        return groups

    @staticmethod
    def _count_values(values) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            key = str(value or "").strip()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
        return counts


def _record_json(record) -> dict[str, Any]:
    return record.model_dump(mode="json")


def _normalize_limit(limit: int) -> int:
    return max(1, min(int(limit), _MAX_LIMIT))


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _unique_non_blank(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _first_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _optional_text(metadata.get(key))
        if value is not None:
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique_non_blank(value)


def _datetime_or_none(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()
