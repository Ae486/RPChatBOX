"""Focused tests for R2 light review overlay persistence and inspection."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.core_state.revision_overlay_contracts import (
    ReviewOverlayRecord,
    RevisionCommentRecord,
)
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.services.core_state.revision_overlay_service import (
    RevisionOverlayService,
    RevisionOverlayServiceError,
)
from rp.services.runtime.workspace_material_service import RuntimeWorkspaceMaterialService
from services.database import get_engine


def test_overlay_persists_under_exact_identity_and_inspects_later(retrieval_session):
    identity = _identity()
    service = RevisionOverlayService(session=retrieval_session)
    overlay = _ensure_overlay(service, identity=identity, draft_ref="artifact:r2:persist")

    comment = service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Make the opening less abrupt.",
        selected_excerpt="The storm arrived at dusk.",
    )
    retrieval_session.commit()

    with Session(get_engine()) as later_session:
        later_service = RevisionOverlayService(session=later_session)
        inspection = later_service.inspect_overlay(
            identity=identity,
            overlay_id=overlay.overlay_id,
        )

    assert inspection.overlay.overlay_id == overlay.overlay_id
    assert inspection.overlay.draft_document_id == overlay.draft_document_id
    assert inspection.overlay.comment_refs == [comment.comment_id]
    assert inspection.comments == [comment]
    assert inspection.active_comment_refs == [comment.comment_id]
    assert inspection.tracked_changes == []
    assert inspection.active_tracked_change_refs == []
    assert inspection.metadata_json["read_only"] is True


def test_comment_requires_selected_excerpt_light_anchor(retrieval_session):
    # Ruling A: the excerpt is the sole comment anchor; block anchors are retired.
    identity = _identity(turn_id="turn-anchor")
    service = RevisionOverlayService(session=retrieval_session)
    overlay = _ensure_overlay(service, identity=identity, draft_ref="artifact:r2:anchor")

    with pytest.raises(ValueError):
        service.add_comment(
            identity=identity,
            overlay_id=overlay.overlay_id,
            instruction_text="Missing the required excerpt anchor.",
            selected_excerpt="   ",
        )


def test_light_comment_creates_review_sidecars_without_truth_or_rewrite_refs(
    retrieval_session,
):
    identity = _identity(turn_id="turn-sidecar")
    service = RevisionOverlayService(session=retrieval_session)
    overlay = _ensure_overlay(service, identity=identity, draft_ref="artifact:r2:sidecar")

    service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Tighten this sentence.",
        selected_excerpt="The storm arrived at dusk.",
    )

    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
        domain="chapter",
    )

    # No draft_document (materialization retired) and no tracked_change sidecars.
    assert {material.payload["payload_kind"] for material in materials} == {
        "review_overlay",
        "revision_comment",
    }
    for material in materials:
        assert material.metadata["source_of_truth"] is False
        assert material.metadata["core_state_truth"] is False
        assert material.metadata["recall_truth"] is False
        assert material.metadata["archival_truth"] is False
        assert material.payload["canonical_truth"] is False
        assert material.payload["rewrite_request_ref"] is None
        assert material.payload["rewrite_instruction_ref"] is None


def test_editing_overlay_does_not_create_llm_rewrite_instruction(retrieval_session):
    identity = _identity(turn_id="turn-editing")
    service = RevisionOverlayService(session=retrieval_session)
    overlay = _ensure_overlay(
        service,
        identity=identity,
        draft_ref="artifact:r2:editing",
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


def test_suggesting_mode_is_unsupported(retrieval_session):
    identity = _identity(turn_id="turn-suggesting")
    service = RevisionOverlayService(session=retrieval_session)

    with pytest.raises(ValueError):
        service.create_or_update_overlay(
            identity=identity,
            draft_ref="artifact:r2:suggesting",
            mode="suggesting",
        )


def test_same_draft_and_mode_ensure_is_idempotent(retrieval_session):
    identity = _identity(turn_id="turn-idempotent")
    service = RevisionOverlayService(session=retrieval_session)
    draft_ref = "artifact:r2:idempotent"

    first_overlay = service.create_or_update_overlay(
        identity=identity,
        draft_ref=draft_ref,
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

    second_overlay = service.create_or_update_overlay(
        identity=identity,
        draft_ref=draft_ref,
        mode="viewing",
    )
    later_materials = material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
        domain="chapter",
    )
    later_material_ids = {material.material_id for material in later_materials}

    assert second_overlay == first_overlay
    assert later_material_ids == initial_material_ids
    # The light surface never materializes a draft document to satisfy idempotency.
    assert {material.payload["payload_kind"] for material in later_materials} == {
        "review_overlay"
    }


def test_resolve_and_delete_comment_lifecycle_keeps_debug_tombstone(
    retrieval_session,
):
    identity = _identity(turn_id="turn-lifecycle")
    service = RevisionOverlayService(session=retrieval_session)
    overlay = _ensure_overlay(
        service, identity=identity, draft_ref="artifact:r2:lifecycle"
    )
    comment = service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Resolve then delete this.",
        selected_excerpt="The storm arrived at dusk.",
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
    overlay = _ensure_overlay(
        service, identity=identity, draft_ref="artifact:r2:superdoc"
    )
    superdoc_anchor_id = "superdoc-comment-anchor-1"

    comment = service.add_comment(
        identity=identity,
        overlay_id=overlay.overlay_id,
        instruction_text="Adapter metadata only.",
        selected_excerpt="The storm arrived at dusk.",
        superdoc_anchor_id=superdoc_anchor_id,
    )
    inspection = service.inspect_overlay(
        identity=identity,
        overlay_id=overlay.overlay_id,
    )

    # Editor id is stored as adapter metadata and never promoted into runtime ids.
    assert comment.metadata_json["superdoc_anchor_id"] == superdoc_anchor_id
    assert superdoc_anchor_id not in comment.comment_id
    assert superdoc_anchor_id not in overlay.overlay_id
    assert superdoc_anchor_id not in identity.story_id
    assert superdoc_anchor_id not in identity.session_id
    assert superdoc_anchor_id not in identity.branch_head_id
    assert superdoc_anchor_id not in identity.turn_id
    assert superdoc_anchor_id not in identity.runtime_profile_snapshot_id
    assert all(superdoc_anchor_id not in ref for ref in inspection.material_refs)
    assert (
        inspection.comments[0].metadata_json["superdoc_anchor_id"]
        == superdoc_anchor_id
    )


def test_overlay_reads_are_isolated_by_full_runtime_identity(retrieval_session):
    identity = _identity(turn_id="turn-isolation")
    other_branch_identity = _identity(
        turn_id="turn-isolation",
        branch_head_id="branch-other",
    )
    service = RevisionOverlayService(session=retrieval_session)
    overlay = _ensure_overlay(
        service, identity=identity, draft_ref="artifact:r2:isolation"
    )

    assert service.list_overlays(identity=identity) == [overlay]
    assert service.list_overlays(identity=other_branch_identity) == []
    with pytest.raises(RevisionOverlayServiceError) as exc:
        service.inspect_overlay(
            identity=other_branch_identity,
            overlay_id=overlay.overlay_id,
        )
    assert exc.value.code == "revision_overlay_not_found"


def test_revision_overlay_dtos_use_factory_defaults_not_shared_mutable_state():
    first = ReviewOverlayRecord(
        overlay_id="overlay-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        mode="editing",
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
        selected_excerpt="Keep separate.",
        instruction_text="Keep separate.",
    )
    second_comment = RevisionCommentRecord(
        comment_id="comment-2",
        turn_id="turn-1",
        draft_ref="draft-1",
        overlay_id="overlay-1",
        selected_excerpt="Also separate.",
        instruction_text="Also separate.",
    )
    first_comment.metadata_json["marker"] = "first"

    assert second_comment.metadata_json == {}
    assert first_comment.anchor_ref is None
    assert second_comment.anchor_ref is None


def _ensure_overlay(
    service: RevisionOverlayService,
    *,
    identity: MemoryRuntimeIdentity,
    draft_ref: str,
    mode: str = "viewing",
) -> ReviewOverlayRecord:
    return service.create_or_update_overlay(
        identity=identity,
        draft_ref=draft_ref,
        mode=mode,
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
