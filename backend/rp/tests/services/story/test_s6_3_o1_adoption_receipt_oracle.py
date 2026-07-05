"""S6-3 O-1 oracle — the single 甲套 adoption receipt is the one live truth pointer.

Deterministic fake-role oracle (HAR-012: no live model, no network, no API key). It
reuses the S-Z1 chapter-close fake-writer harness and drives the REAL flow — 甲套
``accept_pending_segment`` -> continuation packet -> chapter close — to pin the frozen
S6 v1.2 adoption contract as the LIVE guard that lets the retired 乙套 tests go:

  * REV-023  accept marks the artifact ACCEPTED and authors the adoption receipt as ONE
             action on the single 甲套 write gate; 乙套 ``adopt_for_continue`` is retired
             and authors nothing; chapter-close/continuation read that one receipt.
  * REV-004  the next writer turn and chapter close read the adopted draft FROM the
             adoption receipt (receipt_id in continuation source_ref_ids + bridge refs),
             not a merely-selected UI candidate.
  * REV-017  the receipt is an ADOPTION_RECEIPT runtime sidecar, never Core/accepted truth.
  * REV-020  an unadopted draft is not the continuation base; the adopted draft is.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlmodel import select

from models.rp_memory_store import RuntimeWorkspaceMaterialRecord
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.story.runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    LongformTurnRequest,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.models.writer.worker_runtime_contracts import WorkerResultStatus
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.writer.draft_selection_service import (
    DraftSelectionService,
    DraftSelectionServiceError,
)
from rp.services.writer.longform_chapter_runtime_service import (
    LongformChapterRuntimeService,
)
from rp.tests.services.story.test_sz1_chapter_close_job_graph import (
    _FakeGovernanceService,
    _FakeWorkerExecutionService,
    _build_turn_domain_service,
)
from rp.tests.services.writer.test_longform_chapter_runtime_service import (
    _accept_outline,
    _artifact_runtime_metadata,
    _seed_story_runtime,
)


def _resolve(identity_service, snapshot, session, command_kind, actor):
    return identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=command_kind.value,
        actor=actor,
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


def _request(session, command_kind, *, target_artifact_id=None):
    return LongformTurnRequest(
        session_id=session.session_id,
        command_kind=command_kind,
        model_id="model-s6-3-o1",
        provider_id="test-provider",
        target_artifact_id=target_artifact_id,
    )


def _accepted_segment_ids(story_session_service, session, chapter):
    return {
        segment.artifact_id
        for segment in story_session_service.active_branch_accepted_story_segments(
            session_id=session.session_id,
            chapter_index=chapter.chapter_index,
        )
    }


def _adoption_receipt_records(retrieval_session, *, identity):
    records = retrieval_session.exec(
        select(RuntimeWorkspaceMaterialRecord)
        .where(RuntimeWorkspaceMaterialRecord.story_id == identity.story_id)
        .where(RuntimeWorkspaceMaterialRecord.session_id == identity.session_id)
        .where(RuntimeWorkspaceMaterialRecord.branch_head_id == identity.branch_head_id)
    ).all()
    return [
        record
        for record in records
        if record.payload_json.get("payload_kind") == "draft_adoption_receipt"
    ]


@pytest.mark.asyncio
async def test_s6_3_o1_single_accept_adoption_receipt_is_the_one_live_truth_pointer(
    retrieval_session,
):
    story_session_service, session, chapter = _seed_story_runtime(retrieval_session)
    _accept_outline(story_session_service, session, chapter)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="s6.3.o1.oracle",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    ctx = SimpleNamespace(
        service=story_session_service,
        db=retrieval_session,
        identity_service=identity_service,
        workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
    )
    turn_domain_service = _build_turn_domain_service(
        ctx,
        executor=_FakeWorkerExecutionService(result_status=WorkerResultStatus.COMPLETED),
        governance=_FakeGovernanceService(),
    )

    # Stage a pending draft on the first beat (the write turn is still open).
    write_identity = _resolve(
        identity_service,
        snapshot,
        session,
        LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        "s6.3.o1.write",
    )
    pending = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Beat one pending draft awaiting adoption.",
        metadata={
            **_artifact_runtime_metadata(
                story_id=write_identity.story_id,
                session_id=write_identity.session_id,
                branch_head_id=write_identity.branch_head_id,
                turn_id=write_identity.turn_id,
                runtime_profile_snapshot_id=write_identity.runtime_profile_snapshot_id,
            ),
            "target_beat_id": "beat_001",
        },
    )
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        phase=LongformChapterPhase.SEGMENT_REVIEW,
        pending_segment_artifact_id=pending.artifact_id,
    )
    identity_service.update_turn_status(
        turn_id=write_identity.turn_id,
        status=StoryTurnStatus.POST_WRITE_PENDING,
    )

    # (8) REV-020 (before): an unadopted draft is NOT the continuation base.
    assert pending.artifact_id not in _accepted_segment_ids(
        story_session_service, session, chapter
    )

    # 甲套: accept marks ACCEPTED and authors the adoption receipt in one action.
    accept_identity = _resolve(
        identity_service,
        snapshot,
        session,
        LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
        "s6.3.o1.accept",
    )
    accept_response = await turn_domain_service.accept_pending_segment(
        request=_request(
            session,
            LongformTurnCommandKind.ACCEPT_PENDING_SEGMENT,
            target_artifact_id=pending.artifact_id,
        ),
        runtime_identity=accept_identity,
    )
    accepted = story_session_service.get_artifact(pending.artifact_id)
    selection_service = DraftSelectionService(session=retrieval_session)
    receipt = selection_service.get_latest_adoption_receipt_for_branch(
        story_id=accept_identity.story_id,
        session_id=accept_identity.session_id,
        branch_head_id=accept_identity.branch_head_id,
        draft_ref=f"artifact:{accepted.artifact_id}",
    )
    receipt_records = _adoption_receipt_records(retrieval_session, identity=accept_identity)

    # (1) 甲套 accept => ACCEPTED artifact + a receipt whose provenance is the 甲套 path.
    assert accept_response.artifact_id == pending.artifact_id
    assert accepted is not None
    assert accepted.status == StoryArtifactStatus.ACCEPTED
    assert receipt is not None
    assert receipt.draft_ref == f"artifact:{accepted.artifact_id}"
    assert receipt.metadata_json["accept_and_continue"] is True
    assert receipt.metadata_json["adopted_artifact_id"] == accepted.artifact_id

    # (2) Single receipt writer: exactly one adoption receipt, authored by H1.
    assert len(receipt_records) == 1
    assert receipt_records[0].payload_json["record_id"] == receipt.receipt_id
    assert receipt.receipt_id.startswith("draft_adoption_")

    # (5) Q3 raw-ref: adopted_output_ref is the accepted artifact id and it resolves.
    assert receipt.adopted_output_ref == accepted.artifact_id
    resolved_adopted = story_session_service.get_artifact(receipt.adopted_output_ref)
    assert resolved_adopted is not None
    assert resolved_adopted.status == StoryArtifactStatus.ACCEPTED

    # (7) REV-017: the receipt is an ADOPTION_RECEIPT sidecar, never Core/accepted truth.
    assert (
        receipt_records[0].material_kind
        == RuntimeWorkspaceMaterialKind.ADOPTION_RECEIPT.value
    )
    assert receipt.metadata_json["runtime_truth_owner"] == "rp_runtime"
    assert receipt.metadata_json["core_state_truth"] is False
    assert receipt.metadata_json["recall_truth"] is False
    assert receipt.metadata_json["archival_truth"] is False
    assert receipt.metadata_json["superdoc_truth_owner"] is False

    # (8) REV-020 (after): the adopted draft is now the continuation base.
    assert accepted.artifact_id in _accepted_segment_ids(
        story_session_service, session, chapter
    )

    # (6) 乙套 ``adopt_for_continue`` is retired and authors NO receipt.
    with pytest.raises(DraftSelectionServiceError) as adopt_exc:
        selection_service.adopt_for_continue(
            identity=accept_identity,
            turn_id=accept_identity.turn_id,
            draft_ref=f"artifact:{accepted.artifact_id}",
        )
    assert adopt_exc.value.code == "revision_adoption_route_retired"
    assert len(_adoption_receipt_records(retrieval_session, identity=accept_identity)) == 1

    # (4) REV-004: the next writer turn's chapter-progress reads the adopted draft from
    #     the receipt — receipt_id is a continuation source ref (H2b live consumer).
    continuation_identity = _resolve(
        identity_service,
        snapshot,
        session,
        LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        "s6.3.o1.continue",
    )
    continuation_packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=OrchestratorPlan(
            output_kind=StoryArtifactKind.STORY_SEGMENT,
            writer_instruction="Continue after the adopted segment.",
        ),
        specialist_bundle=SpecialistResultBundle(),
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        runtime_identity=continuation_identity,
    )
    chapter_progress = next(
        section
        for section in continuation_packet.mode_sidecar_sections
        if section.label == "chapter_progress"
    )
    assert receipt.receipt_id in chapter_progress.source_ref_ids
    assert chapter_progress.metadata_json["adoption_receipt_id"] == receipt.receipt_id
    assert chapter_progress.metadata_json["latest_accepted_segment_id"] == (
        accepted.artifact_id
    )

    # (3) H2a: the chapter-close else-branch feeds the SAME receipt_id into the bridge
    #     source refs — the adopted draft is read from the receipt, not a UI candidate.
    close_identity = _resolve(
        identity_service,
        snapshot,
        session,
        LongformTurnCommandKind.COMPLETE_CHAPTER,
        "s6.3.o1.close",
    )
    await turn_domain_service.complete_chapter(
        request=_request(session, LongformTurnCommandKind.COMPLETE_CHAPTER),
        runtime_identity=close_identity,
    )
    bridge = LongformChapterRuntimeService(
        story_session_service=story_session_service,
        session=retrieval_session,
    ).get_latest_bridge_material_for_target_chapter(
        story_id=close_identity.story_id,
        session_id=close_identity.session_id,
        branch_head_id=close_identity.branch_head_id,
        target_chapter_index=chapter.chapter_index + 1,
    )
    assert bridge is not None
    _, bridge_material = bridge
    assert receipt.receipt_id in bridge_material.source_refs
    assert receipt.adopted_output_ref in bridge_material.source_refs
