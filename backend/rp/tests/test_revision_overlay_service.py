"""Focused tests for R2 review overlay persistence and inspection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlmodel import Session

from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.revision_overlay_contracts import (
    ReviewOverlayRecord,
    RevisionAnchorRef,
    RevisionCommentRecord,
)
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.draft_materialization_service import DraftMaterializationService
from rp.services.revision_overlay_service import (
    RevisionOverlayService,
    RevisionOverlayServiceError,
)
from rp.services.runtime_workspace_material_service import RuntimeWorkspaceMaterialService
from services.database import get_engine


def test_overlay_persists_under_exact_identity_and_inspects_later(retrieval_session):
    identity = _identity()
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:persist")

    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        instruction_text="Make the opening less abrupt.",
        selected_excerpt=draft.blocks[0].selected_excerpt,
    )
    tracked_change = service.add_tracked_change(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        change_kind="replace",
        original_text="The storm arrived at dusk.",
        suggested_text="The storm reached the valley at dusk.",
    )
    retrieval_session.commit()

    with Session(get_engine()) as later_session:
        later_service = RevisionOverlayService(session=later_session)
        inspection = later_service.inspect_overlay(
            identity=identity,
            overlay_id=overlay.overlay_id,
        )

    assert inspection.overlay.overlay_id == overlay.overlay_id
    assert inspection.overlay.draft_document_id == draft.draft_document_id
    assert inspection.overlay.comment_refs == [comment.comment_id]
    assert inspection.overlay.tracked_change_refs == [tracked_change.tracked_change_id]
    assert inspection.comments == [comment]
    assert inspection.tracked_changes == [tracked_change]
    assert inspection.active_comment_refs == [comment.comment_id]
    assert inspection.active_tracked_change_refs == [tracked_change.tracked_change_id]
    assert inspection.metadata_json["read_only"] is True


def test_comment_and_tracked_change_reject_anchors_outside_current_draft(
    retrieval_session,
):
    identity = _identity(turn_id="turn-anchor")
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:anchor")
    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    missing_anchor = _anchor("draftblk_missing")

    with pytest.raises(RevisionOverlayServiceError) as comment_exc:
        service.add_comment(
            identity=identity,
            overlay_id=overlay.overlay_id,
            anchor_ref=missing_anchor,
            instruction_text="Point at a missing paragraph.",
        )
    assert comment_exc.value.code == "revision_anchor_block_not_found"

    with pytest.raises(RevisionOverlayServiceError) as tracked_exc:
        service.add_tracked_change(
            identity=identity,
            overlay_id=overlay.overlay_id,
            anchor_ref=missing_anchor,
            change_kind="delete",
            original_text="Missing.",
        )
    assert tracked_exc.value.code == "revision_anchor_block_not_found"


def test_suggesting_creates_review_sidecars_without_truth_or_rewrite_refs(
    retrieval_session,
):
    identity = _identity(turn_id="turn-suggesting")
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:suggest")
    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )

    service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        instruction_text="Tighten this sentence.",
    )
    service.add_tracked_change(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        change_kind="insert",
        suggested_text="A lantern flickered nearby.",
    )

    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
        domain="chapter",
    )

    assert {material.payload["payload_kind"] for material in materials} == {
        "draft_document",
        "review_overlay",
        "revision_comment",
        "tracked_change",
    }
    for material in materials:
        assert material.metadata["source_of_truth"] is False
        assert material.metadata["core_state_truth"] is False
        assert material.metadata["recall_truth"] is False
        assert material.metadata["archival_truth"] is False
        assert material.payload["canonical_truth"] is False
        assert material.payload["rewrite_request_ref"] is None
        assert material.payload["rewrite_instruction_ref"] is None


def test_editing_overlay_does_not_create_llm_rewrite_instruction(
    retrieval_session,
):
    identity = _identity(turn_id="turn-editing")
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:editing")

    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="editing",
    )
    inspection = service.inspect_overlay(
        identity=identity,
        overlay_id=overlay.overlay_id,
    )

    assert inspection.overlay.mode == "editing"
    assert inspection.overlay.comment_refs == []
    assert inspection.overlay.tracked_change_refs == []
    assert inspection.overlay.metadata_json["rewrite_request_ref"] is None
    assert inspection.overlay.metadata_json["rewrite_instruction_ref"] is None


def test_same_draft_and_mode_ensure_is_idempotent(retrieval_session):
    identity = _identity(turn_id="turn-idempotent")
    service = RevisionOverlayService(session=retrieval_session)
    draft = DraftMaterializationService().materialize_draft(
        identity=identity,
        draft_ref="draft:r2:idempotent",
        source_output_ref="artifact:turn-idempotent",
        output_text="The storm arrived at dusk.\n\nMira kept walking.",
        source_format="markdown",
    )

    first_draft = service.record_draft_document(
        identity=identity,
        draft_document=draft,
    )
    first_overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=first_draft.draft_document_id,
        mode="viewing",
    )
    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    initial_material_ids = {
        material.material_id
        for material in material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            domain="chapter",
        )
    }

    second_draft = service.record_draft_document(
        identity=identity,
        draft_document=draft,
    )
    second_overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="viewing",
    )
    later_material_ids = {
        material.material_id
        for material in material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            domain="chapter",
        )
    }

    assert second_draft == first_draft
    assert second_overlay == first_overlay
    assert later_material_ids == initial_material_ids


def test_resolve_and_delete_comment_lifecycle_keeps_debug_tombstone(
    retrieval_session,
):
    identity = _identity(turn_id="turn-lifecycle")
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:lifecycle")
    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    comment = service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=_anchor(draft.blocks[0].block_id),
        instruction_text="Resolve then delete this.",
    )

    resolved = service.resolve_comment(identity=identity, comment_id=comment.comment_id)
    deleted = service.delete_comment(identity=identity, comment_id=comment.comment_id)
    inspection = service.inspect_overlay(
        identity=identity,
        overlay_id=overlay.overlay_id,
    )

    assert resolved.status == "resolved"
    assert deleted.status == "deleted"
    assert [item.comment_id for item in inspection.comments] == [comment.comment_id]
    assert inspection.comments[0].status == "deleted"
    assert inspection.active_comment_refs == []


def test_superdoc_id_stays_adapter_metadata_not_runtime_truth_id(retrieval_session):
    identity = _identity(turn_id="turn-superdoc")
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:superdoc")
    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )
    superdoc_anchor_id = "superdoc-comment-anchor-1"

    comment = service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        anchor_ref=RevisionAnchorRef(
            anchor_scope="single_block",
            block_ids=[draft.blocks[0].block_id],
            superdoc_anchor_id=superdoc_anchor_id,
        ),
        instruction_text="Adapter metadata only.",
    )
    inspection = service.inspect_overlay(
        identity=identity,
        overlay_id=overlay.overlay_id,
    )

    assert comment.anchor_ref.superdoc_anchor_id == superdoc_anchor_id
    assert superdoc_anchor_id not in comment.comment_id
    assert superdoc_anchor_id not in overlay.overlay_id
    assert all(superdoc_anchor_id not in ref for ref in inspection.material_refs)
    assert inspection.comments[0].anchor_ref.superdoc_anchor_id == superdoc_anchor_id


def test_overlay_reads_are_isolated_by_full_runtime_identity(retrieval_session):
    identity = _identity(turn_id="turn-isolation")
    other_branch_identity = _identity(
        turn_id="turn-isolation",
        branch_head_id="branch-other",
    )
    service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(service, identity=identity, draft_ref="draft:r2:isolation")
    overlay = service.create_or_update_overlay(
        identity=identity,
        draft_document_id=draft.draft_document_id,
        mode="suggesting",
    )

    assert service.list_overlays(identity=identity) == [overlay]
    assert service.list_overlays(identity=other_branch_identity) == []
    with pytest.raises(RevisionOverlayServiceError) as exc:
        service.inspect_overlay(
            identity=other_branch_identity,
            overlay_id=overlay.overlay_id,
        )
    assert exc.value.code == "revision_overlay_not_found"


def test_same_draft_document_id_can_materialize_on_different_branches(
    retrieval_session,
):
    identity = _identity(turn_id="turn-same-draft")
    other_branch_identity = _identity(
        turn_id="turn-same-draft",
        branch_head_id="branch-other",
    )
    service = RevisionOverlayService(session=retrieval_session)

    first = _record_draft(service, identity=identity, draft_ref="draft:r2:same")
    second = _record_draft(
        service,
        identity=other_branch_identity,
        draft_ref="draft:r2:same",
    )

    assert first.draft_document_id == second.draft_document_id
    assert service.find_draft_document_by_ref(
        identity=identity,
        draft_ref="draft:r2:same",
    ) == first
    assert service.find_draft_document_by_ref(
        identity=other_branch_identity,
        draft_ref="draft:r2:same",
    ) == second


def test_revision_overlay_dtos_use_factory_defaults_not_shared_mutable_state():
    first = ReviewOverlayRecord(
        overlay_id="overlay-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        mode="suggesting",
    )
    second = ReviewOverlayRecord(
        overlay_id="overlay-2",
        turn_id="turn-1",
        draft_ref="draft-2",
        draft_document_id="doc-2",
        mode="viewing",
    )
    first.comment_refs.append("comment-1")
    first.metadata_json["marker"] = "first"

    assert second.comment_refs == []
    assert second.metadata_json == {}

    first_comment = RevisionCommentRecord(
        comment_id="comment-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        overlay_id="overlay-1",
        anchor_ref=_anchor("block-1"),
        instruction_text="Keep separate.",
    )
    second_comment = RevisionCommentRecord(
        comment_id="comment-2",
        turn_id="turn-1",
        draft_ref="draft-1",
        overlay_id="overlay-1",
        anchor_ref=_anchor("block-1"),
        instruction_text="Also separate.",
    )
    first_comment.metadata_json["marker"] = "first"

    assert second_comment.metadata_json == {}


def test_anchor_contract_rejects_empty_or_invalid_inline_shape():
    with pytest.raises(ValidationError):
        RevisionAnchorRef(anchor_scope="single_block", block_ids=[])

    with pytest.raises(ValidationError, match="exactly one"):
        RevisionAnchorRef(
            anchor_scope="inline",
            block_ids=["block-1", "block-2"],
        )

    with pytest.raises(ValidationError, match="end_offset"):
        RevisionAnchorRef(
            anchor_scope="single_block",
            block_ids=["block-1"],
            start_offset=10,
            end_offset=1,
        )


def _record_draft(
    service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
):
    draft = DraftMaterializationService().materialize_draft(
        identity=identity,
        draft_ref=draft_ref,
        source_output_ref=f"artifact:{identity.turn_id}",
        output_text="The storm arrived at dusk.\n\nMira kept walking.",
        source_format="markdown",
    )
    return service.record_draft_document(identity=identity, draft_document=draft)


def _anchor(block_id: str) -> RevisionAnchorRef:
    return RevisionAnchorRef(
        anchor_scope="single_block",
        block_ids=[block_id],
        start_offset=0,
        end_offset=5,
    )


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-r2"),
        session_id=overrides.get("session_id", "session-r2"),
        branch_head_id=overrides.get("branch_head_id", "branch-r2"),
        turn_id=overrides.get("turn_id", "turn-r2"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-r2",
        ),
    )
