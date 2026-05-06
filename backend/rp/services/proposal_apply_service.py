"""Apply authoritative proposals through the existing StoryStateApplyService."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from rp.models.core_mutation import CoreMutationEnvelope
from rp.models.dsl import ObjectRef
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemorySourceRef,
)
from rp.models.memory_crud import (
    AddRelationOp,
    AppendEventOp,
    PatchFieldsOp,
    ProposalReceipt,
    ProposalSubmitInput,
    RemoveRecordOp,
    RemoveRelationOp,
    SetStatusOp,
    UpsertRecordOp,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
)

from .authoritative_compatibility_mirror_service import (
    AuthoritativeCompatibilityMirrorService,
)
from .core_state_dual_write_service import CoreStateDualWriteService
from .memory_change_event_service import MemoryChangeEventService
from .memory_object_mapper import (
    normalize_authoritative_ref,
    resolve_authoritative_binding,
)
from .proposal_repository import (
    ProposalRepository,
    extract_core_mutation_envelope,
    extract_worker_governance_metadata,
)
from .runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from .story_session_service import StorySessionService
from .story_state_apply_service import StoryStateApplyService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProposalApplyService:
    """Apply canonical authoritative proposals and persist apply receipts."""

    def __init__(
        self,
        *,
        story_session_service: StorySessionService,
        proposal_repository: ProposalRepository,
        story_state_apply_service: StoryStateApplyService | None = None,
        core_state_dual_write_service: CoreStateDualWriteService | None = None,
        core_state_store_write_switch_enabled: bool = False,
        authoritative_compatibility_mirror_service: AuthoritativeCompatibilityMirrorService
        | None = None,
        memory_change_event_service: MemoryChangeEventService | None = None,
        runtime_workspace_material_service: RuntimeWorkspaceMaterialService
        | None = None,
    ) -> None:
        self._story_session_service = story_session_service
        self._proposal_repository = proposal_repository
        self._story_state_apply_service = (
            story_state_apply_service or StoryStateApplyService()
        )
        self._core_state_dual_write_service = core_state_dual_write_service
        self._core_state_store_write_switch_enabled = (
            core_state_store_write_switch_enabled
        )
        self._authoritative_compatibility_mirror_service = (
            authoritative_compatibility_mirror_service
            or AuthoritativeCompatibilityMirrorService(
                story_session_service=story_session_service
            )
        )
        self._memory_change_event_service = memory_change_event_service
        self._runtime_workspace_material_service = runtime_workspace_material_service

    def apply_proposal(self, proposal_id: str) -> ProposalReceipt:
        proposal_record = self._proposal_repository.get_proposal_record(proposal_id)
        if proposal_record is None:
            raise ValueError(f"Proposal not found: {proposal_id}")
        if proposal_record.status == "applied":
            apply_receipts = self._proposal_repository.list_apply_receipts_for_proposal(
                proposal_id
            )
            if not apply_receipts:
                raise ValueError("phase_e_apply_receipt_missing_for_applied_proposal")
            return self._proposal_repository.get_proposal_receipt(proposal_id)
        input_model = self._proposal_repository.get_proposal_input(proposal_id)
        session = self._resolve_story_session(
            proposal_record.story_id, proposal_record.session_id
        )
        if session is None:
            self._proposal_repository.update_proposal_status(
                proposal_id,
                status="failed",
                error_message="phase_e_apply_story_session_missing",
            )
            raise ValueError("phase_e_apply_story_session_missing")
        try:
            # Keep authoritative state mutation, apply receipt creation, and
            # proposal status transition in one nested unit so failed receipt
            # persistence cannot leak a half-applied state update.
            with self._proposal_repository.session.begin_nested():
                patch, target_refs = self._build_patch(input_model.operations)
                before_snapshot = self._load_before_snapshot(
                    session=session, target_refs=target_refs
                )
                current_revisions = self._validate_base_revisions(
                    session=session,
                    proposal_record=proposal_record,
                    input_model=input_model,
                    target_refs=target_refs,
                )
                after_snapshot = self._story_state_apply_service.apply(
                    state_map=before_snapshot,
                    patch=patch,
                )
                store_primary = self._use_store_primary_write()
                if not store_primary:
                    self._authoritative_compatibility_mirror_service.sync_mirror_state(
                        session_id=session.session_id,
                        state_map=after_snapshot,
                    )

                revision_after = {
                    target_ref.object_id: (
                        current_revisions[target_ref.object_id] + 1
                        if target_ref.object_id in current_revisions
                        else self._next_revision_for_target(
                            story_id=proposal_record.story_id,
                            target_ref=target_ref,
                            session_id=session.session_id,
                        )
                    )
                    for target_ref in target_refs
                }
                apply_receipt = self._proposal_repository.create_apply_receipt(
                    proposal_id=proposal_id,
                    story_id=proposal_record.story_id,
                    session_id=session.session_id,
                    chapter_workspace_id=proposal_record.chapter_workspace_id,
                    target_refs=target_refs,
                    revision_after=revision_after,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot,
                    warnings=[],
                    apply_backend=(
                        "core_state_store"
                        if store_primary
                        else "dual_write"
                        if self._core_state_dual_write_service is not None
                        else "adapter_backed"
                    ),
                )
                if self._core_state_dual_write_service is not None:
                    store_writes = self._core_state_dual_write_service.apply_authoritative_mutation(
                        session=session,
                        before_snapshot=before_snapshot,
                        after_snapshot=after_snapshot,
                        target_refs=target_refs,
                        revision_after=revision_after,
                        apply_id=apply_receipt.apply_id,
                        proposal_id=proposal_id,
                    )
                    for object_id, (
                        current_record,
                        revision_record,
                    ) in store_writes.items():
                        target_ref = next(
                            ref for ref in target_refs if ref.object_id == object_id
                        )
                        self._proposal_repository.create_apply_target_link(
                            apply_id=apply_receipt.apply_id,
                            proposal_id=proposal_id,
                            story_id=proposal_record.story_id,
                            session_id=session.session_id,
                            object_id=object_id,
                            domain=target_ref.domain.value,
                            domain_path=target_ref.domain_path or object_id,
                            scope=target_ref.scope or "story",
                            revision=revision_after[object_id],
                            authoritative_object_id=current_record.authoritative_object_id,
                            authoritative_revision_id=revision_record.authoritative_revision_id,
                        )
                if store_primary:
                    self._authoritative_compatibility_mirror_service.sync_mirror_state(
                        session_id=session.session_id,
                        state_map=after_snapshot,
                    )
                self._record_apply_outcomes(
                    proposal_record=proposal_record,
                    input_model=input_model,
                    target_refs=target_refs,
                    apply_receipt=apply_receipt,
                )
                return self._proposal_repository.update_proposal_status(
                    proposal_id,
                    status="applied",
                    applied_at=_utcnow(),
                )
        except Exception as exc:
            self._proposal_repository.update_proposal_status(
                proposal_id,
                status="failed",
                error_message=str(exc),
            )
            raise

    def _validate_base_revisions(
        self,
        *,
        session,
        proposal_record,
        input_model: ProposalSubmitInput,
        target_refs: list[ObjectRef],
    ) -> dict[str, int]:
        if not input_model.base_refs:
            return {}

        base_refs_by_identity: dict[tuple[str, str, str, str, str], ObjectRef] = {}
        for base_ref in input_model.base_refs:
            normalized_base_ref = normalize_authoritative_ref(base_ref).model_copy(
                update={"revision": base_ref.revision}
            )
            if resolve_authoritative_binding(normalized_base_ref) is None:
                continue
            base_refs_by_identity[
                self._authoritative_ref_identity(normalized_base_ref)
            ] = normalized_base_ref

        current_revisions: dict[str, int] = {}
        for target_ref in target_refs:
            identity = self._authoritative_ref_identity(target_ref)
            base_ref = base_refs_by_identity.get(identity)
            if base_ref is None or base_ref.revision is None:
                raise ValueError(
                    "phase_e_apply_base_revision_missing:"
                    f"{self._format_authoritative_ref_identity(target_ref)}"
                )

            current_revision = self._current_revision_for_base_ref(
                story_id=proposal_record.story_id,
                session_id=session.session_id,
                target_ref=target_ref,
                base_ref=base_ref,
            )
            if current_revision != base_ref.revision:
                raise ValueError(
                    "phase_e_apply_base_revision_conflict:"
                    f"{self._format_authoritative_ref_identity(target_ref)}:"
                    f"current={current_revision}:base={base_ref.revision}"
                )
            current_revisions[target_ref.object_id] = current_revision
        return current_revisions

    def _current_revision_for_base_ref(
        self,
        *,
        story_id: str,
        session_id: str,
        target_ref: ObjectRef,
        base_ref: ObjectRef,
    ) -> int:
        if self._use_store_primary_write():
            dual_write_service = self._require_core_state_dual_write_service()
            return dual_write_service.current_authoritative_revision(
                session_id=session_id,
                target_ref=target_ref,
            )
        return self._proposal_repository.latest_revision_for_target(
            story_id=story_id,
            target_ref=target_ref,
            session_id=session_id,
        )

    @staticmethod
    def _authoritative_ref_identity(ref: ObjectRef) -> tuple[str, str, str, str, str]:
        normalized = normalize_authoritative_ref(ref)
        return (
            normalized.object_id,
            normalized.layer.value,
            normalized.domain.value,
            normalized.domain_path or normalized.object_id,
            normalized.scope or "story",
        )

    @staticmethod
    def _format_authoritative_ref_identity(ref: ObjectRef) -> str:
        normalized = normalize_authoritative_ref(ref)
        return (
            f"object_id={normalized.object_id}|"
            f"layer={normalized.layer.value}|"
            f"domain={normalized.domain.value}|"
            f"domain_path={normalized.domain_path or normalized.object_id}|"
            f"scope={normalized.scope or 'story'}"
        )

    def _resolve_story_session(self, story_id: str, session_id: str | None):
        if session_id:
            return self._story_session_service.get_session(session_id)
        return self._story_session_service.get_latest_session_for_story(story_id)

    def _use_store_primary_write(self) -> bool:
        return (
            self._core_state_store_write_switch_enabled
            and self._core_state_dual_write_service is not None
        )

    def _require_core_state_dual_write_service(self) -> CoreStateDualWriteService:
        if self._core_state_dual_write_service is None:
            raise ValueError("phase_e_core_state_dual_write_service_missing")
        return self._core_state_dual_write_service

    def _load_before_snapshot(self, *, session, target_refs: list) -> dict:
        mirror_snapshot = (
            self._authoritative_compatibility_mirror_service.read_mirror_state(
                session=session
            )
        )
        if not self._use_store_primary_write():
            return mirror_snapshot
        dual_write_service = self._require_core_state_dual_write_service()
        dual_write_service.ensure_authoritative_targets_seed(
            session=session,
            snapshot=mirror_snapshot,
            target_refs=target_refs,
        )
        return dual_write_service.materialize_authoritative_snapshot(
            session=session,
            fallback_snapshot=mirror_snapshot,
        )

    def _next_revision_for_target(
        self,
        *,
        story_id: str,
        target_ref,
        session_id: str,
    ) -> int:
        if self._use_store_primary_write():
            dual_write_service = self._require_core_state_dual_write_service()
            return (
                dual_write_service.current_authoritative_revision(
                    session_id=session_id,
                    target_ref=target_ref,
                )
                + 1
            )
        return (
            self._proposal_repository.latest_revision_for_target(
                story_id=story_id,
                target_ref=target_ref,
                session_id=session_id,
            )
            + 1
        )

    def _build_patch(self, operations) -> tuple[dict, list]:
        patch: dict = {}
        target_refs: dict[str, object] = {}
        for operation in operations:
            target_ref = normalize_authoritative_ref(operation.target_ref)
            binding = resolve_authoritative_binding(target_ref)
            if binding is None:
                raise ValueError(
                    f"phase_e_apply_non_authoritative_target:{target_ref.object_id}"
                )
            target_refs[target_ref.object_id] = target_ref
            if isinstance(operation, PatchFieldsOp):
                patch.setdefault(binding.backend_field, {})
                if not isinstance(patch[binding.backend_field], dict):
                    raise ValueError(
                        f"phase_e_apply_patch_shape_conflict:{binding.backend_field}"
                    )
                patch[binding.backend_field] = {
                    **dict(patch[binding.backend_field]),
                    **dict(operation.field_patch),
                }
                continue
            if isinstance(operation, UpsertRecordOp):
                patch[binding.backend_field] = dict(operation.record_data)
                continue
            if isinstance(operation, AppendEventOp):
                patch.setdefault(binding.backend_field, [])
                if not isinstance(patch[binding.backend_field], list):
                    raise ValueError(
                        f"phase_e_apply_patch_shape_conflict:{binding.backend_field}"
                    )
                patch[binding.backend_field] = [
                    *list(patch[binding.backend_field]),
                    dict(operation.event_data),
                ]
                continue
            if isinstance(
                operation,
                (RemoveRecordOp, AddRelationOp, RemoveRelationOp, SetStatusOp),
            ):
                raise ValueError(
                    f"phase_e_apply_operation_not_supported:{operation.kind}"
                )
            raise ValueError(f"phase_e_apply_operation_not_supported:{operation.kind}")
        return patch, list(target_refs.values())

    def _record_apply_outcomes(
        self,
        *,
        proposal_record,
        input_model: ProposalSubmitInput,
        target_refs: list[ObjectRef],
        apply_receipt,
    ) -> None:
        warning_tokens: list[str] = []
        governance_payload = dict(proposal_record.governance_metadata_json or {})
        worker_governance = extract_worker_governance_metadata(governance_payload)
        if worker_governance is not None:
            warning_tokens.extend(_governance_warning_tokens(worker_governance))

        core_mutation = extract_core_mutation_envelope(governance_payload)
        if core_mutation is not None:
            invalidated_candidate_ids = self._invalidate_matching_worker_candidates(
                core_mutation=core_mutation,
                target_refs=target_refs,
            )
            warning_tokens.extend(_core_mutation_warning_tokens(core_mutation))
            warning_tokens.extend(
                f"core_mutation:projection_dirty={target_ref.domain_path or target_ref.object_id}"
                for target_ref in target_refs
            )
            warning_tokens.extend(
                f"core_mutation:invalidated_candidate={material_id}"
                for material_id in invalidated_candidate_ids
            )
            event_id = self._record_core_mutation_event(
                proposal_record=proposal_record,
                input_model=input_model,
                core_mutation=core_mutation,
                target_refs=target_refs,
                apply_receipt=apply_receipt,
                invalidated_candidate_ids=invalidated_candidate_ids,
            )
            if event_id is not None:
                warning_tokens.append(f"core_mutation:event_id={event_id}")
            elif core_mutation.identity is None:
                warning_tokens.append("core_mutation:identity=absent")

        deduped = _dedupe_warning_tokens(warning_tokens)
        if deduped:
            self._proposal_repository.append_apply_receipt_warnings(
                proposal_id=proposal_record.proposal_id,
                warnings=deduped,
            )

    def _invalidate_matching_worker_candidates(
        self,
        *,
        core_mutation: CoreMutationEnvelope,
        target_refs: list[ObjectRef],
    ) -> list[str]:
        if core_mutation.identity is None:
            return []
        service = self._resolve_runtime_workspace_material_service()
        target_paths = {
            target_ref.domain_path or target_ref.object_id for target_ref in target_refs
        }
        invalidated_ids: list[str] = []
        seen_material_ids: set[str] = set()
        for target_ref in target_refs:
            materials = service.list_materials(
                identity=core_mutation.identity,
                material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
                domain=target_ref.domain.value,
            )
            for material in materials:
                if material.material_id in seen_material_ids:
                    continue
                if material.lifecycle in {
                    RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
                    RuntimeWorkspaceMaterialLifecycle.EXPIRED,
                    RuntimeWorkspaceMaterialLifecycle.DISCARDED,
                }:
                    continue
                if not self._worker_candidate_matches_target(
                    material=material,
                    target_paths=target_paths,
                ):
                    continue
                service.update_lifecycle(
                    identity=core_mutation.identity,
                    material_id=material.material_id,
                    lifecycle=RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
                    reason=(
                        "authoritative_core_mutation_applied:"
                        f"{core_mutation.origin_kind}"
                    ),
                )
                invalidated_ids.append(material.material_id)
                seen_material_ids.add(material.material_id)
        return invalidated_ids

    @staticmethod
    def _worker_candidate_matches_target(
        *,
        material,
        target_paths: set[str],
    ) -> bool:
        candidate_paths = {
            value
            for value in (
                _extract_target_path(material.domain_path),
                _extract_target_path(
                    (material.metadata or {}).get("target_domain_path")
                ),
                _extract_target_path((material.metadata or {}).get("domain_path")),
                _extract_nested_target_path(
                    (material.metadata or {}).get("target_ref")
                ),
                _extract_nested_target_path((material.payload or {}).get("target_ref")),
                _extract_nested_target_path(
                    (material.payload or {}).get("authoritative_ref")
                ),
            )
            if value is not None
        }
        return bool(candidate_paths.intersection(target_paths))

    def _record_core_mutation_event(
        self,
        *,
        proposal_record,
        input_model: ProposalSubmitInput,
        core_mutation: CoreMutationEnvelope,
        target_refs: list[ObjectRef],
        apply_receipt,
        invalidated_candidate_ids: list[str],
    ) -> str | None:
        if core_mutation.identity is None:
            return None
        event = MemoryChangeEvent(
            event_id=f"core_mutation_event_{uuid4().hex}",
            identity=core_mutation.identity,
            actor=core_mutation.actor,
            event_kind="core_authoritative_mutation_applied",
            layer=target_refs[0].layer.value
            if target_refs
            else "core_state.authoritative",
            domain=input_model.domain.value,
            block_id=target_refs[0].object_id if len(target_refs) == 1 else None,
            entry_id=apply_receipt.apply_id,
            operation_kind="core_mutation.apply",
            source_refs=self._build_event_source_refs(
                proposal_record=proposal_record,
                core_mutation=core_mutation,
                target_refs=target_refs,
                apply_receipt=apply_receipt,
            ),
            dirty_targets=self._build_dirty_targets(
                core_mutation=core_mutation,
                target_refs=target_refs,
                apply_receipt=apply_receipt,
            ),
            visibility_effect="current_truth_updated",
            metadata={
                "shared_core_mutation_kernel": True,
                "proposal_id": proposal_record.proposal_id,
                "apply_id": apply_receipt.apply_id,
                "origin_kind": core_mutation.origin_kind,
                "reason": core_mutation.reason,
                "worker_id": core_mutation.worker_id,
                "phase": core_mutation.phase,
                "permission_decision": core_mutation.permission_decision,
                "permission_reason_codes": list(core_mutation.permission_reason_codes),
                "trace_refs": list(core_mutation.trace_refs),
                "operation_kinds": [
                    operation.kind for operation in input_model.operations
                ],
                "invalidated_candidate_ids": list(invalidated_candidate_ids),
                "projection_refresh": "stale_mark_only",
            },
        )
        self._resolve_memory_change_event_service().record_event(event)
        return event.event_id

    @staticmethod
    def _build_event_source_refs(
        *,
        proposal_record,
        core_mutation: CoreMutationEnvelope,
        target_refs: list[ObjectRef],
        apply_receipt,
    ) -> list[MemorySourceRef]:
        block_id = target_refs[0].object_id if len(target_refs) == 1 else None
        domain = (
            target_refs[0].domain.value if target_refs else core_mutation.domain.value
        )
        layer = (
            target_refs[0].layer.value if target_refs else "core_state.authoritative"
        )
        return [
            *core_mutation.source_refs,
            MemorySourceRef(
                source_type="memory_proposal",
                source_id=proposal_record.proposal_id,
                layer=layer,
                domain=domain,
                block_id=block_id,
                metadata={"origin_kind": core_mutation.origin_kind},
            ),
            MemorySourceRef(
                source_type="memory_apply_receipt",
                source_id=apply_receipt.apply_id,
                layer=layer,
                domain=domain,
                block_id=block_id,
                metadata={"proposal_id": proposal_record.proposal_id},
            ),
        ]

    @staticmethod
    def _build_dirty_targets(
        *,
        core_mutation: CoreMutationEnvelope,
        target_refs: list[ObjectRef],
        apply_receipt,
    ) -> list[MemoryDirtyTarget]:
        dirty_targets: list[MemoryDirtyTarget] = []
        for target_ref in target_refs:
            domain_path = target_ref.domain_path or target_ref.object_id
            dirty_targets.append(
                MemoryDirtyTarget(
                    target_kind="core_authoritative_block",
                    target_id=target_ref.object_id,
                    layer=target_ref.layer.value,
                    domain=target_ref.domain.value,
                    block_id=target_ref.object_id,
                    reason="core_mutation_applied",
                    metadata={
                        "revision_after": apply_receipt.revision_after_json.get(
                            target_ref.object_id
                        ),
                        "origin_kind": core_mutation.origin_kind,
                    },
                )
            )
            dirty_targets.append(
                MemoryDirtyTarget(
                    target_kind="projection_refresh_pending",
                    target_id=domain_path,
                    layer="core_state.projection",
                    domain=target_ref.domain.value,
                    block_id=f"projection:{domain_path}",
                    reason="authoritative_core_changed",
                    metadata={
                        "refresh_state": "stale_mark_only",
                        "source_truth": "core_state.authoritative",
                    },
                )
            )
        return dirty_targets

    def _resolve_memory_change_event_service(self) -> MemoryChangeEventService:
        if self._memory_change_event_service is None:
            self._memory_change_event_service = MemoryChangeEventService(
                session=self._proposal_repository.session
            )
        return self._memory_change_event_service

    def _resolve_runtime_workspace_material_service(
        self,
    ) -> RuntimeWorkspaceMaterialService:
        if self._runtime_workspace_material_service is None:
            self._runtime_workspace_material_service = RuntimeWorkspaceMaterialService(
                session=self._proposal_repository.session,
                memory_change_event_service=self._resolve_memory_change_event_service(),
            )
        return self._runtime_workspace_material_service


def _governance_warning_tokens(governance_metadata) -> list[str]:
    warnings = [
        f"worker_memory:story_id={governance_metadata.identity.story_id}",
        f"worker_memory:session_id={governance_metadata.identity.session_id}",
        f"worker_memory:branch_head_id={governance_metadata.identity.branch_head_id}",
        f"worker_memory:turn_id={governance_metadata.identity.turn_id}",
        f"worker_memory:worker_id={governance_metadata.worker_id}",
        f"worker_memory:phase={governance_metadata.phase}",
        (
            "worker_memory:runtime_profile_snapshot_id="
            f"{governance_metadata.runtime_profile_snapshot_id}"
        ),
        (
            "worker_memory:permission_decision="
            f"{governance_metadata.permission_decision}"
        ),
    ]
    warnings.extend(
        f"worker_memory:reason_code={code}"
        for code in governance_metadata.permission_reason_codes
    )
    return warnings


def _core_mutation_warning_tokens(core_mutation: CoreMutationEnvelope) -> list[str]:
    warnings = [
        f"core_mutation:origin_kind={core_mutation.origin_kind}",
        f"core_mutation:actor={core_mutation.actor}",
        f"core_mutation:source_ref_count={len(core_mutation.source_refs)}",
        f"core_mutation:trace_ref_count={len(core_mutation.trace_refs)}",
    ]
    if core_mutation.identity is not None:
        warnings.extend(
            [
                f"core_mutation:story_id={core_mutation.identity.story_id}",
                f"core_mutation:session_id={core_mutation.identity.session_id}",
                f"core_mutation:branch_head_id={core_mutation.identity.branch_head_id}",
                f"core_mutation:turn_id={core_mutation.identity.turn_id}",
                (
                    "core_mutation:runtime_profile_snapshot_id="
                    f"{core_mutation.identity.runtime_profile_snapshot_id}"
                ),
            ]
        )
    if core_mutation.worker_id is not None:
        warnings.append(f"core_mutation:worker_id={core_mutation.worker_id}")
    if core_mutation.phase is not None:
        warnings.append(f"core_mutation:phase={core_mutation.phase}")
    if core_mutation.permission_decision is not None:
        warnings.append(
            f"core_mutation:permission_decision={core_mutation.permission_decision}"
        )
    warnings.extend(
        f"core_mutation:reason_code={code}"
        for code in core_mutation.permission_reason_codes
    )
    return warnings


def _extract_target_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _extract_nested_target_path(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("domain_path", "object_id"):
        candidate = value.get(key)
        normalized = _extract_target_path(candidate)
        if normalized is not None:
            return normalized
    return None


def _dedupe_warning_tokens(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped
