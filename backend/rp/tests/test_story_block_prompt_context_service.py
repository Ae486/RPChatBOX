"""Tests for active-story internal Block prompt context compile."""

from __future__ import annotations

from rp.models.dsl import Domain, Layer
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
from rp.services.projection_state_service import ProjectionStateService
from rp.services.proposal_repository import ProposalRepository
from rp.services.rp_block_read_service import RpBlockReadService
from rp.services.story_block_consumer_state_service import (
    StoryBlockConsumerStateService,
)
from rp.services.story_block_prompt_context_service import (
    StoryBlockPromptContextService,
)
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService


def _seed_story_runtime(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-block-context",
        source_workspace_id="workspace-block-context",
        mode="longform",
        runtime_story_config={},
        writer_contract={},
        current_state_json={
            "chapter_digest": {"current_chapter": 1, "title": "Legacy Chapter"},
        },
        initial_phase=LongformChapterPhase.OUTLINE_DRAFTING,
    )
    chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=1,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "current_outline_digest": ["Legacy Outline"],
        },
    )
    story_session_service.commit()
    return session, chapter, story_session_service


def _build_prompt_context_service(retrieval_session, story_session_service):
    proposal_repository = ProposalRepository(retrieval_session)
    core_state_store_repository = CoreStateStoreRepository(retrieval_session)
    projection_state_service = ProjectionStateService(
        story_session_service=story_session_service,
        adapter=ChapterWorkspaceProjectionAdapter(story_session_service),
        core_state_store_repository=core_state_store_repository,
        store_read_enabled=True,
    )
    builder_projection_context_service = BuilderProjectionContextService(
        projection_state_service=projection_state_service,
    )
    version_history_read_service = VersionHistoryReadService(
        adapter=StorySessionCoreStateAdapter(story_session_service),
        proposal_repository=proposal_repository,
        core_state_store_repository=core_state_store_repository,
        store_read_enabled=True,
    )
    memory_inspection_read_service = MemoryInspectionReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        proposal_repository=proposal_repository,
        version_history_read_service=version_history_read_service,
        core_state_store_repository=core_state_store_repository,
        store_read_enabled=True,
    )
    rp_block_read_service = RpBlockReadService(
        story_session_service=story_session_service,
        builder_projection_context_service=builder_projection_context_service,
        core_state_store_repository=core_state_store_repository,
        memory_inspection_read_service=memory_inspection_read_service,
        store_read_enabled=True,
    )
    consumer_state_service = StoryBlockConsumerStateService(
        session=retrieval_session,
        story_session_service=story_session_service,
        rp_block_read_service=rp_block_read_service,
    )
    return (
        StoryBlockPromptContextService(
            rp_block_read_service=rp_block_read_service,
            story_block_consumer_state_service=consumer_state_service,
        ),
        core_state_store_repository,
    )


def test_story_block_prompt_context_service_builds_legacy_compatible_maps(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    prompt_context_service, core_repo = _build_prompt_context_service(
        retrieval_session,
        story_session_service,
    )
    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter"},
        metadata_json={"test_marker": "prompt_context_authoritative"},
    )
    projection_row = core_repo.upsert_projection_slot(
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        current_revision=4,
        items_json=["Formal Outline"],
        metadata_json={"test_marker": "prompt_context_projection"},
        last_refresh_kind="test_refresh",
    )

    context = prompt_context_service.build_consumer_context(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert context is not None
    assert context.dirty is True
    assert context.dirty_reasons == ["never_synced"]
    assert context.authoritative_state["chapter_digest"]["title"] == "Formal Chapter"
    assert context.projection_state["current_outline_digest"] == ["Formal Outline"]
    assert context.projection_state["foundation_digest"] == []
    assert [block.label for block in context.attached_blocks] == [
        "chapter.current",
        "projection.current_outline_digest",
    ]
    assert context.attached_blocks[1].block_id == projection_row.projection_slot_id
    assert context.metadata["missing_block_ids"] == []


def test_story_block_prompt_context_service_respects_writer_packet_attachment_scope(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    prompt_context_service, core_repo = _build_prompt_context_service(
        retrieval_session,
        story_session_service,
    )
    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter"},
        metadata_json={"test_marker": "prompt_context_authoritative"},
    )
    core_repo.upsert_projection_slot(
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        current_revision=4,
        items_json=["Formal Outline"],
        metadata_json={"test_marker": "prompt_context_projection"},
        last_refresh_kind="test_refresh",
    )

    context = prompt_context_service.build_consumer_context(
        session_id=session.session_id,
        consumer_key="story.writer_packet",
    )

    assert context is not None
    assert context.authoritative_state == {}
    assert [block.label for block in context.attached_blocks] == [
        "projection.current_outline_digest"
    ]


def test_story_block_prompt_context_service_excludes_runtime_workspace_blocks(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    prompt_context_service, core_repo = _build_prompt_context_service(
        retrieval_session,
        story_session_service,
    )
    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter"},
        metadata_json={"test_marker": "prompt_context_authoritative"},
    )
    core_repo.upsert_projection_slot(
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        current_revision=4,
        items_json=["Formal Outline"],
        metadata_json={"test_marker": "prompt_context_projection"},
        last_refresh_kind="test_refresh",
    )
    story_session_service.create_artifact(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        artifact_kind=StoryArtifactKind.STORY_SEGMENT,
        status=StoryArtifactStatus.DRAFT,
        content_text="Runtime draft segment",
        metadata={"command_kind": "write_next_segment"},
        revision=2,
    )
    story_session_service.create_discussion_entry(
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        role="assistant",
        content_text="Runtime discussion entry",
    )

    context = prompt_context_service.build_consumer_context(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert context is not None
    assert [block.label for block in context.attached_blocks] == [
        "chapter.current",
        "projection.current_outline_digest",
    ]
    assert all(
        block.layer != Layer.RUNTIME_WORKSPACE for block in context.attached_blocks
    )
    assert context.authoritative_state["chapter_digest"]["title"] == "Formal Chapter"
    assert context.projection_state["current_outline_digest"] == ["Formal Outline"]
