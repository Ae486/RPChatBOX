"""Tests for cached active-story Block prompt compile and lazy rebuild."""

from __future__ import annotations

from datetime import datetime

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
from rp.services.story_block_prompt_compile_service import (
    StoryBlockPromptCompileService,
)
from rp.services.story_block_prompt_context_service import (
    StoryBlockPromptContextService,
)
from rp.services.story_block_prompt_render_service import (
    StoryBlockPromptRenderService,
)
from rp.services.story_session_core_state_adapter import StorySessionCoreStateAdapter
from rp.services.story_session_service import StorySessionService
from rp.services.version_history_read_service import VersionHistoryReadService


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None)


def _seed_story_runtime(retrieval_session):
    story_session_service = StorySessionService(retrieval_session)
    session = story_session_service.create_session(
        story_id="story-block-compile",
        source_workspace_id="workspace-block-compile",
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


def _build_prompt_compile_service(retrieval_session, story_session_service):
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
    prompt_context_service = StoryBlockPromptContextService(
        rp_block_read_service=rp_block_read_service,
        story_block_consumer_state_service=consumer_state_service,
    )
    prompt_render_service = StoryBlockPromptRenderService()
    return (
        StoryBlockPromptCompileService(
            story_block_prompt_context_service=prompt_context_service,
            story_block_prompt_render_service=prompt_render_service,
            story_block_consumer_state_service=consumer_state_service,
        ),
        consumer_state_service,
        core_state_store_repository,
    )


def _seed_formal_blocks(session, chapter, core_repo):
    authoritative_row = core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=3,
        data_json={"current_chapter": 1, "title": "Formal Chapter"},
        metadata_json={"test_marker": "compile_authoritative"},
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
        data_json={"current_chapter": 1, "title": "Formal Chapter"},
        revision_source_kind="test",
        metadata_json={"test_marker": "compile_authoritative_revision"},
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
        metadata_json={"test_marker": "compile_projection"},
        last_refresh_kind="test_refresh",
    )
    core_repo.upsert_projection_slot_revision(
        projection_slot_id=projection_row.projection_slot_id,
        story_id=session.story_id,
        session_id=session.session_id,
        chapter_workspace_id=chapter.chapter_workspace_id,
        layer=Layer.CORE_STATE_PROJECTION.value,
        domain=Domain.CHAPTER.value,
        domain_path="projection.current_outline_digest",
        summary_id="projection.current_outline_digest",
        slot_name="current_outline_digest",
        scope="chapter",
        revision=4,
        items_json=["Formal Outline"],
        refresh_source_kind="test_refresh",
        metadata_json={"test_marker": "compile_projection_revision"},
    )
    return authoritative_row, projection_row


def test_story_block_prompt_compile_service_reuses_cached_overlay_when_unchanged(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    compile_service, consumer_state_service, core_repo = _build_prompt_compile_service(
        retrieval_session,
        story_session_service,
    )
    _seed_formal_blocks(session, chapter, core_repo)

    compiled = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    reused = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert compiled is not None
    assert compiled.compile_mode == "rebuilt"
    assert compiled.compile_reasons == ["never_compiled"]
    assert compiled.context.dirty is True
    assert "[BLOCK_PROMPT_CONTEXT]" in compiled.prompt_overlay
    assert reused is not None
    assert reused.compile_mode == "reused"
    assert reused.prompt_overlay == compiled.prompt_overlay
    assert _normalize_datetime(reused.compiled_at) == _normalize_datetime(
        compiled.compiled_at
    )
    record = consumer_state_service.get_consumer_record(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    assert record is not None
    assert record.last_compiled_prompt_overlay == compiled.prompt_overlay


def test_story_block_prompt_compile_service_rebuilds_after_consumer_sync_change(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    compile_service, consumer_state_service, core_repo = _build_prompt_compile_service(
        retrieval_session,
        story_session_service,
    )
    _seed_formal_blocks(session, chapter, core_repo)

    initial = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    rebuilt = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    reused = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert initial is not None
    assert rebuilt is not None
    assert rebuilt.compile_mode == "rebuilt"
    assert "consumer_sync_state_changed" in rebuilt.compile_reasons
    assert rebuilt.context.dirty is False
    assert "dirty=false" in rebuilt.prompt_overlay
    assert reused is not None
    assert reused.compile_mode == "reused"
    assert reused.prompt_overlay == rebuilt.prompt_overlay


def test_story_block_prompt_compile_service_rebuilds_after_authoritative_revision_change(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    compile_service, consumer_state_service, core_repo = _build_prompt_compile_service(
        retrieval_session,
        story_session_service,
    )
    authoritative_row, _ = _seed_formal_blocks(session, chapter, core_repo)

    _ = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    _ = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    core_repo.upsert_authoritative_object(
        story_id=session.story_id,
        session_id=session.session_id,
        layer=Layer.CORE_STATE_AUTHORITATIVE.value,
        domain=Domain.CHAPTER.value,
        domain_path="chapter.current",
        object_id="chapter.current",
        scope="story",
        current_revision=5,
        data_json={"current_chapter": 1, "title": "Formal Chapter Two"},
        metadata_json={"test_marker": "compile_authoritative"},
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
        revision=5,
        data_json={"current_chapter": 1, "title": "Formal Chapter Two"},
        revision_source_kind="test",
        metadata_json={"test_marker": "compile_authoritative_revision_2"},
    )

    rebuilt = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert rebuilt is not None
    assert rebuilt.compile_mode == "rebuilt"
    assert "compiled_block_revision_changed" in rebuilt.compile_reasons
    assert rebuilt.context.authoritative_state["chapter_digest"]["title"] == (
        "Formal Chapter Two"
    )


def test_story_block_prompt_compile_service_rebuilds_after_chapter_workspace_change(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    compile_service, consumer_state_service, core_repo = _build_prompt_compile_service(
        retrieval_session,
        story_session_service,
    )
    _seed_formal_blocks(session, chapter, core_repo)

    _ = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    _ = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    next_chapter = story_session_service.create_chapter_workspace(
        session_id=session.session_id,
        chapter_index=2,
        phase=LongformChapterPhase.OUTLINE_DRAFTING,
        builder_snapshot_json={
            "current_outline_digest": ["Next Chapter Outline"],
        },
    )
    story_session_service.update_session(
        session_id=session.session_id,
        current_chapter_index=next_chapter.chapter_index,
    )
    story_session_service.commit()

    rebuilt = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert rebuilt is not None
    assert rebuilt.compile_mode == "rebuilt"
    assert "compiled_chapter_workspace_changed" in rebuilt.compile_reasons
    assert rebuilt.context.chapter_workspace_id == next_chapter.chapter_workspace_id


def test_story_block_prompt_compile_service_reuses_overlay_after_runtime_workspace_changes(
    retrieval_session,
):
    session, chapter, story_session_service = _seed_story_runtime(retrieval_session)
    compile_service, consumer_state_service, core_repo = _build_prompt_compile_service(
        retrieval_session,
        story_session_service,
    )
    _seed_formal_blocks(session, chapter, core_repo)

    initial = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    consumer_state_service.mark_consumer_synced(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )
    rebuilt_after_sync = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
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

    reused = compile_service.compile_consumer_prompt(
        session_id=session.session_id,
        consumer_key="story.orchestrator",
    )

    assert initial is not None
    assert rebuilt_after_sync is not None
    assert rebuilt_after_sync.compile_mode == "rebuilt"
    assert "consumer_sync_state_changed" in rebuilt_after_sync.compile_reasons
    assert reused is not None
    assert reused.compile_mode == "reused"
    assert reused.prompt_overlay == rebuilt_after_sync.prompt_overlay
    assert all(
        block.layer != Layer.RUNTIME_WORKSPACE
        for block in reused.context.attached_blocks
    )
