"""Persist reversible draft selections and accept-and-continue adoption receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session
from sqlmodel import select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.revision_overlay_contracts import (
    LongformDraftAdoptionReceipt,
    LongformDraftSelectionReceipt,
    RewriteCandidateRecord,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.services.rewrite_candidate_service import RewriteCandidateService
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService


DRAFT_SELECTION_PAYLOAD_VERSION = "draft-selection.v1"
DRAFT_ADOPTION_PAYLOAD_VERSION = "draft-adoption.v1"
_DRAFT_SELECTION_DOMAIN = "chapter"


class DraftSelectionServiceError(ValueError):
    """Stable draft selection/adoption error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class DraftSelectionService:
    """Manage longform candidate selection without treating it as adoption."""

    def __init__(
        self,
        *,
        rewrite_candidate_service: RewriteCandidateService | None = None,
        workspace_material_service: RuntimeWorkspaceMaterialService | None = None,
        session: Session | None = None,
    ) -> None:
        self._session = session
        self._workspace_material_service = (
            workspace_material_service
            if workspace_material_service is not None
            else RuntimeWorkspaceMaterialService(session=session)
        )
        self._rewrite_candidate_service = (
            rewrite_candidate_service
            if rewrite_candidate_service is not None
            else RewriteCandidateService(
                workspace_material_service=self._workspace_material_service,
                session=session,
            )
        )

    def select_candidate(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
        candidate_output_refs: list[str],
        selected_output_ref: str,
        draft_ref: str | None = None,
    ) -> LongformDraftSelectionReceipt:
        self._require_turn(identity=identity, turn_id=turn_id)
        normalized_candidate_refs = _normalize_ref_list(
            candidate_output_refs,
            field_name="candidate_output_refs",
        )
        normalized_selected_ref = _require_non_blank(
            selected_output_ref,
            field_name="selected_output_ref",
        )
        if normalized_selected_ref not in normalized_candidate_refs:
            raise DraftSelectionServiceError(
                "revision_selected_output_not_candidate",
                normalized_selected_ref,
            )
        candidates = self._require_candidate_refs_visible(
            identity=identity,
            candidate_output_refs=normalized_candidate_refs,
            draft_ref=draft_ref,
        )
        resolved_draft_ref = self._resolve_draft_ref(
            candidates=candidates,
            draft_ref=draft_ref,
        )
        now = _utcnow()
        receipt = LongformDraftSelectionReceipt(
            receipt_id=f"draft_selection_{uuid4().hex}",
            turn_id=identity.turn_id,
            draft_ref=resolved_draft_ref,
            candidate_output_refs=normalized_candidate_refs,
            selected_output_ref=normalized_selected_ref,
            selected_at=now,
            metadata_json={
                "payload_version": DRAFT_SELECTION_PAYLOAD_VERSION,
                "selection_state": "active",
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "canonical_truth": False,
                "adopted_output_ref": None,
            },
        )
        self._record_selection_receipt(identity=identity, receipt=receipt)
        return receipt

    def clear_selection(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
        draft_ref: str | None = None,
    ) -> LongformDraftSelectionReceipt | None:
        self._require_turn(identity=identity, turn_id=turn_id)
        active = self.get_active_selection(identity=identity, draft_ref=draft_ref)
        if active is None:
            return None
        now = _utcnow()
        cleared = active.model_copy(
            update={
                "receipt_id": f"draft_selection_{uuid4().hex}",
                "cleared_at": now,
                "metadata_json": {
                    **dict(active.metadata_json),
                    "selection_state": "cleared",
                    "cleared_by": "user",
                    "cleared_at": now.isoformat(),
                },
            }
        )
        self._record_selection_receipt(identity=identity, receipt=cleared)
        return cleared

    def adopt_for_continue(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
        selected_output_ref: str | None = None,
        draft_ref: str | None = None,
    ) -> LongformDraftAdoptionReceipt:
        self._require_turn(identity=identity, turn_id=turn_id)
        candidates = self._list_candidates(identity=identity, draft_ref=draft_ref)
        if not candidates:
            raise DraftSelectionServiceError(
                "revision_candidate_not_found",
                _optional_detail(draft_ref) or identity.turn_id,
            )
        candidate_refs = [candidate.candidate_output_ref for candidate in candidates]
        resolved_draft_ref = self._resolve_draft_ref(
            candidates=candidates,
            draft_ref=draft_ref,
        )
        normalized_selected_ref = (
            None
            if selected_output_ref is None
            else _require_non_blank(
                selected_output_ref,
                field_name="selected_output_ref",
            )
        )
        selection_receipt_id: str | None = None
        if normalized_selected_ref is None and len(candidate_refs) == 1:
            adopted_ref = candidate_refs[0]
        elif normalized_selected_ref is not None:
            adopted_ref = normalized_selected_ref
        else:
            active = self.get_active_selection(
                identity=identity,
                draft_ref=resolved_draft_ref,
            )
            if active is None:
                raise DraftSelectionServiceError(
                    "revision_adoption_selection_required",
                    identity.turn_id,
                )
            adopted_ref = active.selected_output_ref
            selection_receipt_id = active.receipt_id
        if adopted_ref not in candidate_refs:
            raise DraftSelectionServiceError(
                "revision_selected_output_not_candidate",
                adopted_ref,
            )
        now = _utcnow()
        receipt = LongformDraftAdoptionReceipt(
            receipt_id=f"draft_adoption_{uuid4().hex}",
            turn_id=identity.turn_id,
            draft_ref=resolved_draft_ref,
            candidate_output_refs=candidate_refs,
            adopted_output_ref=adopted_ref,
            adopted_at=now,
            selection_receipt_id=selection_receipt_id,
            metadata_json={
                "payload_version": DRAFT_ADOPTION_PAYLOAD_VERSION,
                "adoption_state": "committed",
                "accept_and_continue": True,
                "next_turn_adopted_output_ref": adopted_ref,
                "canonical_continuation_base": True,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "core_state_truth": False,
                "recall_truth": False,
                "archival_truth": False,
            },
        )
        self._record_adoption_receipt(identity=identity, receipt=receipt)
        return receipt

    def get_active_selection(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
    ) -> LongformDraftSelectionReceipt | None:
        receipts = self.list_selection_receipts(identity=identity, draft_ref=draft_ref)
        if not receipts:
            return None
        latest = max(receipts, key=_selection_sort_key)
        return None if latest.cleared_at is not None else latest

    def list_selection_receipts(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
    ) -> list[LongformDraftSelectionReceipt]:
        normalized_draft_ref = _normalize_optional_text(draft_ref)
        receipts = [
            LongformDraftSelectionReceipt.model_validate(material.payload.get("record"))
            for material in self._list_selection_materials(identity=identity)
            if material.payload.get("payload_kind") == "draft_selection_receipt"
        ]
        if normalized_draft_ref is None:
            return receipts
        return [
            receipt
            for receipt in receipts
            if receipt.draft_ref == normalized_draft_ref
        ]

    def list_adoption_receipts(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
    ) -> list[LongformDraftAdoptionReceipt]:
        normalized_draft_ref = _normalize_optional_text(draft_ref)
        receipts = [
            LongformDraftAdoptionReceipt.model_validate(material.payload.get("record"))
            for material in self._list_adoption_materials(identity=identity)
            if material.payload.get("payload_kind") == "draft_adoption_receipt"
        ]
        if normalized_draft_ref is None:
            return receipts
        return [
            receipt
            for receipt in receipts
            if receipt.draft_ref == normalized_draft_ref
        ]

    def get_latest_adoption_receipt(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
    ) -> LongformDraftAdoptionReceipt | None:
        receipts = self.list_adoption_receipts(identity=identity, draft_ref=draft_ref)
        if not receipts:
            return None
        return max(receipts, key=lambda receipt: receipt.adopted_at)

    def get_latest_adoption_receipt_for_branch(
        self,
        *,
        story_id: str,
        session_id: str,
        branch_head_id: str,
        draft_ref: str | None = None,
    ) -> LongformDraftAdoptionReceipt | None:
        if self._session is None:
            return None
        normalized_draft_ref = _normalize_optional_text(draft_ref)
        stmt = (
            select(RuntimeWorkspaceMaterialRecord)
            .where(RuntimeWorkspaceMaterialRecord.story_id == story_id)
            .where(RuntimeWorkspaceMaterialRecord.session_id == session_id)
            .where(RuntimeWorkspaceMaterialRecord.branch_head_id == branch_head_id)
            .where(
                RuntimeWorkspaceMaterialRecord.material_kind
                == RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY.value
            )
            .order_by(RuntimeWorkspaceMaterialRecord.created_at.asc())
            .order_by(RuntimeWorkspaceMaterialRecord.material_id.asc())
        )
        records = list(self._session.exec(stmt).all())
        receipts: list[LongformDraftAdoptionReceipt] = []
        for record in records:
            payload = record.payload_json
            if payload.get("payload_version") != DRAFT_ADOPTION_PAYLOAD_VERSION:
                continue
            if payload.get("payload_kind") != "draft_adoption_receipt":
                continue
            receipt_payload = payload.get("record")
            if not isinstance(receipt_payload, dict):
                continue
            receipt = LongformDraftAdoptionReceipt.model_validate(receipt_payload)
            if normalized_draft_ref is not None and receipt.draft_ref != normalized_draft_ref:
                continue
            receipts.append(receipt)
        if not receipts:
            return None
        return max(receipts, key=lambda receipt: receipt.adopted_at)

    def adopted_output_anchor_for_next_turn(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
    ) -> dict[str, object] | None:
        receipt = self.get_latest_adoption_receipt(
            identity=identity,
            draft_ref=draft_ref,
        )
        if receipt is None:
            return None
        return {
            "turn_id": receipt.turn_id,
            "draft_ref": receipt.draft_ref,
            "adopted_output_ref": receipt.adopted_output_ref,
            "adoption_receipt_id": receipt.receipt_id,
            "source_kind": "longform_draft_adoption_receipt",
            "canonical_continuation_base": True,
        }

    def _require_candidate_refs_visible(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        candidate_output_refs: list[str],
        draft_ref: str | None,
    ) -> list[RewriteCandidateRecord]:
        candidates = self._list_candidates(identity=identity, draft_ref=draft_ref)
        visible_refs = {candidate.candidate_output_ref for candidate in candidates}
        missing = [ref for ref in candidate_output_refs if ref not in visible_refs]
        if missing:
            raise DraftSelectionServiceError(
                "revision_selected_output_not_candidate",
                ",".join(missing),
            )
        return [
            candidate
            for candidate in candidates
            if candidate.candidate_output_ref in set(candidate_output_refs)
        ]

    def _list_candidates(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None,
    ) -> list[RewriteCandidateRecord]:
        return self._rewrite_candidate_service.list_candidates(
            identity=identity,
            draft_ref=_normalize_optional_text(draft_ref),
        )

    @staticmethod
    def _resolve_draft_ref(
        *,
        candidates: list[RewriteCandidateRecord],
        draft_ref: str | None,
    ) -> str:
        normalized_draft_ref = _normalize_optional_text(draft_ref)
        draft_refs = {candidate.draft_ref for candidate in candidates}
        if normalized_draft_ref is not None:
            if normalized_draft_ref not in draft_refs:
                raise DraftSelectionServiceError(
                    "revision_draft_not_visible",
                    normalized_draft_ref,
                )
            return normalized_draft_ref
        if len(draft_refs) != 1:
            raise DraftSelectionServiceError(
                "revision_draft_ref_required",
                ",".join(sorted(draft_refs)),
            )
        return next(iter(draft_refs))

    def _record_selection_receipt(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        receipt: LongformDraftSelectionReceipt,
    ) -> None:
        self._workspace_material_service.record_material(
            self._receipt_material(
                identity=identity,
                material_id=f"draft_selection_{receipt.receipt_id}",
                payload_version=DRAFT_SELECTION_PAYLOAD_VERSION,
                payload_kind="draft_selection_receipt",
                record_id=receipt.receipt_id,
                record=receipt.model_dump(mode="json"),
                created_by="revision_overlay.draft_selection",
                source_refs=[
                    _candidate_source_ref(
                        receipt_id=receipt.receipt_id,
                        candidate_output_ref=candidate_output_ref,
                        source_type="rewrite_candidate",
                    )
                    for candidate_output_ref in receipt.candidate_output_refs
                ],
                metadata={
                    "selection_receipt": True,
                    "selection_state": (
                        "cleared" if receipt.cleared_at is not None else "active"
                    ),
                    "selected_output_ref": receipt.selected_output_ref,
                    "adopted_output_ref": None,
                    "canonical_truth": False,
                },
            )
        )

    def _record_adoption_receipt(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        receipt: LongformDraftAdoptionReceipt,
    ) -> None:
        source_refs = [
            _candidate_source_ref(
                receipt_id=receipt.receipt_id,
                candidate_output_ref=candidate_output_ref,
                source_type="rewrite_candidate",
            )
            for candidate_output_ref in receipt.candidate_output_refs
        ]
        if receipt.selection_receipt_id is not None:
            source_refs.append(
                MemorySourceRef(
                    source_type="draft_selection_receipt",
                    source_id=receipt.selection_receipt_id,
                    layer="runtime_workspace",
                    domain=_DRAFT_SELECTION_DOMAIN,
                    block_id="chapter.runtime_workspace",
                    entry_id=receipt.receipt_id,
                    metadata={
                        "selection_receipt_id": receipt.selection_receipt_id,
                        "receipt_id": receipt.receipt_id,
                    },
                )
            )
        self._workspace_material_service.record_material(
            self._receipt_material(
                identity=identity,
                material_id=f"draft_adoption_{receipt.receipt_id}",
                payload_version=DRAFT_ADOPTION_PAYLOAD_VERSION,
                payload_kind="draft_adoption_receipt",
                record_id=receipt.receipt_id,
                record=receipt.model_dump(mode="json"),
                created_by="revision_overlay.draft_adoption",
                source_refs=source_refs,
                metadata={
                    "adoption_receipt": True,
                    "adoption_state": "committed",
                    "adopted_output_ref": receipt.adopted_output_ref,
                    "selection_receipt_id": receipt.selection_receipt_id,
                    "canonical_continuation_base": True,
                    "canonical_truth": False,
                },
            )
        )

    @staticmethod
    def _receipt_material(
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        payload_version: str,
        payload_kind: str,
        record_id: str,
        record: dict,
        created_by: str,
        source_refs: list[MemorySourceRef],
        metadata: dict[str, object],
    ) -> RuntimeWorkspaceMaterial:
        return RuntimeWorkspaceMaterial(
            material_id=material_id,
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            identity=identity,
            domain=_DRAFT_SELECTION_DOMAIN,
            domain_path=f"chapter.revision_overlay.{payload_kind}",
            source_refs=source_refs,
            payload={
                "payload_version": payload_version,
                "payload_kind": payload_kind,
                "record_id": record_id,
                "record": record,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "canonical_truth": False,
                **metadata,
            },
            visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
            created_by=created_by,
            metadata={
                "revision_overlay_receipt": True,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "core_state_truth": False,
                "recall_truth": False,
                "archival_truth": False,
                **metadata,
            },
        )

    def _list_selection_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ):
        return [
            material
            for material in self._workspace_material_service.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
                domain=_DRAFT_SELECTION_DOMAIN,
                lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
            )
            if material.payload.get("payload_version") == DRAFT_SELECTION_PAYLOAD_VERSION
        ]

    def _list_adoption_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ):
        return [
            material
            for material in self._workspace_material_service.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
                domain=_DRAFT_SELECTION_DOMAIN,
                lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
            )
            if material.payload.get("payload_version") == DRAFT_ADOPTION_PAYLOAD_VERSION
        ]

    @staticmethod
    def _require_turn(*, identity: MemoryRuntimeIdentity, turn_id: str) -> None:
        normalized_turn_id = _require_non_blank(turn_id, field_name="turn_id")
        if identity.turn_id != normalized_turn_id:
            raise DraftSelectionServiceError(
                "revision_turn_mismatch",
                normalized_turn_id,
            )


def _candidate_source_ref(
    *,
    receipt_id: str,
    candidate_output_ref: str,
    source_type: str,
) -> MemorySourceRef:
    return MemorySourceRef(
        source_type=source_type,
        source_id=candidate_output_ref,
        layer="runtime_workspace",
        domain=_DRAFT_SELECTION_DOMAIN,
        block_id="chapter.runtime_workspace",
        entry_id=receipt_id,
        metadata={
            "candidate_output_ref": candidate_output_ref,
            "receipt_id": receipt_id,
        },
    )


def _selection_sort_key(receipt: LongformDraftSelectionReceipt) -> datetime:
    return receipt.cleared_at or receipt.selected_at


def _normalize_ref_list(values: list[str], *, field_name: str) -> list[str]:
    if not values:
        raise DraftSelectionServiceError(
            "revision_candidate_refs_required",
            field_name,
        )
    return [_require_non_blank(value, field_name=field_name) for value in values]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _optional_detail(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    return normalized


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise DraftSelectionServiceError(
            "revision_required_field_missing",
            field_name,
        )
    return normalized


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
