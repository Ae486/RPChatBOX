"""Focused tests for memory debug/eval trace read surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from models.rp_memory_store import (
    MemoryApplyReceiptRecord,
    MemoryChangeEventRecord,
    MemoryProposalRecord,
    RuntimeWorkspaceMaterialRecord,
)
from models.rp_story_store import (
    BranchHeadRecord,
    ChapterWorkspaceRecord,
    StorySessionRecord,
)
from rp.models.core_mutation import (
    CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT,
    CoreMutationEnvelope,
)
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import LongformChapterPhase
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.memory_trace_read_service import MemoryTraceReadService
from rp.services.proposal_repository import ProposalRepository
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService
from services.database import get_engine


@dataclass(frozen=True)
class _SeededTraceEvidence:
    identity: MemoryRuntimeIdentity
    sibling_identity: MemoryRuntimeIdentity
    card_id: str
    usage_id: str
    proposal_id: str
    apply_id: str


def test_turn_trace_joins_exact_identity_evidence(retrieval_session):
    seeded = _seed_trace_evidence(retrieval_session)

    trace = MemoryTraceReadService(session=retrieval_session).get_turn_trace(
        identity=seeded.identity
    )

    assert trace["identity"] == seeded.identity.model_dump(mode="json")
    assert {event["event_kind"] for event in trace["events"]} >= {
        "runtime_workspace_material_recorded",
        "core_authoritative_mutation_applied",
    }
    assert all(
        event["identity"] == seeded.identity.model_dump(mode="json")
        for event in trace["events"]
    )
    assert {item["material_id"] for item in trace["runtime_workspace_materials"]} == {
        seeded.card_id,
        seeded.usage_id,
    }
    assert trace["read_manifests"][0]["writer_usage_refs"] == [seeded.usage_id]
    assert trace["read_manifests"][0]["readback_route"] == "deterministic_rebuild"
    assert trace["proposal_receipts"][0]["proposal"]["proposal_id"] == (
        seeded.proposal_id
    )
    assert trace["proposal_receipts"][0]["apply_receipts"][0]["apply_id"] == (
        seeded.apply_id
    )
    assert trace["retrieval_usage_refs"] == [
        {
            "material_id": seeded.usage_id,
            "short_id": "U1",
            "used_card_material_ids": [seeded.card_id],
            "used_expanded_chunk_material_ids": [],
            "missed_query_material_ids": [],
            "source_refs": [
                {
                    "source_type": "retrieval_card_material",
                    "source_id": seeded.card_id,
                    "layer": "runtime_workspace",
                    "domain": None,
                    "block_id": None,
                    "entry_id": seeded.card_id,
                    "revision": None,
                    "metadata": {"source_of_truth": False},
                }
            ],
        }
    ]
    assert any(
        target["target_kind"] == "projection_refresh_pending"
        for target in trace["dirty_targets"]
    )
    assert trace["metadata"]["event_replay"] is False
    assert trace["metadata"]["mutation_surface"] is False


def test_trace_reads_are_branch_isolated(retrieval_session):
    seeded = _seed_trace_evidence(retrieval_session)
    sibling_identity = seeded.sibling_identity
    material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session,
        memory_change_event_service=MemoryChangeEventService(session=retrieval_session),
    )
    material_service.record_material(
        _material(
            material_id="mat-sibling-card",
            identity=sibling_identity,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            short_id="R1",
        )
    )
    retrieval_session.commit()

    service = MemoryTraceReadService(session=retrieval_session)
    turn_trace = service.get_turn_trace(identity=seeded.identity)
    branch_trace = service.get_branch_trace(
        story_id=seeded.identity.story_id,
        branch_head_id=seeded.identity.branch_head_id,
    )

    assert "mat-sibling-card" not in {
        item["material_id"] for item in turn_trace["runtime_workspace_materials"]
    }
    assert "mat-sibling-card" not in {
        item["material_id"] for item in branch_trace["runtime_workspace_materials"]
    }
    assert all(
        event["identity"]["branch_head_id"] == seeded.identity.branch_head_id
        for event in branch_trace["events"]
    )


def test_source_proposal_and_material_traces_join_related_evidence(retrieval_session):
    seeded = _seed_trace_evidence(retrieval_session)
    service = MemoryTraceReadService(session=retrieval_session)

    source_trace = service.get_source_ref_trace(
        story_id=seeded.identity.story_id,
        source_ref=seeded.usage_id,
    )
    proposal_trace = service.get_proposal_trace(
        story_id=seeded.identity.story_id,
        proposal_id=seeded.proposal_id,
    )
    material_trace = service.get_material_trace(
        story_id=seeded.identity.story_id,
        material_ref=seeded.card_id,
    )

    assert source_trace["proposal_receipts"][0]["proposal"]["proposal_id"] == (
        seeded.proposal_id
    )
    assert any(
        event["metadata"].get("proposal_id") == seeded.proposal_id
        for event in proposal_trace["events"]
    )
    assert proposal_trace["proposal_receipts"][0]["apply_receipts"][0][
        "revision_after"
    ] == {"chapter.current": 2}
    assert {
        item["material_id"] for item in material_trace["runtime_workspace_materials"]
    } == {
        seeded.card_id,
        seeded.usage_id,
    }
    assert material_trace["retrieval_usage_refs"][0]["used_card_material_ids"] == [
        seeded.card_id
    ]


def test_proposal_trace_joins_proposal_source_material_without_event(
    retrieval_session,
):
    seeded = _seed_trace_evidence(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        scope="story",
        revision=2,
    )
    input_model = ProposalSubmitInput(
        story_id=seeded.identity.story_id,
        mode=StoryMode.LONGFORM.value,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        operations=[
            {
                "kind": "patch_fields",
                "target_ref": target_ref.model_dump(mode="json"),
                "field_patch": {"summary": "uses proposal-local source refs"},
            }
        ],
        base_refs=[target_ref],
        reason="proposal-local source ref trace",
    )
    proposal = repository.create_proposal(
        input_model=input_model,
        status="pending",
        policy_decision="review",
        submit_source="test.trace",
        core_mutation_envelope=CoreMutationEnvelope(
            identity=seeded.identity,
            origin_kind=CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT,
            actor="user.editor",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=list(input_model.operations),
            base_refs=list(input_model.base_refs),
            source_refs=[
                MemorySourceRef(
                    source_type="runtime_workspace_material",
                    source_id=seeded.card_id,
                    layer="runtime_workspace",
                    domain=Domain.CHAPTER.value,
                    entry_id=seeded.card_id,
                    metadata={"source_of_truth": False},
                )
            ],
            trace_refs=["trace:proposal-local-source-ref"],
            reason="proposal-local source ref trace",
        ),
        session_id=seeded.identity.session_id,
        chapter_workspace_id=None,
    )

    trace = MemoryTraceReadService(session=retrieval_session).get_proposal_trace(
        story_id=seeded.identity.story_id,
        proposal_id=proposal.proposal_id,
    )

    assert {item["material_id"] for item in trace["runtime_workspace_materials"]} >= {
        seeded.card_id
    }
    assert trace["proposal_receipts"][0]["proposal"]["proposal_id"] == (
        proposal.proposal_id
    )


def test_trace_readback_survives_new_session_after_persistence(retrieval_session):
    seeded = _seed_trace_evidence(retrieval_session)
    retrieval_session.commit()

    with Session(get_engine()) as later_session:
        trace = MemoryTraceReadService(session=later_session).get_turn_trace(
            identity=seeded.identity
        )

    assert {item["material_id"] for item in trace["runtime_workspace_materials"]} == {
        seeded.card_id,
        seeded.usage_id,
    }
    assert trace["proposal_receipts"][0]["proposal"]["proposal_id"] == (
        seeded.proposal_id
    )
    assert trace["read_manifests"][0]["writer_usage_refs"] == [seeded.usage_id]


def test_trace_reads_do_not_mutate_memory_stores(retrieval_session):
    seeded = _seed_trace_evidence(retrieval_session)
    retrieval_session.commit()
    counts_before = _store_counts(retrieval_session)
    service = MemoryTraceReadService(session=retrieval_session)

    service.get_turn_trace(identity=seeded.identity)
    service.get_branch_trace(
        story_id=seeded.identity.story_id,
        branch_head_id=seeded.identity.branch_head_id,
    )
    service.get_source_ref_trace(
        story_id=seeded.identity.story_id,
        source_ref=seeded.usage_id,
    )
    service.get_proposal_trace(
        story_id=seeded.identity.story_id,
        proposal_id=seeded.proposal_id,
    )
    service.get_material_trace(
        story_id=seeded.identity.story_id,
        material_ref=seeded.card_id,
    )

    assert _store_counts(retrieval_session) == counts_before


def _seed_trace_evidence(retrieval_session) -> _SeededTraceEvidence:
    session, chapter, identity, sibling_identity = _seed_runtime_identities(
        retrieval_session
    )
    event_service = MemoryChangeEventService(session=retrieval_session)
    material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session,
        memory_change_event_service=event_service,
    )
    card_receipt = material_service.record_material(
        _material(
            material_id="mat-card-r1",
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            short_id="R1",
            payload={
                "hit_id": "chunk-1",
                "query_id": "query-1",
                "excerpt": "The old seal broke during the storm.",
            },
            source_refs=[
                MemorySourceRef(
                    source_type="retrieval_hit",
                    source_id="chunk-1",
                    layer="recall",
                    domain=Domain.CHAPTER.value,
                    metadata={"rank": 1},
                )
            ],
        )
    )
    usage_receipt = material_service.record_material(
        _material(
            material_id="mat-usage-u1",
            identity=identity,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            short_id="U1",
            lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
            visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
            payload={
                "used_card_material_ids": [card_receipt.material.material_id],
                "used_expanded_chunk_material_ids": [],
                "missed_query_material_ids": [],
            },
            source_refs=[
                MemorySourceRef(
                    source_type="retrieval_card_material",
                    source_id=card_receipt.material.material_id,
                    layer="runtime_workspace",
                    entry_id=card_receipt.material.material_id,
                    metadata={"source_of_truth": False},
                )
            ],
        )
    )
    repository = ProposalRepository(retrieval_session)
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        scope="story",
        revision=1,
    )
    input_model = ProposalSubmitInput(
        story_id=session.story_id,
        mode=StoryMode.LONGFORM.value,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        operations=[
            {
                "kind": "patch_fields",
                "target_ref": target_ref.model_dump(mode="json"),
                "field_patch": {"title": "Traced Chapter"},
            }
        ],
        base_refs=[target_ref],
        reason="trace test proposal",
    )
    core_envelope = CoreMutationEnvelope(
        identity=identity,
        origin_kind=CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT,
        actor="user.editor",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        operations=list(input_model.operations),
        base_refs=list(input_model.base_refs),
        source_refs=[
            MemorySourceRef(
                source_type="runtime_workspace_material",
                source_id=usage_receipt.material.material_id,
                layer="runtime_workspace",
                domain=Domain.CHAPTER.value,
                entry_id=usage_receipt.material.material_id,
                metadata={"source_of_truth": False},
            )
        ],
        trace_refs=["trace:test-memory-trace"],
        reason="trace test proposal",
    )
    proposal = repository.create_proposal(
        input_model=input_model,
        status="applied",
        policy_decision="silent",
        submit_source="test.trace",
        core_mutation_envelope=core_envelope,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
    )
    apply_receipt = repository.create_apply_receipt(
        proposal_id=proposal.proposal_id,
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        target_refs=[target_ref],
        revision_after={"chapter.current": 2},
        before_snapshot={"chapter_digest": {"title": "Chapter One"}},
        after_snapshot={"chapter_digest": {"title": "Traced Chapter"}},
        warnings=[],
        apply_backend="trace_test",
    )
    event_service.record_event(
        MemoryChangeEvent(
            event_id="event-core-apply",
            identity=identity,
            actor="user.editor",
            event_kind="core_authoritative_mutation_applied",
            layer=Layer.CORE_STATE_AUTHORITATIVE.value,
            domain=Domain.CHAPTER.value,
            block_id="chapter.current",
            entry_id=apply_receipt.apply_id,
            operation_kind="core_mutation.apply",
            source_refs=[
                MemorySourceRef(
                    source_type="memory_proposal",
                    source_id=proposal.proposal_id,
                    layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                    domain=Domain.CHAPTER.value,
                    block_id="chapter.current",
                    metadata={"origin_kind": CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT},
                ),
                MemorySourceRef(
                    source_type="runtime_workspace_material",
                    source_id=usage_receipt.material.material_id,
                    layer="runtime_workspace",
                    domain=Domain.CHAPTER.value,
                    entry_id=usage_receipt.material.material_id,
                ),
            ],
            dirty_targets=[
                MemoryDirtyTarget(
                    target_kind="core_authoritative_block",
                    target_id="chapter.current",
                    layer=Layer.CORE_STATE_AUTHORITATIVE.value,
                    domain=Domain.CHAPTER.value,
                    block_id="chapter.current",
                    reason="core_mutation_applied",
                ),
                MemoryDirtyTarget(
                    target_kind="projection_refresh_pending",
                    target_id="chapter.current",
                    layer=Layer.CORE_STATE_PROJECTION.value,
                    domain=Domain.CHAPTER.value,
                    block_id="projection:chapter.current",
                    reason="authoritative_core_changed",
                ),
            ],
            visibility_effect="current_truth_updated",
            metadata={
                "proposal_id": proposal.proposal_id,
                "apply_id": apply_receipt.apply_id,
            },
        )
    )
    retrieval_session.flush()
    return _SeededTraceEvidence(
        identity=identity,
        sibling_identity=sibling_identity,
        card_id=card_receipt.material.material_id,
        usage_id=usage_receipt.material.material_id,
        proposal_id=proposal.proposal_id,
        apply_id=apply_receipt.apply_id,
    )


def _seed_runtime_identities(
    retrieval_session,
) -> tuple[
    StorySessionRecord,
    ChapterWorkspaceRecord,
    MemoryRuntimeIdentity,
    MemoryRuntimeIdentity,
]:
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-memory-trace",
        source_workspace_id="workspace-memory-trace",
        mode=StoryMode.LONGFORM.value,
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {"current_phase": "outline_drafting"},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={},
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.memory_trace",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="continue",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    sibling_branch = BranchHeadRecord(
        branch_head_id=f"branch:{session.session_id}:sibling",
        story_id=session.story_id,
        session_id=session.session_id,
        branch_name="sibling",
        parent_branch_head_id=None,
        forked_from_turn_id=None,
        head_turn_id=None,
        status="active",
        visibility_scope="active_lineage",
    )
    retrieval_session.add(sibling_branch)
    retrieval_session.flush()
    sibling_turn = identity_service.create_turn(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=sibling_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    sibling_identity = identity_service.resolve_memory_identity(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=sibling_branch.branch_head_id,
        turn_id=sibling_turn.turn_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    return session, chapter, identity, sibling_identity


def _material(
    *,
    material_id: str,
    identity: MemoryRuntimeIdentity,
    material_kind: RuntimeWorkspaceMaterialKind,
    short_id: str,
    payload: dict | None = None,
    source_refs: list[MemorySourceRef] | None = None,
    lifecycle: RuntimeWorkspaceMaterialLifecycle = (
        RuntimeWorkspaceMaterialLifecycle.ACTIVE
    ),
    visibility: str = RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
) -> RuntimeWorkspaceMaterial:
    return RuntimeWorkspaceMaterial(
        material_id=material_id,
        material_kind=material_kind,
        identity=identity,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.runtime.trace",
        source_refs=source_refs or [],
        short_id=short_id,
        payload=payload or {"excerpt": "trace evidence"},
        lifecycle=lifecycle,
        visibility=visibility,
        created_by="test.memory_trace",
        metadata={},
    )


def _store_counts(retrieval_session) -> dict[str, int]:
    return {
        "events": retrieval_session.exec(
            select(func.count()).select_from(MemoryChangeEventRecord)
        ).one(),
        "materials": retrieval_session.exec(
            select(func.count()).select_from(RuntimeWorkspaceMaterialRecord)
        ).one(),
        "proposals": retrieval_session.exec(
            select(func.count()).select_from(MemoryProposalRecord)
        ).one(),
        "apply_receipts": retrieval_session.exec(
            select(func.count()).select_from(MemoryApplyReceiptRecord)
        ).one(),
    }
