"""Controller-level tests for story runtime memory read side."""

from __future__ import annotations

from typing import Any, cast
from types import SimpleNamespace

import pytest
from sqlmodel import select

from models.rp_story_store import RuntimeProfileSnapshotRecord
from rp.models.core_mutation import (
    CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT,
    CoreMutationEnvelope,
    DirectCoreEditRequest,
)
from rp.models.dsl import Domain, Layer, ObjectRef
from rp.models.memory_contract_registry import (
    MemoryChangeEvent,
    MemoryDirtyTarget,
    MemorySourceRef,
)
from rp.models.memory_crud import (
    MemoryBlockProposalSubmitRequest,
    ProposalSubmitInput,
)
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.runtime_workspace_material import (
    RuntimeWorkspaceMaterial,
    RuntimeWorkspaceMaterialKind,
    RuntimeWorkspaceMaterialLifecycle,
    RuntimeWorkspaceMaterialVisibility,
)
from rp.models.setup_workspace import StoryMode
from rp.models.story_runtime import (
    LongformChapterPhase,
    LongformTurnCommandKind,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.models.runtime_identity import StoryTurnStatus
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.memory_change_event_service import MemoryChangeEventService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.projection_read_service import ProjectionReadService
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.runtime_profile_snapshot_service import RuntimeProfileSnapshotService
from rp.services.runtime_workflow_job_service import RuntimeWorkflowJobService
from rp.services.runtime_workspace_material_service import (
    RuntimeWorkspaceMaterialService,
)
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.setup_workspace_service import SetupWorkspaceService
from rp.services.story_activation_service import StoryActivationService
from rp.services.story_block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    StoryBlockMutationService,
)
from rp.services.story_runtime_controller import (
    MemoryBlockHistoryUnsupportedError,
    StoryRuntimeController,
)
from rp.services.story_runtime_debug_query_service import StoryRuntimeDebugQueryService
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_runtime_identity_service import StoryRuntimeIdentityService
from rp.services.story_runtime_migration_service import StoryRuntimeMigrationService
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.version_history_read_service import VersionHistoryReadService
from rp.services.memory_trace_read_service import MemoryTraceReadService


class _Dumpable(dict):
    def model_dump(self, *, mode: str = "json"):
        return dict(self)


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


async def _apply_authoritative_patch(retrieval_session):
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
    await workflow.submit_and_route(
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
        submit_source="test",
        policy=PostWriteMaintenancePolicy(
            preset_id="test",
            fallback_decision=PolicyDecision.NOTIFY_APPLY,
        ),
    )
    story_session_service.commit()
    return story_session_service, repository, session.session_id


def _build_controller(
    retrieval_session,
    story_session_service: StorySessionService,
    repository: ProposalRepository,
):
    core_state_adapter = StorySessionCoreStateAdapter(story_session_service)
    core_repo = CoreStateStoreRepository(retrieval_session)
    projection_adapter = ChapterWorkspaceProjectionAdapter(story_session_service)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=projection_adapter,
    )
    builder_projection_context_service = BuilderProjectionContextService(
        projection_state_service
    )
    version_history_read_service = VersionHistoryReadService(
        adapter=core_state_adapter,
        proposal_repository=repository,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    provenance_read_service = ProvenanceReadService(
        adapter=core_state_adapter,
        proposal_repository=repository,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    projection_read_service = ProjectionReadService(
        adapter=projection_adapter,
        core_state_store_repository=core_repo,
        store_read_enabled=True,
    )
    memory_inspection_read_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        proposal_repository=repository,
        version_history_read_service=version_history_read_service,
    )
    proposal_apply_service = ProposalApplyService(
        story_session_service=story_session_service,
        proposal_repository=repository,
        story_state_apply_service=StoryStateApplyService(),
    )
    proposal_workflow_service = ProposalWorkflowService(
        proposal_repository=repository,
        proposal_apply_service=proposal_apply_service,
        post_write_apply_handler=PostWriteApplyHandler(),
    )
    rp_block_read_service = RpBlockReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        core_state_store_repository=core_repo,
        memory_inspection_read_service=memory_inspection_read_service,
        store_read_enabled=True,
    )
    block_mutation_service = StoryBlockMutationService(
        story_session_service=story_session_service,
        rp_block_read_service=rp_block_read_service,
        memory_inspection_read_service=memory_inspection_read_service,
        proposal_apply_service=proposal_apply_service,
        proposal_workflow_service=proposal_workflow_service,
    )
    debug_query_service = StoryRuntimeDebugQueryService(
        session=retrieval_session,
        story_session_service=story_session_service,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
        memory_trace_read_service=MemoryTraceReadService(session=retrieval_session),
        runtime_workflow_job_service=RuntimeWorkflowJobService(retrieval_session),
    )
    return StoryRuntimeController(
        story_session_service=story_session_service,
        story_activation_service=cast(Any, SimpleNamespace()),
        version_history_read_service=version_history_read_service,
        provenance_read_service=provenance_read_service,
        projection_read_service=projection_read_service,
        memory_inspection_read_service=memory_inspection_read_service,
        rp_block_read_service=rp_block_read_service,
        story_block_mutation_service=block_mutation_service,
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
        story_runtime_debug_query_service=debug_query_service,
        story_runtime_migration_service=StoryRuntimeMigrationService(
            debug_query_service=debug_query_service,
        ),
    )


def _build_runtime_identity(retrieval_session, *, session_id: str):
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session_id,
        created_from="test.story_runtime_controller.direct_edit",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    return identity_service.resolve_runtime_entry_identity(
        session_id=session_id,
        command_kind="write_next_segment",
        actor="memory_direct_edit_test",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )


@pytest.mark.asyncio
async def test_story_runtime_controller_exposes_memory_read_side(retrieval_session):
    story_session_service, repository, session_id = await _apply_authoritative_patch(
        retrieval_session
    )
    controller = _build_controller(retrieval_session, story_session_service, repository)
    session = story_session_service.get_session(session_id)
    chapter = story_session_service.get_current_chapter(session_id)
    core_repo = CoreStateStoreRepository(retrieval_session)
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        metadata_json={
            "test_marker": "controller_block",
            "read_only": True,
            "mutation_mode": "wrong_mode_from_store",
            "history_mode": "wrong_history_from_store",
            "proposal_visibility": "wrong_visibility_from_store",
        },
        latest_apply_id="apply-controller-block",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        revision_source_kind="controller_test",
        source_apply_id="apply-controller-block",
        metadata_json={"test_marker": "controller_block_revision"},
    )
    projection_row = core_repo.upsert_projection_slot(
        story_id=session.story_id,
        session_id=session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        current_revision=4,
        items_json=["Block outline"],
        metadata_json={
            "test_marker": "controller_block_projection",
            "read_only": False,
            "mutation_mode": "wrong_mode_from_store",
            "history_mode": "wrong_history_from_store",
            "proposal_visibility": "wrong_visibility_from_store",
        },
        last_refresh_kind="controller_test_refresh",
        payload_schema_ref="schema://core-state/projection-slot",
    )
    core_repo.upsert_projection_slot_revision(
        projection_slot_id=projection_row.projection_slot_id,
        story_id=session.story_id,
        session_id=session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        revision=4,
        items_json=["Block outline"],
        refresh_source_kind="controller_test_refresh",
        refresh_source_ref="artifact:outline",
        metadata_json={"test_marker": "controller_block_projection_revision"},
    )
    unrelated_receipt = repository.create_proposal(
        input_model=ProposalSubmitInput(
            story_id="story-1",
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.unrelated",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.unrelated",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.unrelated",
                    },
                    "field_patch": {"title": "Wrong Block"},
                }
            ],
        ),
        status="applied",
        policy_decision="notify_apply",
        submit_source="test",
        session_id=session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
    )

    authoritative_items = controller.list_memory_authoritative(session_id=session_id)
    projection_items = controller.list_memory_projection(session_id=session_id)
    block_items = controller.list_memory_blocks(session_id=session_id)
    authoritative_block_items = controller.list_memory_blocks(
        session_id=session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE,
    )
    core_store_block_items = controller.list_memory_blocks(
        session_id=session_id,
        source="core_state_store",
    )
    proposal_items = controller.list_memory_proposals(
        session_id=session_id, status="applied"
    )
    authoritative_block_proposals = controller.list_memory_block_proposals(
        session_id=session_id,
        block_id=authoritative_row.authoritative_object_id,
        status="applied",
    )
    projection_block_proposals = controller.list_memory_block_proposals(
        session_id=session_id,
        block_id=projection_row.projection_slot_id,
    )
    missing_block_proposals = controller.list_memory_block_proposals(
        session_id=session_id,
        block_id="missing-block",
    )
    versions = controller.read_memory_versions(
        session_id=session_id,
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )
    provenance = controller.read_memory_provenance(
        session_id=session_id,
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )
    authoritative_block_versions = await controller.read_memory_block_versions(
        session_id=session_id,
        block_id=authoritative_row.authoritative_object_id,
    )
    authoritative_block_provenance = await controller.read_memory_block_provenance(
        session_id=session_id,
        block_id=authoritative_row.authoritative_object_id,
    )
    projection_block_versions = await controller.read_memory_block_versions(
        session_id=session_id,
        block_id=projection_row.projection_slot_id,
    )
    projection_block_provenance = await controller.read_memory_block_provenance(
        session_id=session_id,
        block_id=projection_row.projection_slot_id,
    )
    overview = controller.read_memory_overview(session_id=session_id)

    chapter_item = next(
        item
        for item in authoritative_items
        if item["object_ref"]["object_id"] == "chapter.current"
    )
    authoritative_block = next(
        item
        for item in block_items
        if item["block_id"] == authoritative_row.authoritative_object_id
    )
    projection_block = next(
        item
        for item in block_items
        if item["block_id"] == projection_row.projection_slot_id
    )
    read_authoritative_block = controller.get_memory_block(
        session_id=session_id,
        block_id=authoritative_row.authoritative_object_id,
    )
    assert chapter_item["data"]["title"] == "Chapter Two"
    assert any(
        item["slot_name"] == "current_outline_digest" for item in projection_items
    )
    assert read_authoritative_block == authoritative_block
    assert (
        controller.get_memory_block(session_id=session_id, block_id="missing-block")
        is None
    )
    assert all(
        item["layer"] == Layer.CORE_STATE_AUTHORITATIVE.value
        for item in authoritative_block_items
    )
    assert authoritative_block in core_store_block_items
    assert projection_block in core_store_block_items
    assert all(item["source"] == "core_state_store" for item in core_store_block_items)
    assert authoritative_block == {
        "block_id": authoritative_row.authoritative_object_id,
        "label": "chapter.current",
        "layer": Layer.CORE_STATE_AUTHORITATIVE.value,
        "domain": Domain.CHAPTER.value,
        "domain_path": "chapter.current",
        "scope": "story",
        "revision": 3,
        "source": "core_state_store",
        "payload_schema_ref": "schema://core-state/chapter-current",
        "data_json": {"current_chapter": 1, "title": "Block Store Chapter"},
        "items_json": None,
        "metadata": {
            "test_marker": "controller_block",
            "route": "core_state_store",
            "source": "core_state_store",
            "source_table": "rp_core_state_authoritative_objects",
            "source_row_id": authoritative_row.authoritative_object_id,
            "story_id": session.story_id,
            "session_id": session_id,
            "latest_apply_id": "apply-controller-block",
            "updated_at": authoritative_block["metadata"]["updated_at"],
            "read_only": False,
            "mutation_mode": "governed_proposal_apply",
            "history_mode": "supported",
            "proposal_visibility": "supported",
        },
    }
    assert projection_block == {
        "block_id": projection_row.projection_slot_id,
        "label": "projection.current_outline_digest",
        "layer": Layer.CORE_STATE_PROJECTION.value,
        "domain": Domain.CHAPTER.value,
        "domain_path": "projection.current_outline_digest",
        "scope": "chapter",
        "revision": 4,
        "source": "core_state_store",
        "payload_schema_ref": "schema://core-state/projection-slot",
        "data_json": None,
        "items_json": ["Block outline"],
        "metadata": {
            "test_marker": "controller_block_projection",
            "route": "core_state_store",
            "source": "core_state_store",
            "source_field": "current_outline_digest",
            "source_table": "rp_core_state_projection_slots",
            "source_row_id": projection_row.projection_slot_id,
            "story_id": session.story_id,
            "session_id": session_id,
            "chapter_workspace_id": chapter.chapter_workspace_id,
            "last_refresh_kind": "controller_test_refresh",
            "updated_at": projection_block["metadata"]["updated_at"],
            "read_only": True,
            "mutation_mode": "unsupported_projection_read_side",
            "history_mode": "supported",
            "proposal_visibility": "empty",
        },
    }
    assert proposal_items
    assert authoritative_block_proposals is not None
    assert len(authoritative_block_proposals) == 1
    assert (
        authoritative_block_proposals[0]["proposal_id"] != unrelated_receipt.proposal_id
    )
    assert authoritative_block_proposals[0]["status"] == "applied"
    assert projection_block_proposals == []
    assert missing_block_proposals is None

    with pytest.raises(
        MemoryBlockMutationUnsupportedError,
        match="authoritative blocks",
    ):
        controller.get_memory_block_proposal(
            session_id=session_id,
            block_id=projection_row.projection_slot_id,
            proposal_id="missing-proposal",
        )

    assert versions.current_ref == "chapter.current@3"
    assert provenance.source_refs == ["core_state_store:authoritative_revision"]
    assert authoritative_block_versions is not None
    assert authoritative_block_versions.current_ref == "chapter.current@3"
    assert authoritative_block_provenance is not None
    assert authoritative_block_provenance.target_ref.object_id == "chapter.current"
    assert authoritative_block_provenance.target_ref.revision == 3
    assert authoritative_block_provenance.source_refs == [
        "core_state_store:authoritative_revision"
    ]
    assert projection_block_versions is not None
    assert (
        projection_block_versions.current_ref == "projection.current_outline_digest@4"
    )
    assert projection_block_provenance is not None
    assert projection_block_provenance.target_ref.object_id == (
        "projection.current_outline_digest"
    )
    assert projection_block_provenance.target_ref.layer == Layer.CORE_STATE_PROJECTION
    assert projection_block_provenance.target_ref.revision == 4
    assert projection_block_provenance.source_refs == [
        "core_state_store:projection_slot_revision"
    ]
    assert overview["session_id"] == session_id
    assert overview["story_id"] == session.story_id
    assert overview["blocks"]["total"] == len(block_items)
    assert overview["blocks"]["by_layer"][Layer.CORE_STATE_AUTHORITATIVE.value] >= 1
    assert overview["blocks"]["by_layer"][Layer.CORE_STATE_PROJECTION.value] >= 1
    assert overview["blocks"]["by_source"]["core_state_store"] >= 2
    assert overview["layers"][Layer.CORE_STATE_AUTHORITATIVE.value]["mutation"] == (
        "governed_proposal_apply"
    )
    assert overview["layers"][Layer.RUNTIME_WORKSPACE.value]["mutation"] == (
        "unsupported_read_only"
    )
    assert overview["layers"][Layer.RECALL.value]["read_surface"] == (
        "memory.search_recall"
    )
    assert overview["proposals"]["by_status"]["applied"] >= 1
    assert overview["consumers"] == {
        "total": 0,
        "dirty": 0,
        "dirty_consumer_keys": [],
        "items": [],
    }
    assert "overview_does_not_sync_or_compile_consumers" in overview["boundaries"]


@pytest.mark.asyncio
async def test_story_runtime_controller_memory_reads_stay_session_scoped(
    retrieval_session,
):
    story_session_service, repository, session_id = await _apply_authoritative_patch(
        retrieval_session
    )
    story_session_service.create_session(
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
    story_session_service.commit()
    controller = _build_controller(retrieval_session, story_session_service, repository)

    versions = controller.read_memory_versions(
        session_id=session_id,
        object_id="chapter.current",
        domain=Domain.CHAPTER,
        domain_path="chapter.current",
    )

    assert versions.current_ref == "chapter.current@2"


@pytest.mark.asyncio
async def test_story_runtime_controller_exposes_runtime_workspace_blocks_as_read_only_views(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    draft_artifact = story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.DRAFT,
        content_text="Draft runtime outline",
        metadata={"command_kind": "generate_outline"},
        revision=2,
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.CHAPTER_OUTLINE,
        status=StoryArtifactStatus.ACCEPTED,
        content_text="Accepted outline should stay outside runtime workspace blocks",
        metadata={"command_kind": "accept_outline"},
        revision=3,
    )
    discussion_entry = story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="user",
        content_text="Can we make the opening threat more visible?",
        linked_artifact_id=draft_artifact.artifact_id,
    )

    runtime_items = controller.list_memory_blocks(
        session_id=session.session_id,
        layer=Layer.RUNTIME_WORKSPACE,
    )
    runtime_source_items = controller.list_memory_blocks(
        session_id=session.session_id,
        source="runtime_workspace_store",
    )
    runtime_artifact_block_id = (
        f"runtime_workspace:artifact:{draft_artifact.artifact_id}"
    )
    runtime_discussion_block_id = (
        f"runtime_workspace:discussion:{discussion_entry.entry_id}"
    )
    runtime_artifact_block = controller.get_memory_block(
        session_id=session.session_id,
        block_id=runtime_artifact_block_id,
    )
    runtime_discussion_block = controller.get_memory_block(
        session_id=session.session_id,
        block_id=runtime_discussion_block_id,
    )
    runtime_artifact_proposals = controller.list_memory_block_proposals(
        session_id=session.session_id,
        block_id=runtime_artifact_block_id,
    )
    runtime_discussion_proposals = controller.list_memory_block_proposals(
        session_id=session.session_id,
        block_id=runtime_discussion_block_id,
    )

    assert {item["block_id"] for item in runtime_items} == {
        runtime_artifact_block_id,
        runtime_discussion_block_id,
    }
    assert all(
        item["source"] == "runtime_workspace_store" for item in runtime_source_items
    )
    assert runtime_artifact_block is not None
    assert runtime_discussion_block is not None
    assert runtime_artifact_block["data_json"]["artifact_kind"] == (
        StoryArtifactKind.CHAPTER_OUTLINE.value
    )
    assert runtime_artifact_block["data_json"]["status"] == (
        StoryArtifactStatus.DRAFT.value
    )
    assert runtime_artifact_block["data_json"]["scene_ref"] is None
    assert runtime_artifact_block["metadata"]["route"] == (
        "story_session_runtime.artifacts"
    )
    assert runtime_artifact_block["metadata"]["scene_ref"] is None
    assert runtime_artifact_block["metadata"]["read_only"] is True
    assert runtime_artifact_block["metadata"]["mutation_mode"] == (
        "unsupported_runtime_workspace_scratch"
    )
    assert runtime_artifact_block["metadata"]["history_mode"] == "unsupported"
    assert runtime_artifact_block["metadata"]["proposal_visibility"] == "empty"
    assert runtime_discussion_block["data_json"]["role"] == "user"
    assert runtime_discussion_block["data_json"]["linked_artifact_id"] == (
        draft_artifact.artifact_id
    )
    assert runtime_discussion_block["data_json"]["scene_ref"] == "chapter:1:scene:1"
    assert runtime_discussion_block["metadata"]["route"] == (
        "story_session_runtime.discussion_entries"
    )
    assert runtime_discussion_block["metadata"]["scene_ref"] == "chapter:1:scene:1"
    assert runtime_discussion_block["metadata"]["read_only"] is True
    assert runtime_discussion_block["metadata"]["mutation_mode"] == (
        "unsupported_runtime_workspace_scratch"
    )
    assert runtime_discussion_block["metadata"]["history_mode"] == "unsupported"
    assert runtime_discussion_block["metadata"]["proposal_visibility"] == "empty"
    assert runtime_artifact_proposals == []
    assert runtime_discussion_proposals == []

    with pytest.raises(
        MemoryBlockMutationUnsupportedError,
        match="authoritative blocks",
    ):
        controller.get_memory_block_proposal(
            session_id=session.session_id,
            block_id=runtime_artifact_block_id,
            proposal_id="missing-proposal",
        )

    with pytest.raises(
        MemoryBlockHistoryUnsupportedError,
        match=Layer.RUNTIME_WORKSPACE.value,
    ):
        await controller.read_memory_block_versions(
            session_id=session.session_id,
            block_id=runtime_artifact_block_id,
        )
    with pytest.raises(
        MemoryBlockHistoryUnsupportedError,
        match=Layer.RUNTIME_WORKSPACE.value,
    ):
        await controller.read_memory_block_provenance(
            session_id=session.session_id,
            block_id=runtime_discussion_block_id,
        )


@pytest.mark.asyncio
async def test_story_runtime_controller_submits_authoritative_block_proposals(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    core_repo = CoreStateStoreRepository(retrieval_session)
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        metadata_json={"test_marker": "controller_block_mutation"},
        latest_apply_id="apply-controller-block",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        revision_source_kind="controller_test",
        source_apply_id="apply-controller-block",
        metadata_json={"test_marker": "controller_block_mutation_revision"},
    )

    receipt = await controller.submit_memory_block_proposal(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        payload=MemoryBlockProposalSubmitRequest(
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                    },
                    "field_patch": {"title": "Governed Chapter"},
                }
            ],
            reason="controller governed mutation",
        ),
    )
    proposal_input = repository.get_proposal_input(receipt["proposal_id"])
    proposal_items = controller.list_memory_block_proposals(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        status="review_required",
    )

    assert receipt is not None
    assert receipt["status"] == "review_required"
    assert receipt["domain"] == Domain.CHAPTER.value
    assert proposal_input.reason == "controller governed mutation"
    normalized_ref = proposal_input.operations[0].target_ref
    assert normalized_ref.object_id == "chapter.current"
    assert normalized_ref.layer == Layer.CORE_STATE_AUTHORITATIVE
    assert normalized_ref.domain == Domain.CHAPTER
    assert normalized_ref.domain_path == "chapter.current"
    assert normalized_ref.scope == "story"
    assert normalized_ref.revision == 3
    assert proposal_items is not None
    assert receipt["proposal_id"] in {item["proposal_id"] for item in proposal_items}


@pytest.mark.asyncio
async def test_story_runtime_controller_reviews_and_applies_authoritative_block_proposals(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    core_repo = CoreStateStoreRepository(retrieval_session)
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        metadata_json={"test_marker": "controller_block_review_apply"},
        latest_apply_id="apply-controller-review",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        revision_source_kind="controller_test",
        source_apply_id="apply-controller-review",
        metadata_json={"test_marker": "controller_block_review_apply_revision"},
    )
    other_session = story_session_service.create_session(
        story_id=session.story_id,
        source_workspace_id="workspace-2",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Other Session"},
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
        session_id=other_session.session_id,
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
    review_required = repository.create_proposal(
        input_model=ProposalSubmitInput(
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
                    "field_patch": {"title": "Reviewed Chapter"},
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
            reason="controller review detail",
            trace_id="trace-controller-review",
        ),
        status="review_required",
        policy_decision="review_required",
        submit_source="test",
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
    )
    other_block = repository.create_proposal(
        input_model=ProposalSubmitInput(
            story_id=session.story_id,
            mode="longform",
            domain=Domain.CHAPTER,
            domain_path="chapter.unrelated",
            operations=[
                {
                    "kind": "patch_fields",
                    "target_ref": {
                        "object_id": "chapter.unrelated",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.unrelated",
                    },
                    "field_patch": {"title": "Wrong Block"},
                }
            ],
        ),
        status="review_required",
        policy_decision="review_required",
        submit_source="test",
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
    )
    other_session_proposal = repository.create_proposal(
        input_model=ProposalSubmitInput(
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
                    "field_patch": {"title": "Wrong Session"},
                }
            ],
        ),
        status="review_required",
        policy_decision="review_required",
        submit_source="test",
        session_id=other_session.session_id,
        chapter_workspace_id=None,
    )

    detail = controller.get_memory_block_proposal(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        proposal_id=review_required.proposal_id,
    )
    applied_detail = controller.apply_memory_block_proposal(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        proposal_id=review_required.proposal_id,
    )
    proposal_items = controller.list_memory_block_proposals(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
    )
    replay_detail = controller.apply_memory_block_proposal(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        proposal_id=review_required.proposal_id,
    )

    assert detail is not None
    assert detail["proposal_id"] == review_required.proposal_id
    assert detail["status"] == "review_required"
    assert detail["policy_decision"] == "review_required"
    assert detail["reason"] == "controller review detail"
    assert detail["trace_id"] == "trace-controller-review"
    assert detail["error_message"] is None
    assert detail["operation_kinds"] == ["patch_fields"]
    assert detail["operations"][0]["field_patch"] == {"title": "Reviewed Chapter"}
    assert detail["base_refs"][0]["domain_path"] == "chapter.current"
    assert detail["apply_receipts"] == []

    assert applied_detail is not None
    assert applied_detail["status"] == "applied"
    assert applied_detail["applied_at"] is not None
    assert len(applied_detail["apply_receipts"]) == 1
    assert applied_detail["apply_receipts"][0]["target_refs"][0]["object_id"] == (
        "chapter.current"
    )
    assert applied_detail["apply_receipts"][0]["revision_after"]["chapter.current"] == 2
    assert any(
        item["proposal_id"] == review_required.proposal_id
        and item["status"] == "applied"
        for item in (proposal_items or [])
    )
    assert replay_detail == applied_detail
    assert (
        len(repository.list_apply_receipts_for_proposal(review_required.proposal_id))
        == 1
    )

    with pytest.raises(Exception, match=other_block.proposal_id):
        controller.get_memory_block_proposal(
            session_id=session.session_id,
            block_id=authoritative_row.authoritative_object_id,
            proposal_id=other_block.proposal_id,
        )
    with pytest.raises(Exception, match=other_session_proposal.proposal_id):
        controller.get_memory_block_proposal(
            session_id=session.session_id,
            block_id=authoritative_row.authoritative_object_id,
            proposal_id=other_session_proposal.proposal_id,
        )


@pytest.mark.asyncio
async def test_story_runtime_controller_direct_edit_routes_through_shared_kernel(
    retrieval_session,
):
    session, _chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    runtime_identity = _build_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
    )
    candidate_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    candidate_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="mat-worker-candidate-direct-edit",
            material_kind=RuntimeWorkspaceMaterialKind.WORKER_CANDIDATE,
            identity=runtime_identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.current",
            short_id="CAND1",
            payload={
                "candidate_patch": {"title": "Candidate Chapter"},
                "target_ref": {"domain_path": "chapter.current"},
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
            created_by="worker.specialist",
        )
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        metadata_json={"test_marker": "controller_direct_edit"},
        latest_apply_id="apply-controller-direct-edit",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        revision_source_kind="controller_test",
        source_apply_id="apply-controller-direct-edit",
        metadata_json={"test_marker": "controller_direct_edit_revision"},
    )

    receipt = await controller.direct_edit_memory_block(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        payload=DirectCoreEditRequest(
            identity=runtime_identity,
            actor="user.memory_editor",
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
                        "revision": 3,
                    },
                    "field_patch": {"title": "Direct Edited Chapter"},
                }
            ],
            base_refs=[
                {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE,
                    "domain": Domain.CHAPTER,
                    "domain_path": "chapter.current",
                    "scope": "story",
                    "revision": 3,
                }
            ],
            source_refs=[
                MemorySourceRef(
                    source_type="review_overlay",
                    source_id="overlay-1",
                    layer="runtime_workspace",
                    domain=Domain.CHAPTER.value,
                    block_id="chapter.current",
                )
            ],
            reason="user corrected chapter title",
        ),
    )

    proposal_record = repository.get_proposal_record(receipt["proposal_id"])
    apply_receipts = repository.list_apply_receipts_for_proposal(receipt["proposal_id"])
    updated_session = story_session_service.get_session(session.session_id)
    candidate = candidate_service.require_material(
        identity=runtime_identity,
        material_id="mat-worker-candidate-direct-edit",
    )
    events = MemoryChangeEventService(session=retrieval_session).list_events(
        identity=runtime_identity
    )
    core_events = [
        event
        for event in events
        if event.event_kind == "core_authoritative_mutation_applied"
    ]

    assert receipt is not None
    assert receipt["status"] == "applied"
    assert proposal_record is not None
    assert proposal_record.governance_metadata_json["core_mutation"]["origin_kind"] == (
        CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT
    )
    assert proposal_record.governance_metadata_json["core_mutation"]["actor"] == (
        "user.memory_editor"
    )
    assert len(apply_receipts) == 1
    assert (
        "core_mutation:origin_kind=user_direct_edit" in apply_receipts[0].warnings_json
    )
    assert (
        "core_mutation:invalidated_candidate=mat-worker-candidate-direct-edit"
        in apply_receipts[0].warnings_json
    )
    assert updated_session is not None
    assert updated_session.current_state_json["chapter_digest"]["title"] == (
        "Direct Edited Chapter"
    )
    assert candidate.lifecycle == RuntimeWorkspaceMaterialLifecycle.INVALIDATED
    assert len(core_events) == 1
    core_event = core_events[0]
    assert core_event.actor == "user.memory_editor"
    assert core_event.metadata["origin_kind"] == CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT
    assert core_event.metadata["projection_refresh"] == "stale_mark_only"
    assert core_event.metadata["invalidated_candidate_ids"] == [
        "mat-worker-candidate-direct-edit"
    ]
    assert any(
        ref.source_type == "review_overlay" and ref.source_id == "overlay-1"
        for ref in core_event.source_refs
    )
    dirty_targets_by_kind = {
        target.target_kind: target for target in core_event.dirty_targets
    }
    assert "core_authoritative_block" in dirty_targets_by_kind
    assert "projection_refresh_pending" in dirty_targets_by_kind
    assert (
        dirty_targets_by_kind["projection_refresh_pending"].metadata["refresh_state"]
        == "stale_mark_only"
    )
    assert any(
        event.event_kind == "runtime_workspace_material_lifecycle_updated"
        for event in events
    )


@pytest.mark.asyncio
async def test_story_runtime_controller_direct_edit_rejects_stale_base_revision(
    retrieval_session,
):
    session, _chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    runtime_identity = _build_runtime_identity(
        retrieval_session,
        session_id=session.session_id,
    )
    core_repo = CoreStateStoreRepository(retrieval_session)
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        metadata_json={"test_marker": "controller_direct_edit_conflict"},
        latest_apply_id="apply-controller-direct-edit-conflict",
        payload_schema_ref="schema://core-state/chapter-current",
    )
    core_repo.upsert_authoritative_revision(
        authoritative_object_id=authoritative_row.authoritative_object_id,
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        revision=3,
        data_json={"current_chapter": 1, "title": "Block Store Chapter"},
        revision_source_kind="controller_test",
        source_apply_id="apply-controller-direct-edit-conflict",
        metadata_json={"test_marker": "controller_direct_edit_conflict_revision"},
    )

    await controller.direct_edit_memory_block(
        session_id=session.session_id,
        block_id=authoritative_row.authoritative_object_id,
        payload=DirectCoreEditRequest(
            identity=runtime_identity,
            actor="user.memory_editor",
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
                        "revision": 3,
                    },
                    "field_patch": {"title": "Fresh Direct Edit"},
                }
            ],
            base_refs=[
                {
                    "object_id": "chapter.current",
                    "layer": Layer.CORE_STATE_AUTHORITATIVE,
                    "domain": Domain.CHAPTER,
                    "domain_path": "chapter.current",
                    "scope": "story",
                    "revision": 3,
                }
            ],
            reason="fresh direct edit",
        ),
    )

    with pytest.raises(ValueError, match="phase_e_apply_base_revision_conflict"):
        await controller.direct_edit_memory_block(
            session_id=session.session_id,
            block_id=authoritative_row.authoritative_object_id,
            payload=DirectCoreEditRequest(
                identity=runtime_identity,
                actor="user.memory_editor",
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
                            "revision": 3,
                        },
                        "field_patch": {"title": "Stale Direct Edit"},
                    }
                ],
                base_refs=[
                    {
                        "object_id": "chapter.current",
                        "layer": Layer.CORE_STATE_AUTHORITATIVE,
                        "domain": Domain.CHAPTER,
                        "domain_path": "chapter.current",
                        "scope": "story",
                        "revision": 3,
                    }
                ],
                reason="stale direct edit",
            ),
        )

    proposal_records = repository.list_proposals_for_story(session.story_id)
    assert proposal_records[-1].status == "failed"
    assert proposal_records[-1].error_message is not None
    assert proposal_records[-1].error_message.startswith(
        "phase_e_apply_base_revision_conflict"
    )


def test_story_activation_service_publishes_first_active_runtime_snapshot(
    retrieval_session,
):
    workspace_service = SetupWorkspaceService(retrieval_session)
    workspace = workspace_service.create_workspace(
        story_id="story-activation-snapshot",
        mode=StoryMode.LONGFORM,
    )
    handoff = SimpleNamespace(
        story_id="story-activation-snapshot",
        workspace_id=workspace.workspace_id,
        mode=SimpleNamespace(value="longform"),
        runtime_story_config=_Dumpable(
            {
                "retrieval_rerank_model_id": "rerank-activation",
                "retrieval_rerank_provider_id": "provider-activation",
            }
        ),
        writer_contract=_Dumpable({"style_rules": ["Tight"]}),
    )

    class _FakeSetupController:
        def run_activation_check(self, *, workspace_id: str):
            assert workspace_id == workspace.workspace_id
            return SimpleNamespace(ready=True, handoff=handoff, blocking_issues=[])

    activation_service = StoryActivationService(
        setup_controller=_FakeSetupController(),
        workspace_service=workspace_service,
        story_session_service=StorySessionService(retrieval_session),
        runtime_profile_snapshot_service=RuntimeProfileSnapshotService(
            retrieval_session
        ),
    )

    result = activation_service.activate_workspace(workspace_id=workspace.workspace_id)

    snapshots = retrieval_session.exec(
        select(RuntimeProfileSnapshotRecord).where(
            RuntimeProfileSnapshotRecord.session_id == result.session_id
        )
    ).all()

    assert len(snapshots) == 1
    assert snapshots[0].status == "active"
    assert snapshots[0].created_from == "story_runtime.activate_workspace"
    assert snapshots[0].activated_at is not None


def test_story_runtime_controller_patch_publishes_new_active_snapshot(
    retrieval_session,
):
    session, _, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    initial = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.runtime_config.initial",
    )
    retrieval_session.commit()

    snapshot = controller.update_runtime_story_config(
        session_id=session.session_id,
        patch={
            "retrieval_rerank_model_id": "rerank-patched",
            "retrieval_rerank_provider_id": "provider-patched",
        },
    )

    published = snapshot_service.require_active_snapshot(session_id=session.session_id)
    refreshed_initial = snapshot_service.require_snapshot(
        initial.runtime_profile_snapshot_id
    )
    refreshed_published = snapshot_service.require_snapshot(
        published.runtime_profile_snapshot_id
    )

    assert snapshot.session.session_id == session.session_id
    assert (
        snapshot.session.runtime_story_config["retrieval_rerank_model_id"]
        == "rerank-patched"
    )
    assert refreshed_initial.runtime_profile_snapshot_id != (
        refreshed_published.runtime_profile_snapshot_id
    )
    assert refreshed_initial.status == "superseded"
    assert refreshed_initial.superseded_at is not None
    assert refreshed_published.status == "active"
    assert refreshed_published.created_from == "story_runtime.runtime_config_patch"
    assert (
        refreshed_published.compiled_profile_json["retrieval_policy"]["rerank_model_id"]
        == "rerank-patched"
    )
    assert (
        refreshed_published.compiled_profile_json["retrieval_policy"][
            "rerank_provider_id"
        ]
        == "provider-patched"
    )


def test_story_runtime_controller_reads_runtime_inspection_bundle(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.runtime.inspect",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind="write_next_segment",
        actor="runtime.inspect.test",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    material_service = RuntimeWorkspaceMaterialService(
        session=retrieval_session,
        memory_change_event_service=MemoryChangeEventService(session=retrieval_session),
    )
    card_receipt = material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="inspect-card-r1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.runtime.retrieval.card",
            short_id="R1",
            payload={"summary": "Storm callback evidence", "query_id": "query-1"},
            visibility=RuntimeWorkspaceMaterialVisibility.WRITER_VISIBLE.value,
            created_by="runtime.inspect.test",
        )
    )
    usage_receipt = material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="inspect-usage-u1",
            material_kind=RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.runtime.retrieval.usage",
            short_id="U1",
            lifecycle=RuntimeWorkspaceMaterialLifecycle.USED,
            payload={
                "used_card_short_ids": ["R1"],
                "expanded_card_short_ids": [],
                "unused_card_short_ids": [],
                "used_card_material_ids": [card_receipt.material.material_id],
                "used_expanded_chunk_material_ids": [],
                "unused_card_material_ids": [],
                "missed_query_short_ids": [],
                "missed_query_material_ids": [],
                "knowledge_gaps": [],
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
            visibility=RuntimeWorkspaceMaterialVisibility.RUNTIME_PRIVATE.value,
            created_by="runtime.inspect.test",
        )
    )
    packet_ref = material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="inspect-packet-ref",
            material_kind=RuntimeWorkspaceMaterialKind.PACKET_REF,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.runtime.packet",
            payload={
                "packet_id": "packet-inspect-1",
                "runtime_read_manifest_id": "manifest-inspect-1",
                "packet_summary_metadata": {"section_counts": {"core_view_sections": 1}},
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
            created_by="runtime.inspect.test",
        )
    )
    worker_evidence = material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="inspect-worker-evidence",
            material_kind=RuntimeWorkspaceMaterialKind.WORKER_EVIDENCE_BUNDLE,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.runtime.worker.LongformMemoryWorker.evidence",
            payload={
                "worker_id": "LongformMemoryWorker",
                "trace_summary": {
                    "adapter_role": "legacy_executor_bridge",
                    "canonical_contract_owner": "WorkerExecutionPlan",
                },
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
            created_by="runtime.inspect.test",
        )
    )
    event_service = MemoryChangeEventService(session=retrieval_session)
    proposal = repository.create_proposal(
        input_model=ProposalSubmitInput(
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
                    "field_patch": {"title": "Inspection Chapter"},
                }
            ],
            base_refs=[
                ObjectRef(
                    object_id="chapter.current",
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=Domain.CHAPTER,
                    domain_path="chapter.current",
                    scope="story",
                    revision=1,
                )
            ],
            reason="runtime inspect proposal",
        ),
        status="applied",
        policy_decision="silent",
        submit_source="test.runtime.inspect",
        core_mutation_envelope=CoreMutationEnvelope(
            identity=identity,
            origin_kind=CORE_MUTATION_ORIGIN_USER_DIRECT_EDIT,
            actor="user.editor",
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
                    "field_patch": {"title": "Inspection Chapter"},
                }
            ],
            base_refs=[
                ObjectRef(
                    object_id="chapter.current",
                    layer=Layer.CORE_STATE_AUTHORITATIVE,
                    domain=Domain.CHAPTER,
                    domain_path="chapter.current",
                    scope="story",
                    revision=1,
                )
            ],
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
            trace_refs=["trace:runtime-inspect"],
            reason="runtime inspect proposal",
        ),
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
    )
    apply_receipt = repository.create_apply_receipt(
        proposal_id=proposal.proposal_id,
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        target_refs=[
            ObjectRef(
                object_id="chapter.current",
                layer=Layer.CORE_STATE_AUTHORITATIVE,
                domain=Domain.CHAPTER,
                domain_path="chapter.current",
                scope="story",
                revision=1,
            )
        ],
        revision_after={"chapter.current": 2},
        before_snapshot={"chapter_digest": {"title": "Before"}},
        after_snapshot={"chapter_digest": {"title": "Inspection Chapter"}},
        warnings=[],
        apply_backend="runtime_inspect_test",
    )
    event_service.record_event(
        MemoryChangeEvent(
            event_id="runtime-inspect-event",
            identity=identity,
            actor="runtime.inspect.test",
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
                )
            ],
            dirty_targets=[
                MemoryDirtyTarget(
                    target_kind="projection_refresh_pending",
                    target_id="chapter.current",
                    layer=Layer.CORE_STATE_PROJECTION.value,
                    domain=Domain.CHAPTER.value,
                    block_id="projection:chapter.current",
                    reason="authoritative_core_changed",
                )
            ],
            visibility_effect="current_truth_updated",
            metadata={
                "proposal_id": proposal.proposal_id,
                "apply_id": apply_receipt.apply_id,
            },
        )
    )
    job_service = RuntimeWorkflowJobService(retrieval_session)
    job_service.ensure_creation_time_obligations(
        identity=identity,
        source_ref_ids=[packet_ref.material.material_id],
        trace_refs=["worker_plan:worker-plan-inspect"],
        metadata={"worker_plan_id": "worker-plan-inspect"},
    )
    identity_service.update_turn_status(
        turn_id=identity.turn_id,
        status=StoryTurnStatus.SETTLED,
        visible_output_ref="artifact:inspect",
        selected_output_ref="artifact:inspect",
        settlement_reason="runtime_inspect_seeded",
    )
    branch_receipt = identity_service.rollback_to_turn(
        session_id=session.session_id,
        target_turn_id=identity.turn_id,
        actor="runtime.inspect.test",
    )
    retrieval_session.commit()

    payload = controller.read_runtime_inspection(
        session_id=session.session_id,
        turn_id=identity.turn_id,
    )

    assert payload["read_only"] is True
    assert payload["selection"]["selected_turn_id"] == identity.turn_id
    assert payload["selection"]["selected_branch_head_id"] == identity.branch_head_id
    assert payload["runtime_profile_snapshot"]["runtime_profile_snapshot_id"] == (
        identity.runtime_profile_snapshot_id
    )
    assert payload["branch_read_scope"]["active_branch_head_id"] == identity.branch_head_id
    assert payload["writer_packet"]["runtime_read_manifest_ids"]
    assert {
        item["material_kind"] for item in payload["runtime_workspace"]["materials"]
    } >= {
        RuntimeWorkspaceMaterialKind.RETRIEVAL_CARD.value,
        RuntimeWorkspaceMaterialKind.RETRIEVAL_USAGE_RECORD.value,
        RuntimeWorkspaceMaterialKind.PACKET_REF.value,
    }
    assert payload["retrieval"]["usage_refs"][0]["material_id"] == (
        usage_receipt.material.material_id
    )
    assert payload["worker_execution"]["prewrite_worker_results"][0]["material_id"] == (
        worker_evidence.material.material_id
    )
    assert payload["proposal_governance"]["proposal_receipts"][0]["proposal"]["proposal_id"] == (
        proposal.proposal_id
    )
    assert any(
        item["event_id"] == "runtime-inspect-event"
        for item in payload["memory_events"]["events"]
    )
    assert payload["job_ledger"]["items"]
    assert any(
        item["control_kind"] == branch_receipt.control_kind.value
        for item in payload["branch_control_receipts"]
    )
    assert "read_only_debug_surface" in payload["boundaries"]


def test_story_runtime_controller_reads_runtime_migration_summary(
    retrieval_session,
):
    session, _, story_session_service = _seed_story_runtime(retrieval_session)
    repository = ProposalRepository(retrieval_session)
    controller = _build_controller(retrieval_session, story_session_service, repository)
    snapshot_service = RuntimeProfileSnapshotService(retrieval_session)
    snapshot = snapshot_service.ensure_active_snapshot(
        session_id=session.session_id,
        created_from="test.runtime.migration",
    )
    identity_service = StoryRuntimeIdentityService(
        retrieval_session,
        runtime_profile_snapshot_service=snapshot_service,
    )
    identity = identity_service.resolve_runtime_entry_identity(
        session_id=session.session_id,
        command_kind=LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value,
        actor="runtime.migration.test",
        requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
    )
    material_service = RuntimeWorkspaceMaterialService(session=retrieval_session)
    material_service.record_material(
        RuntimeWorkspaceMaterial(
            material_id="migration-worker-evidence",
            material_kind=RuntimeWorkspaceMaterialKind.WORKER_EVIDENCE_BUNDLE,
            identity=identity,
            domain=Domain.CHAPTER.value,
            domain_path="chapter.runtime.worker.LongformMemoryWorker.evidence",
            payload={
                "worker_id": "LongformMemoryWorker",
                "trace_summary": {
                    "adapter_role": "legacy_executor_bridge",
                    "canonical_contract_owner": "WorkerExecutionPlan",
                },
            },
            visibility=RuntimeWorkspaceMaterialVisibility.WORKER_VISIBLE.value,
            created_by="runtime.migration.test",
        )
    )
    RuntimeWorkflowJobService(retrieval_session).ensure_creation_time_obligations(
        identity=identity,
        trace_refs=["worker_plan:worker-plan-migration"],
        metadata={"worker_plan_id": "worker-plan-migration"},
    )
    retrieval_session.commit()

    payload = controller.read_runtime_migration_summary(
        session_id=session.session_id,
        turn_id=identity.turn_id,
    )

    assert payload["read_only"] is True
    assert payload["migration_flags"]["session_branch_anchor_pinned"] is True
    assert payload["migration_flags"]["session_snapshot_anchor_pinned"] is True
    assert payload["migration_flags"]["turn_trace_available"] is True
    assert payload["migration_flags"]["worker_result_visible"] is True
    assert payload["migration_flags"]["worker_plan_refs_visible"] is True
    assert payload["migration_flags"]["legacy_fixed_chain_backslide_detected"] is False
    assert payload["legacy_fixed_chain_backslide"] == {
        "detected": False,
        "reason_codes": [],
    }
    assert payload["compatibility_surfaces"]
    assert any(
        item["marker_id"] == "legacy_command_surface"
        and item["value"] == LongformTurnCommandKind.WRITE_NEXT_SEGMENT.value
        for item in payload["observed_adapter_markers"]
    )
    assert any(
        item["marker_id"] == "worker_result_adapter_role"
        and item["value"] == "legacy_executor_bridge"
        for item in payload["observed_adapter_markers"]
    )
    assert "migration_surface_is_read_only" in payload["boundaries"]


def test_story_runtime_migration_summary_detects_fixed_chain_backslide():
    detection = StoryRuntimeMigrationService._detect_legacy_fixed_chain_backslide(
        inspection={
            "worker_execution": {
                "prewrite_worker_results": [
                    {
                        "material_id": "worker-evidence-without-plan",
                        "payload": {
                            "worker_id": "LongformMemoryWorker",
                            "trace_summary": {
                                "adapter_role": "legacy_executor_bridge",
                                "canonical_contract_owner": "OrchestratorPlan",
                            },
                        },
                    }
                ],
                "worker_plan_refs": [],
            }
        },
        observed_markers=[],
    )

    assert detection == {
        "detected": True,
        "reason_codes": [
            "legacy_adapter_without_worker_execution_plan_owner",
            "worker_result_without_worker_plan_ref",
        ],
    }
