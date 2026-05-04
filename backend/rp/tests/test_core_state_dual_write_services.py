"""Tests for Phase G dual-write services and integration points."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlmodel import select

from models.rp_core_state_store import (
    CoreStateAuthoritativeObjectRecord,
    CoreStateAuthoritativeRevisionRecord,
    CoreStateProjectionSlotRecord,
    CoreStateProjectionSlotRevisionRecord,
)
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import (
    MemoryDirtyTarget,
    MemoryRuntimeIdentity,
    MemorySourceRef,
)
from rp.models.memory_crud import ProposalSubmitInput
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.projection_refresh import (
    ProjectionRefreshRequest,
    ProjectionRefreshServiceError,
)
from rp.models.story_runtime import LongformChapterPhase, SpecialistResultBundle
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_dual_write_service import CoreStateDualWriteService
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_refresh_service import ProjectionRefreshService
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.story_activation_service import StoryActivationService
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService


def _build_dual_write_service(retrieval_session) -> CoreStateDualWriteService:
    return CoreStateDualWriteService(
        repository=CoreStateStoreRepository(retrieval_session)
    )


def _projection_identity() -> MemoryRuntimeIdentity:
    return MemoryRuntimeIdentity(
        story_id="story-g-dual",
        session_id="session-g-dual",
        branch_head_id="branch-head-g-dual",
        turn_id="turn-g-dual",
        runtime_profile_snapshot_id="profile-snapshot-g-dual",
    )


def _projection_source_ref(*, revision: int) -> ObjectRef:
    return ObjectRef(
        object_id="chapter.current",
        layer=Layer.CORE_STATE_AUTHORITATIVE,
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
        scope="story",
        revision=revision,
    )


def _projection_refresh_request(
    *,
    base_revision: int | None = None,
    source_revision: int | None = None,
    dirty_targets: list[MemoryDirtyTarget] | None = None,
) -> ProjectionRefreshRequest:
    source_authoritative_refs = []
    if source_revision is not None:
        source_authoritative_refs = [_projection_source_ref(revision=source_revision)]
    return ProjectionRefreshRequest(
        identity=_projection_identity(),
        refresh_actor="worker.reviewer",
        refresh_reason="post_write",
        refresh_source_kind="post_write",
        refresh_source_ref="proposal-1",
        base_revision=base_revision,
        source_authoritative_refs=source_authoritative_refs,
        source_refs=[
            MemorySourceRef(
                source_type="retrieval_card",
                source_id="R1",
                layer="runtime_workspace",
                domain="chapter",
                block_id="chapter.runtime",
            )
        ],
        dirty_targets=dirty_targets or [],
    )


def _seed_story_runtime(retrieval_session):
    service = StorySessionService(retrieval_session)
    session = service.create_session(
        story_id="story-g-dual",
        source_workspace_id="workspace-g-dual",
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
            "foundation_digest": ["Found A"],
            "blueprint_digest": ["Blueprint A"],
            "current_outline_digest": ["Outline A"],
            "recent_segment_digest": ["Segment A"],
            "current_state_digest": ["State A"],
        },
    )
    service.commit()
    refreshed_session = service.get_session(session.session_id)
    refreshed_chapter = service.get_chapter_workspace(chapter.chapter_workspace_id)
    assert refreshed_session is not None
    assert refreshed_chapter is not None
    return refreshed_session, refreshed_chapter, service


@pytest.mark.asyncio
async def test_proposal_apply_service_dual_writes_authoritative_store(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
            core_state_dual_write_service=dual_write_service,
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id=session.story_id,
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
        submit_source="test",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )
    story_session_service.commit()

    apply_receipt = repository.list_apply_receipts_for_proposal(receipt.proposal_id)[0]
    current_row = retrieval_session.exec(
        select(CoreStateAuthoritativeObjectRecord).where(
            CoreStateAuthoritativeObjectRecord.session_id == session.session_id,
            CoreStateAuthoritativeObjectRecord.object_id == "chapter.current",
        )
    ).one()
    revisions = retrieval_session.exec(
        select(CoreStateAuthoritativeRevisionRecord)
        .where(
            CoreStateAuthoritativeRevisionRecord.session_id == session.session_id,
            CoreStateAuthoritativeRevisionRecord.object_id == "chapter.current",
        )
        .order_by(CoreStateAuthoritativeRevisionRecord.revision.asc())
    ).all()
    links = repository.list_apply_target_links_for_apply(apply_receipt.apply_id)

    assert apply_receipt.apply_backend == "dual_write"
    assert current_row.current_revision == 2
    assert current_row.data_json["title"] == "Chapter Two"
    assert current_row.latest_apply_id == apply_receipt.apply_id
    assert [item.revision for item in revisions] == [1, 2]
    assert revisions[0].revision_source_kind == "repair"
    assert revisions[1].revision_source_kind == "proposal_apply"
    assert links and links[0].revision == 2


@pytest.mark.asyncio
async def test_proposal_apply_service_write_switch_uses_formal_store_as_source(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    dual_write_service.seed_activation_state(session=session, chapter=chapter)

    stale_snapshot = dict(session.current_state_json or {})
    stale_snapshot["narrative_progress"] = {
        "current_phase": "outline_drafting",
        "accepted_segments": 99,
    }
    story_session_service.update_session(
        session_id=session.session_id,
        current_state_json=stale_snapshot,
    )

    repository = ProposalRepository(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
            core_state_dual_write_service=dual_write_service,
            core_state_store_write_switch_enabled=True,
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id=session.story_id,
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
        submit_source="test",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )
    story_session_service.commit()

    refreshed_session = story_session_service.get_session(session.session_id)
    assert refreshed_session is not None
    apply_receipt = repository.list_apply_receipts_for_proposal(receipt.proposal_id)[0]

    assert apply_receipt.apply_backend == "core_state_store"
    assert (
        apply_receipt.before_snapshot_json["narrative_progress"]["accepted_segments"]
        == 0
    )
    assert (
        refreshed_session.current_state_json["chapter_digest"]["title"] == "Chapter Two"
    )
    assert (
        refreshed_session.current_state_json["narrative_progress"]["accepted_segments"]
        == 0
    )


@pytest.mark.asyncio
async def test_proposal_apply_service_write_switch_seeds_before_base_revision_check(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    workflow = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=ProposalApplyService(
            story_session_service=story_session_service,
            proposal_repository=repository,
            story_state_apply_service=StoryStateApplyService(),
            core_state_dual_write_service=dual_write_service,
            core_state_store_write_switch_enabled=True,
        ),
        post_write_apply_handler=PostWriteApplyHandler(),
    )

    receipt = await workflow.submit_and_route(
        ProposalSubmitInput(
            story_id=session.story_id,
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
                    "field_patch": {"title": "Seeded Before Check"},
                }
            ],
            base_refs=[
                {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE,
                    "domain": Domain.CHAPTER,
                    "domain_path": "chapter.current",
                    "scope": "story",
                    "revision": 1,
                }
            ],
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        submit_source="test",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )

    current_row = retrieval_session.exec(
        select(CoreStateAuthoritativeObjectRecord).where(
            CoreStateAuthoritativeObjectRecord.session_id == session.session_id,
            CoreStateAuthoritativeObjectRecord.object_id == "chapter.current",
        )
    ).one()
    revisions = retrieval_session.exec(
        select(CoreStateAuthoritativeRevisionRecord)
        .where(
            CoreStateAuthoritativeRevisionRecord.session_id == session.session_id,
            CoreStateAuthoritativeRevisionRecord.object_id == "chapter.current",
        )
        .order_by(CoreStateAuthoritativeRevisionRecord.revision.asc())
    ).all()
    apply_receipt = repository.list_apply_receipts_for_proposal(receipt.proposal_id)[0]

    assert receipt.status == "applied"
    assert apply_receipt.apply_backend == "core_state_store"
    assert apply_receipt.revision_after_json["chapter.current"] == 2
    assert current_row.current_revision == 2
    assert current_row.data_json["title"] == "Seeded Before Check"
    assert [item.revision for item in revisions] == [1, 2]
    assert revisions[0].revision_source_kind == "write_switch_seed"
    assert revisions[1].revision_source_kind == "proposal_apply"


def test_projection_refresh_service_dual_writes_formal_projection_store(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    original_authoritative_snapshot = deepcopy(session.current_state_json or {})
    dual_write_service = _build_dual_write_service(retrieval_session)
    refresh_service = ProjectionRefreshService(
        story_session_service,
        core_state_dual_write_service=dual_write_service,
    )

    updated_chapter = refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
    )

    current_rows = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id
            == updated_chapter.chapter_workspace_id
        )
    ).all()
    outline_row = next(
        item
        for item in current_rows
        if item.summary_id == "projection.current_outline_digest"
    )
    revisions = retrieval_session.exec(
        select(CoreStateProjectionSlotRevisionRecord).where(
            CoreStateProjectionSlotRevisionRecord.chapter_workspace_id
            == updated_chapter.chapter_workspace_id,
            CoreStateProjectionSlotRevisionRecord.summary_id
            == "projection.current_outline_digest",
        )
    ).all()
    refreshed_session = story_session_service.get_session(session.session_id)

    assert len(current_rows) == 5
    assert refreshed_session is not None
    assert refreshed_session.current_state_json == original_authoritative_snapshot
    assert outline_row.current_revision == 1
    assert outline_row.items_json == ["New Outline"]
    assert outline_row.metadata_json["layer_family"] == "core_state.derived_projection"
    assert (
        outline_row.metadata_json["semantic_layer"] == "Core State.derived_projection"
    )
    assert outline_row.metadata_json["projection_role"] == "current_projection"
    assert outline_row.metadata_json["materialization_event"] == "projection_refresh"
    assert outline_row.metadata_json["maintenance_event"] == "bundle_refresh"
    assert outline_row.metadata_json["authoritative_mutation"] is False
    assert len(revisions) == 1
    assert revisions[0].refresh_source_kind == "bundle_refresh"
    assert (
        revisions[0].metadata_json["semantic_layer"] == "Core State.derived_projection"
    )
    assert revisions[0].metadata_json["projection_role"] == "current_projection"
    assert revisions[0].metadata_json["authoritative_mutation"] is False


def test_projection_refresh_service_records_freshness_metadata_and_dirty_targets(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    dual_write_service.seed_activation_state(session=session, chapter=chapter)
    refresh_service = ProjectionRefreshService(
        story_session_service,
        core_state_dual_write_service=dual_write_service,
    )
    request = _projection_refresh_request(
        base_revision=1,
        source_revision=1,
        dirty_targets=[
            MemoryDirtyTarget(
                target_kind="packet_window",
                target_id="writer.packet.current",
                domain="chapter",
                reason="projection_refresh",
            )
        ],
    )

    updated_chapter = refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
        refresh_request=request,
    )

    outline_row = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id
            == updated_chapter.chapter_workspace_id,
            CoreStateProjectionSlotRecord.summary_id
            == "projection.current_outline_digest",
        )
    ).one()
    revision_row = retrieval_session.exec(
        select(CoreStateProjectionSlotRevisionRecord)
        .where(
            CoreStateProjectionSlotRevisionRecord.chapter_workspace_id
            == updated_chapter.chapter_workspace_id,
            CoreStateProjectionSlotRevisionRecord.summary_id
            == "projection.current_outline_digest",
        )
        .order_by(CoreStateProjectionSlotRevisionRecord.revision.desc())
    ).first()
    assert revision_row is not None

    assert outline_row.current_revision == 2
    assert outline_row.metadata_json["refresh_actor"] == "worker.reviewer"
    assert outline_row.metadata_json["refresh_reason"] == "post_write"
    assert outline_row.metadata_json["base_revision"] == 1
    assert outline_row.metadata_json["projection_dirty_state"] == "dirty"
    assert outline_row.metadata_json["source_authoritative_refs"][0]["revision"] == 1
    assert (
        outline_row.metadata_json["source_refs"][0]["source_type"] == "retrieval_card"
    )
    assert (
        outline_row.metadata_json["dirty_targets"][0]["target_kind"] == "packet_window"
    )
    assert revision_row.metadata_json["refresh_actor"] == "worker.reviewer"
    assert revision_row.revision == 2
    assert revision_row.metadata_json["base_revision"] == 1


def test_projection_refresh_service_rejects_stale_base_revision_before_write(
    retrieval_session,
):
    _, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    session = story_session_service.get_session(chapter.session_id)
    assert session is not None
    dual_write_service.seed_activation_state(session=session, chapter=chapter)
    refresh_service = ProjectionRefreshService(
        story_session_service,
        core_state_dual_write_service=dual_write_service,
    )

    with pytest.raises(ProjectionRefreshServiceError) as exc:
        refresh_service.refresh_from_bundle(
            chapter=chapter,
            bundle=SpecialistResultBundle(
                foundation_digest=["New Found"],
                blueprint_digest=["New Blueprint"],
                current_outline_digest=["New Outline"],
                recent_segment_digest=["New Segment"],
                current_state_digest=["New State"],
            ),
            refresh_request=_projection_refresh_request(
                base_revision=0,
                source_revision=1,
            ),
        )

    assert exc.value.code == "projection_refresh_base_revision_conflict"


def test_projection_refresh_service_rejects_stale_source_revision_before_write(
    retrieval_session,
):
    _, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    session = story_session_service.get_session(chapter.session_id)
    assert session is not None
    dual_write_service.seed_activation_state(session=session, chapter=chapter)
    refresh_service = ProjectionRefreshService(
        story_session_service,
        core_state_dual_write_service=dual_write_service,
    )

    with pytest.raises(ProjectionRefreshServiceError) as exc:
        refresh_service.refresh_from_bundle(
            chapter=chapter,
            bundle=SpecialistResultBundle(
                foundation_digest=["New Found"],
                blueprint_digest=["New Blueprint"],
                current_outline_digest=["New Outline"],
                recent_segment_digest=["New Segment"],
                current_state_digest=["New State"],
            ),
            refresh_request=_projection_refresh_request(
                base_revision=1,
                source_revision=2,
            ),
        )

    assert exc.value.code == "projection_refresh_source_revision_conflict"


def test_projection_refresh_service_emits_shared_event_when_identity_is_supplied(
    retrieval_session,
):
    _, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    event_service = MemoryChangeEventService()
    refresh_service = ProjectionRefreshService(
        story_session_service,
        memory_change_event_service=event_service,
    )
    request = _projection_refresh_request(
        dirty_targets=[
            MemoryDirtyTarget(
                target_kind="packet_window",
                target_id="writer.packet.current",
                domain="chapter",
                reason="projection_refresh",
            )
        ],
    )

    refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
        refresh_request=request,
    )

    assert request.identity is not None
    events = event_service.list_events(identity=request.identity)
    assert len(events) == 1
    assert events[0].event_kind == "projection_refreshed"
    assert events[0].dirty_targets[0].target_kind == "packet_window"


def test_projection_refresh_service_allows_repeated_shared_events_for_same_identity(
    retrieval_session,
):
    _, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    event_service = MemoryChangeEventService()
    refresh_service = ProjectionRefreshService(
        story_session_service,
        memory_change_event_service=event_service,
    )
    request = _projection_refresh_request()

    refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
        refresh_request=request,
    )
    refresh_service.refresh_from_bundle(
        chapter=chapter,
        bundle=SpecialistResultBundle(
            foundation_digest=["New Found"],
            blueprint_digest=["New Blueprint"],
            current_outline_digest=["New Outline"],
            recent_segment_digest=["New Segment"],
            current_state_digest=["New State"],
        ),
        refresh_request=request,
    )

    events = event_service.list_events(identity=request.identity)
    assert len(events) == 2
    assert events[0].event_id != events[1].event_id
    assert [event.event_kind for event in events] == [
        "projection_refreshed",
        "projection_refreshed",
    ]


def test_projection_state_service_dual_writes_lifecycle_projection_updates(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    dual_write_service.seed_activation_state(session=session, chapter=chapter)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_dual_write_service=dual_write_service,
    )

    projection_state_service.set_current_outline(
        chapter_workspace_id=chapter.chapter_workspace_id,
        outline_text="Fresh Outline",
    )
    projection_state_service.append_recent_segment(
        chapter_workspace_id=chapter.chapter_workspace_id,
        excerpt="Segment B",
    )

    outline_row = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id
            == chapter.chapter_workspace_id,
            CoreStateProjectionSlotRecord.summary_id
            == "projection.current_outline_digest",
        )
    ).one()
    recent_segment_row = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id
            == chapter.chapter_workspace_id,
            CoreStateProjectionSlotRecord.summary_id
            == "projection.recent_segment_digest",
        )
    ).one()

    assert outline_row.current_revision == 3
    assert outline_row.items_json == ["Fresh Outline"]
    assert recent_segment_row.current_revision == 3
    assert recent_segment_row.items_json == ["Segment A", "Segment B"]


def test_projection_state_service_write_switch_uses_formal_store_as_source(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)
    dual_write_service.seed_activation_state(session=session, chapter=chapter)

    stale_snapshot = dict(chapter.builder_snapshot_json or {})
    stale_snapshot["recent_segment_digest"] = ["Stale Segment"]
    story_session_service.update_chapter_workspace(
        chapter_workspace_id=chapter.chapter_workspace_id,
        builder_snapshot_json=stale_snapshot,
    )

    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_dual_write_service=dual_write_service,
        core_state_store_write_switch_enabled=True,
    )

    projection_state_service.append_recent_segment(
        chapter_workspace_id=chapter.chapter_workspace_id,
        excerpt="Segment B",
    )
    story_session_service.commit()

    updated_chapter = story_session_service.get_chapter_workspace(
        chapter.chapter_workspace_id
    )
    assert updated_chapter is not None
    recent_segment_row = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.chapter_workspace_id
            == chapter.chapter_workspace_id,
            CoreStateProjectionSlotRecord.summary_id
            == "projection.recent_segment_digest",
        )
    ).one()

    assert recent_segment_row.current_revision == 2
    assert recent_segment_row.items_json == ["Segment A", "Segment B"]
    assert updated_chapter.builder_snapshot_json["recent_segment_digest"] == [
        "Segment A",
        "Segment B",
    ]


def test_story_activation_service_dual_writes_formal_seed_rows(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    dual_write_service = _build_dual_write_service(retrieval_session)

    class _Dumpable:
        def __init__(self, payload):
            self._payload = payload

        def model_dump(self, mode="json"):
            return dict(self._payload)

    workspace = SimpleNamespace(
        workspace_id="workspace-activation",
        activated_story_session_id=None,
        accepted_commits=[
            SimpleNamespace(
                step_id=SimpleNamespace(value="foundation"),
                summary_tier_1="Found A",
                summary_tier_0=None,
                commit_id="commit-1",
            )
        ],
        longform_blueprint_draft=SimpleNamespace(
            premise="Premise",
            central_conflict="Conflict",
            protagonist_arc="Arc",
            chapter_strategy="Strategy",
            ending_direction="Ending",
            chapter_blueprints=[
                SimpleNamespace(
                    title="Chapter One",
                    purpose="Goal",
                    major_beats=["Beat 1", "Beat 2"],
                )
            ],
        ),
        story_config_draft=SimpleNamespace(notes="Notes"),
    )
    handoff = SimpleNamespace(
        story_id="story-activation",
        workspace_id="workspace-activation",
        mode=SimpleNamespace(value="longform"),
        runtime_story_config=_Dumpable({}),
        writer_contract=_Dumpable({}),
    )

    class _FakeSetupController:
        def run_activation_check(self, *, workspace_id: str):
            assert workspace_id == "workspace-activation"
            return SimpleNamespace(ready=True, handoff=handoff, blocking_issues=[])

    class _FakeWorkspaceService:
        def __init__(self):
            self.activated_session_id = None

        def get_workspace(self, workspace_id: str):
            assert workspace_id == "workspace-activation"
            return workspace

        def mark_activated_story_session(self, *, workspace_id: str, session_id: str):
            assert workspace_id == "workspace-activation"
            workspace.activated_story_session_id = session_id
            self.activated_session_id = session_id

    activation_service = StoryActivationService(
        setup_controller=_FakeSetupController(),
        workspace_service=_FakeWorkspaceService(),
        story_session_service=story_session_service,
        core_state_dual_write_service=dual_write_service,
    )

    result = activation_service.activate_workspace(workspace_id="workspace-activation")

    authoritative_rows = retrieval_session.exec(
        select(CoreStateAuthoritativeObjectRecord).where(
            CoreStateAuthoritativeObjectRecord.session_id == result.session_id
        )
    ).all()
    projection_rows = retrieval_session.exec(
        select(CoreStateProjectionSlotRecord).where(
            CoreStateProjectionSlotRecord.session_id == result.session_id
        )
    ).all()

    assert len(authoritative_rows) == 6
    assert len(projection_rows) == 5
