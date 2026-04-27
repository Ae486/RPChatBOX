"""Controller-level tests for story runtime memory read side."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rp.models.dsl import Domain, Layer
from rp.models.memory_crud import (
    MemoryBlockProposalSubmitRequest,
    ProposalSubmitInput,
)
from rp.models.post_write_policy import PolicyDecision, PostWriteMaintenancePolicy
from rp.models.story_runtime import (
    LongformChapterPhase,
    StoryArtifactKind,
    StoryArtifactStatus,
)
from rp.services.builder_projection_context_service import (
    BuilderProjectionContextService,
)
from rp.services.chapter_workspace_projection_adapter import (
    ChapterWorkspaceProjectionAdapter,
)
from rp.services.core_state_store_repository import CoreStateStoreRepository
from rp.services.memory_inspection_read_service import MemoryInspectionReadService
from rp.services.post_write_apply_handler import PostWriteApplyHandler
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_apply_service import ProposalApplyService
from rp.services.proposal_repository import ProposalRepository
from rp.services.proposal_workflow_service import ProposalWorkflowService
from rp.services.projection_read_service import ProjectionReadService
from rp.services.provenance_read_service import ProvenanceReadService
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_block_mutation_service import (
    MemoryBlockMutationUnsupportedError,
    StoryBlockMutationService,
)
from rp.services.story_runtime_controller import (
    MemoryBlockHistoryUnsupportedError,
    StoryRuntimeController,
)
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.story_state_apply_service import StoryStateApplyService
from rp.services.version_history_read_service import VersionHistoryReadService


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
    return StoryRuntimeController(
        story_session_service=story_session_service,
        story_activation_service=SimpleNamespace(),
        version_history_read_service=version_history_read_service,
        provenance_read_service=provenance_read_service,
        projection_read_service=projection_read_service,
        memory_inspection_read_service=memory_inspection_read_service,
        rp_block_read_service=rp_block_read_service,
        story_block_mutation_service=block_mutation_service,
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
        metadata_json={"test_marker": "controller_block"},
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
        metadata_json={"test_marker": "controller_block_projection"},
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
    assert runtime_artifact_block["metadata"]["route"] == (
        "story_session_runtime.artifacts"
    )
    assert runtime_discussion_block["data_json"]["role"] == "user"
    assert runtime_discussion_block["data_json"]["linked_artifact_id"] == (
        draft_artifact.artifact_id
    )
    assert runtime_discussion_block["metadata"]["route"] == (
        "story_session_runtime.discussion_entries"
    )
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
                    "revision": 3,
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
