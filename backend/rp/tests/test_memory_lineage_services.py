"""Tests for authoritative version/provenance and inspection read services."""

from __future__ import annotations

import pytest

from models.rp_story_store import BranchHeadRecord
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_crud import (
    MemoryGetStateInput,
    MemoryListVersionsInput,
    MemoryReadProvenanceInput,
    ProposalSubmitInput,
)
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import LongformChapterPhase
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.projection_state_service import ProjectionStateService
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.runtime_read_manifest_service import (
    BranchVisibilityResolver,
    RuntimeReadManifestService,
)
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.retrieval_broker import RetrievalBroker
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.version_history_read_service import VersionHistoryReadService
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
)
from rp.models.runtime_identity import StoryTurnStatus


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-1",
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
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
            "writer_hints": ["Hint A"],
        },
    )
    service.commit()
    return (
        service.get_session(session.session_id),
        service.get_chapter_by_index(
            session_id=session.session_id,
            chapter_index=1,
        ),
        service,
    )


async def _apply_chapter_patch(retrieval_session):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.current",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Chapter Two"},
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="tool",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )
    # RetrievalBroker opens its own Session, so the persisted proposal/apply lineage
    # must be committed here to exercise the durable read side instead of same-session state.
    story_session_service.commit()
    return receipt, story_session_service, repository


@pytest.mark.asyncio
async def test_version_and_provenance_services_use_apply_receipts(retrieval_session):
    receipt, story_session_service, repository = await _apply_chapter_patch(
        retrieval_session
    )
    adapter = StorySessionCoreStateAdapter(
        story_session_service, default_story_id="story-1"
    )
    version_service = VersionHistoryReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    provenance_service = ProvenanceReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    versions = version_service.list_versions(target_ref)
    provenance = provenance_service.read_provenance(target_ref)

    assert versions.current_ref == "chapter.current@2"
    assert versions.versions == ["chapter.current@2", "chapter.current@1"]
    assert provenance.proposal_refs == [f"proposal:{receipt.proposal_id}"]
    assert provenance.source_refs == [
        "compatibility_mirror:story_session.current_state_json"
    ]


@pytest.mark.asyncio
async def test_retrieval_broker_exposes_authoritative_lineage(retrieval_session):
    receipt, _, _ = await _apply_chapter_patch(retrieval_session)
    broker = RetrievalBroker(default_story_id="story-1")
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    versions = await broker.list_versions(
        MemoryListVersionsInput(target_ref=target_ref)
    )
    provenance = await broker.read_provenance(
        MemoryReadProvenanceInput(target_ref=target_ref)
    )
    state = await broker.get_state(MemoryGetStateInput(refs=[target_ref]))

    assert versions.current_ref == "chapter.current@2"
    assert provenance.proposal_refs == [f"proposal:{receipt.proposal_id}"]
    assert state.items[0].object_ref.revision == 2
    assert state.version_refs == ["chapter.current@2"]


@pytest.mark.asyncio
async def test_memory_inspection_read_service_lists_objects_slots_and_proposals(
    retrieval_session,
):
    _, story_session_service, repository = await _apply_chapter_patch(retrieval_session)
    session = story_session_service.get_latest_session_for_story("story-1")
    assert session is not None
    adapter = StorySessionCoreStateAdapter(
        story_session_service, default_story_id="story-1"
    )
    version_service = VersionHistoryReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        proposal_repository=repository,
        version_history_read_service=version_service,
    )

    authoritative_objects = inspection_service.list_authoritative_objects(
        session_id=session.session_id
    )
    projection_slots = inspection_service.list_projection_slots(
        session_id=session.session_id
    )
    proposals = inspection_service.list_proposals(
        story_id="story-1", session_id=session.session_id
    )

    chapter_entry = next(
        item
        for item in authoritative_objects
        if item["object_ref"]["object_id"] == "chapter.current"
    )
    assert chapter_entry["object_ref"]["revision"] == 2
    assert chapter_entry["data"]["title"] == "Chapter Two"
    assert all(item["slot_name"] != "writer_hints" for item in projection_slots)
    assert proposals[0]["status"] == "applied"


@pytest.mark.asyncio
async def test_session_scoped_lineage_and_inspection_do_not_fall_back_to_story_latest(
    retrieval_session,
):
    receipt, story_session_service, repository = await _apply_chapter_patch(
        retrieval_session
    )
    original_session = story_session_service.get_latest_session_for_story("story-1")
    assert original_session is not None

    newer_session = story_session_service.create_session(
        story_id="story-1",
        source_workspace_id="workspace-2",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Fresh Session"},
            "narrative_progress": {
                "current_phase": "outline_drafting",
                "accepted_segments": 0,
            },
            "timeline_spine": [],
            "active_threads": [],
            "foreshadow_registry": [],
            "character_state_digest": {},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    story_session_service.create_chapter_workspace(
        session_id=newer_session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Found B"],
            "blueprint_digest": ["Blueprint B"],
            "current_outline_digest": ["Outline B"],
            "recent_segment_digest": ["Segment B"],
            "current_state_digest": ["State B"],
        },
    )
    story_session_service.commit()

    adapter = StorySessionCoreStateAdapter(
        story_session_service, default_story_id="story-1"
    )
    version_service = VersionHistoryReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    provenance_service = ProvenanceReadService(
        adapter=adapter,
        proposal_repository=repository,
    )
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
    )
    inspection_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        proposal_repository=repository,
        version_history_read_service=version_service,
    )
    target_ref = ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    versions = version_service.list_versions(
        target_ref, session_id=original_session.session_id
    )
    provenance = provenance_service.read_provenance(
        target_ref, session_id=original_session.session_id
    )
    authoritative_objects = inspection_service.list_authoritative_objects(
        session_id=original_session.session_id
    )

    assert versions.current_ref == "chapter.current@2"
    assert provenance.proposal_refs == [f"proposal:{receipt.proposal_id}"]
    chapter_entry = next(
        item
        for item in authoritative_objects
        if item["object_ref"]["object_id"] == "chapter.current"
    )
    assert chapter_entry["object_ref"]["revision"] == 2
    assert chapter_entry["data"]["title"] == "Chapter Two"


def test_branch_visibility_resolver_tracks_active_lineage_and_parent_cutoff(
    retrieval_session,
):
    session, _, _ = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.branch_visibility",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    main_branch = identity_service.ensure_default_branch(
        session_id=session.session_id,
        story_id=session.story_id,
    )
    turn_one = identity_service.create_turn(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    turn_two = identity_service.create_turn(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    branch = BranchHeadRecord(
        branch_head_id="branch:forked:test",
        story_id=session.story_id,
        session_id=session.session_id,
        branch_name="forked",
        parent_branch_head_id=main_branch.branch_head_id,
        forked_from_turn_id=turn_one.turn_id,
        head_turn_id=None,
        status="active",
        visibility_scope="active_lineage",
    )
    retrieval_session.add(branch)
    retrieval_session.flush()
    fork_turn = identity_service.create_turn(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind="continue",
        actor="story_runtime",
    )
    identity = identity_service.resolve_memory_identity(
        session_id=session.session_id,
        story_id=session.story_id,
        branch_head_id=branch.branch_head_id,
        turn_id=fork_turn.turn_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )

    resolver = BranchVisibilityResolver(retrieval_session)
    scope = resolver.build_runtime_scope(identity=identity)

    assert scope.visible_branch_head_ids == [
        branch.branch_head_id,
        main_branch.branch_head_id,
    ]
    assert scope.turn_cutoff_by_branch[branch.branch_head_id] == fork_turn.turn_id
    assert scope.turn_cutoff_by_branch[main_branch.branch_head_id] == turn_one.turn_id
    assert resolver.is_visible(
        scope=scope,
        visibility_scope="branch_scoped",
        visibility_state="active",
        owning_branch_head_id=main_branch.branch_head_id,
        origin_turn_id=turn_one.turn_id,
    )
    assert not resolver.is_visible(
        scope=scope,
        visibility_scope="branch_scoped",
        visibility_state="active",
        owning_branch_head_id=main_branch.branch_head_id,
        origin_turn_id=turn_two.turn_id,
    )
    assert not resolver.is_visible(
        scope=scope,
        visibility_scope="branch_scoped",
        visibility_state="hidden",
        owning_branch_head_id=branch.branch_head_id,
        origin_turn_id=fork_turn.turn_id,
    )


def test_branch_visibility_resolver_hides_rollback_future_but_allows_new_future(
    retrieval_session,
):
    session, _, _ = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.branch_visibility.rollback",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identities = []
    for index in range(3):
        identity = identity_service.resolve_runtime_entry_identity(
            session_id=session.session_id,
            command_kind=f"continue-{index}",
            actor="story_runtime",
            requested_runtime_profile_snapshot_id=(
                snapshot.runtime_profile_snapshot_id
            ),
        )
        identity_service.update_turn_status(
            turn_id=identity.turn_id,
            status=StoryTurnStatus.SETTLED,
            visible_output_ref=f"artifact:{index}",
            selected_output_ref=f"artifact:{index}",
            settlement_reason="test_settled",
        )
        identities.append(identity)
    target_identity = identities[1]
    hidden_identity = identities[2]

    identity_service.rollback_to_turn(
        session_id=session.session_id,
        target_turn_id=target_identity.turn_id,
        actor="user",
    )
    resolver = BranchVisibilityResolver(retrieval_session)
    target_scope = resolver.build_runtime_scope(identity=target_identity)

    assert target_scope.turn_cutoff_by_branch[target_identity.branch_head_id] == (
        target_identity.turn_id
    )
    assert target_scope.hidden_turn_ids_by_branch[target_identity.branch_head_id] == [
        hidden_identity.turn_id
    ]
    assert not resolver.is_visible(
        scope=target_scope,
        visibility_scope="branch_scoped",
        visibility_state="active",
        owning_branch_head_id=hidden_identity.branch_head_id,
        origin_turn_id=hidden_identity.turn_id,
    )

    new_identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="continue-after-rollback",
        actor="story_runtime",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    new_scope = BranchVisibilityResolver(retrieval_session).build_runtime_scope(
        identity=new_identity
    )

    assert new_scope.turn_cutoff_by_branch[new_identity.branch_head_id] == (
        new_identity.turn_id
    )
    assert resolver.is_visible(
        scope=new_scope,
        visibility_scope="branch_scoped",
        visibility_state="active",
        owning_branch_head_id=new_identity.branch_head_id,
        origin_turn_id=new_identity.turn_id,
    )
    assert not resolver.is_visible(
        scope=new_scope,
        visibility_scope="branch_scoped",
        visibility_state="active",
        owning_branch_head_id=hidden_identity.branch_head_id,
        origin_turn_id=hidden_identity.turn_id,
    )


def test_runtime_read_manifest_service_is_deterministic_and_separates_visible_selected_omitted(
    retrieval_session,
):
    session, _, _ = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.read_manifest",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="continue",
        actor="story_runtime",
    )
    workspace_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    workspace_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="card-R1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            domain="chapter",
            domain_path="runtime.retrieval.card",
            payload={"title": "Card One"},
            visibility="writer_visible",
            created_by="worker.retrieval",
            metadata={"visibility_scope": "branch_scoped"},
        )
    )
    workspace_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="usage-U1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            identity=identity,
            domain="chapter",
            domain_path="runtime.retrieval.usage",
            payload={"used_refs": ["card-R1"]},
            visibility="runtime_private",
            created_by="writer",
            metadata={"visibility_scope": "branch_scoped"},
        )
    )
    workspace_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="miss-M1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_MISS,
            identity=identity,
            domain="chapter",
            domain_path="runtime.retrieval.miss",
            payload={"query_text": "unknown tavern"},
            visibility="runtime_private",
            created_by="writer",
            metadata={"visibility_scope": "branch_scoped"},
        )
    )
    packet_sections = [
        {"label": "foundation_digest", "items": ["Found A"]},
        {"label": "current_outline_digest", "items": ["Outline A"]},
    ]
    service = RuntimeReadManifestService(
        session=retrieval_session,
        runtime_workspace_material_service=workspace_service,
    )

    manifest_a = service.build_writer_manifest(
        identity=identity,
        packet_kind="writer",
        packet_sections=packet_sections,
        selected_section_labels=["foundation_digest"],
    )
    manifest_b = service.build_writer_manifest(
        identity=identity,
        packet_kind="writer",
        packet_sections=packet_sections,
        selected_section_labels=["foundation_digest"],
    )

    assert manifest_a.manifest_id == manifest_b.manifest_id
    assert [item["packet_section_label"] for item in manifest_a.selected_refs] == [
        "foundation_digest"
    ]
    assert {item["reason"] for item in manifest_a.omitted_refs} == {
        "packet_section_not_selected",
        "packet_visible_runtime_workspace_only",
    }
    assert manifest_a.retrieval_card_refs == ["card-R1"]
    assert manifest_a.retrieval_miss_refs == []
    assert manifest_a.writer_usage_refs == ["usage-U1"]
    assert manifest_a.active_branch_lineage == [identity.branch_head_id]
    visible_ids = {str(item["ref_id"]) for item in manifest_a.visible_refs}
    selected_ids = {str(item["ref_id"]) for item in manifest_a.selected_refs}
    assert "usage-U1" not in visible_ids
    assert "usage-U1" not in selected_ids
    assert "miss-M1" not in visible_ids
    assert "miss-M1" not in selected_ids


def test_runtime_read_manifest_hash_is_stable_for_equivalent_json_shapes(
    retrieval_session,
):
    session, _, _ = _seed_story_runtime(retrieval_session)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.read_manifest_json_stability",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="continue",
        actor="story_runtime",
    )
    service = RuntimeReadManifestService(session=retrieval_session)

    manifest_a = service.build_writer_manifest(
        identity=identity,
        packet_kind="writer",
        packet_sections=[
            {
                "label": "foundation_digest",
                "items": [{"b": 2, "a": 1}],
            }
        ],
        selected_section_labels=["foundation_digest"],
    )
    manifest_b = service.build_writer_manifest(
        identity=identity,
        packet_kind="writer",
        packet_sections=[
            {
                "items": [{"a": 1, "b": 2}],
                "label": "foundation_digest",
            }
        ],
        selected_section_labels=["foundation_digest"],
    )

    assert (
        manifest_a.visible_refs[0]["content_hash"]
        == (manifest_b.visible_refs[0]["content_hash"])
    )
    assert manifest_a.manifest_id == manifest_b.manifest_id
