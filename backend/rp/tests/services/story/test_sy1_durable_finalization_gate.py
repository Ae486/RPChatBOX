"""S-Y1 oracle: durable turn-level RET-005 finalization gate (service-level).

The in-flight harness guard already rejects a usage-missing writer turn before
persist; this durable gate is the deterministic-layer (RET-003) backstop at the
TURN-008 visibility boundary. These oracles drive
``StoryTurnDomainService.persist_generated_artifact`` directly with a crafted
``WritingWorkerExecutionResult.retrieval_usage_ledger`` (plus, where needed, a
seeded usage record), so they exercise the durable gate without a real harness
run.

Falsifiable, deterministic, L1 (no network / no keys).
"""

from __future__ import annotations

import pytest

from models.rp_story_store import StoryTurnRecord
from rp.models.memory.contract_registry import MemoryRuntimeIdentity
from rp.models.retrieval.runtime_contracts import RetrievalUsageLedgerSnapshot
from rp.models.runtime.identity import StoryTurnStatus
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialVisibility,
)
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
from rp.services.story.turn_domain_service import WriterFinalizationRejected
from rp.tests.services.projection.test_projection_builder_services import (
    _build_turn_domain_service,
    _seed_story_runtime,
)


USAGE_REQUIRED_CODE = "writer_retrieval_usage_required_before_final_output"
KIND_MISMATCH_CODE = "writer_retrieval_usage_record_kind_mismatch"


class _Prepared:
    def __init__(
        self,
        *,
        session,
        chapter,
        service,
        material_service,
        turn_domain_service,
        runtime_identity,
        plan,
        bundle,
        packet,
    ) -> None:
        self.session = session
        self.chapter = chapter
        self.service = service
        self.material_service = material_service
        self.turn_domain_service = turn_domain_service
        self.runtime_identity = runtime_identity
        self.plan = plan
        self.bundle = bundle
        self.packet = packet


def _prepare_segment_turn(retrieval_session) -> _Prepared:
    session, chapter, service = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.sy1.gate",
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
    return _Prepared(
        session=session,
        chapter=chapter,
        service=service,
        material_service=material_service,
        turn_domain_service=turn_domain_service,
        runtime_identity=runtime_identity,
        plan=plan,
        bundle=bundle,
        packet=packet,
    )


def _gate_identity(packet, fallback: MemoryRuntimeIdentity) -> MemoryRuntimeIdentity:
    # Mirror StoryTurnDomainService._packet_runtime_identity so seeded materials
    # share the identity the gate reads.
    if packet.identity is not None:
        return packet.identity
    payload = packet.metadata.get("runtime_identity")
    if isinstance(payload, dict):
        return MemoryRuntimeIdentity.model_validate(payload)
    return fallback


def _seed_material(
    material_service: RuntimeWorkspaceMaterialService,
    identity: MemoryRuntimeIdentity,
    *,
    material_id: str,
    kind: RuntimeWorkspaceMaterialKind,
    short_id: str,
) -> None:
    material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id=material_id,
            material_kind=kind,
            identity=identity,
            domain="chapter",
            domain_path="chapter.runtime.retrieval.usage",
            short_id=short_id,
            payload={},
            visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
            created_by="test.sy1.seed",
        )
    )


def _persist(prepared: _Prepared, ledger: RetrievalUsageLedgerSnapshot | None):
    return prepared.turn_domain_service.persist_generated_artifact(
        request=LongformTurnRequest(
            session_id=prepared.session.session_id,
            command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT,
            model_id="model",
        ),
        packet=prepared.packet,
        plan=prepared.plan,
        writing_result=WritingWorkerExecutionResult(
            request_id="writer-exec-sy1",
            packet_id=prepared.packet.packet_id,
            turn_id=prepared.runtime_identity.turn_id,
            operation_mode="writing",
            output_text="Generated segment text.",
            output_kind=prepared.plan.output_kind.value,
            usage_metadata={"total_tokens": 30},
            retrieval_usage_ledger=ledger,
        ),
        specialist_bundle=prepared.bundle,
        pending_artifact_id=None,
    )


def _segment_artifacts(prepared: _Prepared):
    return [
        artifact
        for artifact in prepared.service.list_artifacts(
            chapter_workspace_id=prepared.chapter.chapter_workspace_id
        )
        if artifact.artifact_kind == StoryArtifactKind.STORY_SEGMENT
    ]


def test_sy1_reject_on_retrieval_without_usage(retrieval_session) -> None:
    prepared = _prepare_segment_turn(retrieval_session)
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=1,
        usage_generation=0,
        usage_material_id=None,
    )

    with pytest.raises(WriterFinalizationRejected) as excinfo:
        _persist(prepared, ledger)

    assert excinfo.value.reason_code == USAGE_REQUIRED_CODE

    turn = retrieval_session.get(StoryTurnRecord, prepared.runtime_identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.FAILED.value
    assert turn.status != StoryTurnStatus.POST_WRITE_PENDING.value
    assert turn.visible_output_ref is None


def test_sy1_settle_on_usage_present(retrieval_session) -> None:
    prepared = _prepare_segment_turn(retrieval_session)
    identity = _gate_identity(prepared.packet, prepared.runtime_identity)
    _seed_material(
        prepared.material_service,
        identity,
        material_id="retrieval_usage_present",
        kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
        short_id="U1",
    )
    retrieval_session.commit()
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=1,
        usage_generation=1,
        usage_material_id="retrieval_usage_present",
    )

    response = _persist(prepared, ledger)

    assert response.artifact_id
    turn = retrieval_session.get(StoryTurnRecord, prepared.runtime_identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.POST_WRITE_PENDING.value
    assert turn.visible_output_ref is not None


def test_sy1_no_retrieval_passthrough(retrieval_session) -> None:
    prepared = _prepare_segment_turn(retrieval_session)
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=0,
        usage_generation=0,
        usage_material_id=None,
    )

    response = _persist(prepared, ledger)

    assert response.artifact_id
    turn = retrieval_session.get(StoryTurnRecord, prepared.runtime_identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.POST_WRITE_PENDING.value
    assert turn.visible_output_ref is not None


def test_sy1_usage_kind_mismatch_rejects(retrieval_session) -> None:
    prepared = _prepare_segment_turn(retrieval_session)
    identity = _gate_identity(prepared.packet, prepared.runtime_identity)
    # The referenced usage material exists but is the WRONG kind.
    _seed_material(
        prepared.material_service,
        identity,
        material_id="retrieval_card_not_usage",
        kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
        short_id="R1",
    )
    retrieval_session.commit()
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=1,
        usage_generation=1,
        usage_material_id="retrieval_card_not_usage",
    )

    with pytest.raises(WriterFinalizationRejected) as excinfo:
        _persist(prepared, ledger)

    assert excinfo.value.reason_code == KIND_MISMATCH_CODE
    turn = retrieval_session.get(StoryTurnRecord, prepared.runtime_identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.FAILED.value


def test_sy1_reject_is_transaction_atomic(retrieval_session) -> None:
    prepared = _prepare_segment_turn(retrieval_session)
    ledger = RetrievalUsageLedgerSnapshot(
        retrieval_generation=2,
        usage_generation=1,
        usage_material_id="retrieval_usage_stale",
    )

    with pytest.raises(WriterFinalizationRejected) as excinfo:
        _persist(prepared, ledger)

    assert excinfo.value.reason_code == USAGE_REQUIRED_CODE

    # Fresh read after the committed FAILED flip: none of the writer-output
    # writes survived the rollback (R1).
    retrieval_session.expire_all()
    turn = retrieval_session.get(StoryTurnRecord, prepared.runtime_identity.turn_id)
    assert turn is not None
    assert turn.status == StoryTurnStatus.FAILED.value
    assert turn.failure_reason == USAGE_REQUIRED_CODE
    assert turn.visible_output_ref is None

    jobs = RuntimeWorkflowJobService(retrieval_session).list_jobs_for_turn(
        turn_id=prepared.runtime_identity.turn_id
    )
    assert jobs == []

    assert _segment_artifacts(prepared) == []
