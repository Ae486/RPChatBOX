"""Tests for V1.1 Core State branch-aware as-of manifests."""

from __future__ import annotations

from copy import deepcopy

from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import MemoryRuntimeIdentity
from rp.models.memory_crud import MemoryGetStateInput
from rp.models.runtime_identity import StoryTurnStatus
from rp.models.story_runtime import LongformChapterPhase
from rp.services.core_state_as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.core_state_read_service import CoreStateReadService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_read_manifest_service import RuntimeReadManifestService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService


def _seed_runtime(retrieval_session):
    story_service = StorySessionService(retrieval_session)
    session = story_service.create_session(
        story_id="story-core-asof",
        source_workspace_id="workspace-core-asof",
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
    chapter = story_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "current_state_digest": ["Chapter One"],
            "current_outline_digest": ["Outline"],
        },
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    dual_write = CoreStateDualWriteService(repository=core_repo)
    dual_write.seed_activation_state(session=session, chapter=chapter)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.core_asof",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    branch = identity_service.ensure_default_branch(
        session_id=session.session_id,
        story_id=session.story_id,
    )
    resolver = CoreStateAsOfResolver(
        session=retrieval_session,
        repository=core_repo,
    )
    return (
        story_service,
        session,
        chapter,
        snapshot.runtime_profile_snapshot_id,
        branch.branch_head_id,
        identity_service,
        dual_write,
        core_repo,
        resolver,
    )


def _create_identity(
    identity_service: StoryRuntimeIdentityService,
    *,
    session_id: str,
    story_id: str,
    branch_head_id: str,
    runtime_profile_snapshot_id: str,
    command_kind: str,
) -> MemoryRuntimeIdentity:
    turn = identity_service.create_turn(
        session_id=session_id,
        story_id=story_id,
        branch_head_id=branch_head_id,
        runtime_profile_snapshot_id=runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind=command_kind,
        actor="test.core_asof",
    )
    return identity_service.resolve_memory_identity(
        session_id=session_id,
        story_id=story_id,
        branch_head_id=branch_head_id,
        turn_id=turn.turn_id,
        runtime_profile_snapshot_id=runtime_profile_snapshot_id,
    )


def _settle(identity_service: StoryRuntimeIdentityService, identity: MemoryRuntimeIdentity):
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=f"artifact:{identity.turn_id}",
        selected_output_ref=f"artifact:{identity.turn_id}",
        settlement_reason="test_core_asof_settled",
    )


def _chapter_ref() -> ObjectRef:
    return ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        scope="story",
    )


def _character_ref() -> ObjectRef:
    return ObjectRef(
        object_id="character.state_digest",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHARACTER,
        domain_path="character.state_digest",
        scope="story",
    )


def _mutate_chapter_title(
    *,
    story_service: StorySessionService,
    dual_write: CoreStateDualWriteService,
    resolver: CoreStateAsOfResolver,
    identity: MemoryRuntimeIdentity,
    title: str,
):
    session = story_service.get_session(identity.session_id)
    assert session is not None
    before_snapshot = dual_write.materialize_authoritative_snapshot(session=session)
    after_snapshot = deepcopy(before_snapshot)
    after_snapshot["chapter_digest"] = {
        **dict(after_snapshot.get("chapter_digest") or {}),
        "title": title,
    }
    target_ref = _chapter_ref()
    revision_after = {
        target_ref.object_id: dual_write.current_authoritative_revision(
            session_id=identity.session_id,
            target_ref=target_ref,
        )
        + 1
    }
    store_writes = dual_write.apply_authoritative_mutation(
        session=session,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        target_refs=[target_ref],
        revision_after=revision_after,
        apply_id=f"apply:{identity.turn_id}",
        proposal_id=f"proposal:{identity.turn_id}",
        runtime_identity=identity,
    )
    return resolver.record_core_mutation(
        identity=identity,
        changed_revisions=[
            revision_record for _, revision_record in store_writes.values()
        ],
        source_event_ids=[f"apply:{identity.turn_id}"],
    )


def _read_payload(
    resolver: CoreStateAsOfResolver,
    *,
    identity: MemoryRuntimeIdentity,
    ref: ObjectRef,
) -> dict:
    manifest = resolver.ensure_manifest_for_identity(identity=identity)
    revision = resolver.resolve_object_revision(manifest=manifest, object_ref=ref)
    return dict(revision.data_json)


def test_core_state_turns_reuse_manifest_and_mutation_copies_changed_revision(
    retrieval_session,
):
    (
        _story_service,
        session,
        _chapter,
        snapshot_id,
        branch_id,
        identity_service,
        dual_write,
        _core_repo,
        resolver,
    ) = _seed_runtime(retrieval_session)
    turn0 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="activation",
    )
    s0 = resolver.ensure_manifest_for_identity(identity=turn0)
    _settle(identity_service, turn0)
    turn1 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-1",
    )
    turn2 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-2",
    )

    assert resolver.ensure_manifest_for_identity(identity=turn1).snapshot_id == (
        s0.snapshot_id
    )
    assert resolver.ensure_manifest_for_identity(identity=turn2).snapshot_id == (
        s0.snapshot_id
    )
    _settle(identity_service, turn1)
    _settle(identity_service, turn2)

    turn3 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-3",
    )
    s1 = _mutate_chapter_title(
        story_service=_story_service,
        dual_write=dual_write,
        resolver=resolver,
        identity=turn3,
        title="Chapter Three",
    )

    chapter_key = resolver.object_ref_key(
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        scope="story",
        object_id="chapter.current",
    )
    character_key = resolver.object_ref_key(
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        scope="story",
        object_id="character.state_digest",
    )
    assert s1.snapshot_id != s0.snapshot_id
    assert s1.parent_snapshot_id == s0.snapshot_id
    assert s1.effective_revision_map[chapter_key] != (
        s0.effective_revision_map[chapter_key]
    )
    assert s1.effective_revision_map[character_key] == (
        s0.effective_revision_map[character_key]
    )
    assert _read_payload(resolver, identity=turn3, ref=_chapter_ref())["title"] == (
        "Chapter Three"
    )


def test_branch_and_rollback_select_turn_bound_core_manifests(retrieval_session):
    (
        story_service,
        session,
        _chapter,
        snapshot_id,
        main_branch_id,
        identity_service,
        dual_write,
        core_repo,
        resolver,
    ) = _seed_runtime(retrieval_session)
    turn0 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="activation",
    )
    s0 = resolver.ensure_manifest_for_identity(identity=turn0)
    _settle(identity_service, turn0)
    turn1 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-1",
    )
    turn2 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-2",
    )
    resolver.ensure_manifest_for_identity(identity=turn1)
    resolver.ensure_manifest_for_identity(identity=turn2)
    _settle(identity_service, turn1)
    _settle(identity_service, turn2)
    turn3 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-3",
    )
    s1 = _mutate_chapter_title(
        story_service=story_service,
        dual_write=dual_write,
        resolver=resolver,
        identity=turn3,
        title="Main Future",
    )
    _settle(identity_service, turn3)
    turn5 = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="continue-5",
    )
    _mutate_chapter_title(
        story_service=story_service,
        dual_write=dual_write,
        resolver=resolver,
        identity=turn5,
        title="Latest Current Row",
    )
    _settle(identity_service, turn5)

    branch_receipt = identity_service.create_branch_from_turn(
        session_id=session.session_id,
        origin_turn_id=turn2.turn_id,
        actor="test.core_asof",
        branch_name="turn2 fork",
    )
    branch_id = branch_receipt.to_branch_head_id
    assert branch_id is not None
    branch_turn = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="branch-continue",
    )
    branch_manifest = resolver.ensure_manifest_for_identity(identity=branch_turn)

    assert branch_manifest.snapshot_id == s0.snapshot_id
    branch_read_service = CoreStateReadService(
        adapter=StorySessionCoreStateAdapter(story_service),
        core_state_store_repository=core_repo,
        store_read_enabled=True,
        runtime_identity=branch_turn,
        core_state_as_of_resolver=resolver,
    )
    state = retrieval_session.run_sync(
        lambda _: None
    ) if False else None
    del state

    async def _read_branch_state():
        return await branch_read_service.get_state(
            MemoryGetStateInput(domain=Domain.CHAPTER)
        )

    import asyncio

    branch_state = asyncio.run(_read_branch_state())
    assert branch_state.items[0].data["title"] == "Chapter One"
    assert all(
        "current_row_and_session_mirror_fallback_blocked" not in warning
        for item in branch_state.items
        for warning in item.warnings
    )

    branch_s1 = _mutate_chapter_title(
        story_service=story_service,
        dual_write=dual_write,
        resolver=resolver,
        identity=branch_turn,
        title="Branch Local",
    )
    assert branch_s1.snapshot_id != s1.snapshot_id
    assert branch_s1.branch_head_id == branch_id
    assert _read_payload(resolver, identity=branch_turn, ref=_chapter_ref())[
        "title"
    ] == "Branch Local"
    assert _read_payload(resolver, identity=turn3, ref=_chapter_ref())["title"] == (
        "Main Future"
    )

    identity_service.switch_branch(
        session_id=session.session_id,
        target_branch_head_id=main_branch_id,
        actor="test.core_asof",
    )
    identity_service.rollback_to_turn(
        session_id=session.session_id,
        target_turn_id=turn2.turn_id,
        actor="test.core_asof",
    )
    after_rollback = _create_identity(
        identity_service,
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch_id,
        runtime_profile_snapshot_id=snapshot_id,
        command_kind="after-rollback",
    )
    rollback_manifest = resolver.ensure_manifest_for_identity(identity=after_rollback)
    assert rollback_manifest.snapshot_id == s0.snapshot_id
    assert len(core_repo.list_authoritative_revisions_for_session(
        session_id=session.session_id
    )) >= 4

    read_manifest_service = RuntimeReadManifestService(
        session=retrieval_session,
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        core_state_as_of_resolver=resolver,
    )
    runtime_manifest = read_manifest_service.build_writer_manifest(
        identity=after_rollback,
        packet_kind="writer",
        packet_sections=[
            {
                "section_id": "projection.current_state_digest",
                "label": "current_state_digest",
                "source_kind": "core_projection_view",
                "items": ["Latest Current Row"],
                "metadata_json": {
                    "source_core_state_snapshot_id": s1.snapshot_id,
                },
            }
        ],
        selected_section_labels=["current_state_digest"],
    )

    assert runtime_manifest.branch_scope["active_branch_head_id"] == main_branch_id
    assert runtime_manifest.core_state_snapshot_id == s0.snapshot_id
    assert runtime_manifest.core_state_revision_map == s0.effective_revision_map
    assert {
        item["reason"] for item in runtime_manifest.omitted_refs
    } == {"core_projection_source_manifest_mismatch"}
