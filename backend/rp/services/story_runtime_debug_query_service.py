"""Read-only runtime inspection bundle for story-runtime debug surfaces."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlmodel import Session, select

from models.rp_story_store import (
    BranchControlReceiptRecord,
    BranchHeadRecord,
    RuntimeProfileSnapshotRecord,
    StoryTurnRecord,
)
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind

from .memory_trace_read_service import MemoryTraceReadService
from .runtime_profile_snapshot_service import RuntimeProfileSnapshotService
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
        snapshot = self._resolve_snapshot(
            session_id=session.session_id,
            selected_turn=selected_turn,
            active_snapshot_id=session.active_runtime_profile_snapshot_id,
        )
        identity = None if selected_turn is None else MemoryRuntimeIdentity(
            story_id=selected_turn.story_id,
            session_id=selected_turn.session_id,
            branch_head_id=selected_turn.branch_head_id,
            turn_id=selected_turn.turn_id,
            runtime_profile_snapshot_id=selected_turn.runtime_profile_snapshot_id,
        )
        branch_read_scope = (
            None
            if identity is None
            else self._branch_visibility_resolver.build_runtime_scope(
                identity=identity
            ).model_dump(mode="json")
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
        warnings: list[str] = []
        if selected_branch is None:
            warnings.append("runtime_branch_unavailable_for_session")
        if selected_turn is None:
            warnings.append("no_exact_turn_selected_for_branch")
        if snapshot is None:
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
                None if selected_branch is None else _record_json(selected_branch)
            ),
            "available_branches": [_record_json(item) for item in branches],
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
            "branch_read_scope": branch_read_scope,
            "writer_packet": writer_packet,
            "worker_execution": worker_execution,
            "retrieval": retrieval,
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
        snapshot = self._runtime_profile_snapshot_service.require_snapshot(snapshot_id)
        if snapshot.session_id != session_id:
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


def _datetime_or_none(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()
