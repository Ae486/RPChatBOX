"""Focused tests for R4 full rewrite candidates."""

from __future__ import annotations

import pytest

from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.core_state.revision_overlay_contracts import RewriteCandidateRecord
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.writer.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.setup_agent.draft_materialization_service import DraftMaterializationService
from rp.services.core_state.revision_overlay_service import RevisionOverlayService
from rp.services.writer.rewrite_candidate_service import (
    RewriteCandidateService,
    RewriteCandidateServiceError,
)
from rp.services.writer.rewrite_request_builder_service import RewriteRequestBuilderService
from rp.services.runtime.workspace_material_service import RuntimeWorkspaceMaterialService


def test_full_rewrite_candidate_is_saved_without_auto_adoption(retrieval_session):
    identity = _identity(turn_id="turn-r4-full")
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:full",
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction="Rewrite with quieter tension.",
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )

    candidate = candidate_service.create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(
            identity=identity,
            output_text="The rain softened the city into a hush.",
        ),
    )

    assert candidate.rewrite_scope == "full"
    assert candidate.full_output_text == "The rain softened the city into a hush."
    assert candidate.candidate_draft_text == candidate.full_output_text
    assert candidate.selected_output_ref is None
    assert candidate.adopted_output_ref is None
    assert candidate.canonical_truth is False
    assert candidate.metadata_json["canonical_truth"] is False
    assert candidate.metadata_json["story_id"] == identity.story_id
    assert candidate.metadata_json["session_id"] == identity.session_id
    assert candidate.metadata_json["branch_head_id"] == identity.branch_head_id
    assert candidate.metadata_json["turn_id"] == identity.turn_id
    assert (
        candidate.metadata_json["runtime_profile_snapshot_id"]
        == identity.runtime_profile_snapshot_id
    )

    listed = candidate_service.list_candidates(identity=identity)
    assert listed == [candidate]

    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
        domain="chapter",
    )
    assert len(materials) == 1
    assert materials[0].payload["payload_kind"] == "rewrite_candidate"
    assert materials[0].payload["canonical_truth"] is False
    assert materials[0].payload["selected_output_ref"] is None
    assert materials[0].payload["adopted_output_ref"] is None
    assert materials[0].metadata["source_of_truth"] is False


def test_candidate_list_is_isolated_by_full_runtime_identity(retrieval_session):
    identity = _identity(turn_id="turn-r4-isolation")
    other_branch_identity = _identity(
        turn_id="turn-r4-isolation",
        branch_head_id="branch-other",
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:isolation",
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction=None,
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )
    candidate = candidate_service.create_full_rewrite_candidate(
        identity=identity,
        rewrite_request=request,
        writer_result=_writer_result(identity=identity, output_text="Branch A draft."),
    )

    assert candidate_service.list_candidates(identity=identity) == [candidate]
    assert candidate_service.list_candidates(identity=other_branch_identity) == []


def test_candidate_creation_rejects_cross_branch_request_reuse(retrieval_session):
    identity = _identity(turn_id="turn-r4-request-identity")
    other_branch_identity = _identity(
        turn_id="turn-r4-request-identity",
        branch_head_id="branch-r4-other",
    )
    overlay_service = RevisionOverlayService(session=retrieval_session)
    draft = _record_draft(
        overlay_service,
        identity=identity,
        draft_ref="draft:r4:request-identity",
    )
    _record_draft(
        overlay_service,
        identity=other_branch_identity,
        draft_ref=draft.draft_ref,
    )
    request = RewriteRequestBuilderService(
        revision_overlay_service=overlay_service,
    ).build_full_rewrite_request(
        identity=identity,
        draft_ref=draft.draft_ref,
        global_instruction=None,
        comment_refs=[],
        tracked_change_refs=[],
    )
    candidate_service = RewriteCandidateService(
        revision_overlay_service=overlay_service,
        session=retrieval_session,
    )

    with pytest.raises(RewriteCandidateServiceError) as exc:
        candidate_service.create_full_rewrite_candidate(
            identity=other_branch_identity,
            rewrite_request=request,
            writer_result=_writer_result(
                identity=other_branch_identity,
                output_text="Wrong branch draft.",
            ),
        )
    assert exc.value.code == "revision_branch_head_id_mismatch"


def test_candidate_dtos_use_factory_defaults_not_shared_mutable_state():
    first = RewriteCandidateRecord(
        candidate_id="candidate-1",
        candidate_output_ref="candidate-1",
        session_id="session-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        rewrite_request_id="request-1",
        rewrite_scope="full",
        full_output_text="First.",
        candidate_draft_text="First.",
        created_at=_created_at(),
    )
    second = RewriteCandidateRecord(
        candidate_id="candidate-2",
        candidate_output_ref="candidate-2",
        session_id="session-1",
        turn_id="turn-1",
        draft_ref="draft-1",
        draft_document_id="doc-1",
        rewrite_request_id="request-2",
        rewrite_scope="full",
        full_output_text="Second.",
        candidate_draft_text="Second.",
        created_at=_created_at(),
    )
    first.touched_comment_ids.append("comment-1")
    first.metadata_json["marker"] = "first"

    assert second.touched_comment_ids == []
    assert second.metadata_json == {}


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
        output_text=(
            "The storm arrived at dusk.\n\n"
            "Mira kept walking.\n\n"
            "The bell tower answered."
        ),
        source_format="markdown",
    )
    return service.record_draft_document(identity=identity, draft_document=draft)


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
        story_id=overrides.get("story_id", "story-r4"),
        session_id=overrides.get("session_id", "session-r4"),
        branch_head_id=overrides.get("branch_head_id", "branch-r4"),
        turn_id=overrides.get("turn_id", "turn-r4"),
        runtime_profile_snapshot_id=overrides.get(
            "runtime_profile_snapshot_id",
            "snapshot-r4",
        ),
    )


def _created_at():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
