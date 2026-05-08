"""Persist review overlay comments and tracked changes as Runtime Workspace sidecars."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from sqlmodel import Session

from rp.models.memory_contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.revision_overlay_contracts import (
    DraftDocumentRecord,
    ReviewOverlayInspectionRecord,
    ReviewOverlayMode,
    ReviewOverlayRecord,
    RevisionAnchorRef,
    RevisionCommentRecord,
    RevisionCommentStatus,
    RevisionTrackedChangeKind,
    TrackedChangeRecord,
)
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService


REVISION_OVERLAY_PAYLOAD_VERSION = "revision-overlay.v1"
_REVIEW_OVERLAY_DOMAIN = "chapter"


class RevisionOverlayServiceError(ValueError):
    """Stable revision overlay service error with a machine-readable code."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}:{detail}")


class RevisionOverlayService:
    """Store RP-owned revision overlay records under exact runtime identity."""

    def __init__(
        self,
        *,
        workspace_material_service: RuntimeWorkspaceMaterialService | None = None,
        session: Session | None = None,
    ) -> None:
        self._workspace_material_service = (
            workspace_material_service
            if workspace_material_service is not None
            else RuntimeWorkspaceMaterialService(session=session)
        )

    def record_draft_document(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_document: DraftDocumentRecord,
    ) -> DraftDocumentRecord:
        self._require_same_turn(identity=identity, turn_id=draft_document.turn_id)
        existing = self._latest_material_for_record(
            identity=identity,
            payload_kind="draft_document",
            record_id=draft_document.draft_document_id,
        )
        if (
            existing is not None
            and existing.payload.get("payload_kind") == "draft_document"
        ):
            return DraftDocumentRecord.model_validate(existing.payload.get("record"))
        material = self._material_for_record(
            identity=identity,
            record_id=draft_document.draft_document_id,
            payload_kind="draft_document",
            record=draft_document.model_dump(mode="json"),
            domain_path="chapter.revision_overlay.draft_document",
            created_by="revision_overlay.draft_materialization",
            source_refs=[
                MemorySourceRef(
                    source_type="writer_output_ref",
                    source_id=draft_document.source_output_ref,
                    layer="runtime_workspace",
                    domain=_REVIEW_OVERLAY_DOMAIN,
                    block_id="chapter.runtime_workspace",
                    entry_id=draft_document.draft_document_id,
                    metadata={
                        "draft_ref": draft_document.draft_ref,
                        "draft_document_id": draft_document.draft_document_id,
                    },
                )
            ],
        )
        self._workspace_material_service.record_material(material)
        return draft_document

    def create_or_update_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_document_id: str,
        mode: ReviewOverlayMode,
    ) -> ReviewOverlayRecord:
        draft_document = self._require_draft_document(
            identity=identity,
            draft_document_id=draft_document_id,
        )
        existing = self._find_overlay_for_draft(
            identity=identity,
            draft_document_id=draft_document_id,
        )
        if existing is not None and existing.mode == mode:
            return existing
        if existing is not None:
            overlay = existing.model_copy(
                update={
                    "mode": mode,
                    "metadata_json": {
                        **existing.metadata_json,
                        "rewrite_request_ref": None,
                        "rewrite_instruction_ref": None,
                    },
                }
            )
        else:
            overlay = ReviewOverlayRecord(
                overlay_id=f"review_overlay_{uuid4().hex}",
                turn_id=identity.turn_id,
                draft_ref=draft_document.draft_ref,
                draft_document_id=draft_document.draft_document_id,
                mode=mode,
                metadata_json={
                    "payload_version": REVISION_OVERLAY_PAYLOAD_VERSION,
                    "story_id": identity.story_id,
                    "session_id": identity.session_id,
                    "branch_head_id": identity.branch_head_id,
                    "runtime_profile_snapshot_id": (
                        identity.runtime_profile_snapshot_id
                    ),
                    "runtime_truth_owner": "rp_runtime",
                    "superdoc_truth_owner": False,
                    "rewrite_request_ref": None,
                    "rewrite_instruction_ref": None,
                },
            )
        self._record_overlay(identity=identity, overlay=overlay)
        return overlay

    def add_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
        anchor_ref: RevisionAnchorRef,
        instruction_text: str,
        selected_excerpt: str | None = None,
    ) -> RevisionCommentRecord:
        overlay = self._require_overlay(identity=identity, overlay_id=overlay_id)
        self._validate_anchor(identity=identity, overlay=overlay, anchor_ref=anchor_ref)
        comment = RevisionCommentRecord(
            comment_id=f"revision_comment_{uuid4().hex}",
            turn_id=identity.turn_id,
            draft_ref=overlay.draft_ref,
            overlay_id=overlay.overlay_id,
            anchor_ref=anchor_ref,
            selected_excerpt=selected_excerpt,
            instruction_text=instruction_text,
            metadata_json={
                "payload_version": REVISION_OVERLAY_PAYLOAD_VERSION,
                "draft_document_id": overlay.draft_document_id,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
            },
        )
        updated_overlay = overlay.model_copy(
            update={"comment_refs": [*overlay.comment_refs, comment.comment_id]}
        )
        self._record_comment(identity=identity, comment=comment)
        self._record_overlay(identity=identity, overlay=updated_overlay)
        return comment

    def add_tracked_change(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
        anchor_ref: RevisionAnchorRef,
        change_kind: RevisionTrackedChangeKind,
        original_text: str | None = None,
        suggested_text: str | None = None,
    ) -> TrackedChangeRecord:
        overlay = self._require_overlay(identity=identity, overlay_id=overlay_id)
        self._validate_anchor(identity=identity, overlay=overlay, anchor_ref=anchor_ref)
        tracked_change = TrackedChangeRecord(
            tracked_change_id=f"tracked_change_{uuid4().hex}",
            turn_id=identity.turn_id,
            draft_ref=overlay.draft_ref,
            overlay_id=overlay.overlay_id,
            anchor_ref=anchor_ref,
            change_kind=change_kind,
            original_text=original_text,
            suggested_text=suggested_text,
            metadata_json={
                "payload_version": REVISION_OVERLAY_PAYLOAD_VERSION,
                "draft_document_id": overlay.draft_document_id,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
            },
        )
        updated_overlay = overlay.model_copy(
            update={
                "tracked_change_refs": [
                    *overlay.tracked_change_refs,
                    tracked_change.tracked_change_id,
                ]
            }
        )
        self._record_tracked_change(identity=identity, tracked_change=tracked_change)
        self._record_overlay(identity=identity, overlay=updated_overlay)
        return tracked_change

    def resolve_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment_id: str,
    ) -> RevisionCommentRecord:
        return self._update_comment_status(
            identity=identity,
            comment_id=comment_id,
            status="resolved",
        )

    def delete_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment_id: str,
    ) -> RevisionCommentRecord:
        return self._update_comment_status(
            identity=identity,
            comment_id=comment_id,
            status="deleted",
        )

    def inspect_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
    ) -> ReviewOverlayInspectionRecord:
        overlay = self._require_overlay(identity=identity, overlay_id=overlay_id)
        comments = [
            comment
            for comment in (
                self._get_comment(identity=identity, comment_id=comment_id)
                for comment_id in overlay.comment_refs
            )
            if comment is not None
        ]
        tracked_changes = [
            tracked_change
            for tracked_change in (
                self._get_tracked_change(
                    identity=identity,
                    tracked_change_id=tracked_change_id,
                )
                for tracked_change_id in overlay.tracked_change_refs
            )
            if tracked_change is not None
        ]
        return ReviewOverlayInspectionRecord(
            overlay=overlay,
            comments=comments,
            tracked_changes=tracked_changes,
            active_comment_refs=[
                comment.comment_id
                for comment in comments
                if comment.status == "active"
            ],
            active_tracked_change_refs=[
                tracked_change.tracked_change_id
                for tracked_change in tracked_changes
                if tracked_change.status == "active"
            ],
            material_refs=self._material_refs_for_overlay(
                identity=identity,
                overlay=overlay,
            ),
            metadata_json={
                "read_only": True,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
            },
        )

    def get_draft_document(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_document_id: str,
    ) -> DraftDocumentRecord:
        return self._require_draft_document(
            identity=identity,
            draft_document_id=draft_document_id,
        )

    def find_draft_document_by_ref(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
    ) -> DraftDocumentRecord | None:
        normalized_draft_ref = _require_non_blank(draft_ref, field_name="draft_ref")
        draft_documents = [
            DraftDocumentRecord.model_validate(material.payload.get("record"))
            for material in self._list_revision_materials(identity=identity)
            if material.payload.get("payload_kind") == "draft_document"
        ]
        matches = [
            draft
            for draft in draft_documents
            if draft.draft_ref == normalized_draft_ref
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda draft: draft.created_at,
        )

    def find_overlay_for_draft_ref(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str,
    ) -> ReviewOverlayRecord | None:
        overlays = self.list_overlays(identity=identity, draft_ref=draft_ref)
        if not overlays:
            return None
        return overlays[-1]

    def list_overlays(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_ref: str | None = None,
    ) -> list[ReviewOverlayRecord]:
        latest_by_overlay_id: dict[str, RuntimeWorkspaceMaterial] = {}
        for material in self._list_revision_materials(identity=identity):
            if material.payload.get("payload_kind") != "review_overlay":
                continue
            overlay_id = str(material.payload.get("record_id") or "")
            previous = latest_by_overlay_id.get(overlay_id)
            if previous is None or _record_version(material) > _record_version(previous):
                latest_by_overlay_id[overlay_id] = material
        overlays = [
            self._overlay_from_material(material)
            for material in latest_by_overlay_id.values()
        ]
        if draft_ref is None:
            return overlays
        normalized_draft_ref = _require_non_blank(draft_ref, field_name="draft_ref")
        return [
            overlay
            for overlay in overlays
            if overlay.draft_ref == normalized_draft_ref
        ]

    def _update_comment_status(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment_id: str,
        status: RevisionCommentStatus,
    ) -> RevisionCommentRecord:
        comment = self._get_comment(identity=identity, comment_id=comment_id)
        if comment is None:
            raise RevisionOverlayServiceError(
                "revision_comment_not_found",
                comment_id,
            )
        self._require_same_turn(identity=identity, turn_id=comment.turn_id)
        updated = comment.model_copy(update={"status": status})
        self._record_comment(identity=identity, comment=updated)
        return updated

    def _record_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay: ReviewOverlayRecord,
    ) -> None:
        self._require_same_turn(identity=identity, turn_id=overlay.turn_id)
        self._record_or_replace_material(
            self._material_for_record(
                identity=identity,
                record_id=overlay.overlay_id,
                payload_kind="review_overlay",
                record=overlay.model_dump(mode="json"),
                domain_path="chapter.revision_overlay.overlay",
                created_by="revision_overlay.review_overlay",
            )
        )

    def _record_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment: RevisionCommentRecord,
    ) -> None:
        self._record_or_replace_material(
            self._material_for_record(
                identity=identity,
                record_id=comment.comment_id,
                payload_kind="revision_comment",
                record=comment.model_dump(mode="json"),
                domain_path="chapter.revision_overlay.comment",
                created_by="revision_overlay.comment",
                source_refs=[
                    MemorySourceRef(
                        source_type="review_overlay",
                        source_id=comment.overlay_id,
                        layer="runtime_workspace",
                        domain=_REVIEW_OVERLAY_DOMAIN,
                        block_id="chapter.runtime_workspace",
                        entry_id=comment.comment_id,
                        metadata={"comment_id": comment.comment_id},
                    )
                ],
            )
        )

    def _record_tracked_change(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        tracked_change: TrackedChangeRecord,
    ) -> None:
        self._record_or_replace_material(
            self._material_for_record(
                identity=identity,
                record_id=tracked_change.tracked_change_id,
                payload_kind="tracked_change",
                record=tracked_change.model_dump(mode="json"),
                domain_path="chapter.revision_overlay.tracked_change",
                created_by="revision_overlay.tracked_change",
                source_refs=[
                    MemorySourceRef(
                        source_type="review_overlay",
                        source_id=tracked_change.overlay_id,
                        layer="runtime_workspace",
                        domain=_REVIEW_OVERLAY_DOMAIN,
                        block_id="chapter.runtime_workspace",
                        entry_id=tracked_change.tracked_change_id,
                        metadata={
                            "tracked_change_id": tracked_change.tracked_change_id
                        },
                    )
                ],
            )
        )

    def _record_or_replace_material(self, material: RuntimeWorkspaceMaterial) -> None:
        self._workspace_material_service.record_material(material)

    def _material_for_record(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        record_id: str,
        payload_kind: str,
        record: dict,
        domain_path: str,
        created_by: str,
        source_refs: list[MemorySourceRef] | None = None,
    ) -> RuntimeWorkspaceMaterial:
        return RuntimeWorkspaceMaterial(
            material_id=self._next_material_id(
                identity=identity,
                payload_kind=payload_kind,
                record_id=record_id,
            ),
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            identity=identity,
            domain=_REVIEW_OVERLAY_DOMAIN,
            domain_path=domain_path,
            source_refs=source_refs or [],
            payload={
                "payload_version": REVISION_OVERLAY_PAYLOAD_VERSION,
                "payload_kind": payload_kind,
                "record_id": record_id,
                "record": record,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "canonical_truth": False,
                "rewrite_request_ref": None,
                "rewrite_instruction_ref": None,
            },
            visibility=RuntimeWorkspaceMaterialVisibility.REVIEW_VISIBLE.value,
            created_by=created_by,
            metadata={
                "revision_overlay_sidecar": True,
                "runtime_truth_owner": "rp_runtime",
                "superdoc_truth_owner": False,
                "canonical_truth": False,
            },
        )

    def _require_draft_document(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_document_id: str,
    ) -> DraftDocumentRecord:
        material = self._latest_material_for_record(
            identity=identity,
            payload_kind="draft_document",
            record_id=draft_document_id,
        )
        if material is None or material.payload.get("payload_kind") != "draft_document":
            raise RevisionOverlayServiceError(
                "revision_draft_not_visible",
                draft_document_id,
            )
        draft = DraftDocumentRecord.model_validate(material.payload.get("record"))
        self._require_same_turn(identity=identity, turn_id=draft.turn_id)
        return draft

    def _require_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
    ) -> ReviewOverlayRecord:
        overlay = self._get_overlay(identity=identity, overlay_id=overlay_id)
        if overlay is None:
            raise RevisionOverlayServiceError(
                "revision_overlay_not_found",
                overlay_id,
            )
        self._require_same_turn(identity=identity, turn_id=overlay.turn_id)
        return overlay

    def _get_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay_id: str,
    ) -> ReviewOverlayRecord | None:
        material = self._latest_material_for_record(
            identity=identity,
            payload_kind="review_overlay",
            record_id=overlay_id,
        )
        if material is None or material.payload.get("payload_kind") != "review_overlay":
            return None
        if material.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED:
            return None
        return self._overlay_from_material(material)

    def _get_comment(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        comment_id: str,
    ) -> RevisionCommentRecord | None:
        material = self._latest_material_for_record(
            identity=identity,
            payload_kind="revision_comment",
            record_id=comment_id,
        )
        if material is None or material.payload.get("payload_kind") != "revision_comment":
            return None
        if material.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED:
            return None
        return RevisionCommentRecord.model_validate(material.payload.get("record"))

    def _get_tracked_change(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        tracked_change_id: str,
    ) -> TrackedChangeRecord | None:
        material = self._latest_material_for_record(
            identity=identity,
            payload_kind="tracked_change",
            record_id=tracked_change_id,
        )
        if material is None or material.payload.get("payload_kind") != "tracked_change":
            return None
        if material.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED:
            return None
        return TrackedChangeRecord.model_validate(material.payload.get("record"))

    def _find_overlay_for_draft(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        draft_document_id: str,
    ) -> ReviewOverlayRecord | None:
        for overlay in self.list_overlays(identity=identity):
            if overlay.draft_document_id == draft_document_id:
                return overlay
        return None

    def _validate_anchor(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay: ReviewOverlayRecord,
        anchor_ref: RevisionAnchorRef,
    ) -> None:
        draft = self._require_draft_document(
            identity=identity,
            draft_document_id=overlay.draft_document_id,
        )
        if draft.draft_ref != overlay.draft_ref:
            raise RevisionOverlayServiceError(
                "revision_comment_draft_mismatch",
                overlay.overlay_id,
            )
        block_ids = {block.block_id for block in draft.blocks}
        missing_blocks = [
            block_id for block_id in anchor_ref.block_ids if block_id not in block_ids
        ]
        if missing_blocks:
            raise RevisionOverlayServiceError(
                "revision_anchor_block_not_found",
                ",".join(missing_blocks),
            )
        block_text_by_id = {block.block_id: block.text for block in draft.blocks}
        for block_id in anchor_ref.block_ids:
            text_length = len(block_text_by_id[block_id])
            for offset in [anchor_ref.start_offset, anchor_ref.end_offset]:
                if offset is not None and offset > text_length:
                    raise RevisionOverlayServiceError(
                        "revision_anchor_offset_out_of_bounds",
                        block_id,
                    )

    def _material_refs_for_overlay(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        overlay: ReviewOverlayRecord,
    ) -> list[str]:
        refs = [
            self._latest_material_id(
                identity=identity,
                payload_kind="review_overlay",
                record_id=overlay.overlay_id,
            ),
            self._latest_material_id(
                identity=identity,
                payload_kind="draft_document",
                record_id=overlay.draft_document_id,
            ),
        ]
        refs.extend(
            self._latest_material_id(
                identity=identity,
                payload_kind="revision_comment",
                record_id=comment_id,
            )
            for comment_id in overlay.comment_refs
            if self._get_comment(identity=identity, comment_id=comment_id) is not None
        )
        refs.extend(
            self._latest_material_id(
                identity=identity,
                payload_kind="tracked_change",
                record_id=tracked_change_id,
            )
            for tracked_change_id in overlay.tracked_change_refs
            if self._get_tracked_change(
                identity=identity,
                tracked_change_id=tracked_change_id,
            )
            is not None
        )
        return refs

    def _list_revision_materials(
        self,
        *,
        identity: MemoryRuntimeIdentity,
    ) -> list[RuntimeWorkspaceMaterial]:
        return [
            material
            for material in self._workspace_material_service.list_materials(
                identity=identity,
                material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
                domain=_REVIEW_OVERLAY_DOMAIN,
            )
            if material.payload.get("payload_version") == REVISION_OVERLAY_PAYLOAD_VERSION
            and material.lifecycle != RuntimeWorkspaceMaterialLifecycle.INVALIDATED
        ]

    @staticmethod
    def _overlay_from_material(material: RuntimeWorkspaceMaterial) -> ReviewOverlayRecord:
        return ReviewOverlayRecord.model_validate(material.payload.get("record"))

    def _latest_material_for_record(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        payload_kind: str,
        record_id: str,
    ) -> RuntimeWorkspaceMaterial | None:
        candidates = [
            material
            for material in self._list_revision_materials(identity=identity)
            if material.payload.get("payload_kind") == payload_kind
            and material.payload.get("record_id") == record_id
        ]
        if not candidates:
            return None
        return max(candidates, key=_record_version)

    def _latest_material_id(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        payload_kind: str,
        record_id: str,
    ) -> str:
        material = self._latest_material_for_record(
            identity=identity,
            payload_kind=payload_kind,
            record_id=record_id,
        )
        if material is None:
            return _record_key(
                identity=identity,
                payload_kind=payload_kind,
                record_id=record_id,
            )
        return material.material_id

    def _next_material_id(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        payload_kind: str,
        record_id: str,
    ) -> str:
        latest = self._latest_material_for_record(
            identity=identity,
            payload_kind=payload_kind,
            record_id=record_id,
        )
        version = 1 if latest is None else _record_version(latest) + 1
        return (
            f"{_record_key(identity=identity, payload_kind=payload_kind, record_id=record_id)}"
            f"_v{version:04d}"
        )

    @staticmethod
    def _require_same_turn(
        *,
        identity: MemoryRuntimeIdentity,
        turn_id: str,
    ) -> None:
        if identity.turn_id != turn_id:
            raise RevisionOverlayServiceError("revision_turn_mismatch", turn_id)


def _record_key(
    *,
    identity: MemoryRuntimeIdentity,
    payload_kind: str,
    record_id: str,
) -> str:
    normalized_kind = _require_non_blank(payload_kind, field_name="payload_kind")
    normalized_record_id = _require_non_blank(record_id, field_name="record_id")
    identity_digest = hashlib.sha256(
        "\x1f".join(
            [
                identity.story_id,
                identity.session_id,
                identity.branch_head_id,
                identity.turn_id,
                identity.runtime_profile_snapshot_id,
                normalized_kind,
                normalized_record_id,
            ]
        ).encode("utf-8")
    ).hexdigest()[:20]
    return f"revision_overlay_{normalized_kind}_{identity_digest}_{normalized_record_id}"


def _record_version(material: RuntimeWorkspaceMaterial) -> int:
    version = material.material_id.rsplit("_v", 1)[-1]
    if version.isdecimal():
        return int(version)
    return 0


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
