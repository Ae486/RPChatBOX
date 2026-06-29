"""S-Y5 integration assertions for retrieval no-truth and rollback cascade."""

from __future__ import annotations

import json

from sqlmodel import select

from models.rp_memory_store import MemoryApplyReceiptRecord, MemoryProposalRecord
from models.rp_story_store import StoryTurnRecord
from rp.models.memory.contract_registry import MemoryRuntimeIdentity, MemorySourceRef
from rp.models.memory.crud import MemoryGetStateInput, RetrievalHit, RetrievalSearchResult
from rp.models.runtime.workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.shared.dsl import Domain
from rp.models.story.runtime import LongformChapterPhase
from rp.services.core_state.authoritative_state_view_service import (
    AuthoritativeStateViewService,
)
from rp.services.core_state.as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state.read_service import CoreStateReadService
from rp.services.core_state.store_repository import CoreStateStoreRepository
from rp.services.retrieval.runtime_card_service import RuntimeRetrievalCardService
from rp.services.runtime.profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime.workspace_material_service import RuntimeWorkspaceMaterialService
from rp.services.story.runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story.session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story.session_service import StorySessionService
from rp.tests.services._helpers.core_state_dual_write_helpers import (
    build_seeded_core_state_dual_write_service,
)
from rp.tests.services.story.test_session_pointer_write_authority import (
    _seed_settled_main_turns,
)


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-sy5",
        source_workspace_id="workspace-sy5",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Chapter One"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {"mira": {"mood": "careful"}},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    return service.get_session(session.session_id), chapter, service


def _create_identity(
    retrieval_session,
    *,
    session_id: str,
    actor: str,
    command_kind: str,
) -> MemoryRuntimeIdentity:
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session_id,
        created_from=f"test.{command_kind}",
    )
    return StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind=command_kind,
        actor=actor,
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


def _materialize_retrieval_card(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    marker: str,
    title: str,
) -> tuple[RuntimeWorkspaceMaterialService, str]:
    service = RuntimeRetrievalCardService(session=retrieval_session)
    result = RetrievalSearchResult(
        query=marker,
        hits=[
            RetrievalHit(
                hit_id=f"hit-{marker}",
                query_id=f"query-{marker}",
                layer="recall",
                domain=Domain.CHAPTER,
                domain_path=f"chapter.recall.{marker}",
                excerpt_text=f"{marker} evidence text",
                score=0.99,
                rank=1,
                metadata={
                    "title": title,
                    "stored_summary": f"{marker} stored summary",
                },
                provenance_refs=[f"source:{marker}"],
            )
        ],
    )
    _, cards, miss = service.materialize_search_result(
        identity=identity,
        result=result,
        actor="writer.retrieval",
        query_text=marker,
        search_kind="recall",
        attempt_index=1,
    )
    assert miss is None
    assert len(cards) == 1
    return service._workspace(), cards[0].material_id


def _record_direct_retrieval_card(
    retrieval_session,
    *,
    identity: MemoryRuntimeIdentity,
    material_id: str,
    short_id: str,
    marker: str,
    ttl: str,
    version: str,
) -> RuntimeWorkspaceMaterialService:
    workspace_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    workspace_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id=material_id,
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path=f"chapter.runtime.retrieval.{marker}",
            short_id=short_id,
            payload={
                "query_text": marker,
                "summary": f"{marker} summary",
                "text": f"{marker} text",
                "title": f"{marker} title",
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by="test.sy5.rollback",
            source_refs=[
                MemorySourceRef(
                    source_type="retrieval_hit",
                    source_id=f"hit:{marker}",
                    layer="recall",
                    domain=Domain.CHAPTER.value,
                    block_id=f"chapter.runtime.retrieval.{marker}",
                    metadata={"source_of_truth": False},
                )
            ],
            metadata={
                "ttl": ttl,
                "version": version,
                "retrieval_layer": "recall",
                "source_of_truth": False,
            },
        )
    )
    return workspace_service


def _flatten(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _authoritative_readback(
    retrieval_session,
    *,
    story_service: StorySessionService,
    session_id: str,
    identity: MemoryRuntimeIdentity,
) -> dict[str, object]:
    adapter = StorySessionCoreStateAdapter(story_service)
    repository = CoreStateStoreRepository(retrieval_session)
    resolver = CoreStateAsOfResolver(session=retrieval_session, repository=repository)
    read_service = CoreStateReadService(
        adapter=adapter,
        core_state_store_repository=repository,
        store_read_enabled=True,
        runtime_identity=identity,
        core_state_as_of_resolver=resolver,
    )
    view_service = AuthoritativeStateViewService(
        adapter=adapter,
        core_state_store_repository=repository,
        store_read_enabled=True,
    )

    async def _read_state():
        return await read_service.get_state(MemoryGetStateInput(domain=Domain.CHAPTER))

    import asyncio

    state_result = asyncio.run(_read_state())
    manifest = resolver.ensure_manifest_for_identity(identity=identity)
    return {
        "manifest": manifest,
        "state_result": state_result,
        "view_map": view_service.get_state_map(session_id=session_id),
        "authoritative_objects": repository.list_authoritative_objects_for_session(
            session_id=session_id
        ),
        "authoritative_revisions": repository.list_authoritative_revisions_for_session(
            session_id=session_id
        ),
    }


def test_sy5_retrieval_card_never_enters_core_truth_without_governed_apply_receipt(
    retrieval_session,
):
    session, chapter, story_service = _seed_story_runtime(retrieval_session)
    repository = CoreStateStoreRepository(retrieval_session)
    build_seeded_core_state_dual_write_service(
        retrieval_session,
        session=session,
        chapter=chapter,
    )
    object_count_before = len(
        repository.list_authoritative_objects_for_session(session_id=session.session_id)
    )
    revision_count_before = len(
        repository.list_authoritative_revisions_for_session(session_id=session.session_id)
    )
    identity = _create_identity(
        retrieval_session,
        session_id=session.session_id,
        actor="test.sy5.no_truth",
        command_kind="sy5-no-truth",
    )
    marker = "sy5-no-truth-marker"
    workspace_service, card_material_id = _materialize_retrieval_card(
        retrieval_session,
        identity=identity,
        marker=marker,
        title="SY5 No Truth Evidence",
    )
    card = workspace_service.require_material(identity=identity, material_id=card_material_id)
    usage = RuntimeRetrievalCardService(session=retrieval_session).record_writer_usage(
        identity=identity,
        used_card_ids=[card.short_id or card.material_id],
        used_expanded_chunk_ids=[],
        actor="writer.retrieval",
    )
    before = _authoritative_readback(
        retrieval_session,
        story_service=story_service,
        session_id=session.session_id,
        identity=identity,
    )

    retrieval_session.flush()

    proposal_rows = retrieval_session.exec(select(MemoryProposalRecord)).all()
    apply_rows = retrieval_session.exec(select(MemoryApplyReceiptRecord)).all()
    object_payloads = [_flatten(row.data_json) for row in before["authoritative_objects"]]
    revision_payloads = [
        _flatten(row.data_json) for row in before["authoritative_revisions"]
    ]
    state_payloads = [_flatten(item.data) for item in before["state_result"].items]
    view_payload = _flatten(before["view_map"])
    card_payload = _flatten(card.payload)
    manifest_map = _flatten(before["manifest"].effective_revision_map)

    assert card.metadata["source_of_truth"] is False
    assert usage.metadata["governed_promotion_only"] is True
    assert card.source_refs[0].source_id == f"hit-{marker}"
    assert proposal_rows == []
    assert apply_rows == []
    assert len(before["authoritative_objects"]) == object_count_before
    assert len(before["authoritative_revisions"]) == revision_count_before
    assert marker not in manifest_map
    assert all(marker not in payload for payload in object_payloads)
    assert all(marker not in payload for payload in revision_payloads)
    assert all(marker not in payload for payload in state_payloads)
    assert marker not in view_payload
    assert marker in card_payload
    assert card.material_kind == RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD
    assert usage.material_kind == RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD


def test_sy5_rollback_invalidates_retrieval_card_by_turn_id_without_ttl_or_version_gate(
    retrieval_session,
):
    story_session, service, identities = _seed_settled_main_turns(
        retrieval_session,
        story_id="sy5-rollback-cascade",
        count=2,
    )
    target_identity = identities[0]
    hidden_identity = identities[1]
    workspace_service = _record_direct_retrieval_card(
        retrieval_session,
        identity=target_identity,
        material_id="retrieval-card-target-turn",
        short_id="R1",
        marker="sy5-target-stale",
        ttl="expired-target-card",
        version="stale-target-version",
    )
    _record_direct_retrieval_card(
        retrieval_session,
        identity=hidden_identity,
        material_id="retrieval-card-hidden-turn",
        short_id="R1",
        marker="sy5-hidden-fresh",
        ttl="fresh-hidden-card",
        version="current-hidden-version",
    )
    target_card_before = workspace_service.require_material(
        identity=target_identity,
        material_id="retrieval-card-target-turn",
    )
    hidden_card_before = workspace_service.require_material(
        identity=hidden_identity,
        material_id="retrieval-card-hidden-turn",
    )
    hidden_turn_before = retrieval_session.get(StoryTurnRecord, hidden_identity.turn_id)
    assert hidden_turn_before is not None
    hidden_turn_visibility_before = hidden_turn_before.visibility_state

    receipt = service.rollback_to_turn(
        session_id=story_session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="test.sy5.rollback",
    )

    target_card_after = workspace_service.require_material(
        identity=target_identity,
        material_id="retrieval-card-target-turn",
    )
    hidden_card_after = workspace_service.require_material(
        identity=hidden_identity,
        material_id="retrieval-card-hidden-turn",
    )
    hidden_turn_after = retrieval_session.get(StoryTurnRecord, hidden_identity.turn_id)
    assert hidden_turn_after is not None

    assert target_card_before.lifecycle == RuntimeWorkspaceMaterialLifecycle.ACTIVE
    assert hidden_card_before.lifecycle == RuntimeWorkspaceMaterialLifecycle.ACTIVE
    assert hidden_turn_visibility_before == "active"
    assert target_card_before.metadata["ttl"] == "expired-target-card"
    assert target_card_before.metadata["version"] == "stale-target-version"
    assert hidden_card_before.metadata["ttl"] == "fresh-hidden-card"
    assert hidden_card_before.metadata["version"] == "current-hidden-version"
    assert hidden_turn_after.visibility_state == "hidden_by_rollback"
    assert target_card_after.lifecycle == RuntimeWorkspaceMaterialLifecycle.ACTIVE
    assert "visibility_state" not in target_card_after.metadata
    assert "invalidated_at" not in target_card_after.metadata
    assert hidden_card_after.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED
    assert hidden_card_after.metadata["visibility_state"] == "hidden_by_rollback"
    assert hidden_card_after.metadata["hidden_after_turn_id"] == target_identity.turn_id
    assert hidden_card_after.metadata["rollback_visibility"] == {
        "hidden_by_control_receipt_id": receipt.receipt_id,
        "hidden_after_turn_id": target_identity.turn_id,
    }
    assert "invalidated_at" in hidden_card_after.metadata
    assert "expired_at" not in hidden_card_after.metadata
    assert hidden_card_after.identity.turn_id == hidden_identity.turn_id
    assert hidden_card_after.identity.turn_id != target_identity.turn_id
    assert "sy5-hidden-fresh" in _flatten(hidden_card_after.payload)
    assert receipt.metadata["visibility_transition"]["invalidated_workspace_material_ids"] == [
        "retrieval-card-hidden-turn"
    ]
