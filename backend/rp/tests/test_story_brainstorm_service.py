"""Focused V4 writer brainstorm Runtime Workspace and Core apply tests."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError
from sqlmodel import select

from models.rp_memory_store import MemoryProposalRecord
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.runtime_identity import StoryTurnStatus
from rp.models.runtime_workspace_material import RuntimeWorkspaceMaterialKind
from rp.models.story_brainstorm import (
    BrainstormApplyRequest,
    BrainstormCoreFieldChange,
    BrainstormItem,
    BrainstormItemStatus,
    BrainstormItemUpdateRequest,
    BrainstormSessionStartRequest,
    BrainstormStructuredItem,
    BrainstormSummarizeRequest,
)
from rp.models.story_runtime import LongformChapterPhase
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_as_of_resolver import CoreStateAsOfResolver
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.story_brainstorm_service import StoryBrainstormService
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.worker_memory_service import WorkerMemoryService
from rp.services.worker_registry_service import WorkerRegistryService


def test_brainstorm_item_forbids_worker_routing_fields():
    with pytest.raises(ValidationError) as exc:
        BrainstormItem(
            item_id="brainstorm-1:item:1",
            summary_text="Make the current chapter title more ominous.",
            target_layer="core",
        )

    assert "Extra inputs are not permitted" in str(exc.value)
    assert "target_layer" in str(exc.value)


@pytest.mark.asyncio
async def test_brainstorm_session_lifecycle_uses_runtime_workspace_material(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-runtime-workspace",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(retrieval_session, story_service=story_service)

    started = service.start_session(
        BrainstormSessionStartRequest(
            identity=identity,
            actor="writer",
            prompt="Discuss possible refinements for the current chapter.",
            source_entry_ids=["discussion-1"],
        )
    )
    summarized = await service.summarize_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormSummarizeRequest(
            identity=identity,
            actor="writer",
            dry_run_items=[
                BrainstormStructuredItem(
                    summary_text="Rename the current chapter to Storm Gate.",
                    evidence_text_refs=["discussion-1"],
                    uncertainty="User has not confirmed the exact title.",
                )
            ],
        ),
    )
    edited = service.update_item(
        brainstorm_id=started.brainstorm_id,
        item_id=summarized.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            summary_text="Rename the current chapter to Storm Gate.",
            status="confirmed",
        ),
    )

    materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.BRAINSTORM_SESSION,
    )

    assert started.metadata["temporary"] is True
    assert started.metadata["source_of_truth"] is False
    assert summarized.items[0].status == BrainstormItemStatus.PROPOSED
    assert "target_layer" not in summarized.items[0].model_dump(mode="json")
    assert edited.items[0].status == BrainstormItemStatus.CONFIRMED
    assert [material.lifecycle.value for material in materials] == [
        "invalidated",
        "invalidated",
        "active",
    ]
    assert materials[-1].payload["brainstorm_id"] == started.brainstorm_id
    assert materials[-1].metadata["source_of_truth"] is False


@pytest.mark.asyncio
async def test_confirmed_item_without_core_change_redirects_for_review(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-non-core-review",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(retrieval_session, story_service=story_service)
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await service.apply_session(
        brainstorm_id=session.brainstorm_id,
        request=BrainstormApplyRequest(
            identity=identity,
            actor="writer",
            item_ids=[session.items[0].item_id],
        ),
    )

    assert receipt.status == "redirect"
    assert receipt.dispatch_receipts[0].status == "redirect"
    assert receipt.dispatch_receipts[0].review_entrypoint == "/memory/inspection"
    latest = service.get_session(
        identity=identity,
        brainstorm_id=session.brainstorm_id,
    )
    assert latest.items[0].status == BrainstormItemStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_confirmed_core_item_applies_through_shared_core_kernel(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-core-apply",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(retrieval_session, story_service=story_service)
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await service.apply_session(
        brainstorm_id=session.brainstorm_id,
        request=BrainstormApplyRequest(
            identity=identity,
            actor="writer",
            item_ids=[session.items[0].item_id],
            core_field_changes=[
                BrainstormCoreFieldChange(
                    source_item_id=session.items[0].item_id,
                    target_ref="chapter.current",
                    base_revision="1",
                    operation="set_field",
                    field_path="title",
                    new_value="Storm Gate",
                    reason="User confirmed title from brainstorm summary.",
                )
            ],
        ),
    )

    refreshed = story_service.get_session(story_session.session_id)
    candidate_materials = RuntimeWorkspaceMaterialService(
        session=retrieval_session
    ).list_materials(
        identity=identity,
        material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
    )

    assert receipt.status == "applied"
    dispatch = receipt.dispatch_receipts[0]
    proposal_record = retrieval_session.exec(
        select(MemoryProposalRecord).where(
            MemoryProposalRecord.proposal_id == dispatch.proposal_id
        )
    ).one()
    assert dispatch.status == "applied"
    assert dispatch.old_value == "Chapter One"
    assert dispatch.new_value == "Storm Gate"
    assert dispatch.metadata["status"] == "applied"
    assert proposal_record.governance_metadata_json["core_mutation"][
        "origin_kind"
    ] == (
        "brainstorm_summary_apply"
    )
    assert refreshed is not None
    assert refreshed.current_state_json["chapter_digest"]["title"] == "Storm Gate"
    assert candidate_materials
    assert candidate_materials[0].payload["old_value"] == "Chapter One"
    assert candidate_materials[0].payload["authoritative_mutation"] is False


@pytest.mark.asyncio
async def test_core_apply_stale_base_revision_returns_conflict_without_mutation(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-core-conflict",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(retrieval_session, story_service=story_service)
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await service.apply_session(
        brainstorm_id=session.brainstorm_id,
        request=BrainstormApplyRequest(
            identity=identity,
            actor="writer",
            item_ids=[session.items[0].item_id],
            core_field_changes=[
                BrainstormCoreFieldChange(
                    source_item_id=session.items[0].item_id,
                    target_ref="chapter.current",
                    base_revision="999",
                    operation="replace_field",
                    field_path="title",
                    new_value="Should Not Apply",
                )
            ],
        ),
    )

    refreshed = story_service.get_session(story_session.session_id)

    assert receipt.status == "conflict"
    assert receipt.dispatch_receipts[0].reason_codes == [
        "phase_e_apply_base_revision_conflict"
    ]
    assert refreshed is not None
    assert refreshed.current_state_json["chapter_digest"]["title"] == "Chapter One"


@pytest.mark.asyncio
async def test_core_apply_missing_apply_as_of_resolver_fails_closed(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-apply-missing-asof-resolver",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        include_apply_core_state_as_of_resolver=False,
        include_apply_core_state_dual_write_service=False,
    )
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await _apply_title_change(
        service=service,
        session=session,
        identity=identity,
        title="Should Not Apply",
    )
    refreshed = story_service.get_session(story_session.session_id)

    assert receipt.status == "failed"
    assert receipt.dispatch_receipts[0].reason_codes == [
        "phase_e_core_state_as_of_resolver_missing_for_core_mutation"
    ]
    assert refreshed is not None
    assert refreshed.current_state_json["chapter_digest"]["title"] == "Chapter One"


@pytest.mark.asyncio
async def test_branch_fork_brainstorm_apply_uses_turn_as_of_core_not_main_future(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-branch-asof",
    )
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=story_session.session_id,
        created_from="test.story_brainstorm.branch_asof",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    main_branch = identity_service.ensure_default_branch(
        session_id=story_session.session_id,
        story_id=story_session.story_id,
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    dual_write = CoreStateDualWriteService(repository=core_repo)
    resolver = CoreStateAsOfResolver(session=retrieval_session, repository=core_repo)

    turn0 = _create_identity(
        identity_service,
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        command_kind="activation",
    )
    resolver.ensure_manifest_for_identity(identity=turn0)
    _settle(identity_service, turn0)
    turn1 = _create_identity(
        identity_service,
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        command_kind="turn-before-fork",
    )
    resolver.ensure_manifest_for_identity(identity=turn1)
    _settle(identity_service, turn1)
    main_future = _create_identity(
        identity_service,
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=main_branch.branch_head_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        command_kind="main-future",
    )
    _mutate_chapter_title(
        story_service=story_service,
        dual_write=dual_write,
        resolver=resolver,
        identity=main_future,
        title="Main Future",
    )
    _settle(identity_service, main_future)

    branch_receipt = identity_service.create_branch_from_turn(
        session_id=story_session.session_id,
        origin_turn_id=turn1.turn_id,
        actor="test.story_brainstorm",
        branch_name="turn1 fork",
    )
    branch_id = branch_receipt.to_branch_head_id
    assert branch_id is not None
    branch_identity = _create_identity(
        identity_service,
        session_id=story_session.session_id,
        story_id=story_session.story_id,
        branch_head_id=branch_id,
        runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
        command_kind="branch-brainstorm",
    )
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        core_state_as_of_resolver=resolver,
        core_state_dual_write_service=dual_write,
        snapshot_service=snapshot_service,
    )
    session = await _confirmed_brainstorm_session(
        service,
        identity=branch_identity,
    )

    receipt = await service.apply_session(
        brainstorm_id=session.brainstorm_id,
        request=BrainstormApplyRequest(
            identity=branch_identity,
            actor="writer",
            item_ids=[session.items[0].item_id],
            core_field_changes=[
                BrainstormCoreFieldChange(
                    source_item_id=session.items[0].item_id,
                    target_ref="chapter.current",
                    base_revision="1",
                    operation="set_field",
                    field_path="title",
                    new_value="Branch Storm",
                )
            ],
        ),
    )

    assert receipt.status == "applied"
    assert receipt.dispatch_receipts[0].old_value == "Chapter One"
    assert _read_chapter_title(resolver, identity=branch_identity) == "Branch Storm"
    assert _read_chapter_title(resolver, identity=main_future) == "Main Future"


@pytest.mark.asyncio
async def test_worker_registry_unavailable_fails_closed_without_apply(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-registry-unavailable",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        include_worker_registry=False,
    )
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await _apply_title_change(
        service=service,
        session=session,
        identity=identity,
        title="Should Not Apply",
    )
    refreshed = story_service.get_session(story_session.session_id)

    assert receipt.status == "pending_review"
    assert receipt.dispatch_receipts[0].reason_codes == [
        "brainstorm_worker_registry_unavailable"
    ]
    assert refreshed is not None
    assert refreshed.current_state_json["chapter_digest"]["title"] == "Chapter One"


@pytest.mark.asyncio
async def test_disabled_worker_permission_fails_closed_without_apply(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-disabled-worker",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.require_snapshot(identity.runtime_profile_snapshot_id)
    compiled = deepcopy(snapshot.compiled_profile_json or {})
    compiled["worker_activation"]["specialist"]["active"] = False
    snapshot.compiled_profile_json = compiled
    retrieval_session.add(snapshot)
    retrieval_session.commit()
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        snapshot_service=snapshot_service,
    )
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await _apply_title_change(
        service=service,
        session=session,
        identity=identity,
        title="Should Not Apply",
    )

    assert receipt.status == "pending_review"
    assert "brainstorm_worker_inactive" in receipt.dispatch_receipts[0].reason_codes


@pytest.mark.asyncio
async def test_forbidden_worker_operation_domain_fails_closed_without_apply(
    retrieval_session,
):
    story_session, _chapter, story_service = _seed_story_runtime(
        retrieval_session,
        story_id="brainstorm-forbidden-operation-domain",
    )
    identity = _runtime_identity(retrieval_session, story_session.session_id)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.require_snapshot(identity.runtime_profile_snapshot_id)
    compiled = deepcopy(snapshot.compiled_profile_json or {})
    compiled["permission_profile"]["domain_defaults"]["chapter"]["propose"] = False
    snapshot.compiled_profile_json = compiled
    retrieval_session.add(snapshot)
    retrieval_session.commit()
    service = _build_service(
        retrieval_session,
        story_service=story_service,
        snapshot_service=snapshot_service,
    )
    session = await _confirmed_brainstorm_session(service, identity=identity)

    receipt = await _apply_title_change(
        service=service,
        session=session,
        identity=identity,
        title="Should Not Apply",
    )
    refreshed = story_service.get_session(story_session.session_id)

    assert receipt.status == "pending_review"
    assert {
        "forbidden_operation_kind",
        "worker_memory_operation_forbidden",
    } <= set(receipt.dispatch_receipts[0].reason_codes)
    assert refreshed is not None
    assert refreshed.current_state_json["chapter_digest"]["title"] == "Chapter One"


async def _apply_title_change(
    *,
    service: StoryBrainstormService,
    session,
    identity,
    title: str,
):
    return await service.apply_session(
        brainstorm_id=session.brainstorm_id,
        request=BrainstormApplyRequest(
            identity=identity,
            actor="writer",
            item_ids=[session.items[0].item_id],
            core_field_changes=[
                BrainstormCoreFieldChange(
                    source_item_id=session.items[0].item_id,
                    target_ref="chapter.current",
                    base_revision="1",
                    operation="set_field",
                    field_path="title",
                    new_value=title,
                )
            ],
        ),
    )


async def _confirmed_brainstorm_session(
    service: StoryBrainstormService,
    *,
    identity,
):
    started = service.start_session(
        BrainstormSessionStartRequest(
            identity=identity,
            actor="writer",
            prompt="Brainstorm a chapter memory update.",
        )
    )
    summarized = await service.summarize_session(
        brainstorm_id=started.brainstorm_id,
        request=BrainstormSummarizeRequest(
            identity=identity,
            actor="writer",
            dry_run_items=[
                BrainstormStructuredItem(
                    summary_text="Rename the current chapter to Storm Gate.",
                    evidence_text_refs=["discussion-1"],
                )
            ],
        ),
    )
    return service.update_item(
        brainstorm_id=started.brainstorm_id,
        item_id=summarized.items[0].item_id,
        request=BrainstormItemUpdateRequest(
            identity=identity,
            actor="writer",
            status="confirmed",
        ),
    )


def _build_service(
    retrieval_session,
    *,
    story_service: StorySessionService,
    include_worker_registry: bool = True,
    include_apply_core_state_as_of_resolver: bool = True,
    include_apply_core_state_dual_write_service: bool = True,
    snapshot_service: RuntimeProfileSnapshotService | None = None,
    core_state_as_of_resolver: CoreStateAsOfResolver | None = None,
    core_state_dual_write_service: CoreStateDualWriteService | None = None,
) -> StoryBrainstormService:
    proposal_repository = ProposalRepository(retrieval_session)
    core_repo = CoreStateStoreRepository(retrieval_session)
    resolver = core_state_as_of_resolver or CoreStateAsOfResolver(
        session=retrieval_session,
        repository=core_repo,
    )
    dual_write = core_state_dual_write_service or CoreStateDualWriteService(
        repository=core_repo,
    )
    projection_state_service = ProjectionStateService(
        story_session_service=story_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_service),
    )
    block_read_service = RpBlockReadService(
        story_session_service=story_service,
        builder_projection_context_service=BuilderProjectionContextService(
            projection_state_service
        ),
        core_state_store_repository=core_repo,
    )
    proposal_workflow_service = ProposalWorkflowService(
        proposal_repository=proposal_repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_service,
            proposal_repository=proposal_repository,
            story_state_apply_service=StoryStateApplyService(),
            core_state_dual_write_service=(
                dual_write if include_apply_core_state_dual_write_service else None
            ),
            core_state_as_of_resolver=(
                resolver if include_apply_core_state_as_of_resolver else None
            ),
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    snapshot_service = snapshot_service or RuntimeProfileSnapshotService(
        retrieval_session
    )
    return StoryBrainstormService(
        story_session_service=story_service,
        runtime_workspace_material_service=RuntimeWorkspaceMaterialService(
            session=retrieval_session
        ),
        proposal_workflow_service=proposal_workflow_service,
        rp_block_read_service=block_read_service,
        worker_registry_service=(
            WorkerRegistryService(
                retrieval_session,
                runtime_profile_snapshot_service=snapshot_service,
            )
            if include_worker_registry
            else None
        ),
        worker_memory_service=WorkerMemoryService(session=retrieval_session),
        core_state_as_of_resolver=resolver,
    )


def _runtime_identity(retrieval_session, session_id: str):
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session_id,
        created_from="test.story_brainstorm",
    )
    return StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    ).resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind="brainstorm",
        actor="writer",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


def _create_identity(
    identity_service: StoryRuntimeIdentityService,
    *,
    session_id: str,
    story_id: str,
    branch_head_id: str,
    runtime_profile_snapshot_id: str,
    command_kind: str,
):
    turn = identity_service.create_turn(
        session_id=session_id,
        story_id=story_id,
        branch_head_id=branch_head_id,
        runtime_profile_snapshot_id=runtime_profile_snapshot_id,
        turn_kind="generation",
        command_kind=command_kind,
        actor="test.story_brainstorm",
    )
    return identity_service.resolve_memory_identity(
        session_id=session_id,
        story_id=story_id,
        branch_head_id=branch_head_id,
        turn_id=turn.turn_id,
        runtime_profile_snapshot_id=runtime_profile_snapshot_id,
    )


def _settle(
    identity_service: StoryRuntimeIdentityService,
    identity,
) -> None:
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref=f"artifact:{identity.turn_id}",
        selected_output_ref=f"artifact:{identity.turn_id}",
        settlement_reason="test_story_brainstorm_settled",
    )


def _chapter_ref() -> ObjectRef:
    return ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        scope="story",
    )


def _mutate_chapter_title(
    *,
    story_service: StorySessionService,
    dual_write: CoreStateDualWriteService,
    resolver: CoreStateAsOfResolver,
    identity,
    title: str,
) -> None:
    story_session = story_service.get_session(identity.session_id)
    assert story_session is not None
    before_snapshot = dual_write.materialize_authoritative_snapshot(
        session=story_session
    )
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
        session=story_session,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        target_refs=[target_ref],
        revision_after=revision_after,
        apply_id=f"apply:{identity.turn_id}",
        proposal_id=f"proposal:{identity.turn_id}",
        runtime_identity=identity,
    )
    resolver.record_core_mutation(
        identity=identity,
        changed_revisions=[
            revision_record for _, revision_record in store_writes.values()
        ],
        source_event_ids=[f"apply:{identity.turn_id}"],
    )


def _read_chapter_title(
    resolver: CoreStateAsOfResolver,
    *,
    identity,
) -> str:
    manifest = resolver.ensure_manifest_for_identity(identity=identity)
    revision = resolver.resolve_object_revision(
        manifest=manifest,
        object_ref=_chapter_ref(),
    )
    return str(dict(revision.data_json).get("title"))


def _seed_story_runtime(retrieval_session, *, story_id: str):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id=story_id,
        source_workspace_id=f"workspace-{story_id}",
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
    chapter = service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "foundation_digest": ["Foundation"],
            "blueprint_digest": ["Blueprint"],
            "current_outline_digest": ["Outline"],
            "recent_segment_digest": ["Segment"],
            "current_state_digest": ["State"],
        },
    )
    service.commit()
    refreshed_session = service.get_session(session.session_id)
    refreshed_chapter = service.get_chapter_workspace(chapter.chapter_workspace_id)
    assert refreshed_session is not None
    assert refreshed_chapter is not None
    return refreshed_session, refreshed_chapter, service
