"""Shared internal worker-facing memory service with snapshot permission guards."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from sqlmodel import Session

from models.rp_story_store import RuntimeProfileSnapshotRecord
from rp.models.dsl import Layer
from rp.models.memory_contract_registry import MemorySourceRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryGetSummaryInput,
    MemorySearchArchivalInput,
    MemorySearchRecallInput,
    ProposalReceipt,
    ProposalSubmitInput,
    RetrievalSearchResult,
    StateReadResult,
    SummaryReadResult,
)
from rp.models.projection_refresh import ProjectionRefreshRequest
from rp.models.runtime_identity import RuntimeProfileSnapshotCompiledProfile
from rp.models.worker_memory import (
    WorkerMemoryContext,
    WorkerPermissionDecision,
    WorkerProposalGovernanceMetadata,
)
from services.database import get_engine

from .post_write_apply_handler import PostWriteApplyHandler
from .proposal_apply_service import ProposalApplyService
from .proposal_repository import ProposalRepository
from .proposal_workflow_service import ProposalWorkflowService
from .retrieval_broker import RetrievalBroker
from .runtime_retrieval_card_service import RuntimeRetrievalCardService
from .story_session_service import StorySessionService
from .story_state_apply_service import StoryStateApplyService


class WorkerMemoryPermissionError(ValueError):
    """Stable worker permission error with machine-readable reason codes."""

    def __init__(self, code: str, detail: str, *, reason_codes: list[str]) -> None:
        self.code = code
        self.reason_codes = list(reason_codes)
        super().__init__(f"{code}:{detail}")


class WorkerMemoryService:
    """Internal worker memory surface that keeps reads/searches/proposals governed."""

    def __init__(
        self,
        *,
        session: Session | None = None,
        runtime_retrieval_card_service: RuntimeRetrievalCardService | None = None,
    ) -> None:
        self._session = session
        self._runtime_retrieval_card_service = runtime_retrieval_card_service

    async def get_state(
        self,
        *,
        ctx: WorkerMemoryContext,
        input_model: MemoryGetStateInput,
    ) -> StateReadResult:
        domains = (
            [input_model.domain.value]
            if input_model.domain is not None
            else [ref.domain.value for ref in input_model.refs]
        )
        self._authorize(
            ctx=ctx,
            operation_kind="read",
            domains=domains,
            layers=[ref.layer.value for ref in input_model.refs],
        )
        return await self._broker(ctx).get_state(input_model)

    async def get_summary(
        self,
        *,
        ctx: WorkerMemoryContext,
        input_model: MemoryGetSummaryInput,
    ) -> SummaryReadResult:
        self._authorize(
            ctx=ctx,
            operation_kind="read",
            domains=[domain.value for domain in input_model.domains]
            or ([ctx.domain] if ctx.domain is not None else []),
            layers=[Layer.CORE_STATE_PROJECTION.value],
        )
        return await self._broker(ctx).get_summary(input_model)

    async def search_recall(
        self,
        *,
        ctx: WorkerMemoryContext,
        input_model: MemorySearchRecallInput,
    ) -> RetrievalSearchResult:
        self._authorize(
            ctx=ctx,
            operation_kind="retrieval.search_recall",
            domains=[domain.value for domain in input_model.domains]
            or ([ctx.domain] if ctx.domain is not None else []),
            layers=[Layer.RECALL.value],
        )
        result, cards, miss = await self._retrieval_cards().search_recall_to_cards(
            identity=ctx.identity,
            input_model=input_model,
            actor=f"worker.{ctx.worker_id}",
        )
        self._extend_context_traces(
            ctx=ctx,
            source_refs=[
                self._material_source_ref(material.material_id)
                for material in [*cards, *([miss] if miss is not None else [])]
            ],
            trace_refs=[
                material.material_id
                for material in [*cards, *([miss] if miss is not None else [])]
            ],
        )
        return result

    async def search_archival(
        self,
        *,
        ctx: WorkerMemoryContext,
        input_model: MemorySearchArchivalInput,
    ) -> RetrievalSearchResult:
        self._authorize(
            ctx=ctx,
            operation_kind="retrieval.search_archival",
            domains=[domain.value for domain in input_model.domains]
            or ([ctx.domain] if ctx.domain is not None else []),
            layers=[Layer.ARCHIVAL.value],
        )
        result, cards, miss = await self._retrieval_cards().search_archival_to_cards(
            identity=ctx.identity,
            input_model=input_model,
            actor=f"worker.{ctx.worker_id}",
        )
        self._extend_context_traces(
            ctx=ctx,
            source_refs=[
                self._material_source_ref(material.material_id)
                for material in [*cards, *([miss] if miss is not None else [])]
            ],
            trace_refs=[
                material.material_id
                for material in [*cards, *([miss] if miss is not None else [])]
            ],
        )
        return result

    async def submit_proposal(
        self,
        *,
        ctx: WorkerMemoryContext,
        input_model: ProposalSubmitInput,
    ) -> ProposalReceipt:
        decision = self._authorize(
            ctx=ctx,
            operation_kind="proposal.submit",
            domains=[input_model.domain.value],
            layers=[
                operation.target_ref.layer.value for operation in input_model.operations
            ],
        )
        with self._session_scope() as (session, managed):
            story_session_service = StorySessionService(session)
            repository = ProposalRepository(session)
            workflow = ProposalWorkflowService(
                proposal_repository=repository,
                proposal_apply_service=ProposalApplyService(
                    story_session_service=story_session_service,
                    proposal_repository=repository,
                    story_state_apply_service=StoryStateApplyService(),
                ),
                post_write_apply_handler=PostWriteApplyHandler(),
            )
            chapter = story_session_service.get_current_chapter(ctx.identity.session_id)
            receipt = await workflow.submit_and_route(
                input_model,
                session_id=ctx.identity.session_id,
                chapter_workspace_id=(
                    chapter.chapter_workspace_id if chapter is not None else None
                ),
                submit_source=f"worker_memory:{ctx.worker_id}",
                governance_metadata=WorkerProposalGovernanceMetadata(
                    identity=ctx.identity,
                    worker_id=ctx.worker_id,
                    phase=ctx.phase,
                    runtime_profile_snapshot_id=ctx.runtime_profile_snapshot_id,
                    permission_decision=decision.permission_decision,
                    permission_reason_codes=decision.reason_codes,
                    source_refs=list(ctx.source_refs),
                    trace_refs=list(ctx.trace_refs),
                ),
            )
            if managed:
                session.commit()
            return receipt

    def refresh_projection(
        self,
        *,
        ctx: WorkerMemoryContext,
        request: ProjectionRefreshRequest,
    ) -> None:
        self._authorize(
            ctx=ctx,
            operation_kind="projection.refresh",
            domains=[ctx.domain] if ctx.domain is not None else [],
            layers=[Layer.CORE_STATE_PROJECTION.value],
        )
        request.identity = ctx.identity
        request.refresh_actor = f"worker.{ctx.worker_id}"
        request.source_refs = self._merge_source_refs(
            [*ctx.source_refs, *request.source_refs]
        )
        if request.refresh_source_ref is None:
            request.refresh_source_ref = f"worker_memory:{ctx.worker_id}:{ctx.phase}"

    def authorize_operation(
        self,
        *,
        ctx: WorkerMemoryContext,
        operation_kind: str,
        domains: list[str],
        layers: list[str],
    ) -> WorkerPermissionDecision:
        """Expose the shared snapshot-derived permission guard to adapters.

        Some runtime flows already have their own proposal/apply orchestration
        but must still reuse the same worker permission contract. This method is
        intentionally a thin wrapper over the internal guard so callers cannot
        bypass snapshot, domain, layer, operation, or phase checks.
        """

        return self._authorize(
            ctx=ctx,
            operation_kind=operation_kind,
            domains=domains,
            layers=layers,
        )

    def _authorize(
        self,
        *,
        ctx: WorkerMemoryContext,
        operation_kind: str,
        domains: list[str],
        layers: list[str],
    ) -> WorkerPermissionDecision:
        with self._session_scope() as (session, _managed):
            snapshot = self._require_snapshot(session=session, ctx=ctx)
            compiled = RuntimeProfileSnapshotCompiledProfile.model_validate(
                snapshot.compiled_profile_json or {}
            )
            ctx.permission_profile = dict(compiled.permission_profile or {})
            worker_activation = compiled.worker_activation.get(ctx.worker_id)
            if worker_activation is None or not worker_activation.active:
                self._raise_permission_error(
                    code="worker_memory_worker_disabled",
                    detail=ctx.worker_id,
                    reason_codes=["disabled_worker"],
                )
            self._validate_phase(
                session=session,
                ctx=ctx,
                worker_activation_metadata=dict(worker_activation.metadata or {}),
            )
            self._validate_operation(
                ctx=ctx,
                compiled=compiled,
                operation_kind=operation_kind,
                domains=domains,
                layers=layers,
            )
            return WorkerPermissionDecision(
                allowed=True,
                permission_decision="allowed",
                reason_codes=["allowed"],
                runtime_profile_snapshot_id=ctx.runtime_profile_snapshot_id,
                permission_profile=dict(compiled.permission_profile or {}),
            )

    def _validate_phase(
        self,
        *,
        session: Session,
        ctx: WorkerMemoryContext,
        worker_activation_metadata: dict[str, Any],
    ) -> None:
        story_session_service = StorySessionService(session)
        chapter = story_session_service.get_active_branch_current_chapter(
            ctx.identity.session_id
        )
        current_phase = chapter.phase.value if chapter is not None else None
        if current_phase is not None and current_phase != ctx.phase:
            self._raise_permission_error(
                code="worker_memory_phase_forbidden",
                detail=f"{ctx.phase}:{current_phase}",
                reason_codes=["forbidden_phase"],
            )
        allowed_phases = worker_activation_metadata.get("allowed_phases")
        if isinstance(allowed_phases, list):
            normalized_allowed = {
                str(item).strip() for item in allowed_phases if str(item).strip()
            }
            if normalized_allowed and ctx.phase not in normalized_allowed:
                self._raise_permission_error(
                    code="worker_memory_phase_forbidden",
                    detail=ctx.phase,
                    reason_codes=["forbidden_phase"],
                )

    def _validate_operation(
        self,
        *,
        ctx: WorkerMemoryContext,
        compiled: RuntimeProfileSnapshotCompiledProfile,
        operation_kind: str,
        domains: list[str],
        layers: list[str],
    ) -> None:
        worker_defaults = dict(
            (compiled.permission_profile or {})
            .get("worker_defaults", {})
            .get(ctx.worker_id, {})
            or {}
        )
        capability = self._capability_for_operation(operation_kind)
        if capability is not None and not self._capability_enabled(
            worker_defaults, capability
        ):
            self._raise_permission_error(
                code="worker_memory_operation_forbidden",
                detail=f"{ctx.worker_id}:{operation_kind}",
                reason_codes=["forbidden_operation_kind"],
            )
        normalized_domains = [item for item in domains if item]
        normalized_layers = [item for item in layers if item]
        for domain in normalized_domains:
            domain_activation = dict(compiled.domain_activation.get(domain, {}) or {})
            if not domain_activation.get("active", False):
                self._raise_permission_error(
                    code="worker_memory_domain_disabled",
                    detail=domain,
                    reason_codes=["disabled_domain"],
                )
            allowed_layers = {
                str(item).strip()
                for item in domain_activation.get("allowed_layers", [])
                if str(item).strip()
            }
            for layer in normalized_layers:
                if allowed_layers and layer not in allowed_layers:
                    self._raise_permission_error(
                        code="worker_memory_layer_forbidden",
                        detail=f"{domain}:{layer}",
                        reason_codes=["forbidden_layer"],
                    )
            domain_defaults = dict(
                (compiled.permission_profile or {})
                .get("domain_defaults", {})
                .get(domain, {})
                or {}
            )
            if capability is not None and not self._capability_enabled(
                domain_defaults, capability
            ):
                self._raise_permission_error(
                    code="worker_memory_operation_forbidden",
                    detail=f"{domain}:{operation_kind}",
                    reason_codes=["forbidden_operation_kind"],
                )
            if normalized_layers and not self._operation_allowed_by_blocks(
                compiled=compiled,
                domain=domain,
                layers=normalized_layers,
                operation_kind=operation_kind,
            ):
                self._raise_permission_error(
                    code="worker_memory_operation_forbidden",
                    detail=f"{domain}:{operation_kind}",
                    reason_codes=["forbidden_operation_kind"],
                )

    @staticmethod
    def _capability_for_operation(operation_kind: str) -> str | None:
        if operation_kind in {
            "read",
            "retrieval.search_recall",
            "retrieval.search_archival",
        }:
            return "read"
        if operation_kind == "proposal.submit":
            return "propose"
        if operation_kind == "projection.refresh":
            return "refresh_projection"
        return None

    @staticmethod
    def _capability_enabled(defaults: dict[str, Any], capability: str) -> bool:
        return defaults.get(capability) is True

    @staticmethod
    def _operation_allowed_by_blocks(
        *,
        compiled: RuntimeProfileSnapshotCompiledProfile,
        domain: str,
        layers: list[str],
        operation_kind: str,
    ) -> bool:
        for template in compiled.block_activation.values():
            payload = dict(template or {})
            if not payload.get("active", False):
                continue
            if str(payload.get("domain_id") or "").strip() != domain:
                continue
            if str(payload.get("layer") or "").strip() not in set(layers):
                continue
            allowed_operations = {
                str(item).strip()
                for item in payload.get("allowed_operations", [])
                if str(item).strip()
            }
            if operation_kind in allowed_operations or (
                operation_kind == "read" and "read" in allowed_operations
            ):
                return True
        return False

    @staticmethod
    def _extend_context_traces(
        *,
        ctx: WorkerMemoryContext,
        source_refs: list[MemorySourceRef],
        trace_refs: list[str],
    ) -> None:
        ctx.source_refs = WorkerMemoryService._merge_source_refs(
            [*ctx.source_refs, *source_refs]
        )
        existing_trace_refs = list(ctx.trace_refs)
        for trace_ref in trace_refs:
            if trace_ref not in existing_trace_refs:
                existing_trace_refs.append(trace_ref)
        ctx.trace_refs = existing_trace_refs

    @staticmethod
    def _merge_source_refs(source_refs: list[MemorySourceRef]) -> list[MemorySourceRef]:
        merged: list[MemorySourceRef] = []
        seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
        for ref in source_refs:
            key = (ref.source_type, ref.source_id, ref.layer, ref.domain, ref.entry_id)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
        return merged

    @staticmethod
    def _material_source_ref(material_id: str) -> MemorySourceRef:
        return MemorySourceRef(
            source_type="runtime_workspace_material",
            source_id=material_id,
            layer="runtime_workspace",
            entry_id=material_id,
            metadata={"source_of_truth": False},
        )

    def _require_snapshot(
        self,
        *,
        session: Session,
        ctx: WorkerMemoryContext,
    ) -> RuntimeProfileSnapshotRecord:
        snapshot = session.get(
            RuntimeProfileSnapshotRecord,
            ctx.runtime_profile_snapshot_id,
        )
        if snapshot is None:
            self._raise_permission_error(
                code="worker_memory_snapshot_missing",
                detail=ctx.runtime_profile_snapshot_id,
                reason_codes=["runtime_profile_snapshot_missing"],
            )
        assert snapshot is not None
        if (
            snapshot.story_id != ctx.identity.story_id
            or snapshot.session_id != ctx.identity.session_id
            or snapshot.runtime_profile_snapshot_id
            != ctx.identity.runtime_profile_snapshot_id
        ):
            self._raise_permission_error(
                code="worker_memory_snapshot_mismatch",
                detail=ctx.runtime_profile_snapshot_id,
                reason_codes=["runtime_profile_snapshot_mismatch"],
            )
        return snapshot

    def _retrieval_cards(self) -> RuntimeRetrievalCardService:
        if self._runtime_retrieval_card_service is not None:
            return self._runtime_retrieval_card_service
        return RuntimeRetrievalCardService(session=self._session)

    @staticmethod
    def _broker(ctx: WorkerMemoryContext) -> RetrievalBroker:
        return RetrievalBroker(
            default_story_id=ctx.identity.story_id,
            runtime_identity=ctx.identity,
        )

    @contextmanager
    def _session_scope(self) -> Iterator[tuple[Session, bool]]:
        if self._session is not None:
            yield self._session, False
            return
        with Session(get_engine()) as session:
            yield session, True

    @staticmethod
    def _raise_permission_error(
        *,
        code: str,
        detail: str,
        reason_codes: list[str],
    ) -> None:
        raise WorkerMemoryPermissionError(
            code,
            detail,
            reason_codes=reason_codes,
        )
