"""Writer brainstorm session, summary, and governed Core apply service."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from typing import Literal
from uuid import uuid4

from models.chat import ChatMessage
from models.rp_core_state_store import CoreStateAuthoritativeRevisionRecord
from rp.models.core_mutation import (
    CORE_MUTATION_ORIGIN_BRAINSTORM_SUMMARY_APPLY,
    CoreMutationEnvelope,
)
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory_crud import PatchFieldsOp, ProposalReceipt
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.story_brainstorm import (
    BrainstormApplyReceipt,
    BrainstormApplyRequest,
    BrainstormCoreFieldChange,
    BrainstormDispatchReceipt,
    BrainstormItem,
    BrainstormItemStatus,
    BrainstormItemUpdateRequest,
    BrainstormSession,
    BrainstormSessionStartRequest,
    BrainstormSessionStatus,
    BrainstormStructuredSummary,
    BrainstormSummarizeRequest,
)
from rp.services.core_state_as_of_resolver import (
    CoreStateAsOfResolver,
    CoreStateAsOfResolverError,
)
from rp.services.memory_object_mapper import authoritative_bindings
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
    RuntimeWorkspaceMaterialServiceError,
)
from rp.services.story_llm_gateway import StoryLlmGateway
from rp.services.story_session_service import StorySessionService
from rp.models.worker_memory import WorkerMemoryContext
from rp.services.worker_memory_service import (
    WorkerMemoryPermissionError,
    WorkerMemoryService,
)
from rp.services.worker_registry_service import (
    LONGFORM_MEMORY_WORKER_ID,
    WorkerRegistryService,
)


BRAINSTORM_MATERIAL_DOMAIN = "narrative_progress"
BRAINSTORM_MATERIAL_DOMAIN_PATH = "narrative_progress.runtime.brainstorm"
BRAINSTORM_APPLY_PHASE = "manual_refresh"


@dataclass(frozen=True)
class _ResolvedAuthoritativeBlock:
    label: str
    domain: Domain
    domain_path: str
    scope: str
    revision: int
    data_json: Any


class StoryBrainstormServiceError(ValueError):
    """Stable brainstorm service error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class StoryBrainstormService:
    """Persist brainstorm scratch and route confirmed Core changes through governance."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService,
        proposal_workflow_service: ProposalWorkflowService,
        rp_block_read_service: RpBlockReadService,
        worker_registry_service: WorkerRegistryService | None = None,
        worker_memory_service: WorkerMemoryService | None = None,
        core_state_as_of_resolver: CoreStateAsOfResolver | None = None,
        llm_gateway: StoryLlmGateway | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._runtime_workspace_material_service = runtime_workspace_material_service
        self._proposal_workflow_service = proposal_workflow_service
        self._rp_block_read_service = rp_block_read_service
        self._worker_registry_service = worker_registry_service
        self._worker_memory_service = worker_memory_service
        self._core_state_as_of_resolver = core_state_as_of_resolver
        self._llm_gateway = llm_gateway or StoryLlmGateway()

    def start_session(self, request: BrainstormSessionStartRequest) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        brainstorm_id = f"brainstorm_{uuid4().hex}"
        session = BrainstormSession(
            brainstorm_id=brainstorm_id,
            identity=request.identity,
            status=BrainstormSessionStatus.OPEN,
            prompt=request.prompt,
            source_entry_ids=request.source_entry_ids,
            created_by=request.actor,
            updated_by=request.actor,
            metadata={
                "runtime_workspace_semantics": True,
                "temporary": True,
                "source_of_truth": False,
                "writer_discussion_mode": True,
                **dict(request.metadata or {}),
            },
        )
        self._record_session_revision(session)
        return session

    def get_session(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(identity)
        return self._load_latest_session(identity=identity, brainstorm_id=brainstorm_id)

    async def summarize_session(
        self,
        *,
        brainstorm_id: str,
        request: BrainstormSummarizeRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        if session.status == BrainstormSessionStatus.CLOSED:
            raise StoryBrainstormServiceError(
                "brainstorm_session_closed",
                brainstorm_id,
            )
        structured = await self._run_structured_summary(
            session=session,
            request=request,
        )
        items = [
            BrainstormItem(
                item_id=f"{brainstorm_id}:item:{index + 1}",
                summary_text=item.summary_text,
                evidence_text_refs=list(item.evidence_text_refs),
                uncertainty=item.uncertainty,
                status=BrainstormItemStatus.PROPOSED,
            )
            for index, item in enumerate(structured.items[: request.max_items])
        ]
        updated = session.model_copy(
            update={
                "status": BrainstormSessionStatus.REVIEWING,
                "items": items,
                "updated_by": request.actor,
                "revision": session.revision + 1,
                "summary_trace": {
                    **dict(session.summary_trace or {}),
                    "operation_kind": "brainstorm_summarize",
                    "schema_id": "rp.story.brainstorm_items.v1",
                    "item_count": len(items),
                    "model_id": request.model_id,
                    "provider_id": request.provider_id,
                    "source_entry_ids": list(session.source_entry_ids),
                    "fail_closed": True,
                },
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    def update_item(
        self,
        *,
        brainstorm_id: str,
        item_id: str,
        request: BrainstormItemUpdateRequest,
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        items: list[BrainstormItem] = []
        found = False
        for item in session.items:
            if item.item_id != item_id:
                items.append(item)
                continue
            found = True
            updates: dict[str, Any] = {}
            if request.summary_text is not None:
                updates["summary_text"] = request.summary_text
                updates["user_edited"] = True
            if request.evidence_text_refs is not None:
                updates["evidence_text_refs"] = request.evidence_text_refs
                updates["user_edited"] = True
            if request.uncertainty is not None:
                updates["uncertainty"] = request.uncertainty
                updates["user_edited"] = True
            if request.status is not None:
                updates["status"] = BrainstormItemStatus(request.status)
            elif updates:
                updates["status"] = BrainstormItemStatus.EDITED
            items.append(item.model_copy(update=updates))
        if not found:
            raise StoryBrainstormServiceError(
                "brainstorm_item_not_found",
                item_id,
            )
        updated = session.model_copy(
            update={
                "items": items,
                "status": BrainstormSessionStatus.REVIEWING,
                "updated_by": request.actor,
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    async def apply_session(
        self,
        *,
        brainstorm_id: str,
        request: BrainstormApplyRequest,
    ) -> BrainstormApplyReceipt:
        self._ensure_identity_matches_session(request.identity)
        session = self._load_latest_session(
            identity=request.identity,
            brainstorm_id=brainstorm_id,
        )
        confirmed_by_id = {
            item.item_id: item
            for item in session.items
            if item.status == BrainstormItemStatus.CONFIRMED
        }
        requested_ids = set(request.item_ids or confirmed_by_id.keys())
        eligible_items = {
            item_id: item
            for item_id, item in confirmed_by_id.items()
            if item_id in requested_ids
        }
        if not eligible_items:
            raise StoryBrainstormServiceError(
                "brainstorm_apply_no_confirmed_items",
                brainstorm_id,
            )

        changes_by_item: dict[str, list[BrainstormCoreFieldChange]] = {}
        for change in request.core_field_changes:
            if change.source_item_id not in eligible_items:
                raise StoryBrainstormServiceError(
                    "brainstorm_apply_unconfirmed_source_item",
                    change.source_item_id,
                )
            changes_by_item.setdefault(change.source_item_id, []).append(change)

        dispatch_receipts: list[BrainstormDispatchReceipt] = []
        item_status_updates: dict[str, BrainstormItemStatus] = {}
        for item_id, item in eligible_items.items():
            item_changes = changes_by_item.get(item_id, [])
            if not item_changes:
                dispatch_receipts.append(
                    self._redirect_receipt(
                        item_id=item.item_id,
                        message=(
                            "No Core worker field change was produced for this "
                            "confirmed brainstorm item."
                        ),
                    )
                )
                item_status_updates[item_id] = BrainstormItemStatus.PENDING_REVIEW
                continue
            for change in item_changes:
                receipt = await self._apply_core_field_change(
                    session=session,
                    change=change,
                    actor=request.actor,
                    reason=request.reason,
                )
                dispatch_receipts.append(receipt)
                item_status_updates[item_id] = _item_status_for_receipt(receipt)

        updated_items = [
            item.model_copy(
                update={
                    "status": item_status_updates.get(item.item_id, item.status),
                }
            )
            for item in session.items
        ]
        overall_status = _overall_apply_status(dispatch_receipts)
        updated_session = session.model_copy(
            update={
                "items": updated_items,
                "status": BrainstormSessionStatus.DISPATCHED,
                "updated_by": request.actor,
                "revision": session.revision + 1,
                "apply_receipts": [
                    *session.apply_receipts,
                    {
                        "status": overall_status,
                        "dispatch_receipts": [
                            item.model_dump(mode="json")
                            for item in dispatch_receipts
                        ],
                    },
                ],
            }
        )
        self._record_session_revision(updated_session, previous=session)
        return BrainstormApplyReceipt(
            brainstorm_id=brainstorm_id,
            identity=request.identity,
            status=overall_status,
            dispatch_receipts=dispatch_receipts,
            refresh=_refresh_payload(request.identity),
        )

    def close_session(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
        actor: str,
        reason: str = "user_closed_noop",
    ) -> BrainstormSession:
        self._ensure_identity_matches_session(identity)
        session = self._load_latest_session(
            identity=identity,
            brainstorm_id=brainstorm_id,
        )
        updated = session.model_copy(
            update={
                "status": BrainstormSessionStatus.CLOSED,
                "close_reason": reason,
                "updated_by": actor,
                "revision": session.revision + 1,
            }
        )
        self._record_session_revision(updated, previous=session)
        return updated

    async def _run_structured_summary(
        self,
        *,
        session: BrainstormSession,
        request: BrainstormSummarizeRequest,
    ) -> BrainstormStructuredSummary:
        if request.dry_run_items is not None:
            return BrainstormStructuredSummary(items=list(request.dry_run_items))
        if request.model_id is None:
            raise StoryBrainstormServiceError(
                "brainstorm_summarize_model_required",
                session.brainstorm_id,
            )
        text, usage = await self._llm_gateway.complete_text_with_usage(
            model_id=request.model_id,
            provider_id=request.provider_id,
            messages=self._summary_messages(session),
            temperature=0,
            max_tokens=1200,
        )
        try:
            payload = self._llm_gateway.extract_json_object(text)
            structured = BrainstormStructuredSummary.model_validate(payload)
        except Exception as exc:
            raise StoryBrainstormServiceError(
                "brainstorm_summarize_invalid_output",
                str(exc),
            ) from exc
        session.summary_trace.update({"usage": usage})
        return structured

    def _summary_messages(self, session: BrainstormSession) -> list[ChatMessage]:
        transcript = self._brainstorm_transcript(session)
        return [
            ChatMessage(
                role="system",
                content=(
                    "You are running the dedicated brainstorm_summarize "
                    "operation. Return JSON only: {\"items\":[...]}. Each item "
                    "may contain summary_text, evidence_text_refs, uncertainty. "
                    "Do not include target_layer, target_domain, operation_kind, "
                    "intent_labels, field_path, operation, or memory routing fields."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "Brainstorm prompt:\n"
                    f"{session.prompt}\n\n"
                    "Brainstorm discussion transcript:\n"
                    f"{transcript}\n\n"
                    "Summarize only user-confirmable intent items."
                ),
            ),
        ]

    def _brainstorm_transcript(self, session: BrainstormSession) -> str:
        current = self._story_session_service.get_current_chapter(
            session.identity.session_id
        )
        if current is None:
            return ""
        entries = self._story_session_service.list_discussion_entries(
            chapter_workspace_id=current.chapter_workspace_id
        )
        selected_ids = set(session.source_entry_ids)
        lines: list[str] = []
        for entry in entries[-24:]:
            if selected_ids and entry.entry_id not in selected_ids:
                continue
            lines.append(f"[{entry.entry_id}] {entry.role}: {entry.content_text}")
        return "\n".join(lines)

    async def _apply_core_field_change(
        self,
        *,
        session: BrainstormSession,
        change: BrainstormCoreFieldChange,
        actor: str,
        reason: str | None,
    ) -> BrainstormDispatchReceipt:
        if change.operation == "delete_field":
            return BrainstormDispatchReceipt(
                source_item_id=change.source_item_id,
                status="failed",
                target_ref=change.target_ref,
                operation=change.operation,
                field_path=change.field_path,
                base_revision=change.base_revision,
                reason_codes=["brainstorm_core_delete_field_not_supported_v4"],
                message="V4 does not support Core delete_field apply yet.",
            )

        try:
            block = self._resolve_authoritative_block(
                identity=session.identity,
                target_ref=change.target_ref,
            )
        except StoryBrainstormServiceError as exc:
            return BrainstormDispatchReceipt(
                source_item_id=change.source_item_id,
                status="pending_review",
                target_ref=change.target_ref,
                operation=change.operation,
                field_path=change.field_path,
                base_revision=change.base_revision,
                reason_codes=[exc.code],
                message=str(exc),
                review_entrypoint="/memory/inspection",
            )
        if block is None:
            return self._redirect_receipt(
                item_id=change.source_item_id,
                target_ref=change.target_ref,
                message="Target is not a known Core authoritative block.",
                reason_codes=["brainstorm_non_core_or_unknown_target"],
            )
        try:
            base_revision = int(change.base_revision)
        except ValueError:
            return BrainstormDispatchReceipt(
                source_item_id=change.source_item_id,
                status="failed",
                target_ref=change.target_ref,
                operation=change.operation,
                field_path=change.field_path,
                base_revision=change.base_revision,
                reason_codes=["brainstorm_core_base_revision_invalid"],
            )
        if int(block.revision or 1) != base_revision:
            return BrainstormDispatchReceipt(
                source_item_id=change.source_item_id,
                status="conflict",
                target_ref=change.target_ref,
                operation=change.operation,
                field_path=change.field_path,
                base_revision=change.base_revision,
                old_value=_value_at_path(block.data_json, change.field_path),
                new_value=change.new_value,
                reason_codes=["phase_e_apply_base_revision_conflict"],
                message=(
                    f"Current revision {block.revision} does not match "
                    f"base revision {change.base_revision}."
                ),
            )
        permission = self._resolve_worker_permission(
            identity=session.identity,
            target_domain=block.domain.value,
        )
        if permission is not None:
            return permission.model_copy(
                update={
                    "source_item_id": change.source_item_id,
                    "target_ref": change.target_ref,
                    "operation": change.operation,
                    "field_path": change.field_path,
                    "base_revision": change.base_revision,
                }
            )

        old_value = _value_at_path(block.data_json, change.field_path)
        field_patch = _field_patch_for_path(
            data=block.data_json,
            field_path=change.field_path,
            new_value=change.new_value,
        )
        target_ref = ObjectRef(
            object_id=block.label,
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=block.domain,
            domain_path=block.domain_path,
            scope=block.scope,
            revision=block.revision,
        )
        candidate = self._record_worker_candidate(
            identity=session.identity,
            change=change,
            block_domain=block.domain.value,
            old_value=old_value,
        )
        source_refs = [
            *change.source_refs,
            MemorySourceRef(
                source_type="brainstorm_item",
                source_id=change.source_item_id,
                layer="runtime_workspace",
                domain=BRAINSTORM_MATERIAL_DOMAIN,
                entry_id=session.brainstorm_id,
                metadata={"brainstorm_id": session.brainstorm_id},
            ),
            MemorySourceRef(
                source_type="runtime_workspace_material",
                source_id=candidate.material.material_id,
                layer="runtime_workspace",
                domain=block.domain.value,
                entry_id=candidate.material.material_id,
                metadata={"source_of_truth": False},
            ),
        ]
        envelope = CoreMutationEnvelope(
            identity=session.identity,
            origin_kind=CORE_MUTATION_ORIGIN_BRAINSTORM_SUMMARY_APPLY,
            actor=f"brainstorm.{actor}",
            worker_id=LONGFORM_MEMORY_WORKER_ID,
            phase=BRAINSTORM_APPLY_PHASE,
            domain=block.domain,
            domain_path=block.domain_path,
            operations=[
                PatchFieldsOp(target_ref=target_ref, field_patch=field_patch)
            ],
            base_refs=[
                target_ref.model_copy(update={"revision": base_revision})
            ],
            source_refs=source_refs,
            trace_refs=[session.brainstorm_id, candidate.material.material_id],
            permission_decision="allowed",
            permission_reason_codes=[
                "allowed",
                "brainstorm_core_oriented_v4",
            ],
            reason=reason or change.reason,
        )
        try:
            proposal = await self._proposal_workflow_service.submit_core_mutation(
                envelope,
                story_id=session.identity.story_id,
                mode="longform",
                session_id=session.identity.session_id,
                chapter_workspace_id=self._current_chapter_workspace_id(
                    session.identity.session_id
                ),
                submit_source="brainstorm_summary_apply",
                policy=PostWriteMaintenancePolicy(
                    preset_id="brainstorm_summary_apply",
                    fallback_decision=PolicyDecision.NOTIFY_APPLY,
                ),
            )
        except ValueError as exc:
            message = str(exc)
            status = (
                "conflict"
                if "phase_e_apply_base_revision_conflict" in message
                else "failed"
            )
            return BrainstormDispatchReceipt(
                source_item_id=change.source_item_id,
                status=status,
                target_ref=change.target_ref,
                proposal_id=None,
                operation=change.operation,
                field_path=change.field_path,
                base_revision=change.base_revision,
                old_value=old_value,
                new_value=change.new_value,
                reason_codes=[message.split(":", 1)[0]],
                message=message,
            )
        return self._proposal_receipt_to_dispatch(
            change=change,
            proposal=proposal,
            old_value=old_value,
        )

    def _resolve_worker_permission(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        target_domain: str,
    ) -> BrainstormDispatchReceipt | None:
        if self._worker_registry_service is None:
            return BrainstormDispatchReceipt(
                source_item_id="pending",
                status="pending_review",
                reason_codes=["brainstorm_worker_registry_unavailable"],
                message="Worker registry is unavailable; brainstorm apply is fail-closed.",
                review_entrypoint="/memory/inspection",
                metadata={"target_domain": target_domain},
            )
        worker = self._worker_registry_service.get_worker(
            LONGFORM_MEMORY_WORKER_ID,
            snapshot_id=identity.runtime_profile_snapshot_id,
            include_inactive=True,
        )
        if worker is None:
            return BrainstormDispatchReceipt(
                source_item_id="pending",
                status="pending_review",
                reason_codes=["brainstorm_worker_not_registered"],
                message="No Core brainstorm worker is registered for this snapshot.",
                review_entrypoint="/memory/inspection",
                metadata={"target_domain": target_domain},
            )
        if not worker.active:
            return BrainstormDispatchReceipt(
                source_item_id="pending",
                status="pending_review",
                reason_codes=["brainstorm_worker_inactive"],
                message="Core brainstorm worker is inactive in the pinned snapshot.",
                review_entrypoint="/memory/inspection",
                metadata={"target_domain": target_domain},
            )
        if BRAINSTORM_APPLY_PHASE not in worker.descriptor.supported_phases:
            return BrainstormDispatchReceipt(
                source_item_id="pending",
                status="pending_review",
                reason_codes=["brainstorm_worker_phase_not_supported"],
                message="Core brainstorm worker does not support manual refresh phase.",
                review_entrypoint="/memory/inspection",
                metadata={"target_domain": target_domain},
            )
        if target_domain not in set(worker.descriptor.owned_domains):
            return BrainstormDispatchReceipt(
                source_item_id="pending",
                status="redirect",
                reason_codes=["brainstorm_non_core_wish_redirect"],
                message="Confirmed item is not owned by the Core brainstorm worker.",
                review_entrypoint="/memory/inspection",
                metadata={"target_domain": target_domain},
            )
        worker_memory_service = self._worker_memory_service or WorkerMemoryService()
        phase = self._current_chapter_phase(identity.session_id) or BRAINSTORM_APPLY_PHASE
        try:
            worker_memory_service.authorize_operation(
                ctx=WorkerMemoryContext(
                    identity=identity,
                    worker_id=worker.source_worker_id,
                    phase=phase,
                    domain=target_domain,
                    runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
                ),
                operation_kind="proposal.submit",
                domains=[target_domain],
                layers=[Layer.CORE_STATE_AUTHORITATIVE.value],
            )
        except WorkerMemoryPermissionError as exc:
            return BrainstormDispatchReceipt(
                source_item_id="pending",
                status="pending_review",
                reason_codes=[*exc.reason_codes, exc.code],
                message=str(exc),
                review_entrypoint="/memory/inspection",
                metadata={
                    "target_domain": target_domain,
                    "worker_id": worker.source_worker_id,
                    "permission_phase": phase,
                },
            )
        return None

    def _record_worker_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        change: BrainstormCoreFieldChange,
        block_domain: str,
        old_value: Any,
    ):
        return self._runtime_workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=(
                    f"brainstorm-candidate:{change.source_item_id}:"
                    f"{uuid4().hex}"
                ),
                material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
                identity=identity,
                domain=block_domain,
                domain_path=change.target_ref,
                payload={
                    "payload_kind": "brainstorm_core_field_change",
                    "source_item_id": change.source_item_id,
                    "target_ref": change.target_ref,
                    "base_revision": change.base_revision,
                    "operation": change.operation,
                    "field_path": change.field_path,
                    "old_value": old_value,
                    "new_value": change.new_value,
                    "reason": change.reason,
                    "memory_layer_agnostic_item": True,
                    "authoritative_mutation": False,
                },
                visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
                created_by="brainstorm.core_worker",
                metadata={
                    "target_domain_path": change.target_ref,
                    "source_item_id": change.source_item_id,
                    "brainstorm_candidate": True,
                    "source_of_truth": False,
                },
            )
        )

    def _proposal_receipt_to_dispatch(
        self,
        *,
        change: BrainstormCoreFieldChange,
        proposal: ProposalReceipt,
        old_value: Any,
    ) -> BrainstormDispatchReceipt:
        status = "applied" if proposal.status == "applied" else "pending_review"
        return BrainstormDispatchReceipt(
            source_item_id=change.source_item_id,
            status=status,
            target_ref=change.target_ref,
            proposal_id=proposal.proposal_id,
            operation=change.operation,
            field_path=change.field_path,
            base_revision=change.base_revision,
            old_value=old_value,
            new_value=change.new_value,
            reason_codes=[
                "brainstorm_summary_apply",
                f"proposal_status:{proposal.status}",
            ],
            metadata=proposal.model_dump(mode="json"),
        )

    def _redirect_receipt(
        self,
        *,
        item_id: str,
        message: str,
        target_ref: str | None = None,
        reason_codes: list[str] | None = None,
    ) -> BrainstormDispatchReceipt:
        return BrainstormDispatchReceipt(
            source_item_id=item_id,
            status="redirect",
            target_ref=target_ref,
            reason_codes=reason_codes or ["brainstorm_non_core_or_unrouted_review"],
            message=message,
            review_entrypoint="/memory/inspection",
        )

    def _resolve_authoritative_block(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        target_ref: str,
    ) -> _ResolvedAuthoritativeBlock | None:
        binding = _binding_for_target_ref(target_ref)
        if binding is None:
            return None
        if self._core_state_as_of_resolver is None:
            raise StoryBrainstormServiceError(
                "brainstorm_core_as_of_resolver_unavailable",
                target_ref,
            )
        object_ref = ObjectRef(
            object_id=binding.object_id,
            layer=Layer.CORE_STATE_AUTHORITATIVE,
            domain=binding.domain,
            domain_path=binding.domain_path,
            scope="story",
        )
        try:
            manifest = self._core_state_as_of_resolver.ensure_manifest_for_identity(
                identity=identity,
                selected_turn_id=identity.turn_id,
            )
            revision = self._core_state_as_of_resolver.resolve_object_revision(
                manifest=manifest,
                object_ref=object_ref,
            )
        except CoreStateAsOfResolverError as exc:
            raise StoryBrainstormServiceError(exc.code, str(exc)) from exc
        return _block_from_revision(
            binding_object_id=binding.object_id,
            revision=revision,
        )
        return None

    def _load_latest_session(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        brainstorm_id: str,
    ) -> BrainstormSession:
        matches: list[BrainstormSession] = []
        for material in self._runtime_workspace_material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION,
            domain=BRAINSTORM_MATERIAL_DOMAIN,
        ):
            payload = dict(material.payload or {})
            if payload.get("brainstorm_id") != brainstorm_id:
                continue
            matches.append(BrainstormSession.model_validate(payload))
        if not matches:
            raise StoryBrainstormServiceError(
                "brainstorm_session_not_found",
                brainstorm_id,
            )
        return max(matches, key=lambda item: item.revision)

    def _record_session_revision(
        self,
        session: BrainstormSession,
        *,
        previous: BrainstormSession | None = None,
    ) -> None:
        if previous is not None:
            try:
                self._runtime_workspace_material_service.update_lifecycle(
                    identity=previous.identity,
                    material_id=self._material_id(previous),
                    lifecycle=RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
                    reason="brainstorm_session_revision_superseded",
                )
            except RuntimeWorkspaceMaterialServiceError:
                pass
        self._runtime_workspace_material_service.record_material(
            RuntimeWorkspaceMaterial(
                material_id=self._material_id(session),
                material_kind=RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION,
                identity=session.identity,
                domain=BRAINSTORM_MATERIAL_DOMAIN,
                domain_path=BRAINSTORM_MATERIAL_DOMAIN_PATH,
                source_refs=list(session.source_refs),
                payload=session.model_dump(mode="json"),
                visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
                created_by="writer.brainstorm",
                metadata={
                    "payload_kind": "brainstorm_session",
                    "brainstorm_id": session.brainstorm_id,
                    "revision": session.revision,
                    "temporary": True,
                    "source_of_truth": False,
                },
            )
        )

    @staticmethod
    def _material_id(session: BrainstormSession) -> str:
        return f"{session.brainstorm_id}:state:{session.revision}"

    def _ensure_identity_matches_session(self, identity: MemoryRuntimeIdentity) -> None:
        story_session = self._story_session_service.get_session(identity.session_id)
        if story_session is None:
            raise StoryBrainstormServiceError(
                "story_session_not_found",
                identity.session_id,
            )
        if story_session.story_id != identity.story_id:
            raise StoryBrainstormServiceError(
                "brainstorm_identity_story_mismatch",
                identity.story_id,
            )

    def _current_chapter_workspace_id(self, session_id: str) -> str | None:
        chapter = self._story_session_service.get_current_chapter(session_id)
        return None if chapter is None else chapter.chapter_workspace_id

    def _current_chapter_phase(self, session_id: str) -> str | None:
        chapter = self._story_session_service.get_current_chapter(session_id)
        if chapter is None:
            return None
        phase = getattr(chapter.phase, "value", chapter.phase)
        return str(phase or "").strip() or None


def _binding_for_target_ref(target_ref: str):
    normalized = str(target_ref or "").strip()
    for binding in authoritative_bindings():
        if normalized in {binding.object_id, binding.domain_path}:
            return binding
    return None


def _block_from_revision(
    *,
    binding_object_id: str,
    revision: CoreStateAuthoritativeRevisionRecord,
) -> _ResolvedAuthoritativeBlock:
    return _ResolvedAuthoritativeBlock(
        label=binding_object_id,
        domain=Domain(revision.domain),
        domain_path=revision.domain_path,
        scope=revision.scope,
        revision=int(revision.revision or 1),
        data_json=deepcopy(revision.data_json),
    )


def _value_at_path(data: Any, path: str) -> Any:
    current = data
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        return None
    return deepcopy(current)


def _field_patch_for_path(*, data: Any, field_path: str, new_value: Any) -> dict[str, Any]:
    segments = field_path.split(".")
    if len(segments) == 1:
        return {segments[0]: new_value}
    root_key = segments[0]
    root_value = deepcopy(data.get(root_key) if isinstance(data, dict) else {})
    if not isinstance(root_value, dict):
        root_value = {}
    cursor = root_value
    for segment in segments[1:-1]:
        next_value = cursor.get(segment)
        if not isinstance(next_value, dict):
            next_value = {}
        cursor[segment] = next_value
        cursor = next_value
    cursor[segments[-1]] = new_value
    return {root_key: root_value}


def _item_status_for_receipt(receipt: BrainstormDispatchReceipt) -> BrainstormItemStatus:
    if receipt.status == "applied":
        return BrainstormItemStatus.APPLIED
    if receipt.status == "conflict":
        return BrainstormItemStatus.CONFLICT
    if receipt.status == "failed":
        return BrainstormItemStatus.FAILED
    if receipt.status in {"pending_review", "redirect"}:
        return BrainstormItemStatus.PENDING_REVIEW
    return BrainstormItemStatus.DISPATCHED


def _overall_apply_status(
    receipts: list[BrainstormDispatchReceipt],
) -> Literal["applied", "pending_review", "redirect", "conflict", "failed"]:
    statuses = {receipt.status for receipt in receipts}
    if "failed" in statuses:
        return "failed"
    if "conflict" in statuses:
        return "conflict"
    if statuses == {"applied"}:
        return "applied"
    if "applied" in statuses or "pending_review" in statuses:
        return "pending_review"
    return "redirect"


def _refresh_payload(identity: MemoryRuntimeIdentity) -> dict[str, Any]:
    return {
        "memory_inspection": {
            "method": "GET",
            "path_template": "/api/rp/story-sessions/{session_id}/memory/inspection",
            "query_params": {
                "branch_head_id": identity.branch_head_id,
                "turn_id": identity.turn_id,
                "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
            },
        },
        "runtime_inspect": {
            "method": "GET",
            "path_template": "/api/rp/story-sessions/{session_id}/runtime/inspect",
            "query_params": {
                "branch_head_id": identity.branch_head_id,
                "turn_id": identity.turn_id,
            },
        },
    }
