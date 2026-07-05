"""S6-6 O-5 oracle: the three revision sidecars carry distinguishable kinds.

Live invariants under test:
  * O-5      selection receipt / adoption receipt / rewrite candidate are three
             distinct Runtime Workspace material kinds; none of them hides under
             the shared REVIEW_OVERLAY / WORKER_CANDIDATE overloading anymore.
  * WRK-005  each sidecar is independently queryable by kind, and rolling back
             (invalidating) one kind does not hide the other two.
  * REV-017  every sidecar stays runtime workspace material, never Core/accepted
             truth.
  * REV-019  the debug read side groups the three kinds separately; rewrite
             candidates are no longer mixed into the memory-worker candidate
             group.
"""

from __future__ import annotations

from uuid import uuid4

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.core_state.revision_overlay_contracts import RewriteRequest
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
)
from rp.models.writer.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story.runtime_debug_query_service import (
    StoryRuntimeDebugQueryService,
)
from rp.services.writer.draft_selection_service import DraftSelectionService
from rp.services.writer.rewrite_candidate_service import RewriteCandidateService


def test_s6_6_o5_revision_sidecar_kinds_are_distinct_and_independently_readable(
    retrieval_session,
):
    identity = _identity(turn_id="turn-s66-o5")
    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)

    # Production write paths for the three sidecars (no hand-rolled materials).
    candidate = RewriteCandidateService(
        session=retrieval_session,
    ).create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=_rewrite_request(identity, draft_ref="draft:s66:o5"),
        writer_result=_writer_result(
            identity=identity,
            output_text="Rewrite candidate text.",
        ),
    )
    selection_service = DraftSelectionService(session=retrieval_session)
    selection = selection_service.select_candidate(
        identity=identity,
        turn_id=identity.turn_id,
        draft_ref=candidate.draft_ref,
        candidate_output_refs=[candidate.candidate_output_ref],
        selected_output_ref=candidate.candidate_output_ref,
    )
    adoption = selection_service.record_accepted_artifact_adoption_receipt(
        identity=identity,
        accepted_artifact_id="artifact-s66-o5-accepted",
    )
    assert selection.receipt_id != adoption.receipt_id

    # (O-5) Each sidecar is queryable by its own kind and carries that kind.
    rewrite_materials = material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.REWRITE_CANDIDATE,
    )
    selection_materials = material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.SELECTION_RECEIPT,
    )
    adoption_materials = material_service.list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.ADOPTION_RECEIPT,
    )
    assert len(rewrite_materials) == 1
    assert len(selection_materials) == 1
    assert len(adoption_materials) == 1
    assert rewrite_materials[0].payload["payload_kind"] == "rewrite_candidate"
    assert selection_materials[0].payload["payload_kind"] == "draft_selection_receipt"
    assert adoption_materials[0].payload["payload_kind"] == "draft_adoption_receipt"

    sidecars = [rewrite_materials[0], selection_materials[0], adoption_materials[0]]
    assert {material.material_kind for material in sidecars} == {
        RuntimeWorkspaceMaterialKind.REWRITE_CANDIDATE,
        RuntimeWorkspaceMaterialKind.SELECTION_RECEIPT,
        RuntimeWorkspaceMaterialKind.ADOPTION_RECEIPT,
    }

    # (O-5 zero residual) None of the sidecars hides under the old shared kinds.
    overloaded_ids = {
        material.material_id
        for kind in (
            RuntimeWorkspaceMaterialKind.REVIEW_OVERLAY,
            RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
        )
        for material in material_service.list_materials(
            identity=identity,
            material_kind=kind,
        )
    }
    assert overloaded_ids.isdisjoint(
        {material.material_id for material in sidecars}
    )

    # (REV-017) All three stay runtime sidecar material, never truth.
    for material in sidecars:
        assert material.metadata["source_of_truth"] is False
        assert material.payload["canonical_truth"] is False

    # (REV-019) Debug read side groups the three kinds separately, and rewrite
    # candidates no longer land in the memory-worker candidate group.
    debug_items = [
        {
            "material_id": material.material_id,
            "material_kind": material.material_kind.value,
        }
        for material in sidecars
    ]
    groups = StoryRuntimeDebugQueryService._group_materials_by_kind(debug_items)
    assert set(groups) == {
        "rewrite_candidate",
        "selection_receipt",
        "adoption_receipt",
    }
    assert all(len(items) == 1 for items in groups.values())
    summary = StoryRuntimeDebugQueryService._worker_execution_summary(
        turn_trace={"runtime_workspace_materials": debug_items},
        jobs=[],
    )
    assert summary["worker_candidate_materials"] == []
    assert [
        item["material_id"] for item in summary["rewrite_candidate_materials"]
    ] == [rewrite_materials[0].material_id]

    # (WRK-005) Rolling back one kind does not hide the other two kinds.
    material_service.update_lifecycle(
        identity=identity,
        material_id=rewrite_materials[0].material_id,
        lifecycle=RuntimeWorkspaceMaterialLifecycle.INVALIDATED,
        reason="rollback hides the future rewrite candidate",
    )
    assert (
        material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.REWRITE_CANDIDATE,
            lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
        )
        == []
    )
    assert len(
        material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.SELECTION_RECEIPT,
            lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
        )
    ) == 1
    assert len(
        material_service.list_materials(
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.ADOPTION_RECEIPT,
            lifecycle=RuntimeWorkspaceMaterialLifecycle.ACTIVE,
        )
    ) == 1
    assert selection_service.get_latest_adoption_receipt(
        identity=identity,
    ) == adoption


def _rewrite_request(
    identity: MemoryRuntimeIdentity,
    *,
    draft_ref: str,
) -> RewriteRequest:
    return RewriteRequest(
        request_id=f"rewrite_request_{uuid4().hex[:12]}",
        session_id=identity.session_id,
        turn_id=identity.turn_id,
        draft_ref=draft_ref,
        draft_document_id=f"light_draft:{uuid4().hex[:12]}",
        rewrite_scope="full",
        global_instruction="Rewrite this candidate.",
        comment_refs=[],
        metadata_json={
            "story_id": identity.story_id,
            "session_id": identity.session_id,
            "branch_head_id": identity.branch_head_id,
            "turn_id": identity.turn_id,
            "runtime_profile_snapshot_id": identity.runtime_profile_snapshot_id,
        },
    )


def _writer_result(
    *,
    identity: MemoryRuntimeIdentity,
    output_text: str,
) -> WritingWorkerExecutionResult:
    return WritingWorkerExecutionResult(
        request_id=f"writer-request:{identity.turn_id}",
        packet_id=f"packet:{identity.turn_id}",
        turn_id=identity.turn_id,
        operation_mode="rewrite",
        output_text=output_text,
        output_kind="story_segment",
        result_status="completed",
    )


def _identity(**overrides: str) -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id=overrides.get("story_id", "story-s66-o5"),
        session_id=overrides.get("session_id", "session-s66-o5"),
        branch_head_id=overrides.get("branch_head_id", "branch-s66-o5"),
        turn_id=overrides.get("turn_id", "turn-s66-o5"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-s66-o5",
        ),
    )
