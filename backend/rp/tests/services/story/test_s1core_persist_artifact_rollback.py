"""Oracle node-5 Tier-A: WRK-004 single-transaction atomicity (C4).

Atomicity [WRK-004]: ``StoryTurnDomainService.persist_generated_artifact`` writes
the artifact, its two creation-time obligation jobs, and the turn-status flip in a
SINGLE transaction with one ``commit()`` at the end
(backend/rp/services/story/turn_domain_service.py:1632). If anything fails before
that commit, the whole unit must roll back: no artifact may exist without its two
obligation jobs, and the turn must stay pre-completion.

Injection seam: the STORY_SEGMENT path calls
``self._projection_state_service.append_recent_segment`` at line 1628 — AFTER the
obligations are flushed (line 1609) and BEFORE the single commit (line 1632). We
monkeypatch that call to raise, then roll back and assert the artifact + jobs +
status flip all reverted together. The intake identity is committed first so the
turn itself survives the rollback in its pre-write ``started`` state.

This is a service-level oracle (NOT graph/API).
"""

from __future__ import annotations

import pytest

from models.rp_story_store import StoryTurnRecord
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.story.runtime import (
    LongformTurnCommandKind,
    LongformTurnRequest,
    OrchestratorPlan,
    SpecialistResultBundle,
    StoryArtifactKind,
)
from rp.models.writer.writing_worker_contracts import WritingWorkerExecutionResult
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workflow_job_service import RuntimeWorkflowJobService
from rp.services.runtime.workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.tests.services.projection.test_projection_builder_services import (
    _build_turn_domain_service,
    _seed_story_runtime,
)


def test_c4_persist_generated_artifact_rolls_back_atomically(
    retrieval_session,
    monkeypatch,
) -> None:
    session, chapter, service = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.wrk004.rollback",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    runtime_identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    # Commit the intake so the turn survives the later rollback (pre-completion).
    retrieval_session.commit()

    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    turn_domain_service = _build_turn_domain_service(
        service,
        runtime_identity_service=identity_service,
        runtime_workspace_material_service=material_service,
    )
    bundle = SpecialistResultBundle(
        foundation_digest=["Found A"],
        blueprint_digest=["Blueprint A"],
        current_outline_digest=["Outline A"],
        recent_segment_digest=["Segment A"],
        current_state_digest=["State A"],
        writer_hints=["Hint A"],
    )
    plan = OrchestratorPlan(
        output_kind=StoryArtifactKind.STORY_SEGMENT,
        writer_instruction="Write the next segment.",
    )
    packet = turn_domain_service.build_packet(
        session_id=session.session_id,
        plan=plan,
        specialist_bundle=bundle,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
        runtime_identity=runtime_identity,
    )

    # Inject failure AFTER obligations (1609) and BEFORE the single commit (1632).
    def _boom(*_args, **_kwargs):
        raise RuntimeError("injected pre-commit failure")

    monkeypatch.setattr(
        turn_domain_service._projection_state_service,
        "append_recent_segment",
        _boom,
    )

    with pytest.raises(RuntimeError, match="injected pre-commit failure"):
        turn_domain_service.persist_generated_artifact(
            request=LongformTurnRequest(
                session_id=session.session_id,
                command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
                model_id="model",
            ),
            packet=packet,
            plan=plan,
            writing_result=WritingWorkerExecutionResult(
                request_id="writer-exec-c4",
                packet_id=packet.packet_id,
                turn_id=runtime_identity.turn_id,
                operation_mode="writing",
                output_text="Generated segment text.",
                output_kind=plan.output_kind.value,
                usage_metadata={"total_tokens": 30},
            ),
            specialist_bundle=bundle,
            pending_artifact_id=None,
        )

    retrieval_session.rollback()

    # The turn survives but stays pre-completion (no writer-finalize flip).
    turn = retrieval_session.get(StoryTurnRecord, runtime_identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.STARTED.value
    assert turn.writer_completed_at is None

    # No obligation jobs persisted (artifact never exists without its 2 jobs).
    jobs = RuntimeWorkflowJobService(retrieval_session).list_jobs_for_turn(
        turn_id=runtime_identity.turn_id
    )
    assert jobs == []

    # No STORY_SEGMENT artifact persisted.
    artifacts = service.list_artifacts(
        chapter_workspace_id=chapter.chapter_workspace_id
    )
    segment_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
    ]
    assert segment_artifacts == []
