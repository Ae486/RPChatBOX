"""Post-write worker-result governance dispatch for Phase F."""

from __future__ import annotations

from typing import Any

from models.rp_story_store import RuntimeWorkflowJobRecord
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.postwrite_runtime_contracts import (
    PostWriteGovernanceDispatchResult,
    WorkerProposalGovernanceEnvelope,
)
from rp.models.projection_refresh import ProjectionRefreshRequest
from rp.models.runtime_workflow_job import (
    RuntimeWorkflowJobCategory,
    RuntimeWorkflowJobCreationMode,
    RuntimeWorkflowJobKind,
    RuntimeWorkflowJobStatus,
)
from rp.models.story_runtime import ChapterWorkspace, SpecialistResultBundle, StorySession
from rp.models.worker_memory import WorkerProposalGovernanceMetadata
from rp.models.worker_runtime_contracts import WorkerExecutionPlan, WorkerResult
from rp.services.core_state_as_of_resolver import CoreStateAsOfResolver
from rp.services.legacy_state_patch_proposal_builder import (
    LegacyStatePatchProposalBuilder,
)
from rp.services.projection_refresh_service import ProjectionRefreshService
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.runtime_workflow_job_service import RuntimeWorkflowJobService


class PostWriteGovernanceServiceError(ValueError):
    """Stable post-write governance error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class PostWriteGovernanceService:
    """Dispatch structured WorkerResult outputs into governed F2 jobs."""

    def __init__(
        self,
        *,
        runtime_workflow_job_service: RuntimeWorkflowJobService,
        projection_refresh_service: ProjectionRefreshService,
        core_state_as_of_resolver: CoreStateAsOfResolver | None = None,
        proposal_workflow_service: ProposalWorkflowService | None = None,
        legacy_state_patch_proposal_builder: LegacyStatePatchProposalBuilder
        | None = None,
    ) -> None:
        self._runtime_workflow_job_service = runtime_workflow_job_service
        self._projection_refresh_service = projection_refresh_service
        self._core_state_as_of_resolver = core_state_as_of_resolver
        self._proposal_workflow_service = proposal_workflow_service
        self._legacy_state_patch_proposal_builder = (
            legacy_state_patch_proposal_builder or LegacyStatePatchProposalBuilder()
        )

    async def dispatch_worker_results(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        session: StorySession,
        chapter: ChapterWorkspace,
        worker_plan: WorkerExecutionPlan,
        worker_results: list[WorkerResult],
        specialist_bundle: SpecialistResultBundle,
    ) -> PostWriteGovernanceDispatchResult:
        selected_worker_result_refs = [
            _worker_result_ref(identity=identity, result=result)
            for result in worker_results
        ]
        projection_job_refs = self._dispatch_projection_refresh_first(
            identity=identity,
            chapter=chapter,
            worker_results=worker_results,
            specialist_bundle=specialist_bundle,
        )
        proposal_job_refs = await self._dispatch_proposal_governance(
            identity=identity,
            session=session,
            chapter=chapter,
            worker_plan=worker_plan,
            worker_results=worker_results,
        )
        materialization_job_refs = self._record_deferred_materialization_jobs(
            identity=identity,
            worker_results=worker_results,
        )
        return PostWriteGovernanceDispatchResult(
            selected_worker_result_refs=selected_worker_result_refs,
            projection_refresh_job_refs=projection_job_refs,
            proposal_job_refs=proposal_job_refs,
            materialization_job_refs=materialization_job_refs,
            trace_refs=[
                f"worker_plan:{worker_plan.plan_id}",
                *selected_worker_result_refs,
            ],
            metadata_json={
                "worker_plan_id": worker_plan.plan_id,
                "selected_worker_count": len(worker_results),
                "post_write_phase": worker_plan.phase,
            },
        )

    def _dispatch_projection_refresh_first(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        chapter: ChapterWorkspace,
        worker_results: list[WorkerResult],
        specialist_bundle: SpecialistResultBundle,
    ) -> list[str]:
        refresh_results = [
            result for result in worker_results if result.projection_refresh_requests
        ]
        if not refresh_results:
            return []
        job = self._runtime_workflow_job_service.ensure_job(
            identity=identity,
            job_kind=RuntimeWorkflowJobKind.PROJECTION_REFRESH,
            job_category=RuntimeWorkflowJobCategory.STATE_GOVERNANCE,
            creation_mode=RuntimeWorkflowJobCreationMode.DERIVED,
            required_for_turn_completion=True,
            source_ref_ids=[
                ref
                for result in refresh_results
                for ref in _worker_result_source_ref_ids(result)
            ],
            trace_refs=[
                _worker_result_ref(identity=identity, result=result)
                for result in refresh_results
            ],
            metadata={
                "dispatch_owner": "post_write_governance_service",
                "dispatch_order": "projection_refresh_first",
                "worker_ids": [result.worker_id for result in refresh_results],
            },
        )
        if _is_terminal(job):
            return [f"runtime_job:{job.job_id}"]
        self._runtime_workflow_job_service.mark_job_running(
            job_id=job.job_id,
            reason="projection_refresh_dispatch_started",
        )
        source_refs = _merge_source_refs(
            [
                source_ref
                for result in refresh_results
                for source_ref in _worker_result_source_refs(result)
            ]
        )
        first_result = refresh_results[0]
        source_core_state_snapshot_id = None
        if self._core_state_as_of_resolver is not None:
            source_core_state_snapshot_id = (
                self._core_state_as_of_resolver.ensure_manifest_for_identity(
                    identity=identity
                ).snapshot_id
            )
        refresh_request = ProjectionRefreshRequest(
            identity=identity,
            refresh_actor=f"worker.{first_result.worker_id}",
            refresh_reason="post_write_worker_result",
            refresh_source_kind="worker_result",
            refresh_source_ref=_worker_result_ref(
                identity=identity,
                result=first_result,
            ),
            source_core_state_snapshot_id=source_core_state_snapshot_id,
            source_refs=source_refs,
            projection_dirty_state="dirty",
        )
        updated_chapter = self._projection_refresh_service.refresh_from_bundle(
            chapter=chapter,
            bundle=specialist_bundle,
            refresh_request=refresh_request,
        )
        completed = self._runtime_workflow_job_service.mark_job_completed(
            job_id=job.job_id,
            reason="projection_refresh_completed",
            result_ref_ids=[
                f"chapter_workspace:{updated_chapter.chapter_workspace_id}",
            ],
            trace_refs=[refresh_request.refresh_source_ref or ""],
            metadata={
                "refresh_actor": refresh_request.refresh_actor,
                "refresh_reason": refresh_request.refresh_reason,
            },
        )
        return [f"runtime_job:{completed.job_id}"]

    async def _dispatch_proposal_governance(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        session: StorySession,
        chapter: ChapterWorkspace,
        worker_plan: WorkerExecutionPlan,
        worker_results: list[WorkerResult],
    ) -> list[str]:
        proposal_results = [
            result for result in worker_results if result.proposal_candidates
        ]
        if not proposal_results:
            return []
        if self._proposal_workflow_service is None:
            raise PostWriteGovernanceServiceError(
                "post_write_proposal_workflow_missing",
                identity.turn_id,
            )
        job = self._runtime_workflow_job_service.ensure_job(
            identity=identity,
            job_kind=RuntimeWorkflowJobKind.PROPOSAL_SUBMIT,
            job_category=RuntimeWorkflowJobCategory.STATE_GOVERNANCE,
            creation_mode=RuntimeWorkflowJobCreationMode.DERIVED,
            required_for_turn_completion=True,
            source_ref_ids=[
                ref
                for result in proposal_results
                for ref in _worker_result_source_ref_ids(result)
            ],
            trace_refs=[
                _worker_result_ref(identity=identity, result=result)
                for result in proposal_results
            ],
            metadata={
                "dispatch_owner": "post_write_governance_service",
                "worker_plan_id": worker_plan.plan_id,
                "worker_ids": [result.worker_id for result in proposal_results],
            },
        )
        if _is_terminal(job):
            return [f"runtime_job:{job.job_id}"]
        self._runtime_workflow_job_service.mark_job_running(
            job_id=job.job_id,
            reason="proposal_governance_dispatch_started",
        )
        proposal_refs: list[str] = []
        governance_payloads: list[dict[str, Any]] = []
        for result in proposal_results:
            envelope = self._build_governance_envelope(
                identity=identity,
                result=result,
            )
            governance_payloads.append(envelope.model_dump(mode="json"))
            governance_metadata = WorkerProposalGovernanceMetadata(
                identity=identity,
                worker_id=envelope.worker_id,
                phase=envelope.phase,
                runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
                permission_decision=envelope.permission_decision,
                permission_reason_codes=list(envelope.permission_reason_codes),
                source_refs=list(envelope.source_refs),
                trace_refs=list(envelope.trace_refs),
            )
            for candidate in result.proposal_candidates:
                proposal_inputs = self._proposal_inputs_from_candidate(
                    story_id=session.story_id,
                    mode=session.mode,
                    candidate=candidate,
                )
                for proposal_input in proposal_inputs:
                    receipt = await self._proposal_workflow_service.submit_and_route(
                        proposal_input,
                        session_id=session.session_id,
                        chapter_workspace_id=chapter.chapter_workspace_id,
                        submit_source="post_write_worker",
                        governance_metadata=governance_metadata,
                    )
                    proposal_refs.append(f"proposal:{receipt.proposal_id}")
        completed = self._runtime_workflow_job_service.mark_job_completed(
            job_id=job.job_id,
            reason="proposal_governance_completed",
            result_ref_ids=proposal_refs,
            trace_refs=[
                ref
                for result in proposal_results
                for ref in _worker_result_trace_refs(identity=identity, result=result)
            ],
            metadata={
                "proposal_count": len(proposal_refs),
                "governance_envelopes": governance_payloads,
            },
        )
        return [f"runtime_job:{completed.job_id}"]

    def _record_deferred_materialization_jobs(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        worker_results: list[WorkerResult],
    ) -> list[str]:
        materialization_refs: list[str] = []
        recall_results = [result for result in worker_results if result.recall_candidates]
        archival_results = [
            result for result in worker_results if result.archival_candidates
        ]
        for job_kind, results in (
            (RuntimeWorkflowJobKind.RECALL_MATERIALIZATION, recall_results),
            (RuntimeWorkflowJobKind.ARCHIVAL_MATERIALIZATION, archival_results),
        ):
            if not results:
                continue
            job = self._runtime_workflow_job_service.ensure_job(
                identity=identity,
                job_kind=job_kind,
                job_category=RuntimeWorkflowJobCategory.MEMORY_MATERIALIZATION,
                creation_mode=RuntimeWorkflowJobCreationMode.DERIVED,
                required_for_turn_completion=False,
                source_ref_ids=[
                    ref
                    for result in results
                    for ref in _worker_result_source_ref_ids(result)
                ],
                trace_refs=[
                    _worker_result_ref(identity=identity, result=result)
                    for result in results
                ],
                metadata={
                    "dispatch_owner": "post_write_governance_service",
                    "f2_scope": "candidate_recorded_materialization_deferred",
                    "worker_ids": [result.worker_id for result in results],
                },
            )
            if not _is_terminal(job):
                job = self._runtime_workflow_job_service.mark_job_deferred(
                    job_id=job.job_id,
                    reason="materialization_deferred_until_later_slice",
                )
            materialization_refs.append(f"runtime_job:{job.job_id}")
        return materialization_refs

    def _build_governance_envelope(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        result: WorkerResult,
    ) -> WorkerProposalGovernanceEnvelope:
        return WorkerProposalGovernanceEnvelope(
            worker_id=result.worker_id,
            phase=result.phase,
            identity=identity,
            permission_decision="allowed_by_post_write_f2_bootstrap",
            permission_reason_codes=[
                "structured_worker_result",
                "snapshot_pinned_worker_plan",
            ],
            source_refs=_worker_result_source_refs(result),
            trace_refs=_worker_result_trace_refs(identity=identity, result=result),
            base_refs=[
                dict(item)
                for candidate in result.proposal_candidates
                for item in list(candidate.get("base_refs") or [])
                if isinstance(item, dict)
            ],
            metadata_json={
                "result_status": result.result_status.value,
                "candidate_count": len(result.proposal_candidates),
                "proposal_candidate_kinds": [
                    str(candidate.get("candidate_kind") or "")
                    for candidate in result.proposal_candidates
                ],
            },
        )

    def _proposal_inputs_from_candidate(
        self,
        *,
        story_id: str,
        mode: str,
        candidate: dict[str, Any],
    ):
        candidate_kind = str(candidate.get("candidate_kind") or "").strip()
        if candidate_kind != "legacy_state_patch":
            raise PostWriteGovernanceServiceError(
                "post_write_proposal_candidate_unsupported",
                candidate_kind or "<blank>",
            )
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            raise PostWriteGovernanceServiceError(
                "post_write_proposal_candidate_payload_invalid",
                candidate_kind,
            )
        return self._legacy_state_patch_proposal_builder.build_inputs(
            story_id=story_id,
            mode=mode,
            patch=dict(payload),
        )


def _worker_result_ref(*, identity: MemoryRuntimeIdentity, result: WorkerResult) -> str:
    return f"worker_result:{identity.turn_id}:{result.worker_id}:{result.phase}"


def _worker_result_source_ref_ids(result: WorkerResult) -> list[str]:
    refs: list[str] = []
    refs.extend(result.evidence_refs)
    context_packet_ref = result.metadata.get("context_packet_ref")
    if isinstance(context_packet_ref, str) and context_packet_ref.strip():
        refs.append(context_packet_ref)
    return _unique_non_blank(refs)


def _worker_result_source_refs(result: WorkerResult) -> list[MemorySourceRef]:
    refs = [
        MemorySourceRef(
            source_type="worker_result",
            source_id=f"{result.worker_id}:{result.phase}",
            layer="runtime_worker",
            domain="chapter",
            metadata={
                "worker_id": result.worker_id,
                "phase": result.phase,
                "result_status": result.result_status.value,
            },
        )
    ]
    refs.extend(
        MemorySourceRef(
            source_type="runtime_workspace_material",
            source_id=ref,
            layer="runtime_workspace",
            domain="chapter",
            entry_id=ref,
            metadata={"source_of_truth": False},
        )
        for ref in result.evidence_refs
    )
    context_packet_ref = result.metadata.get("context_packet_ref")
    if isinstance(context_packet_ref, str) and context_packet_ref.strip():
        refs.append(
            MemorySourceRef(
                source_type="worker_context_packet",
                source_id=context_packet_ref.strip(),
                layer="runtime_worker",
                domain="chapter",
                entry_id=context_packet_ref.strip(),
                metadata={
                    "worker_id": result.worker_id,
                    "phase": result.phase,
                },
            )
        )
    return _merge_source_refs(refs)


def _worker_result_trace_refs(
    *,
    identity: MemoryRuntimeIdentity,
    result: WorkerResult,
) -> list[str]:
    refs = [_worker_result_ref(identity=identity, result=result)]
    context_packet_ref = result.metadata.get("context_packet_ref")
    if isinstance(context_packet_ref, str) and context_packet_ref.strip():
        refs.append(context_packet_ref.strip())
    return _unique_non_blank(refs)


def _merge_source_refs(refs: list[MemorySourceRef]) -> list[MemorySourceRef]:
    merged: list[MemorySourceRef] = []
    seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
    for ref in refs:
        key = (ref.source_type, ref.source_id, ref.layer, ref.domain, ref.entry_id)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return merged


def _unique_non_blank(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _is_terminal(job: RuntimeWorkflowJobRecord) -> bool:
    return job.status in {
        RuntimeWorkflowJobStatus.COMPLETED.value,
        RuntimeWorkflowJobStatus.DEFERRED.value,
        RuntimeWorkflowJobStatus.CANCELLED.value,
    }
