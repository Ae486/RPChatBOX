"""Read-only migration summary for runtime-story compatibility surfaces."""

from __future__ import annotations

from typing import Any

from rp.models.story_runtime import LongformTurnCommandKind

from .story_runtime_debug_query_service import StoryRuntimeDebugQueryService

_COMPATIBILITY_SURFACES = [
    {
        "surface_id": "legacy_longform_command_surface",
        "status": "active_product_compat_entry",
        "runtime_truth_owner": "StoryRuntimeAdapterService",
        "boundary": "legacy command only translates into runtime-owned operation mode",
    },
    {
        "surface_id": "legacy_orchestrator_plan_adapter",
        "status": "adapter_input_only",
        "runtime_truth_owner": "WorkerExecutionPlan",
        "boundary": "legacy OrchestratorPlan does not define canonical worker plan",
    },
    {
        "surface_id": "legacy_specialist_executor_bridge",
        "status": "temporary_worker_executor",
        "runtime_truth_owner": "WorkerResult",
        "boundary": "LongformSpecialistService only survives behind LongformMemoryWorker",
    },
    {
        "surface_id": "thin_context_packet_builder",
        "status": "active",
        "runtime_truth_owner": "WritingPacket",
        "boundary": "builder only assembles digested packet slots and stable refs",
    },
]

_NATIVE_READ_SURFACES = [
    "runtime.inspect",
    "runtime.migration",
    "memory.trace.turn",
    "memory.trace.proposal",
    "memory.trace.material",
    "runtime.debug.graph_shell",
]

_MIGRATION_BOUNDARIES = [
    "migration_surface_is_read_only",
    "does_not_reintroduce_fixed_chain_as_runtime_truth",
    "legacy_mvp_surfaces_remain_reference_or_adapter_only",
]


class StoryRuntimeMigrationService:
    """Summarize compatibility state without mutating runtime data."""

    def __init__(
        self,
        *,
        debug_query_service: StoryRuntimeDebugQueryService,
    ) -> None:
        self._debug_query_service = debug_query_service

    def read_runtime_migration_summary(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        inspection = self._debug_query_service.read_runtime_inspection(
            session_id=session_id,
            branch_head_id=branch_head_id,
            turn_id=turn_id,
            limit=limit,
        )
        observed_markers = self._observed_adapter_markers(inspection=inspection)
        session = dict(inspection.get("session") or {})
        selected_branch = inspection.get("selected_branch") or {}
        selected_turn = inspection.get("selected_turn") or {}
        snapshot = inspection.get("runtime_profile_snapshot") or {}
        worker_execution = inspection.get("worker_execution") or {}
        writer_packet = inspection.get("writer_packet") or {}
        retrieval = inspection.get("retrieval") or {}
        job_ledger = inspection.get("job_ledger") or {}
        branch_receipts = inspection.get("branch_control_receipts") or []
        legacy_fixed_chain_backslide = self._detect_legacy_fixed_chain_backslide(
            inspection=inspection,
            observed_markers=observed_markers,
        )
        return {
            "surface_role": "story_runtime_migration_read_surface",
            "read_only": True,
            "selection": dict(inspection.get("selection") or {}),
            "session": session,
            "selected_branch_head_id": selected_branch.get("branch_head_id"),
            "selected_turn_id": selected_turn.get("turn_id"),
            "runtime_profile_snapshot_id": snapshot.get("runtime_profile_snapshot_id"),
            "migration_flags": {
                "session_branch_anchor_pinned": bool(
                    session.get("active_branch_head_id")
                ),
                "session_snapshot_anchor_pinned": bool(
                    session.get("active_runtime_profile_snapshot_id")
                ),
                "turn_trace_available": inspection.get("turn_trace") is not None,
                "writer_packet_visible": bool(writer_packet),
                "worker_result_visible": bool(
                    worker_execution.get("prewrite_worker_results")
                    or worker_execution.get("worker_candidate_materials")
                ),
                "worker_plan_refs_visible": bool(
                    worker_execution.get("worker_plan_refs")
                ),
                "retrieval_usage_visible": bool(retrieval.get("usage_refs")),
                "job_ledger_visible": bool(job_ledger.get("items")),
                "branch_control_receipts_visible": bool(branch_receipts),
                "legacy_fixed_chain_backslide_detected": (
                    legacy_fixed_chain_backslide["detected"]
                ),
            },
            "legacy_fixed_chain_backslide": legacy_fixed_chain_backslide,
            "compatibility_surfaces": list(_COMPATIBILITY_SURFACES),
            "observed_adapter_markers": observed_markers,
            "native_read_surfaces": list(_NATIVE_READ_SURFACES),
            "warnings": list(inspection.get("warnings") or []),
            "boundaries": list(_MIGRATION_BOUNDARIES),
        }

    @staticmethod
    def _observed_adapter_markers(*, inspection: dict[str, Any]) -> list[dict[str, Any]]:
        markers: list[dict[str, Any]] = []
        selected_turn = inspection.get("selected_turn") or {}
        command_kind = str(selected_turn.get("command_kind") or "").strip()
        if command_kind and command_kind in {item.value for item in LongformTurnCommandKind}:
            markers.append(
                {
                    "marker_id": "legacy_command_surface",
                    "value": command_kind,
                    "source": "selected_turn.command_kind",
                }
            )
        for item in (inspection.get("worker_execution") or {}).get(
            "prewrite_worker_results",
            [],
        ):
            payload = item.get("payload") or {}
            trace_summary = payload.get("trace_summary") or {}
            adapter_role = str(trace_summary.get("adapter_role") or "").strip()
            if adapter_role:
                markers.append(
                    {
                        "marker_id": "worker_result_adapter_role",
                        "value": adapter_role,
                        "source": item.get("material_id"),
                        "worker_id": payload.get("worker_id"),
                    }
                )
            canonical_owner = str(
                trace_summary.get("canonical_contract_owner") or ""
            ).strip()
            if canonical_owner:
                markers.append(
                    {
                        "marker_id": "worker_result_canonical_owner",
                        "value": canonical_owner,
                        "source": item.get("material_id"),
                        "worker_id": payload.get("worker_id"),
                    }
                )
        for worker_plan_ref in (inspection.get("worker_execution") or {}).get(
            "worker_plan_refs",
            [],
        ):
            markers.append(
                {
                    "marker_id": "worker_plan_ref",
                    "value": worker_plan_ref,
                    "source": "job_ledger",
                }
            )
        return markers

    @classmethod
    def _detect_legacy_fixed_chain_backslide(
        cls,
        *,
        inspection: dict[str, Any],
        observed_markers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reasons: list[str] = []
        worker_execution = inspection.get("worker_execution") or {}
        worker_results = list(worker_execution.get("prewrite_worker_results") or [])
        worker_plan_refs = list(worker_execution.get("worker_plan_refs") or [])
        for item in worker_results:
            payload = item.get("payload") or {}
            trace_summary = payload.get("trace_summary") or {}
            adapter_role = str(trace_summary.get("adapter_role") or "").strip()
            canonical_owner = str(
                trace_summary.get("canonical_contract_owner") or ""
            ).strip()
            if adapter_role and canonical_owner != "WorkerExecutionPlan":
                reasons.append(
                    "legacy_adapter_without_worker_execution_plan_owner"
                )
        if worker_results and not worker_plan_refs:
            reasons.append("worker_result_without_worker_plan_ref")
        if cls._has_marker(
            observed_markers,
            marker_id="legacy_orchestrator_plan_runtime_truth",
        ):
            reasons.append("legacy_orchestrator_plan_used_as_runtime_truth")
        return {
            "detected": bool(reasons),
            "reason_codes": _unique_non_blank(reasons),
        }

    @staticmethod
    def _has_marker(
        markers: list[dict[str, Any]],
        *,
        marker_id: str,
    ) -> bool:
        return any(
            str(item.get("marker_id") or "").strip() == marker_id
            for item in markers
        )


def _unique_non_blank(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
