"""Apply authoritative proposals through the existing StoryStateApplyService."""

from __future__ import annotations

from datetime import datetime, timezone

from rp.models.dsl import ObjectRef
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

from .authoritative_compatibility_mirror_service import (
    AuthoritativeCompatibilityMirrorService,
)
from .core_state_dual_write_service import CoreStateDualWriteService
from .memory_object_mapper import (
    normalize_authoritative_ref,
    resolve_authoritative_binding,
)
from .proposal_repository import ProposalRepository
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
